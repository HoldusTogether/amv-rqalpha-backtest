from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# AKShare 东方财富概念/行业板块历史行情的最早可用数据通常为 2019 年左右
# 部分热门概念可追溯至 2015 年
FETCH_START = "20050101"
FETCH_END = "20260601"


def _import_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise SystemExit("akshare is not installed. Run: pip install akshare") from exc
    return ak


def _call_with_retry(label, func, retries=2, delay=3):
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            print(f"  {label} failed attempt {attempt}: {exc}", file=sys.stderr)
            if attempt <= retries:
                time.sleep(delay)
    raise RuntimeError(f"{label} failed after {retries + 1} attempts") from last_error


def fetch_concept_names() -> pd.DataFrame:
    ak = _import_akshare()
    return _call_with_retry("stock_board_concept_name_em", lambda: ak.stock_board_concept_name_em())


def fetch_concept_hist(symbol: str) -> pd.DataFrame | None:
    ak = _import_akshare()
    try:
        df = _call_with_retry(
            f"stock_board_concept_hist_em({symbol})",
            lambda: ak.stock_board_concept_hist_em(
                symbol=symbol, start_date=FETCH_START, end_date=FETCH_END,
                period="日k", adjust="",
            ),
            retries=1,
        )
        return df
    except Exception as e:
        print(f"  WARN: {symbol} hist failed: {e}", file=sys.stderr)
        return None


def build_concept_returns(concept_names: pd.DataFrame) -> pd.DataFrame:
    """Fetch historical daily data for all concepts and build unified DataFrame."""
    all_rows: list[dict] = []
    total = len(concept_names)

    for i, (_, row) in enumerate(concept_names.iterrows()):
        name = str(row.get("板块名称", "")).strip()
        if not name:
            continue

        hist = fetch_concept_hist(name)
        if hist is None or hist.empty:
            continue

        for _, r in hist.iterrows():
            date_val = r.get("日期")
            close_val = r.get("收盘")
            pct_val = r.get("涨跌幅")
            if pd.isna(date_val) or pd.isna(close_val):
                continue
            ret = (pct_val / 100.0) if pd.notna(pct_val) else 0.0
            all_rows.append({
                "date": str(date_val)[:10],
                "concept": name,
                "close": float(close_val),
                "return": float(ret),
            })

        if (i + 1) % 30 == 0 or (i + 1) == total:
            print(f"  [{i+1}/{total}] {name}: {len(hist)} rows")

        time.sleep(0.3)

    if not all_rows:
        print("  No concept data fetched from AKShare!")
        return pd.DataFrame()

    result = pd.DataFrame(all_rows)
    result = result.sort_values(["date", "concept"]).reset_index(drop=True)
    return result


def build_etf_mapping(concept_names: pd.DataFrame) -> pd.DataFrame:
    """Merge existing concept→ETF mapping with new AKShare concepts (default ETF)."""
    existing_path = ROOT / "data" / "concept_etf_map.csv"

    existing_concepts = set()
    mappings = []

    if existing_path.exists():
        old = pd.read_csv(existing_path)
        mappings.append(old)
        for _, r in old.iterrows():
            existing_concepts.add(str(r.get("concept", "")).strip())

    total = len(concept_names)
    new_rows: list[dict] = []

    for i, (_, row) in enumerate(concept_names.iterrows()):
        name = str(row.get("板块名称", "")).strip()
        if not name or name in existing_concepts:
            continue
        existing_concepts.add(name)
        new_rows.append({
            "concept": name,
            "order_book_id": "510050.XSHG",
            "etf_name": "上证50ETF",
            "priority": 2,
        })

    if new_rows:
        mappings.append(pd.DataFrame(new_rows))
        print(f"  Added {len(new_rows)} new concepts (default ETF 510050.XSHG)")

    if not mappings:
        return pd.DataFrame(columns=["concept", "order_book_id", "etf_name", "priority"])

    result = pd.concat(mappings, ignore_index=True)
    result = result.drop_duplicates(subset=["concept"], keep="first")
    result["priority"] = pd.to_numeric(result["priority"], errors="coerce").fillna(999).astype(int)
    result = result.sort_values(["concept", "priority"])
    return result


def main():
    print("=== Step 1: Fetch concept board names from AKShare ===")
    concepts = fetch_concept_names()
    print(f"  Total concepts: {len(concepts)}")

    print("\n=== Step 2: Fetch concept historical OHLC ===")
    returns = build_concept_returns(concepts)
    if not returns.empty:
        out_path = ROOT / "data" / "concept_daily_returns.csv"
        returns.to_csv(out_path, index=False, encoding="utf-8")
        print(f"\n  Saved {len(returns)} rows: {out_path}")
        print(f"  Concepts: {returns['concept'].nunique()}")
        print(f"  Date range: {returns['date'].min()} ~ {returns['date'].max()}")
    else:
        print("  No data saved!")

    print("\n=== Step 3: Build concept→ETF mapping ===")
    mapping = build_etf_mapping(concepts)
    if not mapping.empty:
        out_path = ROOT / "data" / "concept_etf_map.csv"
        mapping.to_csv(out_path, index=False, encoding="utf-8")
        print(f"\n  Saved {len(mapping)} mappings: {out_path}")
        print(f"  Unique ETFs: {mapping['order_book_id'].nunique()}")
    else:
        print("  No mapping saved!")

    print("\nDone!")


if __name__ == "__main__":
    main()
