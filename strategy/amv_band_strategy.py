"""
AMV择时 + ETF概念行业轮动（主策略）

开仓条件：AMV单日涨幅 >= 3.5% 且收阳
减仓条件：AMV单日跌幅 >= 2%（半仓）
清仓条件：AMV单日跌幅 >= 3%
选标方式：概念行业轮动——计算每个概念过去N日涨幅，选最强概念映射ETF
数据来源：concept_daily_returns.csv（TDX .day文件，真实概念价格数据）
"""
from __future__ import annotations

import sys
from pathlib import Path

import atexit
import json

import pandas as pd
from rqalpha.apis import *

PROJECT_ROOT = Path.cwd()
sys.path.append(str(PROJECT_ROOT / "strategy"))

from amv_rules import (
    BandParams,
    RiskParams,
    check_stop_loss,
    decide_action,
    get_amv_row,
    initial_state,
    load_amv_daily,
    load_etf_candidates,
)
from momentum_selectors import (
    load_concept_daily,
    load_concept_etf_map,
    load_etf_daily,
    select_etf_by_concept_momentum,
)

MOMENTUM_WINDOW = 5  # 动量窗口，可选 1（单日）或 5（5日累计）


def init(context):
    strategy_file = Path(context.config.base.strategy_file).resolve()
    context.project_root = strategy_file.parent.parent
    context.data_dir = context.project_root / "data"
    context.params = BandParams(
        long_threshold=0.035,
        reduce_threshold=-0.02,
        short_threshold=-0.03,
        long_weight=1.0,
        reduce_weight=0.5,
    )
    context.risk_params = RiskParams(
        stop_loss_pct=0.08,
        max_hold_days=60,
        take_profit_pct=0.0,
    )
    context.amv_daily = load_amv_daily(context.data_dir / "amv_daily.csv")
    context.etf_daily = load_etf_daily(context.data_dir / "etf_flow.csv")
    context.concept_daily = load_concept_daily(context.data_dir / "concept_daily_returns.csv")
    context.concept_map = load_concept_etf_map(context.data_dir / "concept_etf_map.csv")
    context.all_etfs = load_etf_candidates(context.data_dir / "etf_flow.csv")
    context.band_state = initial_state()
    context._signal_log = []
    atexit.register(_save_signal_log, str(context.project_root / "reports" / "report" / "signal_log.json"), context._signal_log)
    logger.info(
        f"[ETF动量] AMV={len(context.amv_daily)}, "
        f"ETF={len(context.etf_daily)}, "
        f"concepts={len(context.concept_map)}, "
        f"candidates={len(context.all_etfs)}, "
        f"window={MOMENTUM_WINDOW}"
    )


def handle_bar(context, bar_dict):
    trade_date = pd.Timestamp(context.now).normalize()
    amv_row = get_amv_row(context.amv_daily, trade_date)
    if amv_row is None:
        return

    decision = decide_action(amv_row, context.band_state, context.params)
    action = decision["action"]
    target_weight = float(decision["target_weight"])
    current_etf = context.band_state.get("current_etf")
    chosen = None

    try:
        # --- 持仓时间检查：超过最大持有天数则强制清仓 ---
        if current_etf and context.band_state.get("entry_date") is not None:
            held_days = (trade_date - context.band_state["entry_date"]).days
            if held_days > context.risk_params.max_hold_days:
                _clear_all(context)
                context.band_state["current_etf"] = None
                _reset_entry(context.band_state)
                logger.info(f"{trade_date.date()} MAX_HOLD({held_days}d) clear {current_etf}")
                return

        # --- ETF级别止损 ---
        if current_etf and action in {"HOLD_LONG", "REDUCE", "WAIT"}:
            try:
                pos = get_position(current_etf)
                if pos.quantity > 0 and pos.pnl_ratio < -context.risk_params.stop_loss_pct:
                    _clear_all(context)
                    context.band_state["current_etf"] = None
                    _reset_entry(context.band_state)
                    logger.info(f"{trade_date.date()} STOP_LOSS({pos.pnl_ratio:.2%}) {current_etf}")
                    return
            except Exception:
                pass

        # --- 执行AMV信号 ---
        if action == "LONG_SIGNAL":
            if current_etf is not None:
                logger.info(f"{trade_date.date()} LONG_SIGNAL but already holding {current_etf}; skip")
                return

            # 概念行业轮动选标（带去集中化）
            avoid = set(context.band_state.get("recent_etfs", []))
            chosen = select_etf_by_concept_momentum(
                context.concept_daily, context.concept_map, trade_date,
                window=MOMENTUM_WINDOW, avoid_etfs=avoid, top_n=3, diversity_strength=0.5,
            )
            target_etf = chosen["order_book_id"]
            target_concept = chosen.get("concept", "")

            # 验证ETF在当日是否可交易
            if not _etf_is_tradable(context, target_etf, trade_date):
                logger.warning(f"{trade_date.date()} {target_etf} not tradable; skip signal")
                return

            context.band_state["current_etf"] = target_etf
            _rebalance_single_etf(context, target_etf, target_weight)
            # 记录入场日期和持仓历史
            context.band_state["entry_date"] = trade_date
            recent = list(context.band_state.get("recent_etfs", []))
            if target_etf not in recent:
                recent.append(target_etf)
                if len(recent) > 5:
                    recent.pop(0)
            context.band_state["recent_etfs"] = recent
            logger.info(
                f"{trade_date.date()} LONG_SIGNAL pct={amv_row['pct_change']:.4f} "
                f"mom={chosen['momentum']:.4f} etf={target_etf} "
                f"concept={target_concept} weight={target_weight:.2f}"
            )
            return

        if action in {"SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"}:
            if current_etf is None:
                return
            _clear_all(context)
            context.band_state["current_etf"] = None
            _reset_entry(context.band_state)
            logger.info(f"{trade_date.date()} {action} pct={amv_row['pct_change']:.4f}")
            return

        if action == "REDUCE":
            if current_etf:
                _rebalance_single_etf(context, current_etf, target_weight)
            logger.info(f"{trade_date.date()} REDUCE pct={amv_row['pct_change']:.4f} weight={target_weight:.2f}")
            return

        logger.info(f"{trade_date.date()} {action} pct={amv_row['pct_change']:.4f}")
    finally:
        context._signal_log.append({
            "date": str(trade_date.date()),
            "pct_change": float(amv_row["pct_change"]),
            "action": action,
            "reason": decision["reason"],
            "target_weight": target_weight,
            "regime": context.band_state.get("regime", ""),
            "current_etf": current_etf,
            "holding_etf": context.band_state.get("current_etf"),
            "selected_etf": chosen["order_book_id"] if chosen else None,
            "selected_concept": chosen.get("concept") if chosen else None,
            "selected_momentum": chosen.get("momentum") if chosen else None,
            "anchor_low": context.band_state.get("anchor_low"),
            "entry_date": str(context.band_state.get("entry_date").date()) if context.band_state.get("entry_date") is not None else None,
        })


def _etf_is_tradable(context, etf: str, trade_date: pd.Timestamp) -> bool:
    """检查ETF在指定日期是否有行情数据（即可交易）。"""
    trade_date = pd.Timestamp(trade_date).normalize()
    try:
        mask = (context.etf_daily["order_book_id"] == etf) & (context.etf_daily["date"] == trade_date)
        row = context.etf_daily[mask]
        if row.empty:
            return False
        return pd.notna(row.iloc[0].get("close"))
    except Exception:
        return False


def _reset_entry(state: dict) -> None:
    state.update({
        "entry_price": None,
        "entry_date": None,
    })


def _rebalance_single_etf(context, target_etf, target_weight):
    for oid in context.all_etfs:
        try:
            if oid != target_etf and get_position(oid).quantity > 0:
                order_target_percent(oid, 0)
        except Exception:
            pass
    try:
        order_target_percent(target_etf, target_weight)
    except Exception:
        logger.warning(f"{pd.Timestamp(context.now).date()} cannot trade {target_etf}; skip")


def _clear_all(context):
    for oid in context.all_etfs:
        try:
            if get_position(oid).quantity > 0:
                order_target_percent(oid, 0)
        except Exception:
            pass


def _save_signal_log(path: str, log: list) -> None:
    if not log:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(log, ensure_ascii=False, default=str), encoding="utf-8")


__config__ = {
    "base": {
        "start_date": "2021-08-02",
        "end_date": "2026-06-01",
        "frequency": "1d",
        "matching_type": "current_bar",
        "benchmark": None,
        "accounts": {"stock": 1000000},
    },
    "extra": {"log_level": "info"},
    "mod": {
        "sys_analyser": {
            "enabled": True,
            "output_file": str(PROJECT_ROOT / "reports" / "result.pkl"),
            "report_save_path": str(PROJECT_ROOT / "reports" / "report"),
        }
    },
}
