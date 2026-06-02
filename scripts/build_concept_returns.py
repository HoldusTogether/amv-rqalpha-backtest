"""
从通达信概念指数 .day 文件构建每日收益率数据。
输出: data/concept_daily_returns.csv (真实价格数据，非代理)
"""
import csv
import os
import struct
from pathlib import Path

TDX_LDAY = r"D:\new_tdx\vipdoc\sh\lday"
TDX_INFOHARBOR = r"D:\new_tdx\T0002\hq_cache\infoharbor_block.dat"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data"


def parse_concept_headers() -> list[tuple[str, str]]:
    data = open(TDX_INFOHARBOR, "rb").read()
    lines = data.split(b"\n")
    concepts = []
    for line in lines:
        decoded = line.decode("gbk", errors="replace").strip()
        if decoded.startswith("#GN_"):
            parts = decoded.split(",")
            if len(parts) >= 3:
                concepts.append((parts[0][4:], parts[2]))
    return concepts


def parse_tdx_day(code: str) -> list[dict] | None:
    path = os.path.join(TDX_LDAY, f"sh{code}.day")
    if not os.path.exists(path):
        return None
    data = open(path, "rb").read()
    records = []
    for i in range(0, len(data), 32):
        rec = data[i:i + 32]
        if len(rec) < 32:
            break
        vals = struct.unpack("<IiiiiiII", rec)
        records.append({"date": vals[0], "close": vals[4] / 100.0})
    return records


def main():
    print("=== 构建概念指数日收益率数据 ===")
    concepts = parse_concept_headers()
    print(f"概念数: {len(concepts)}")

    all_rows = []
    for i, (name, code) in enumerate(concepts):
        records = parse_tdx_day(code)
        if not records:
            continue

        prev_close = None
        for r in records:
            close = r["close"]
            ret = 0.0 if prev_close is None else (close - prev_close) / prev_close
            prev_close = close
            all_rows.append({
                "date": f"{r['date']//10000:04d}-{r['date']%10000//100:02d}-{r['date']%100:02d}",
                "concept": name,
                "close": close,
                "return": round(ret, 8),
            })

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(concepts)}] {name}: {len(records)}条")

    print(f"\n总行数: {len(all_rows)}")

    # 按日期排序
    all_rows.sort(key=lambda r: (r["date"], r["concept"]))

    out_path = OUTPUT_DIR / "concept_daily_returns_tdx.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "concept", "close", "return"])
        writer.writeheader()
        writer.writerows(all_rows)

    unique_dates = len(set(r["date"] for r in all_rows))
    print(f"输出: {out_path}")
    print(f"概念数: {len(concepts)}, 交易天数: {unique_dates}")
    print(f"日期范围: {all_rows[0]['date']} ~ {all_rows[-1]['date']}")
    print("完成！")


if __name__ == "__main__":
    main()
