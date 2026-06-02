"""
验证：通达信 tdxzsbase.cfg 中的个股主力资金流 vs 我们概念指数proxy资金流
"""
import os, struct

# ----- 1. 从 tdxzsbase.cfg 读取个股主力资金流 (最新交易日) -----
path = r"D:\new_tdx\T0002\hq_cache\tdxzsbase.cfg"
data = open(path, "rb").read()
lines = data.split(b"\n")

stock_flow = {}  # stock_code -> {large_buy, large_sell, net}
lines_dates = set()

for line in lines:
    decoded = line.decode("gbk", errors="replace").strip()
    if not decoded:
        continue
    parts = decoded.split("|")
    if len(parts) < 26:
        continue
    try:
        code = parts[1].strip()
        large_buy = float(parts[2])
        large_sell = float(parts[3])
        total_buy = float(parts[4])
        total_sell = float(parts[5])
        dt = parts[7]
        lines_dates.add(dt)
    except (ValueError, IndexError):
        continue
    stock_flow[code] = {
        "large_buy": large_buy, "large_sell": large_sell,
        "large_net": large_buy - large_sell,
        "total_buy": total_buy, "total_sell": total_sell,
        "total_net": total_buy - total_sell,
        "date": dt,
    }

print(f"tdxzsbase.cfg 个股数: {len(stock_flow)}")
print(f"包含日期: {sorted(lines_dates)}")

# ----- 2. 从 infoharbor_block.dat 读取概念成分股 -----
path2 = r"D:\new_tdx\T0002\hq_cache\infoharbor_block.dat"
data2 = open(path2, "rb").read()
lines2 = data2.split(b"\n")

# 找 "白酒概念" 的成分股
target_concept = "白酒概念"
target_code = None
members = []

i = 0
while i < len(lines2):
    decoded = lines2[i].decode("gbk", errors="replace").strip()
    if decoded.startswith(f"#GN_{target_concept},"):
        parts = decoded.split(",")
        target_code = parts[2]  # index code
        i += 1
        # Next lines contain member stocks
        while i < len(lines2):
            next_line = lines2[i].decode("gbk", errors="replace").strip()
            if not next_line or next_line.startswith("#GN_"):
                break
            for token in next_line.split(","):
                token = token.strip()
                if token and "#" in token:
                    members.append(token)
            i += 1
        break
    i += 1

print(f"\n{target_concept}: index_code={target_code}, 成分股数={len(members)}")
print(f"  示例: {members[:5]}")

# ----- 3. 汇总个股资金流 -----
def to_shsz_code(member_str):
    """0#000001 -> 000001 (SH/SZ depends on prefix)"""
    parts = member_str.split("#")
    if len(parts) != 2:
        return None
    mkt, code = parts
    return code  # TDX uses 6-digit without prefix

total_large_net = 0.0
total_total_net = 0.0
found = 0
missing = 0

for m in members:
    code = to_shsz_code(m)
    if code and code in stock_flow:
        sf = stock_flow[code]
        total_large_net += sf["large_net"]
        total_total_net += sf["total_net"]
        found += 1
    else:
        missing += 1

print(f"\n找到资金流数据的成分股: {found}/{len(members)}")
print(f"未找到: {missing}")
print(f"\n== {target_concept} 真实每日资金流 (tdxzsbase.cfg) ==")
print(f"  主力净流入(大单): {total_large_net:,.0f}")
print(f"  总净流入(所有单): {total_total_net:,.0f}")

# 对比proxy
print(f"\n  数据日期: {sorted(lines_dates)}")
