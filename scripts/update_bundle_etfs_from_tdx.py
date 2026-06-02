"""
更新 RQAlpha bundle 中的 ETF (funds.h5) 数据，
利用通达信 .day 文件补充 2026-05-15 之后的行情。

操作方式：读取现有数据 → 从 TDX 追加新记录 → 删除重建 dataset。
"""
from __future__ import annotations

import struct
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "bundle" / "bundle"
TDX_SH_DIR = Path(r"D:\new_tdx\vipdoc\sh\lday")
TDX_SZ_DIR = Path(r"D:\new_tdx\vipdoc\sz\lday")

TDX_RECORD_FMT = "<IiiiiiIf"
TDX_RECORD_SIZE = struct.calcsize(TDX_RECORD_FMT)
CUTOFF_DATE = 20260515

BUNDLE_DTYPE = [
    ("datetime", "<i8"), ("open", "<f8"), ("close", "<f8"), ("high", "<f8"),
    ("low", "<f8"), ("prev_close", "<f8"), ("limit_up", "<f8"),
    ("limit_down", "<f8"), ("volume", "<f8"), ("total_turnover", "<f8"),
]


def read_tdx_day(filepath: Path) -> pd.DataFrame | None:
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
        records.append({
            "date": date_int,
            "open": open_ / 1000.0,
            "high": high / 1000.0,
            "low": low / 1000.0,
            "close": close / 1000.0,
            "volume": float(vol),
            "amount": amount,
        })
    if not records:
        return None
    df = pd.DataFrame(records)
    df = df.sort_values("date")
    return df


def _make_record(date_int: int, row: pd.Series, prev_close: float) -> np.void:
    dt = int(row["date"]) * 1000000
    return np.array([(dt, row["open"], row["close"], row["high"], row["low"],
                      prev_close, round(prev_close * 1.1, 2), round(prev_close * 0.9, 2),
                      row["volume"], row["amount"])], dtype=BUNDLE_DTYPE)[0]


def extend_existing_etf(tdx_df: pd.DataFrame, last_close: float) -> list[np.void]:
    """为已有 ETF 追加 CUTOFF_DATE 之后的新记录。"""
    new_df = tdx_df[tdx_df["date"] > CUTOFF_DATE].copy()
    if new_df.empty:
        return []
    records = []
    prev = last_close
    for _, row in new_df.iterrows():
        records.append(_make_record(0, row, prev))
        prev = row["close"]
    return records


def build_full_records(tdx_df: pd.DataFrame) -> list[np.void]:
    """为新 ETF 构建完整数据（从 TDX 全部记录）。"""
    records = []
    prev = None
    for _, row in tdx_df.iterrows():
        if prev is None:
            prev = row["close"]
        records.append(_make_record(0, row, prev))
        prev = row["close"]
    return records


def get_target_etfs() -> set[str]:
    oids: set[str] = set()
    for fname in ["concept_etf_map.csv", "etf_candidates.csv"]:
        path = ROOT / "data" / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if "turnover" in df.columns:
            df["turnover"] = pd.to_numeric(df["turnover"], errors="coerce").fillna(0)
            df = df.sort_values("turnover", ascending=False)
        limit = None if fname == "concept_etf_map.csv" else 50
        for oid in df.head(limit)["order_book_id"]:
            oids.add(str(oid).strip())
    return oids


def main():
    print("=== Update RQAlpha Bundle ETFs (funds.h5) from TDX ===")

    target_etfs = get_target_etfs()
    print(f"Target ETFs: {len(target_etfs)}")

    funds_path = BUNDLE_DIR / "funds.h5"
    if not funds_path.exists():
        print(f"ERROR: {funds_path} not found")
        return

    bak_path = funds_path.with_suffix(".h5.bak")
    if not bak_path.exists():
        funds_path.rename(bak_path)
        print(f"Backup saved: {bak_path}")

    src = h5py.File(str(bak_path), "r")
    dst = h5py.File(str(funds_path), "w")

    all_keys = set(src.keys())
    updated = 0
    created = 0
    skipped_no_tdx = 0
    skipped_current = 0

    for oid in all_keys:
        ds = src[oid]
        data = ds[:]
        dst.create_dataset(oid, data=data, maxshape=(None,), chunks=True,
                          compression="gzip", compression_opts=9)

    for oid in sorted(target_etfs):
        code = oid.split(".")[0]
        if oid.endswith(".XSHG"):
            tdx_path = TDX_SH_DIR / f"sh{code}.day"
        elif oid.endswith(".XSHE"):
            tdx_path = TDX_SZ_DIR / f"sz{code}.day"
        else:
            continue

        tdx_df = read_tdx_day(tdx_path)
        if tdx_df is None:
            skipped_no_tdx += 1
            continue

        if oid in all_keys:
            ds = dst[oid]
            existing = ds[:]
            last_bundle_date = int(existing["datetime"][-1]) // 1000000
            last_tdx_date = int(tdx_df["date"].max())
            if last_bundle_date >= last_tdx_date:
                skipped_current += 1
                continue

            new_records = extend_existing_etf(tdx_df, float(existing["close"][-1]))
            if not new_records:
                skipped_current += 1
                continue

            combined = np.append(existing, np.array(new_records, dtype=BUNDLE_DTYPE))
            del dst[oid]
            dst.create_dataset(oid, data=combined, maxshape=(None,), chunks=True,
                              compression="gzip", compression_opts=9)
            print(f"  UPD {oid}: {len(existing)} → {len(combined)} rows (+{len(new_records)}, last={last_tdx_date})")
            updated += 1
        else:
            # 新增 ETF（取 TDX 中 > CUTOFF_DATE 的记录）
            new_df = tdx_df[tdx_df["date"] > CUTOFF_DATE].copy()
            if new_df.empty:
                continue
            new_records = build_full_records(new_df)
            if not new_records:
                continue
            data = np.array(new_records, dtype=BUNDLE_DTYPE)
            dst.create_dataset(oid, data=data, maxshape=(None,), chunks=True,
                              compression="gzip", compression_opts=9)
            print(f"  ADD {oid}: {len(data)} rows (last={new_df['date'].max()})")
            created += 1

    src.close()
    dst.close()

    print(f"\nDone. Updated: {updated}, Created: {created}, "
          f"Skipped (no TDX): {skipped_no_tdx}, Already current: {skipped_current}")


if __name__ == "__main__":
    main()
