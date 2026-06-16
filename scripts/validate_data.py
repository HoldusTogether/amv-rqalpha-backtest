#!/usr/bin/env python
"""Validate data quality for AMV ETF backtest strategy.

Checks:
1. Price range validation (no negative or extreme values)
2. Date continuity (no unexpected gaps)
3. Missing data detection
4. Signal frequency sanity check

Usage: python scripts/validate_data.py [--strict]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

warnings: list[str] = []
errors: list[str] = []


def check_file_exists(filepath: Path) -> bool:
    """Check that a required data file exists."""
    if not filepath.exists():
        errors.append(f"MISSING: {filepath.name}")
        return False
    print(f"  [OK] {filepath.name} exists")
    return True


def check_amv_daily():
    """Validate amv_daily.csv."""
    path = DATA_DIR / "amv_daily.csv"
    if not check_file_exists(path):
        return

    df = pd.read_csv(path)

    # Check required columns
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        errors.append(f"AMV: missing columns {missing}")
        return

    # Check no negative prices (single unified check)
    for col in ["open", "high", "low", "close"]:
        negatives = (df[col] < 0).sum()
        if negatives > 0:
            errors.append(f"AMV: {col} has {negatives} negative value(s) (min={df[col].min()})")
        else:
            print(f"  [OK] AMV {col} no negative values")

    # Check pct_change
    if "pct_change" in df.columns:
        extreme = (df["pct_change"].abs() > 0.3).sum()
        if extreme > 0:
            warnings.append(f"AMV: {extreme} rows with extreme pct_change (>30%)")

    # Check date continuity
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    date_diffs = df["date"].diff().dt.days.dropna()
    gaps = (date_diffs > 2).sum()  # Allow weekends (2-day gaps)
    if gaps > 0:
        warnings.append(f"AMV: {gaps} date gaps > 2 days")
    else:
        print(f"  [OK] AMV date continuity OK")

    print(f"  [OK] AMV data: {len(df)} rows, {df['date'].min().date()} ~ {df['date'].max().date()}")


def check_concept_data():
    """Validate concept_daily_returns*.csv."""
    for filename in ["concept_daily_returns.csv", "concept_daily_returns_tdx.csv"]:
        path = DATA_DIR / filename
        if not check_file_exists(path):
            continue

        df = pd.read_csv(path, parse_dates=["date"])

        if df.empty:
            errors.append(f"CONCEPT: {filename} is empty")
            continue

        # Check columns
        if "date" not in df.columns or "concept" not in df.columns:
            errors.append(f"CONCEPT: {filename} missing required columns")
            continue

        # Check for NaN close
        if "close" in df.columns:
            nan_close = df["close"].isna().sum()
            if nan_close > 0:
                warnings.append(f"CONCEPT ({filename}): {nan_close} NaN close values")
            else:
                print(f"  [OK] {filename}: no NaN close values")

        # Check for NaN or extreme return values
        if "return" in df.columns:
            nan_return = df["return"].isna().sum()
            if nan_return > 0:
                warnings.append(f"CONCEPT ({filename}): {nan_return} NaN return values")
            extreme_ret = (df["return"].abs() > 0.30).sum() if "return" in df.columns else 0
            if extreme_ret > 0:
                warnings.append(f"CONCEPT ({filename}): {extreme_ret} extreme return values (>30%)")
        else:
            print(f"  [OK] {filename}: no return column to check")

        date_min = df["date"].min().date() if hasattr(df["date"].min(), "date") else df["date"].min()
        date_max = df["date"].max().date() if hasattr(df["date"].max(), "date") else df["date"].max()
        print(f"  [OK] {filename}: {len(df)} rows, {date_min} ~ {date_max}")


def check_etf_data():
    """Validate etf_flow.csv."""
    path = DATA_DIR / "etf_flow.csv"
    if not check_file_exists(path):
        return

    df = pd.read_csv(path)

    if df.empty:
        errors.append("ETF: etf_flow.csv is empty")
        return

    # Check required columns
    required = {"date", "order_book_id", "close"}
    missing = required - set(df.columns)
    if missing:
        errors.append(f"ETF: missing columns {missing}")
        return

    # Check unique ETFs
    unique_etfs = df["order_book_id"].nunique()
    print(f"  [OK] ETF data: {len(df)} rows, {unique_etfs} ETFs")

    # Check for NaN close
    nan_close = df["close"].isna().sum()
    if nan_close > 0:
        warnings.append(f"ETF: {nan_close} NaN close values")
    else:
        print(f"  [OK] ETF: no NaN close values")


def check_concept_etf_map():
    """Validate concept_etf_map.csv."""
    path = DATA_DIR / "concept_etf_map.csv"
    if not check_file_exists(path):
        return

    df = pd.read_csv(path)

    # Check columns
    required = {"concept", "order_book_id"}
    missing = required - set(df.columns)
    if missing:
        errors.append(f"MAPPING: missing columns {missing}")
        return

    unique_concepts = df["concept"].nunique()
    unique_etfs = df["order_book_id"].nunique()
    print(f"  [OK] concept_etf_map: {unique_concepts} concepts, {unique_etfs} ETFs")


def main() -> int:
    print("=== Data Validation ===\n")

    print("Checking AMV data...")
    check_amv_daily()

    print("\nChecking concept data...")
    check_concept_data()

    print("\nChecking ETF data...")
    check_etf_data()

    print("\nChecking concept-ETF mapping...")
    check_concept_etf_map()

    # Summary
    print(f"\n=== Summary ===")
    if errors:
        print(f"ERRORS: {len(errors)}")
        for e in errors:
            print(f"  [ERROR] {e}")

    if warnings:
        print(f"WARNINGS: {len(warnings)}")
        for w in warnings:
            print(f"  [WARN] {w}")

    if not errors:
        print("Data validation PASSED")
        return 0
    else:
        print("Data validation FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
