"""Threshold scan - compute return from equity (收益率 metric is buggy for <4%)"""
from __future__ import annotations

import os, re, shutil, subprocess, sys, time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
STRATEGY = ROOT / "strategy" / "amv_band_strategy.py"
BUNDLE = ROOT / "bundle" / "bundle"
REPORT_DIR = ROOT / "reports" / "report"
SUMMARY_PATH = REPORT_DIR / "summary.xlsx"
RESULT_PKL = ROOT / "reports" / "result.pkl"
env = os.environ.copy()
env["PYTHONPATH"] = f"{ROOT / 'strategy'};{env.get('PYTHONPATH', '')}"

THRESHOLDS = [0.025, 0.03, 0.035, 0.04, 0.05]


def run_one(long_t):
    orig = STRATEGY.read_text(encoding="utf-8")
    text = re.sub(r'long_threshold=[\d.]+', f'long_threshold={long_t}', orig)
    STRATEGY.write_text(text, encoding="utf-8")

    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    if RESULT_PKL.exists():
        RESULT_PKL.unlink()

    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "rqalpha", "run",
         "-d", str(BUNDLE), "-f", str(STRATEGY),
         "-s", "2021-08-02", "-e", "2026-06-01",
         "-a", "stock", "1000000", "-fq", "1d",
         "--matching-type", "current_bar"],
        env=env, capture_output=True, text=True, timeout=600,
    )
    elapsed = time.time() - t0
    STRATEGY.write_text(orig, encoding="utf-8")

    if not SUMMARY_PATH.exists():
        return None

    import pandas as pd
    s = pd.read_excel(SUMMARY_PATH, index_col=0, header=None)
    m = {}
    for idx, row in s.iterrows():
        val = row.iloc[0]
        key = str(idx).strip()
        if pd.isna(val):
            continue
        try:
            m[key] = float(val)
        except (ValueError, TypeError):
            m[key] = val

    # Compute total return from equity
    eq = m.get("总权益", 0)
    init_str = m.get("初始资金", "STOCK:1000000.0")
    init = 1000000.0
    if isinstance(init_str, str) and ":" in init_str:
        try:
            init = float(init_str.split(":")[1])
        except:
            pass
    if eq and init:
        m["_total_return"] = (eq - init) / init  # always fractional (0.838 = 83.8%)

    return m


def main():
    results = {}
    for lt in THRESHOLDS:
        print(f"  long={lt:.1%} ... ", end="", flush=True)
        m = run_one(lt)
        results[lt] = m
        if m:
            ret = m.get("_total_return", 0) * 100
            ann = m.get("年化收益率", 0)
            ann_pct = ann * 100 if isinstance(ann, float) and -1 <= ann <= 1 else ann
            sharpe = m.get("夏普比率", 0)
            dd = m.get("最大回撤", 0)
            dd_pct = dd * 100 if isinstance(dd, float) and -1 <= dd <= 1 else dd
            pf = m.get("盈亏比", 0)
            win = m.get("胜率", 0)
            win_pct = win * 100 if isinstance(win, float) and -1 <= win <= 1 else win
            calmar = m.get("卡玛比率", 0)
            eq = m.get("总权益", 0)
            print(f"  eq={eq:.0f} ret={ret:.1f}% ann={ann_pct:.1f}% sharpe={sharpe:.3f} dd={dd_pct:.1f}% pf={pf:.3f} win={win_pct:.1f}% calmar={calmar:.3f}")
        else:
            print("FAIL")

    print(f"\n{'='*100}")
    print(f"{'阈值':>8} {'总收益':>8} {'年化':>7} {'夏普':>7} {'卡玛':>7} {'回撤':>7} {'PF':>7} {'胜率':>7}")
    print('-' * 100)
    for lt in THRESHOLDS:
        m = results.get(lt)
        if not m:
            print(f"{lt:.1%}  {'FAIL':>8}")
            continue
        ret = m.get("_total_return", 0) * 100
        ann = m.get("年化收益率", 0)
        ann_pct = ann * 100 if isinstance(ann, float) and -1 <= ann <= 1 else ann
        sharpe = m.get("夏普比率", 0)
        calmar = m.get("卡玛比率", 0)
        dd = m.get("最大回撤", 0)
        dd_pct = dd * 100 if isinstance(dd, float) and -1 <= dd <= 1 else dd
        pf = m.get("盈亏比", 0)
        win = m.get("胜率", 0)
        win_pct = win * 100 if isinstance(win, float) and -1 <= win <= 1 else win
        print(f"{lt:.1%}  {ret:>7.1f}% {ann_pct:>6.1f}% {sharpe:>6.2f} {calmar:>6.2f} {dd_pct:>6.1f}% {pf:>6.2f} {win_pct:>6.1f}%")

    valid = [(lt, m) for lt, m in results.items() if m]
    if valid:
        best_sharpe = max(valid, key=lambda x: x[1].get("夏普比率", -999))
        best_calmar = max(valid, key=lambda x: x[1].get("卡玛比率", -999))
        best_return = max(valid, key=lambda x: x[1].get("_total_return", -999))
        print(f"\nBest Sharpe : {best_sharpe[0]:.1%} (Sharpe={best_sharpe[1].get('夏普比率',0):.3f})")
        print(f"Best Calmar: {best_calmar[0]:.1%} (Calmar={best_calmar[1].get('卡玛比率',0):.3f})")
        ret_pct = best_return[1].get('_total_return', 0) * 100
        print(f"Best Return: {best_return[0]:.1%} ({ret_pct:.1f}%)")


if __name__ == "__main__":
    main()
