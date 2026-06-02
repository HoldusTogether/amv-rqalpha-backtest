"""Compare Direction A vs Direction B backtest results."""
import pickle
from pathlib import Path
from collections import Counter

REPORTS = Path("D:/workSpace/amv-rqalpha-backtest/reports")

def load(name):
    with open(REPORTS / f"result_{name}.pkl", "rb") as f:
        return pickle.load(f)

def main():
    results = {n: load(n) for n in ["a", "b"]}
    sa = results["a"]["summary"]
    sb = results["b"]["summary"]
    ta = results["a"]["trades"]
    tb = results["b"]["trades"]

    print("=" * 65)
    print("  方向A vs 方向B 完整对比 (窗口=5日)")
    print("  方向A: ETF动量轮动 (真实价格)")
    print("  方向B: 概念动量轮动 (真实价格)")
    print("  区间: {} ~ {}".format(sa["start_date"], sa["end_date"]))
    print("  初始资金: 1,000,000")
    print("=" * 65)

    print()
    print("{0:>25s}  {1:>12s}  {2:>12s}  {3:>12s}  {4:s}".format(
        "指标", "方向A", "方向B", "差异", "优胜"))
    print("-" * 72)

    items = [
        ("total_returns", "总收益率", True),
        ("annualized_returns", "年化收益率", True),
        ("sharpe", "夏普比率", True),
        ("sortino", "索提诺比率", True),
        ("volatility", "波动率", False),
        ("max_drawdown", "最大回撤", False),
        ("win_rate", "胜率", True),
        ("max_drawdown_duration_days", "回撤天数", False),
        ("total_value", "终值", True),
    ]

    for key, label, higher_better in items:
        va = sa[key]
        vb = sb[key]
        if isinstance(va, float) and isinstance(vb, float):
            diff = va - vb
            if higher_better:
                better = "A" if diff > 0 else ("B" if diff < 0 else "-")
            else:
                better = "A" if diff < 0 else ("B" if diff > 0 else "-")
            print("{0:>25s}  {1:>12.4f}  {2:>12.4f}  {3:>+12.4f}  {4:s}".format(
                label, va, vb, diff, better))

    tdiff = len(ta) - len(tb)
    print("{0:>25s}  {1:>12d}  {2:>12d}  {3:>+12d}  {4:s}".format(
        "交易次数", len(ta), len(tb), tdiff, "A" if len(ta) < len(tb) else "B"))

    print()
    print("--- 方向A (ETF动量轮动) 明细 ---")
    print("  总收益率:       {0:.2f}%".format(sa["total_returns"] * 100))
    print("  年化收益率:     {0:.2f}%".format(sa["annualized_returns"] * 100))
    print("  夏普比率:       {0:.4f}".format(sa["sharpe"]))
    print("  索提诺比率:     {0:.4f}".format(sa["sortino"]))
    print("  波动率:         {0:.4f}".format(sa["volatility"]))
    print("  最大回撤:       {0:.2f}%".format(sa["max_drawdown"] * 100))
    print("  回撤持续天数:   {0:d}天".format(sa["max_drawdown_duration_days"]))
    print("  胜率:           {0:.2f}%".format(sa["win_rate"] * 100))
    print("  交易次数:       {0:d}".format(len(ta)))
    print("  终值:           {0:.2f}".format(sa["total_value"]))
    print("  净收益:         {0:.2f}".format(sa["total_value"] - 1000000))

    print()
    print("--- 方向B (概念动量轮动) 明细 ---")
    print("  总收益率:       {0:.2f}%".format(sb["total_returns"] * 100))
    print("  年化收益率:     {0:.2f}%".format(sb["annualized_returns"] * 100))
    print("  夏普比率:       {0:.4f}".format(sb["sharpe"]))
    print("  索提诺比率:     {0:.4f}".format(sb["sortino"]))
    print("  波动率:         {0:.4f}".format(sb["volatility"]))
    print("  最大回撤:       {0:.2f}%".format(sb["max_drawdown"] * 100))
    print("  回撤持续天数:   {0:d}天".format(sb["max_drawdown_duration_days"]))
    print("  胜率:           {0:.2f}%".format(sb["win_rate"] * 100))
    print("  交易次数:       {0:d}".format(len(tb)))
    print("  终值:           {0:.2f}".format(sb["total_value"]))
    print("  净收益:         {0:.2f}".format(sb["total_value"] - 1000000))

    print()
    print("--- 方向B 兜底检查 ---")
    if hasattr(tb, "columns") and "order_book_id" in tb.columns:
        fallback = tb[tb["order_book_id"] == "510050.XSHG"]
        print("  兜底到上证50ETF的交易次数: {0:d} / {1:d}".format(len(fallback), len(tb)))
        if len(fallback) > 0:
            fallback_dates = fallback["datetime"].tolist() if "datetime" in fallback.columns else []
            print("  (兜底交易日: {0:s})".format(", ".join(str(d)[:10] for d in fallback_dates[:15])))
    else:
        print("  无法检查兜底 (trades格式: {0:s})".format(str(type(tb))))

    print()
    print("--- 方向A ETF选择统计 (前10) ---")
    if hasattr(ta, "columns") and "order_book_id" in ta.columns:
        codes = ta["order_book_id"].value_counts()
        for code, cnt in codes.head(10).items():
            print("  {0:s}: {1:d}次".format(code, cnt))

    print()
    print("--- 方向B ETF选择统计 (前10) ---")
    if hasattr(tb, "columns") and "order_book_id" in tb.columns:
        codes = tb["order_book_id"].value_counts()
        for code, cnt in codes.head(10).items():
            print("  {0:s}: {1:d}次".format(code, cnt))

    print()
    print("=" * 65)
    print("  结论")
    print("=" * 65)
    a_wins = 0
    b_wins = 0
    for key, label, higher_better in items:
        va = sa[key]
        vb = sb[key]
        if isinstance(va, float) and isinstance(vb, float):
            diff = va - vb
            if higher_better:
                if diff > 0:
                    a_wins += 1
                elif diff < 0:
                    b_wins += 1
            else:
                if diff < 0:
                    a_wins += 1
                elif diff > 0:
                    b_wins += 1
    if len(ta) < len(tb):
        a_wins += 1
    elif len(tb) < len(ta):
        b_wins += 1

    print("  方向A获胜指标数: {0:d}/{1:d}".format(a_wins, len(items) + 1))
    print("  方向B获胜指标数: {0:d}/{1:d}".format(b_wins, len(items) + 1))

    net_a = sa["total_value"] - 1000000
    net_b = sb["total_value"] - 1000000
    print("  方向A净收益: {0:.0f}元".format(net_a))
    print("  方向B净收益: {0:.0f}元".format(net_b))
    if net_b > 0:
        print("  A比B多赚: {0:.0f}元 ({1:.1f}%)".format(net_a - net_b, (net_a/net_b - 1) * 100))

    if a_wins > b_wins:
        print()
        print("  >>> 方向A (ETF动量轮动) 整体表现更优 <<<")
    elif b_wins > a_wins:
        print()
        print("  >>> 方向B (概念动量轮动) 整体表现更优 <<<")
    else:
        print()
        print("  >>> 两者表现接近，需进一步分析 <<<")

if __name__ == "__main__":
    main()
