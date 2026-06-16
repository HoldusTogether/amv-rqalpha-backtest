"""
数据新鲜度检查脚本
用法: python scripts/check_data_freshness.py
"""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def check_data_freshness() -> dict:
    """检查所有数据文件的新鲜度"""
    today = datetime.now().date()
    results = {}
    
    # 检查 AMV 数据
    amv_path = DATA_DIR / "amv_daily.csv"
    if amv_path.exists():
        amv = pd.read_csv(amv_path)
        latest = pd.to_datetime(amv["date"]).max().date()
        days_behind = (today - latest).days
        results["amv_daily"] = {
            "latest": str(latest),
            "days_behind": days_behind,
            "status": "ok" if days_behind <= 2 else "stale" if days_behind <= 5 else "critical",
        }
    
    # 检查 concept 数据 (优�� TDX)
    tdx_path = DATA_DIR / "concept_daily_returns_tdx.csv"
    akshare_path = DATA_DIR / "concept_daily_returns.csv"
    
    if tdx_path.exists():
        tdx = pd.read_csv(tdx_path)
        latest = pd.to_datetime(tdx["date"]).max().date()
        days_behind = (today - latest).days
        results["concept_daily_tdx"] = {
            "latest": str(latest),
            "days_behind": days_behind,
            "status": "ok" if days_behind <= 2 else "stale" if days_behind <= 5 else "critical",
        }
    elif akshare_path.exists():
        akshare = pd.read_csv(akshare_path)
        latest = pd.to_datetime(akshare["date"]).max().date()
        days_behind = (today - latest).days
        results["concept_daily_akshare"] = {
            "latest": str(latest),
            "days_behind": days_behind,
            "status": "ok" if days_behind <= 2 else "stale" if days_behind <= 5 else "critical",
        }
    
    # 检查 ETF 数据
    etf_path = DATA_DIR / "etf_flow.csv"
    if etf_path.exists():
        etf = pd.read_csv(etf_path)
        latest = pd.to_datetime(etf["date"]).max().date()
        days_behind = (today - latest).days
        results["etf_flow"] = {
            "latest": str(latest),
            "days_behind": days_behind,
            "status": "ok" if days_behind <= 2 else "stale" if days_behind <= 5 else "critical",
        }
    
    return results


def main():
    print("=== Data Freshness Check ===")
    today = datetime.now().date()
    print(f"Today: {today}\n")
    
    results = check_data_freshness()
    
    if not results:
        print("No data files found!")
        return 1
    
    # 打印结果
    ok_count = 0
    stale_count = 0
    critical_count = 0
    
    for name, info in results.items():
        status = info["status"]
        days = info["days_behind"]
        latest = info["latest"]
        
        if status == "ok":
            icon = "✓"
            ok_count += 1
        elif status == "stale":
            icon = "⚠"
            stale_count += 1
        else:
            icon = "✗"
            critical_count += 1
        
        print(f"{icon} {name}: latest={latest}, behind={days} days")
    
    print()
    print(f"Summary: {ok_count} ok, {stale_count} stale, {critical_count} critical")
    
    # 如���有严重问题，返回错误码
    if critical_count > 0:
        print("\n⚠ WARNING: Critical data staleness detected!")
        print("Run: .\\scripts\\update_data.ps1")
        return 2
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
