import pandas as pd
amv = pd.read_csv(r"D:\workSpace\amv-rqalpha-backtest\data\amv_daily.csv")
amv["date"] = pd.to_datetime(amv["date"])
amv = amv[amv["date"] >= "2021-01-01"]

pct = pd.to_numeric(amv["pct_change"], errors="coerce")
print(f"原始max: {pct.abs().max():.6f}")
print(f"原始值示例: {pct.head().tolist()}")

# If max > 1.5, divide by 100 (as normalize does)
if pct.abs().max() > 1.5:
    pct = pct / 100.0
    print(f"已除以100，新的max: {pct.max():.6f}")

print(f"\n2021年起 pct_change 统计:")
print(f"  max={pct.max():.6f} ({pct.max()*100:.2f}%)")
print(f"  min={pct.min():.6f} ({pct.min()*100:.2f}%)")  
print(f"  mean={pct.mean():.6f}")
print(f"  std={pct.std():.6f}")
print(f"  >=+4% (0.04): {(pct>=0.04).sum()}次")
print(f"  <=-2.3% (-0.023): {(pct<=-0.023).sum()}次")
print(f"  >=+2% (0.02): {(pct>=0.02).sum()}次")
print(f"  >=+1% (0.01): {(pct>=0.01).sum()}次")
