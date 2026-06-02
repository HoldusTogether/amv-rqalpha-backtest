"""Focused grid search around optimal point: long=[3,3.5,4]%, reduce=[1.5,2,2.5]%, short=[2.5,3,3.5]%"""
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

LONGS = [0.03, 0.035, 0.04]
REDUCES = [-0.015, -0.02, -0.025]
SHORTS = [-0.025, -0.03, -0.035]
REDUCE_W = 0.5


def patch_and_run(long_t, reduce_t, short_t):
    orig = STRATEGY.read_text(encoding="utf-8")
    text = re.sub(r'long_threshold=[\d.]+', f'long_threshold={long_t}', orig)
    text = re.sub(r'reduce_threshold=-?[\d.]+', f'reduce_threshold={reduce_t}', text)
    text = re.sub(r'short_threshold=-?[\d.]+', f'short_threshold={short_t}', text)
    text = re.sub(r'reduce_weight=[\d.]+', f'reduce_weight={REDUCE_W}', text)
    STRATEGY.write_text(text, encoding="utf-8")

    if REPORT_DIR.exists(): shutil.rmtree(REPORT_DIR)
    if RESULT_PKL.exists(): RESULT_PKL.unlink()

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
        if pd.isna(val): continue
        try: m[key] = float(val)
        except: m[key] = val

    eq = m.get("总权益", 0)
    init_str = m.get("初始资金", "STOCK:1000000.0")
    init = 1000000.0
    if isinstance(init_str, str) and ":" in init_str:
        try: init = float(init_str.split(":")[1])
        except: pass
    m["_ret"] = (eq - init) / init if eq and init else 0
    m["_elapsed"] = elapsed
    return m


def fmt(m):
    if not m: return "FAIL"
    ret = m["_ret"] * 100
    ann = m.get("年化收益率", 0)
    ann_pct = ann * 100 if isinstance(ann, float) and -1 <= ann <= 1 else ann
    sharpe = m.get("夏普比率", 0)
    dd = m.get("最大回撤", 0)
    dd_pct = dd * 100 if isinstance(dd, float) and -1 <= dd <= 1 else dd
    pf = m.get("盈亏比", 0)
    win = m.get("胜率", 0)
    win_pct = win * 100 if isinstance(win, float) and -1 <= win <= 1 else win
    return ret, ann_pct, sharpe, dd_pct, pf, win_pct, m["_elapsed"]


def main():
    # Build valid combos: reduce > short (less negative)
    combos = []
    for lt in LONGS:
        for rt in REDUCES:
            for st in SHORTS:
                if st < rt:  # short more negative than reduce
                    combos.append((lt, rt, st))

    print(f"Grid: {len(combos)} combos\n")
    results = []
    for i, (lt, rt, st) in enumerate(combos):
        label = f"L{lt:.1%}_R{rt:.1%}_S{st:.1%}"
        print(f"  [{i+1}/{len(combos)}] {label} ... ", end="", flush=True)
        m = patch_and_run(lt, rt, st)
        if m:
            ret, ann, sharpe, dd, pf, win, t = fmt(m)
            print(f"ret={ret:.1f}% ann={ann:.1f}% sharpe={sharpe:.3f} dd={dd:.1f}% pf={pf:.3f} win={win:.1f}% [{t:.0f}s]")
            results.append((lt, rt, st, m))
        else:
            print("FAIL")

    print(f"\n{'='*115}")
    print(f"{'Long':>7} {'Reduce':>8} {'Short':>7} {'总收益':>8} {'年化':>7} {'夏普':>7} {'回撤':>7} {'PF':>7} {'胜率':>7}")
    print('-' * 115)
    for lt, rt, st, m in results:
        ret, ann, sharpe, dd, pf, win, _ = fmt(m)
        print(f"{lt:.1%}  {rt:.1%}  {st:.1%}  {ret:>7.1f}% {ann:>6.1f}% {sharpe:>6.2f} {dd:>6.1f}% {pf:>6.2f} {win:>6.1f}%")

    if results:
        best_sharpe = max(results, key=lambda x: x[3].get("夏普比率", -999))
        best_ret = max(results, key=lambda x: x[3]["_ret"])
        best_dd = min(results, key=lambda x: x[3].get("最大回撤", 999))
        print(f"\nBest Sharpe : L{best_sharpe[0]:.1%} R{best_sharpe[1]:.1%} S{best_sharpe[2]:.1%} (Sharpe={best_sharpe[3].get('夏普比率',0):.3f}, Ret={best_sharpe[3]['_ret']*100:.1f}%)")
        print(f"Best Return: L{best_ret[0]:.1%} R{best_ret[1]:.1%} S{best_ret[2]:.1%} ({best_ret[3]['_ret']*100:.1f}%)")
        print(f"Best DD    : L{best_dd[0]:.1%} R{best_dd[1]:.1%} S{best_dd[2]:.1%} (DD={best_dd[3].get('最大回撤',0)*100:.1f}%)")


if __name__ == "__main__":
    main()
