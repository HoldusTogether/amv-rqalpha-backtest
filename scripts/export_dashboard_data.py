from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "strategy"))

from amv_rules import (  # noqa: E402
    BandParams,
    decide_action,
    initial_state,
    load_amv_daily,
)
from momentum_selectors import (  # noqa: E402
    load_concept_daily,
    load_concept_etf_map,
    load_etf_daily,
    select_etf_by_concept_momentum,
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _safe_float(value, default=0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _iso_date(value) -> str:
    return pd.Timestamp(value).date().isoformat()


# ── 策略信号标签（含阈值） ──
SIGNAL_LABELS = {
    "LONG_SIGNAL": "多头确认(+4%)",
    "REDUCE": "减仓(-1.5%)",
    "SHORT_CLEAR": "空头清仓(-2.3%)",
    "ANCHOR_BREAK_CLEAR": "跌破锚点清仓",
    "HOLD_LONG": "持有",
    "WAIT": "等待",
}


REASON_LABELS = {
    "amv_long_threshold": "AMV涨幅突破+4%",
    "amv_short_threshold": "AMV跌幅突破-2.3%",
    "amv_reduce_threshold": "AMV跌幅突破-1.5%",
    "amv_anchor_break": "跌破锚定低点",
    "roll_anchor": "多头延续·滚动锚点",
    "hold": "持仓中",
    "no_signal": "无信号",
}


def _compute_trade_action(
    raw_action: str,
    was_holding: bool,
    is_new_entry: bool,
    prev_weight: float = 0.0,
    new_weight: float = 0.0,
) -> str:
    """根据信号+持仓状态推断实际交易动作"""
    if raw_action == "LONG_SIGNAL" and is_new_entry:
        return "买入"
    if raw_action in {"SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"} and was_holding:
        return "清仓"
    if raw_action == "REDUCE" and was_holding and new_weight != prev_weight:
        return "减仓"
    # 无实际交易
    if was_holding:
        return "持有"
    else:
        return "等待"


def _position_status_label(target_weight: float) -> str:
    if target_weight >= 0.99:
        return "满仓"
    elif target_weight > 0:
        return "半仓"
    return "空仓"


def build_signals() -> list[dict]:
    data_dir = ROOT / "data"
    amv = load_amv_daily(data_dir / "amv_daily.csv")
    concept_daily = load_concept_daily(data_dir / "concept_daily_returns.csv")
    concept_map = load_concept_etf_map(data_dir / "concept_etf_map.csv")

    state = initial_state()
    params = BandParams()
    rows: list[dict] = []

    for _, amv_row in amv.iterrows():
        # 记录处理此K线前的持仓状态
        prev_holding_etf = state.get("current_etf")
        prev_weight = state.get("target_weight", 0.0)
        was_holding = prev_holding_etf is not None and prev_weight > 0

        decision = decide_action(amv_row, state, params)
        chosen = None
        raw_action = decision["action"]
        is_new_entry = False

        # 处理选标/清仓
        # 每次AMV突破多头阈值都跑概念动量选标（无论是否已持仓）
        pct_signal = _safe_float(amv_row["pct_change"])
        is_bullish_signal = bool(amv_row["is_bullish"])
        if pct_signal >= 0.04 and is_bullish_signal:
            avoid = set(state.get("recent_etfs", []))
            chosen = select_etf_by_concept_momentum(
                concept_daily, concept_map, amv_row["date"],
                window=5, avoid_etfs=avoid, top_n=3, diversity_strength=0.5,
            )
            if state.get("current_etf") is None:
                target_etf = chosen["order_book_id"]
                state["current_etf"] = target_etf
                state["entry_date"] = amv_row["date"]
                recent = list(state.get("recent_etfs", []))
                if target_etf not in recent:
                    recent.append(target_etf)
                    if len(recent) > 5:
                        recent.pop(0)
                state["recent_etfs"] = recent
                is_new_entry = True

        if raw_action in {"SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"}:
            if was_holding:
                state["current_etf"] = None

        # 构建显示字段
        # ── 策略信号：基于 AMV 涨跌幅独立判断，不受持仓状态影响 ──
        pct_signal = _safe_float(amv_row["pct_change"])
        low_signal = _safe_float(amv_row["low"])
        is_bullish_signal = bool(amv_row["is_bullish"])
        anchor_low_signal = state.get("anchor_low")
        has_pos_signal = prev_holding_etf is not None and prev_weight > 0

        if pct_signal >= 0.04 and is_bullish_signal:
            signal_label = "多头确认(+4%)"
        elif pct_signal <= -0.023:
            signal_label = "空头清仓(-2.3%)"
        elif pct_signal <= -0.015 and has_pos_signal:
            signal_label = "减仓(-1.5%)"
        elif has_pos_signal and anchor_low_signal is not None and _safe_float(low_signal) < _safe_float(anchor_low_signal):
            signal_label = "跌破锚点清仓"
        elif has_pos_signal:
            signal_label = "持有"
        else:
            signal_label = "等待"

        # 选中标的：仅在多头确认信号时展示概念动量选出的标的
        # 持有/减仓/清仓/等待时均为空
        display_selected_etf = chosen["order_book_id"] if chosen is not None else None

        target_w = _safe_float(decision["target_weight"])
        rows.append(
            {
                "date": _iso_date(amv_row["date"]),
                "open": _safe_float(amv_row["open"]),
                "high": _safe_float(amv_row["high"]),
                "low": _safe_float(amv_row["low"]),
                "close": _safe_float(amv_row["close"]),
                "pct_change": _safe_float(amv_row["pct_change"]),
                # 策略信号（原始）
                "action": raw_action,
                # 策略信号标签（基于 AMV 阈值独立判断）
                "signal_label": signal_label,
                # 交易动作
                "trade_action": _compute_trade_action(raw_action, was_holding, is_new_entry, prev_weight, target_w),
                # 状态
                "regime": state["regime"],
                # 仓位信息
                "position_status": _position_status_label(target_w),
                "target_weight": _safe_float(target_w),
                "holding_etf": state.get("current_etf"),
                # 选标信息（多头确认时展示对应标的）
                "selected_etf": display_selected_etf,
                "selected_concept": chosen["concept"] if chosen else None,
                "selected_momentum": chosen["momentum"] if chosen else None,
                # 锚点
                "anchor_low": _safe_float(state.get("anchor_low"), None),
                # 原因（中文）
                "reason": decision["reason"],
                "reason_label": REASON_LABELS.get(decision["reason"], decision["reason"]),
            }
        )
    return rows


def build_portfolio() -> list[dict]:
    frame = _read_csv(ROOT / "reports" / "report" / "portfolio.csv")
    rows: list[dict] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "date": _iso_date(row["date"]),
                "cash": _safe_float(row.get("cash")),
                "total_value": _safe_float(row.get("total_value")),
                "market_value": _safe_float(row.get("market_value")),
                "unit_net_value": _safe_float(row.get("unit_net_value")),
            }
        )
    return rows


def build_trades() -> list[dict]:
    frame = _read_csv(ROOT / "reports" / "report" / "trades.csv")
    rows: list[dict] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "datetime": str(row.get("trading_datetime") or row.get("datetime")),
                "order_book_id": str(row.get("order_book_id", "")),
                "symbol": str(row.get("symbol", "")),
                "side": str(row.get("side", "")),
                "quantity": _safe_int(row.get("last_quantity")),
                "price": _safe_float(row.get("last_price")),
                "cost": _safe_float(row.get("transaction_cost")),
            }
        )
    return rows


def build_positions_weight() -> list[dict]:
    frame = _read_csv(ROOT / "reports" / "report" / "positions_weight.csv")
    if frame.empty:
        return []
    frame = frame.fillna(0)
    date_col = frame.columns[0]
    rows: list[dict] = []
    for _, row in frame.iterrows():
        weights = {}
        for col in frame.columns:
            if col == date_col:
                continue
            weights[col] = _safe_float(row[col])
        rows.append({"date": _iso_date(row[date_col]), "weights": weights})
    return rows


def build_summary(portfolio: list[dict], trades: list[dict], signals: list[dict]) -> dict:
    if not portfolio:
        return {}

    first = portfolio[0]
    last = portfolio[-1]
    start = first["date"]
    end = last["date"]
    total_return = (last["unit_net_value"] / first["unit_net_value"]) - 1 if first["unit_net_value"] else 0.0

    peak = -1
    max_drawdown = 0.0
    for row in portfolio:
        nav = float(row["unit_net_value"])
        peak = max(peak, nav)
        dd = nav / peak - 1
        max_drawdown = min(max_drawdown, dd)

    latest_signal = signals[-1] if signals else {}

    return {
        "start_date": start,
        "end_date": end,
        "total_return": _safe_float(total_return),
        "max_drawdown": _safe_float(max_drawdown),
        "ending_value": _safe_float(portfolio[-1]["total_value"]),
        "trades": len(trades),
        "latest_regime": latest_signal.get("regime", "NA"),
        "latest_action": latest_signal.get("action", "NA"),
        "latest_signal_label": latest_signal.get("signal_label", ""),
        "latest_trade_action": latest_signal.get("trade_action", ""),
        "latest_position_status": latest_signal.get("position_status", ""),
        "latest_etf": latest_signal.get("holding_etf") or "",
        "latest_reason_label": latest_signal.get("reason_label", ""),
    }


def main() -> int:
    portfolio = build_portfolio()
    # 限制信号数据到回测实际覆盖的日期范围
    min_date = portfolio[0]["date"] if portfolio else ""
    max_date = portfolio[-1]["date"] if portfolio else ""
    signals = build_signals()
    if min_date:
        signals = [s for s in signals if min_date <= s["date"] <= max_date]
    trades = build_trades()
    positions_weight = build_positions_weight()
    summary = build_summary(portfolio, trades, signals)

    out_dir = ROOT / "web" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "summary": summary,
        "signals": signals,
        "portfolio": portfolio,
        "trades": trades,
        "positions_weight": positions_weight,
    }
    out_path = out_dir / "dashboard.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"dashboard data exported: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
