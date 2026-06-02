"""
检查AKShare概念板块资金流相关API
"""
import akshare as ak
import inspect

# Search for sector/concept fund flow related functions
all_funcs = [name for name in dir(ak) if "fund" in name.lower() or "flow" in name.lower() or "sector" in name.lower() or "板块" in name or "概念" in name or "资金" in name]
print("AKShare 相关函数:")
for f in sorted(all_funcs):
    print(f"  {f}")

print("\n--- stock_sector_fund_flow_rank ---")
try:
    help(ak.stock_sector_fund_flow_rank)
except:
    print("not available")

print("\n--- stock_individual_fund_flow ---")
try:
    help(ak.stock_individual_fund_flow)
except Exception as e:
    print(f"error: {e}")

# Try calling the sector flow rank
print("\n--- 尝试获取板块资金流排名 ---")
try:
    df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
    print(f"成功! 类型: {type(df).__name__}, 形状: {df.shape}")
    print(df.head(10).to_string())
except Exception as e:
    print(f"行业资金流失败: {e}")

try:
    df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")
    print(f"\n成功(概念)! 类型: {type(df).__name__}, 形状: {df.shape}")
    print(df.head(10).to_string())
except Exception as e:
    print(f"概念资金流失败: {e}")
