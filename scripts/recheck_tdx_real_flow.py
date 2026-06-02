"""
重新审视 td xzsbase.cfg：它可能包含概念级别的真实资金流数据！
"""
path = r"D:\new_tdx\T0002\hq_cache\tdxzsbase.cfg"
data = open(path, "rb").read()
lines = data.split(b"\n")

print(f"总行数: {len(lines)}")

# Check code types
codes = []
for line in lines:
    decoded = line.decode("gbk", errors="replace").strip()
    if not decoded:
        continue
    parts = decoded.split("|")
    if len(parts) >= 2:
        codes.append(parts[1])

# Count by prefix
from collections import Counter
prefix_count = Counter()
for c in codes:
    if c.startswith("88"):
        prefix_count["88xxxx (概念/板块)"] += 1
    elif c.startswith("000"):
        prefix_count["000xxx (上证指数)"] += 1
    elif c.startswith("399"):
        prefix_count["399xxx (深证指数)"] += 1
    elif c.startswith("1"):
        prefix_count["1xxxxx (行业/板块)"] += 1
    else:
        prefix_count[f"{c[:2]}xxx"] += 1

print("\n代码前缀分布:")
for k, v in prefix_count.most_common():
    print(f"  {k}: {v}")

# Find concept codes (88xxxx)
concept_codes = [c for c in codes if c.startswith("88")]
print(f"\n概念代码 (88xxxx): {len(concept_codes)}")
print(f"  示例: {concept_codes[:10]}")

# Compare with concept index codes from infoharbor_block.dat
# If they match, tdxzsbase.cfg has concept-level data!
