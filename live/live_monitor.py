"""
AMV 实盘监控脚本

用法: python live/live_monitor.py [--force] [--no-push]
前置条件: data/*.csv 已是最新数据

参数:
  --force    忽略当日去重，强制重新运行
  --no-push  抑制内置的 Server酱 微信推送（仍会构造消息并打印
             "PUSH SUPPRESSED: <title>"）。用于上游脚本（如
             scripts/live_update_and_monitor.ps1）接管推送职责。

流程:
  1. 读取 state.json 恢复持仓状态
  2. 加载最新 AMV/概念/ETF 数据
  3. 运行 decide_action 判断信号
  4. 若有信号变化 → Server酱 推送到微信（除非 --no-push）
  5. 保存状态到 state.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "strategy"))

from amv_rules import (
    BandParams,
    decide_action,
    initial_state,
    load_amv_daily,
)
from momentum_selectors import (
    load_concept_daily,
    load_concept_etf_map,
    load_etf_daily,
    select_etf_by_concept_momentum,
)

from live.config import (
    DIVERSITY_STRENGTH,
    LONG_THRESHOLD,
    LONG_WEIGHT,
    MOMENTUM_WINDOW,
    PUSH_ON_NO_SIGNAL,
    REDUCE_THRESHOLD,
    REDUCE_WEIGHT,
    SERVERCHAN_SENDKEY,
    SHORT_THRESHOLD,
    TOP_N,
)

DATA_DIR = ROOT / "data"
LIVE_DIR = ROOT / "live"
STATE_FILE = LIVE_DIR / "state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state = initial_state()
        state.update(raw)
        return state
    return initial_state()


def save_state(state: dict) -> None:
    state["last_monitor_date"] = str(date.today())
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def push_notification(title: str, content: str) -> bool:
    if not SERVERCHAN_SENDKEY:
        print("[推送] 未配置 SERVERCHAN_SENDKEY，跳过推送")
        return False
    url = "https://sctapi.ftqq.com/{}.send".format(SERVERCHAN_SENDKEY)
    data = urllib.parse.urlencode({"title": title, "desp": content}).encode()
    try:
        resp = urllib.request.urlopen(url, data=data, timeout=15)
        result = json.loads(resp.read())
        if result.get("code") == 0:
            print("[推送] 成功: {}".format(title))
            return True
        else:
            print("[推送] API 返回错误: {}".format(result))
            return False
    except Exception as e:
        print("[推送] 失败: {}".format(e))
        return False


def fmt_pct(v: float) -> str:
    return "{:.2f}%".format(v * 100)


def build_msg(
    action: str,
    amv_row: pd.Series,
    chosen: dict | None,
    state: dict,
) -> tuple[str, str]:
    pct = float(amv_row["pct_change"])
    today_str = str(date.today())

    if action == "LONG_SIGNAL":
        eid = chosen["order_book_id"]
        ename = chosen.get("etf_name", eid)
        concept = chosen.get("concept", "")
        title = "【AMV策略】买入信号 📈"
        content = (
            "### 买入信号\n\n"
            "**日期：** {}\n"
            "**AMV涨幅：** {} {}\n"
            "**建议动作：** 买入 → 满仓(100%)\n"
            "**推荐标的：** {} {}\n"
            "**推荐概念：** {}\n"
            "**当前仓位：** 空仓 → 满仓"
        ).format(
            today_str,
            fmt_pct(pct),
            "(收阳✅)" if pct > 0 else "",
            eid, ename, concept,
        )
        return title, content

    if action == "REDUCE":
        eid = state.get("current_etf", "")
        ename = state.get("etf_name", eid)
        cur_w = state.get("target_weight", 1.0)
        title = "【AMV策略】减仓信号 ⚠️"
        content = (
            "### 减仓信号\n\n"
            "**日期：** {}\n"
            "**AMV跌幅：** {}\n"
            "**建议动作：** 减仓至 {:.0f}%\n"
            "**持仓标的：** {} {}\n"
            "**当前仓位：** {:.0f}% → {:.0f}%"
        ).format(today_str, fmt_pct(pct), cur_w * 100, eid, ename, cur_w * 100 / 0.5, cur_w * 100)
        return title, content

    if action in ("SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"):
        eid = state.get("current_etf", "")
        ename = state.get("etf_name", eid)
        entry = state.get("entry_date")
        held_str = ""
        if entry:
            try:
                entry_d = pd.Timestamp(entry).date()
                held = (date.today() - entry_d).days
                held_str = "（持有 {} 天）".format(held)
            except Exception:
                pass
        reason = "跌破-3.0%空头清仓" if action == "SHORT_CLEAR" else "跌破锚点清仓"
        title = "【AMV策略】清仓信号 🔴"
        content = (
            "### 清仓信号\n\n"
            "**日期：** {}\n"
            "**AMV跌幅：** {}\n"
            "**清仓标的：** {} {} {}\n"
            "**原因：** {}\n"
            "**建议动作：** 全部卖出"
        ).format(today_str, fmt_pct(pct), eid, ename, held_str, reason)
        return title, content

    title = "【AMV策略】今日无交易信号"
    if state.get("current_etf"):
        eid = state["current_etf"]
        ename = state.get("etf_name", eid)
        w = state.get("target_weight", 0)
        content = (
            "**日期：** {}\n"
            "**AMV：** {}\n"
            "**持仓：** {} {} ({:.0f}%)\n"
            "**动作：** 继续持有"
        ).format(today_str, fmt_pct(pct), eid, ename, w * 100)
    else:
        content = (
            "**日期：** {}\n"
            "**AMV：** {}\n"
            "**持仓：** 空仓\n"
            "**动作：** 继续等待"
        ).format(today_str, fmt_pct(pct))
    return title, content


def main() -> int:
    parser = argparse.ArgumentParser(description="AMV 实盘监控")
    parser.add_argument(
        "--force", action="store_true",
        help="忽略去重，强制重新运行",
    )
    parser.add_argument(
        "--no-push", action="store_true",
        help="抑制内置微信推送（仍构造消息并打印 PUSH SUPPRESSED）",
    )
    args = parser.parse_args()

    today = date.today()
    print("=== AMV 实盘监控 {} ===".format(today))

    # ── 加载状态 ──
    state = load_state()
    prev_action = state.get("last_action", "WAIT")

    # 去重
    last_date = state.get("last_monitor_date")
    if not args.force and last_date and last_date == str(today):
        print("今日 {} 已运行过，跳过（使用 --force 重新运行）".format(today))
        return 0

    # ── 加载数据 ──
    print("加载 AMV 数据...")
    amv = load_amv_daily(str(DATA_DIR / "amv_daily.csv"))
    if amv.empty:
        print("ERROR: AMV 数据为空")
        return 1
    amv_row = amv.iloc[-1]
    amv_date = pd.Timestamp(amv_row["date"]).date()
    print("  最新 AMV 日期: {} (今天: {})".format(amv_date, today))
    if amv_date < today:
        print("  WARNING: AMV 数据尚未更新到今日")
    if not bool(amv_row.get("is_bullish", True)):
        print("  AMV 未收阳")

    print("加载概念数据...")
    concept_daily = load_concept_daily(str(DATA_DIR / "concept_daily_returns.csv"))
    concept_map = load_concept_etf_map(str(DATA_DIR / "concept_etf_map.csv"))
    print("  概念数: {}".format(len(concept_map)))

    print("加载 ETF 数据...")
    etf_daily = load_etf_daily(str(DATA_DIR / "etf_flow.csv"))
    unique_etfs = etf_daily["order_book_id"].nunique() if not etf_daily.empty else 0
    print("  ETF 数: {}".format(unique_etfs))

    # ── 构建 band_state ──
    band_state = initial_state()
    for k in ("regime", "anchor_low", "anchor_date", "target_weight", "last_action"):
        if k in state:
            band_state[k] = state[k]
    band_state["current_etf"] = state.get("current_etf")
    band_state["target_weight"] = state.get("target_weight", 0.0)

    params = BandParams(
        long_threshold=LONG_THRESHOLD,
        reduce_threshold=REDUCE_THRESHOLD,
        short_threshold=SHORT_THRESHOLD,
        long_weight=LONG_WEIGHT,
        reduce_weight=REDUCE_WEIGHT,
    )

    # ── 执行策略 ──
    decision = decide_action(amv_row, band_state, params)
    action = decision["action"]
    print("  信号: {}  权重: {:.2f}".format(action, float(decision["target_weight"])))

    chosen = None

    if action == "LONG_SIGNAL":
        if state.get("current_etf") is not None:
            print("  LONG_SIGNAL 但已有持仓 {}，忽略".format(state["current_etf"]))
            action = "HOLD_LONG"
        else:
            avoid = set(state.get("recent_etfs", []))
            trade_date = pd.Timestamp(amv_row["date"])
            chosen = select_etf_by_concept_momentum(
                concept_daily, concept_map, trade_date,
                window=MOMENTUM_WINDOW,
                avoid_etfs=avoid,
                top_n=TOP_N,
                diversity_strength=DIVERSITY_STRENGTH,
            )
            if chosen:
                state["current_etf"] = chosen["order_book_id"]
                state["etf_name"] = chosen.get("etf_name", "")
                state["entry_date"] = str(amv_date)
                state["target_weight"] = 1.0
                recent = list(state.get("recent_etfs", []))
                if chosen["order_book_id"] not in recent:
                    recent.append(chosen["order_book_id"])
                    if len(recent) > 5:
                        recent.pop(0)
                state["recent_etfs"] = recent
                print("  推荐 ETF: {} {} (概念: {}, 动量: {:.4f})".format(
                    chosen["order_book_id"],
                    chosen.get("etf_name", ""),
                    chosen.get("concept", ""),
                    chosen.get("momentum", 0),
                ))
            else:
                print("  WARNING: ETF 选择失败")
                action = "WAIT"

    elif action == "REDUCE":
        cur_w = state.get("target_weight", 1.0)
        new_w = band_state["target_weight"]
        state["target_weight"] = new_w
        print("  减仓: {:.0f}% → {:.0f}%".format(cur_w * 100, new_w * 100))

    elif action in ("SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"):
        print("  清仓: {}".format(state.get("current_etf", "")))
        state["current_etf"] = None
        state["etf_name"] = ""
        state["entry_date"] = None
        state["target_weight"] = 0.0

    # ── 回写 band_state 中的回测状态 ──
    state["regime"] = band_state.get("regime", state.get("regime", "INIT"))
    state["anchor_low"] = band_state.get("anchor_low")
    state["anchor_date"] = band_state.get("anchor_date")
    state["last_action"] = action

    # ── 推送 ──
    actionable = {"LONG_SIGNAL", "REDUCE", "SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"}
    is_actionable = action in actionable
    is_new_signal = action != prev_action
    should_push = (is_actionable and is_new_signal) or PUSH_ON_NO_SIGNAL

    if should_push:
        title, content = build_msg(action, amv_row, chosen, state)
        if args.no_push:
            print("PUSH SUPPRESSED: {}".format(title))
        else:
            print("推送: {}".format(title))
            push_notification(title, content)
    else:
        print("无变化 ({} → {})，不推送".format(prev_action, action))

    # ── 保存状态 ──
    save_state(state)
    print("=== 完成 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
