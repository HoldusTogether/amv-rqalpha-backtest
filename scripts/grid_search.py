"""AMV择时参数网格搜索

在指定参数网格上运行回测，按夏普比率排序输出结果。
用法: .venv\Scripts\python.exe scripts\grid_search.py
"""
from __future__ import annotations

import contextlib
import io
import itertools
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = PROJECT_ROOT / "bundle" / "bundle"
STRATEGY = PROJECT_ROOT / "strategy" / "amv_band_strategy.py"

# 搜索的参数网格
PARAM_GRID = {
    "long_threshold": [0.03, 0.04, 0.05],
    "short_threshold": [-0.02, -0.025],
    "reduce_weight": [0.5, 0.7],
}
# reduce_threshold 固定为 long_threshold 的一半
REDUCE_RATIO = 0.5

# 回测时间范围
START_DATE = "2021-08-02"
END_DATE = "2026-06-01"


def run_backtest(params: dict) -> dict:
    """运行一次回测，返回摘要指标。"""
    long_t = params["long_threshold"]
    short_t = params["short_threshold"]
    reduce_w = params["reduce_weight"]
    reduce_t = long_t * REDUCE_RATIO  # reduce = half of long threshold

    # 修改策略文件中的参数
    strategy_text = STRATEGY.read_text(encoding="utf-8")
    old_params = (
        f"long_threshold=0.04,\n"
        f"        reduce_threshold=-0.015,\n"
        f"        short_threshold=-0.023,\n"
        f"        long_weight=1.0,\n"
        f"        reduce_weight=0.5,"
    )
    new_params = (
        f"long_threshold={long_t},\n"
        f"        reduce_threshold={reduce_t},\n"
        f"        short_threshold={short_t},\n"
        f"        long_weight=1.0,\n"
        f"        reduce_weight={reduce_w},"
    )
    strategy_text = strategy_text.replace(old_params, new_params)
    STRATEGY.write_text(strategy_text, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT / 'strategy'};{env.get('PYTHONPATH', '')}"

    import subprocess
    cmd = [
        sys.executable, "-m", "rqalpha",
        "run",
        "-d", str(BUNDLE),
        "-f", str(STRATEGY),
        "-s", START_DATE,
        "-e", END_DATE,
        "-a", "stock", "1000000",
        "-fq", "1d",
        "--matching-type", "current_bar",
        "--output", str(PROJECT_ROOT / "reports" / "result.pkl"),
    ]
    t0 = time.time()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    elapsed = time.time() - t0

    # 解析结果
    summary = {}
    for line in result.stdout.split("\n"):
        for key in ["总收益率", "年化收益率", "夏普比率", "最大回撤", "胜率", "利润因子"]:
            if key in line:
                summary[key] = line.strip()

    return {
        "params": params,
        "elapsed": f"{elapsed:.0f}s",
        "summary": summary,
        "returncode": result.returncode,
        "error": result.stderr[:500] if result.returncode != 0 else "",
    }


def main():
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    results = []

    print(f"网格搜索: {len(list(itertools.product(*values)))} 种组合")
    print(f"时间范围: {START_DATE} ~ {END_DATE}")
    print()

    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        label = " ".join(f"{k}={v}" for k, v in params.items())
        print(f"测试: {label}")
        res = run_backtest(params)
        print(f"  耗时: {res['elapsed']}, 状态: {'OK' if res['returncode']==0 else 'FAIL'}")
        if res["summary"]:
            for k, v in res["summary"].items():
                print(f"  {k}: {v}")
        if res["error"]:
            print(f"  错误: {res['error']}")
        results.append(res)
        print()

    # 恢复默认参数
    run_backtest({"long_threshold": 0.04, "short_threshold": -0.023, "reduce_weight": 0.5})

    # 输出结果汇总
    print("\n=== 结果汇总 ===")
    for r in sorted(results, key=lambda x: x.get("summary", {}).get("夏普比率", "")):
        print(r["params"], r.get("summary", {}))


if __name__ == "__main__":
    main()
