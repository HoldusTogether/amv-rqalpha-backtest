from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "strategy"))

from amv_rules import load_amv_daily  # noqa: E402


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


REASON_LABELS = {
    "amv_long_threshold": "AMV涨幅突破+3.5%",
    "amv_short_threshold": "AMV跌幅突破-3.0%",
    "amv_reduce_threshold": "AMV跌幅突破-2.0%",
    "amv_anchor_break": "跌破锚定低点",
    "roll_anchor": "多头延续·滚动锚点",
    "hold": "持仓中",
    "no_signal": "无信号",
}


def build_signals() -> list[dict]:
    log_path = ROOT / "reports" / "report" / "signal_log.json"
    if not log_path.exists():
        print(f"WARNING: signal_log.json not found at {log_path}")
        return []

    log = json.loads(log_path.read_text(encoding="utf-8"))

    amv = load_amv_daily(ROOT / "data" / "amv_daily.csv")
    amv_map = {}
    for _, row in amv.iterrows():
        d = _iso_date(row["date"])
        amv_map[d] = {
            "open": _safe_float(row["open"]),
            "high": _safe_float(row["high"]),
            "low": _safe_float(row["low"]),
            "close": _safe_float(row["close"]),
        }

    rows = []
    for entry in log:
        d = entry["date"]
        candle = amv_map.get(d, {})
        action = entry["action"]
        reason = entry["reason"]
        target_w = float(entry["target_weight"])
        current_etf = entry.get("current_etf")
        holding_etf = entry.get("holding_etf")

        if action == "LONG_SIGNAL":
            signal_label = "多头确认(+3.5%)"
        elif action == "SHORT_CLEAR":
            signal_label = "空头清仓(-3.0%)"
        elif action == "REDUCE":
            signal_label = "减仓(-2.0%)"
        elif action == "ANCHOR_BREAK_CLEAR":
            signal_label = "跌破锚点清仓"
        elif action == "HOLD_LONG":
            signal_label = "持有"
        else:
            signal_label = "等待"

        was_holding = current_etf is not None
        is_new_entry = action == "LONG_SIGNAL" and not was_holding
        if action == "LONG_SIGNAL" and is_new_entry:
            trade_action = "买入"
        elif action in {"SHORT_CLEAR", "ANCHOR_BREAK_CLEAR"} and was_holding:
            trade_action = "清仓"
        elif action == "REDUCE" and was_holding:
            trade_action = "减仓"
        elif holding_etf is not None:
            trade_action = "持有"
        else:
            trade_action = "等待"

        if target_w >= 0.99:
            position_status = "满仓"
        elif target_w > 0:
            position_status = "半仓"
        else:
            position_status = "空仓"

        rows.append({
            "date": d,
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "pct_change": _safe_float(entry.get("pct_change")),
            "action": action,
            "signal_label": signal_label,
            "trade_action": trade_action,
            "regime": entry.get("regime", ""),
            "position_status": position_status,
            "target_weight": target_w,
            "holding_etf": holding_etf,
            "selected_etf": entry.get("selected_etf"),
            "selected_concept": entry.get("selected_concept"),
            "selected_momentum": _safe_float(entry.get("selected_momentum"), None),
            "anchor_low": entry.get("anchor_low"),
            "reason": reason,
            "reason_label": REASON_LABELS.get(reason, reason),
        })
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
