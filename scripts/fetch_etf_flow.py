"""
Fetch real ETF capital flow data from AKShare (Eastmoney) and bundle.
Strategy: pick the ETF with highest net capital inflow on each day.
"""
import sys
import random
from pathlib import Path
import pandas as pd
import numpy as np
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "strategy"))
DATA_DIR = ROOT / "data"


def _import_akshare():
    import akshare as ak
    return ak


def _call_with_retry(label, func, retries=2, delay=3):
    last_error = None
    for attempt in range(1, retries + 2):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            print(f"  {label} failed attempt {attempt}: {exc}")
            if attempt <= retries:
                time.sleep(delay)
    raise RuntimeError(f"{label} failed after {retries + 1} attempts") from last_error


def get_eligible_etfs(min_turnover=20_000_000) -> list[dict]:
    """
    Get eligible equity ETFs from AKShare real-time data.
    Filters: equity ETFs (not money market/bond), with min daily turnover.
    """
    ak = _import_akshare()
    spot = _call_with_retry("fund_etf_spot_em", lambda: ak.fund_etf_spot_em(), retries=2)
    
    # Filter: exclude money market, bond, commodity, currency
    skip_keywords = ['货币', '国债', '可转债', '公司债', '地方债', '城投债', 
                     '短融', '信用债', '利率债', '政金债', '金债']
    
    mask = ~spot['名称'].str.contains('|'.join(skip_keywords), na=False)
    
    # Filter by turnover (成交额) if available
    if '成交额' in spot.columns:
        spot['成交额'] = pd.to_numeric(spot['成交额'], errors='coerce')
        mask &= (spot['成交额'].fillna(0) >= min_turnover)
    
    eligible = spot[mask].copy()
    
    # Build order_book_id
    def to_oid(code):
        code = str(code).strip().zfill(6)
        if code.startswith(('5', '6')):
            return f"{code}.XSHG"
        if code.startswith(('0', '1', '3')):
            return f"{code}.XSHE"
        return None
    
    eligible['order_book_id'] = eligible['代码'].apply(to_oid)
    eligible = eligible.dropna(subset=['order_book_id'])
    
    results = []
    for _, row in eligible.iterrows():
        results.append({
            'order_book_id': row['order_book_id'],
            'etf_name': str(row['名称']),
            'turnover': float(row.get('成交额', 0) or 0),
        })
    
    return results


def compute_flow_proxy(hist_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute daily capital flow proxy from OHLCV data.
    
    Formula (standard in Chinese markets):
    Money Flow = Turnover * (2*Close - High - Low) / (High - Low)
    
    This gives a signed flow value:
    - Positive: buying pressure (close near high)
    - Negative: selling pressure (close near low)
    """
    df = hist_df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    
    # Rename columns
    rename = {
        '日期': 'date', '开盘': 'open', '收盘': 'close', 
        '最高': 'high', '最低': 'low', '成交量': 'volume',
        '成交额': 'turnover', '涨跌幅': 'pct_chg', '换手率': 'turnover_rate'
    }
    df = df.rename(columns=rename)
    df['date'] = pd.to_datetime(df['date'])
    
    for col in ['open', 'close', 'high', 'low', 'volume', 'turnover']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Capital flow formula
    # Net Flow = turnover * (2*close - high - low) / (high - low)
    price_range = df['high'] - df['low']
    price_range = price_range.replace(0, np.nan)  # avoid div by zero
    
    df['flow_multiplier'] = (2 * df['close'] - df['high'] - df['low']) / price_range
    df['net_flow'] = df['turnover'] * df['flow_multiplier']
    
    # Also compute MFI (Money Flow Index) as a normalized measure
    # Typical price = (high + low + close) / 3
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['raw_money_flow'] = df['typical_price'] * df['volume']
    
    # Positive money flow vs negative
    df['positive_flow'] = np.where(df['typical_price'] > df['typical_price'].shift(1), 
                                    df['raw_money_flow'], 0)
    df['negative_flow'] = np.where(df['typical_price'] < df['typical_price'].shift(1),
                                    df['raw_money_flow'], 0)
    
    # MFI (14-day): 100 - 100 / (1 + positive_ratio)
    window = 14
    df['mfi'] = 100 - 100 / (1 + (
        df['positive_flow'].rolling(window).sum() / 
        df['negative_flow'].rolling(window).sum().replace(0, np.nan)
    ))
    
    return df[['date', 'net_flow', 'flow_multiplier', 'mfi', 'turnover', 'pct_chg']]


def fetch_etf_history(oid: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """
    Fetch historical daily data for an ETF from AKShare Eastmoney.
    Returns None if fails.
    """
    code = oid.split('.')[0]
    ak = _import_akshare()
    try:
        df = _call_with_retry(
            f"fund_etf_hist_em({code})",
            lambda: ak.fund_etf_hist_em(
                symbol=code, period='daily',
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust='qfq'
            ),
            retries=1
        )
        return df
    except Exception as e:
        print(f"  WARN: failed to fetch {oid}: {e}")
        return None


def build_etf_flow_data(etfs: list[dict], start_date: str, end_date: str) -> pd.DataFrame:
    """
    Build complete ETF flow dataframe for all eligible ETFs.
    """
    all_flows = []
    total = len(etfs)
    
    for i, etf in enumerate(etfs):
        oid = etf['order_book_id']
        name = etf['etf_name']
        print(f"  [{i+1}/{total}] {oid} {name[:20]}...")
        
        hist = fetch_etf_history(oid, start_date, end_date)
        if hist is None or hist.empty:
            continue
        
        flow = compute_flow_proxy(hist)
        flow['order_book_id'] = oid
        flow['etf_name'] = name
        all_flows.append(flow)
        
        jitter = random.uniform(1.5, 3.0)
        print(f"    sleep {jitter:.1f}s to avoid rate limit...")
        time.sleep(jitter)  # rate limit
    
    if not all_flows:
        return pd.DataFrame()
    
    result = pd.concat(all_flows, ignore_index=True)
    result = result.sort_values(['date', 'net_flow'], ascending=[True, False])
    result['date'] = result['date'].dt.date.astype(str)
    return result


def main():
    print("Step 1: Getting eligible ETFs from AKShare...")
    etfs = get_eligible_etfs(min_turnover=50_000_000)  # min 50M daily turnover
    print(f"  Found {len(etfs)} eligible ETFs")
    
    # Save ETF list
    etf_list = pd.DataFrame(etfs)
    out_path = DATA_DIR / "etf_candidates.csv"
    etf_list.to_csv(out_path, index=False, encoding='utf-8')
    print(f"  Saved ETF list: {out_path}")
    
    # For backtest, we need data from 2020
    print("\nStep 2: Fetching historical data and computing capital flow...")
    print("  This may take a while for many ETFs...")
    
    # Start with a subset: top 50 by turnover
    top50 = sorted(etfs, key=lambda x: -x['turnover'])[:50]
    print(f"  Using top {len(top50)} ETFs by turnover")
    
    flow_df = build_etf_flow_data(top50, "2020-01-01", "2026-06-01")
    
    if flow_df.empty:
        print("  ERROR: no data fetched!")
        return
    
    out_path = DATA_DIR / "etf_flow.csv"
    flow_df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"\n  Saved {len(flow_df)} rows: {out_path}")
    print(f"  Date range: {flow_df['date'].min()} ~ {flow_df['date'].max()}")
    print(f"  ETFs covered: {flow_df['order_book_id'].nunique()}")
    
    # Quick stats
    print(f"\n  Top 10 ETFs by average daily net flow:")
    avg_flow = flow_df.groupby(['order_book_id', 'etf_name'])['net_flow'].mean().sort_values(ascending=False).head(10)
    for oid, flow in avg_flow.items():
        print(f"    {oid[0]}: {flow[1]:.0f}" if isinstance(oid, tuple) else f"    {oid}: {flow:.0f}")


if __name__ == "__main__":
    main()
