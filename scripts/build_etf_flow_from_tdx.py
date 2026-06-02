"""
从通达信 TDX .day 文件提取 ETF 行情数据，计算资金流向代理指标。
替代被东方财富 API 限流的 fetch_etf_flow.py（AKShare 方式）。

数据链路：
  通达信 .day 文件 (D:\new_tdx\vipdoc\sh|sz\lday\*.day)
    → OHLC + 成交额 + 成交量 (32字节/条)
    → 资金流向公式: flow_mult = (2*close - high - low) / (high - low)
    → net_flow = total_turnover * flow_mult
    → etf_flow.csv

TDX .day 文件格式 (32 bytes/record, little-endian):
  offset   type     field
  0        uint32   date (YYYYMMDD)
  4        int32    open (分, /100 → 元)
  8        int32    high (分)
  12       int32    low (分)
  16       int32    close (分)
  20       float32  amount (元)
  24       int32    volume
  28       int32    reserved
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TDX_SH_DIR = Path(r"D:\new_tdx\vipdoc\sh\lday")
TDX_SZ_DIR = Path(r"D:\new_tdx\vipdoc\sz\lday")

TDX_RECORD_FMT = "<IiiiiiIf"
TDX_RECORD_SIZE = struct.calcsize(TDX_RECORD_FMT)


def read_tdx_day(filepath: Path) -> pd.DataFrame | None:
    """读取单只ETF的通达信 .day 文件，返回 OHLCV DataFrame。"""
    if not filepath.exists():
        return None
    raw = filepath.read_bytes()
    n = len(raw) // TDX_RECORD_SIZE
    records: list[dict] = []
    for i in range(n):
        chunk = raw[i * TDX_RECORD_SIZE : (i + 1) * TDX_RECORD_SIZE]
        if len(chunk) < TDX_RECORD_SIZE:
            break
        date_int, open_, high, low, close, amount, vol, _reserved = struct.unpack(
            TDX_RECORD_FMT, chunk
        )
        records.append(
            {
                "date": date_int,
                "open": open_ / 1000.0,
                "high": high / 1000.0,
                "low": low / 1000.0,
                "close": close / 1000.0,
                "volume": vol,
                "total_turnover": amount,
            }
        )
    if not records:
        return None
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    return df


def compute_flow_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """计算资金流向代理指标，与 fetch_etf_flow.py 的 compute_flow_proxy 一致。"""
    price_range = df["high"] - df["low"]
    price_range = price_range.replace(0, np.nan)

    flow_mult = (2 * df["close"] - df["high"] - df["low"]) / price_range
    net_flow = df["total_turnover"] * flow_mult

    df = df.copy()
    df["net_flow"] = net_flow
    df["flow_mult"] = flow_mult
    return df


def build_etf_list() -> pd.DataFrame:
    """从 concept_etf_map.csv + etf_candidates.csv 合并ETF列表，去重。"""
    result_dfs = []

    # 1. 策略所需ETF（concept_etf_map.csv）
    map_path = DATA_DIR / "concept_etf_map.csv"
    if map_path.exists():
        cmap = pd.read_csv(map_path)
        oids = set()
        for _, row in cmap.iterrows():
            oid = str(row.get("order_book_id", "")).strip()
            if oid:
                oids.add(oid)
        if oids:
            result_dfs.append(pd.DataFrame({"order_book_id": list(oids), "source": "concept_map"}))

    # 2. 候选ETF（按成交额排序）
    cand_path = DATA_DIR / "etf_candidates.csv"
    if cand_path.exists():
        cand = pd.read_csv(cand_path)
        if "order_book_id" in cand.columns:
            cand = cand.drop_duplicates(subset=["order_book_id"])
            cand["source"] = "candidates"
            # 按成交额降序排列
            if "turnover" in cand.columns:
                cand["turnover"] = pd.to_numeric(cand["turnover"], errors="coerce").fillna(0)
                cand = cand.sort_values("turnover", ascending=False)
            result_dfs.append(cand[["order_book_id", "source"]])

    if not result_dfs:
        raise SystemExit("ERROR: no ETF list found (need concept_etf_map.csv or etf_candidates.csv)")

    merged = pd.concat(result_dfs, ignore_index=True)
    merged = merged.drop_duplicates(subset=["order_book_id"], keep="first")
    return merged


def main():
    print("=== Build ETF Flow Data from TDX .day files ===")

    print("\nStep 1: Building ETF list...")
    etf_list = build_etf_list()
    print(f"  Total unique ETFs: {len(etf_list)}")

    print("\nStep 2: Reading TDX .day files...")
    all_rows: list[pd.DataFrame] = []
    missing = 0
    skipped_not_etf = 0

    for _, row in etf_list.iterrows():
        oid = str(row["order_book_id"])
        code = oid.split(".")[0]
        source = row.get("source", "unknown")

        # 定位 .day 文件
        if oid.endswith(".XSHG"):
            fpath = TDX_SH_DIR / f"sh{code}.day"
        elif oid.endswith(".XSHE"):
            fpath = TDX_SZ_DIR / f"sz{code}.day"
        else:
            skipped_not_etf += 1
            continue

        df = read_tdx_day(fpath)
        if df is None:
            missing += 1
            continue

        df["order_book_id"] = oid
        df = compute_flow_proxy(df)
        all_rows.append(df[["date", "order_book_id", "open", "high", "low", "close",
                           "volume", "total_turnover", "net_flow", "flow_mult"]])
        print(f"  [{len(all_rows)}] {oid} ({source}) — {len(df)} rows, {df['date'].min().date()} ~ {df['date'].max().date()}")

    print(f"\n  Read {len(all_rows)} ETFs successfully, {missing} missing, {skipped_not_etf} skipped (non-SH/SZ)")

    if not all_rows:
        print("  ERROR: no data fetched!")
        return

    print("\nStep 3: Concatenating and sorting...")
    result = pd.concat(all_rows, ignore_index=True)
    result = result.sort_values(["date", "order_book_id"]).reset_index(drop=True)
    result["date"] = result["date"].dt.date.astype(str)

    out_path = DATA_DIR / "etf_flow.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n  Saved {len(result)} rows: {out_path}")
    print(f"  Date range: {result['date'].min()} ~ {result['date'].max()}")
    print(f"  ETFs covered: {result['order_book_id'].nunique()}")

    top_by_avg_flow = (
        result.groupby("order_book_id")["net_flow"]
        .mean()
        .sort_values(ascending=False)
        .head(10)
    )
    print(f"\n  Top 10 ETFs by avg daily net flow:")
    for oid, flow in top_by_avg_flow.items():
        print(f"    {oid}: {flow:.0f}")


if __name__ == "__main__":
    main()
