from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _import_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise SystemExit("akshare is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install akshare") from exc
    return ak


def _call_with_retry(label, func, retries=2, delay=2):
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            print(f"{label} failed attempt {attempt}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if attempt <= retries:
                time.sleep(delay)
    raise RuntimeError(f"{label} failed after {retries + 1} attempts") from last_error


def _date_range(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        frame = frame.loc[pd.to_datetime(frame["date"]) >= pd.to_datetime(start)]
    if end:
        frame = frame.loc[pd.to_datetime(frame["date"]) <= pd.to_datetime(end)]
    return frame


def _tdx_sma(series: pd.Series, n: int = 10, m: int = 1) -> pd.Series:
    return series.ewm(alpha=m / n, adjust=False).mean()


def _normalize_index_frame(frame: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, str]:
    cols = {str(col).strip(): col for col in frame.columns}
    if "日期" in cols:
        result = pd.DataFrame(
            {
                "date": pd.to_datetime(frame[cols["日期"]]),
                "open": pd.to_numeric(frame[cols.get("开盘")], errors="coerce"),
                "high": pd.to_numeric(frame[cols.get("最高")], errors="coerce"),
                "low": pd.to_numeric(frame[cols.get("最低")], errors="coerce"),
                "close": pd.to_numeric(frame[cols.get("收盘")], errors="coerce"),
                "amount": pd.to_numeric(frame[cols.get("成交额")], errors="coerce") if "成交额" in cols else pd.NA,
                "volume": pd.to_numeric(frame[cols.get("成交量")], errors="coerce") if "成交量" in cols else pd.NA,
            }
        )
    else:
        result = frame.rename(columns={c: str(c).strip().lower() for c in frame.columns}).copy()
        result["date"] = pd.to_datetime(result["date"])
        for col in ["open", "high", "low", "close", "amount", "volume"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
            else:
                result[col] = pd.NA

    value_col = "amount" if result["amount"].notna().any() else "volume"
    if value_col == "volume":
        print(f"{symbol}: amount not available; falling back to volume proxy", file=sys.stderr)
    result = result[["date", "open", "high", "low", "close", value_col]].rename(columns={value_col: "source_value"})
    result["symbol"] = symbol
    return result.dropna(subset=["date", "source_value"]), value_col


def fetch_index_daily(symbol: str) -> tuple[pd.DataFrame, str]:
    ak = _import_akshare()
    try:
        frame = _call_with_retry(
            f"stock_zh_index_daily_em({symbol})",
            lambda: ak.stock_zh_index_daily_em(symbol=symbol),
            retries=1,
        )
        return _normalize_index_frame(frame, symbol)
    except Exception as exc:
        print(f"{symbol}: Eastmoney index daily unavailable; fallback to Sina. {exc}", file=sys.stderr)

    frame = _call_with_retry(
        f"stock_zh_index_daily({symbol})",
        lambda: ak.stock_zh_index_daily(symbol=symbol),
        retries=1,
    )
    return _normalize_index_frame(frame, symbol)


def build_amv_proxy(symbols: list[str], start: str | None, end: str | None) -> pd.DataFrame:
    frames = []
    value_cols = set()
    for symbol in symbols:
        frame, value_col = fetch_index_daily(symbol)
        frames.append(frame[["date", "source_value"]])
        value_cols.add(value_col)

    combined = pd.concat(frames, ignore_index=True).groupby("date", as_index=False)["source_value"].sum()
    combined = combined.sort_values("date")
    combined["amv_value"] = _tdx_sma(combined["source_value"], n=10, m=1)
    combined["open"] = combined["amv_value"].shift(1)
    combined["close"] = combined["amv_value"]
    combined["high"] = combined[["open", "close"]].max(axis=1)
    combined["low"] = combined[["open", "close"]].min(axis=1)
    combined["pct_change"] = combined["close"] / combined["open"] - 1
    result = combined.dropna(subset=["open", "close", "pct_change"]).copy()

    scale = 10_000_000 if value_cols == {"amount"} else 100_000_000
    for col in ["open", "high", "low", "close"]:
        result[col] = result[col] / scale
    result = _date_range(result, start, end)
    result["date"] = result["date"].dt.date.astype(str)
    return result[["date", "open", "high", "low", "close", "pct_change"]]


def fetch_concept_flow(concept_symbol: str) -> pd.DataFrame:
    ak = _import_akshare()
    frame = _call_with_retry(
        f"stock_fund_flow_concept({concept_symbol})",
        lambda: ak.stock_fund_flow_concept(symbol=concept_symbol),
        retries=2,
    )
    required = {"行业", "净额"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"concept flow missing columns: {sorted(missing)}")

    trade_date = pd.Timestamp.now(tz="Asia/Shanghai").date().isoformat()
    result = pd.DataFrame(
        {
            "date": trade_date,
            "concept": frame["行业"].astype(str).str.strip(),
            "net_inflow": pd.to_numeric(frame["净额"], errors="coerce") * 100_000_000,
        }
    )
    return result.dropna(subset=["concept", "net_inflow"])


def fetch_etf_spot() -> pd.DataFrame:
    ak = _import_akshare()
    frame = _call_with_retry("fund_etf_spot_em", lambda: ak.fund_etf_spot_em(), retries=2)
    required = {"代码", "名称"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"ETF spot missing columns: {sorted(missing)}")
    result = frame.copy()
    result["code"] = result["代码"].astype(str).str.zfill(6)
    result["order_book_id"] = result["code"].map(to_rqalpha_order_book_id)
    result["etf_name"] = result["名称"].astype(str).str.strip()
    return result.dropna(subset=["order_book_id", "etf_name"])


def to_rqalpha_order_book_id(code: str) -> str | None:
    code = str(code).strip().zfill(6)
    if code.startswith("5"):
        return f"{code}.XSHG"
    if code.startswith("1"):
        return f"{code}.XSHE"
    return None


def concept_keyword(concept: str) -> str:
    keyword = str(concept).strip()
    for token in ["概念", "板块", "指数", "产业", "行业", "主题", "基金"]:
        keyword = keyword.replace(token, "")
    return keyword.strip()


def build_etf_map(concept_flow: pd.DataFrame, etf_spot: pd.DataFrame, existing_path: Path) -> pd.DataFrame:
    existing = pd.DataFrame(columns=["concept", "order_book_id", "etf_name", "priority"])
    if existing_path.exists():
        existing = pd.read_csv(existing_path)

    rows = []
    existing_pairs = set(zip(existing.get("concept", []), existing.get("order_book_id", [])))
    existing_concepts = set(existing.get("concept", []))
    etfs = etf_spot[["order_book_id", "etf_name"]].drop_duplicates()

    for concept in concept_flow["concept"].dropna().unique():
        if concept in existing_concepts:
            continue
        keyword = concept_keyword(concept)
        if len(keyword) < 2:
            continue
        matched = etfs.loc[etfs["etf_name"].str.contains(keyword, case=False, regex=False, na=False)]
        if matched.empty:
            continue
        chosen = matched.iloc[0]
        pair = (concept, chosen["order_book_id"])
        if pair in existing_pairs:
            continue
        rows.append(
            {
                "concept": concept,
                "order_book_id": chosen["order_book_id"],
                "etf_name": chosen["etf_name"],
                "priority": 1,
            }
        )

    appended = pd.DataFrame(rows)
    result = pd.concat([existing, appended], ignore_index=True)
    if result.empty:
        return existing
    result["priority"] = pd.to_numeric(result["priority"], errors="coerce").fillna(999).astype(int)
    return result.drop_duplicates(subset=["concept", "order_book_id"]).sort_values(["concept", "priority"])


def write_csv(frame: pd.DataFrame, path: Path, append_by_date_concept: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if append_by_date_concept and path.exists():
        old = pd.read_csv(path)
        frame = pd.concat([old, frame], ignore_index=True)
        frame = frame.drop_duplicates(subset=["date", "concept"], keep="last")
        frame = frame.sort_values(["date", "net_inflow"], ascending=[True, False])
    frame.to_csv(path, index=False, encoding="utf-8")
    print(f"wrote {len(frame)} rows: {path}")


def command_amv_proxy(args) -> int:
    frame = build_amv_proxy(args.index_symbols, args.start, args.end)
    write_csv(frame, args.output_dir / "amv_daily.csv")
    return 0


def command_concept_flow(args) -> int:
    frame = fetch_concept_flow(args.concept_symbol)
    write_csv(frame, args.output_dir / "concept_flow.csv", append_by_date_concept=True)
    return 0


def command_etf_map(args) -> int:
    concept_path = args.output_dir / "concept_flow.csv"
    if not concept_path.exists():
        raise SystemExit(f"missing {concept_path}; run concept-flow first")
    concept_flow = pd.read_csv(concept_path)
    etf_spot = fetch_etf_spot()
    extra_cols = [col for col in ["最新价", "成交额", "数据日期"] if col in etf_spot.columns]
    write_csv(etf_spot[["order_book_id", "etf_name", *extra_cols]], args.output_dir / "etf_spot.csv")
    mapping = build_etf_map(concept_flow, etf_spot, args.output_dir / "concept_etf_map.csv")
    write_csv(mapping, args.output_dir / "concept_etf_map.csv")
    return 0


def command_all(args) -> int:
    command_amv_proxy(args)
    command_concept_flow(args)
    command_etf_map(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch free market data for the 0AMV RQAlpha project via AKShare.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--start", help="YYYY-MM-DD; only used by amv-proxy/all")
    parser.add_argument("--end", help="YYYY-MM-DD; only used by amv-proxy/all")
    parser.add_argument("--index-symbols", nargs="+", default=["sh000001", "sz399106"])
    parser.add_argument("--concept-symbol", default="即时", choices=["即时", "3日排行", "5日排行", "10日排行", "20日排行"])

    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, handler in {
        "amv-proxy": command_amv_proxy,
        "concept-flow": command_concept_flow,
        "etf-map": command_etf_map,
        "all": command_all,
    }.items():
        sub = subparsers.add_parser(command)
        sub.set_defaults(func=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

