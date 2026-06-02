from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BandParams:
    long_threshold: float = 0.04
    reduce_threshold: float = -0.015
    short_threshold: float = -0.023
    long_weight: float = 1.0
    reduce_weight: float = 0.5
    roll_anchor_on_new_long_signal: bool = True


@dataclass(frozen=True)
class RiskParams:
    stop_loss_pct: float = 0.08
    max_hold_days: int = 60
    take_profit_pct: float = 0.0


def _as_date_index(frame: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    if date_col not in frame.columns:
        raise ValueError(f"missing required column: {date_col}")
    result = frame.copy()
    result[date_col] = pd.to_datetime(result[date_col]).dt.normalize()
    result = result.sort_values(date_col).set_index(date_col, drop=False)
    return result


def _normalize_pct(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    # AMV pct_change is decimal (0.05=5%), just clip extreme artifacts
    values = values.clip(-0.30, 0.30)
    return values


def load_amv_daily(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"amv_daily.csv missing columns: {sorted(missing)}")

    frame = _as_date_index(frame)
    for col in ["open", "high", "low", "close"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    if "pct_change" in frame.columns:
        frame["pct_change"] = _normalize_pct(frame["pct_change"])
    else:
        frame["pct_change"] = frame["close"].pct_change()

    frame["is_bullish"] = frame["close"] > frame["open"]
    return frame


def get_amv_row(amv_daily: pd.DataFrame, trade_date: pd.Timestamp) -> pd.Series | None:
    trade_date = pd.Timestamp(trade_date).normalize()
    if trade_date not in amv_daily.index:
        return None
    row = amv_daily.loc[trade_date]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    return row


def load_etf_candidates(path: str | Path) -> list[str]:
    """Load list of candidate ETF order_book_ids from etf_flow CSV."""
    df = pd.read_csv(path)
    return sorted(df["order_book_id"].dropna().unique().tolist())


def initial_state() -> dict[str, Any]:
    return {
        "regime": "NEUTRAL",
        "anchor_date": None,
        "anchor_low": None,
        "current_etf": None,
        "target_weight": 0.0,
        "last_action": None,
        "entry_price": None,
        "entry_date": None,
        "recent_etfs": [],
    }


def check_stop_loss(
    current_price: float,
    state: dict[str, Any],
    params: RiskParams = RiskParams(),
) -> dict[str, Any]:
    entry_price = state.get("entry_price")
    entry_date = state.get("entry_date")
    if entry_price is None or current_price <= 0:
        return {"triggered": False}

    if params.take_profit_pct > 0 and current_price >= entry_price * (1 + params.take_profit_pct):
        state.update({"target_weight": 0.0, "last_action": "STOP_LOSS"})
        return {"triggered": True, "reason": "take_profit"}

    if current_price <= entry_price * (1 - params.stop_loss_pct):
        state.update({"target_weight": 0.0, "last_action": "STOP_LOSS"})
        return {"triggered": True, "reason": "stop_loss"}

    return {"triggered": False}


def decide_action(
    amv_row: pd.Series,
    state: dict[str, Any],
    params: BandParams = BandParams(),
) -> dict[str, Any]:
    pct = float(amv_row["pct_change"])
    low = float(amv_row["low"])
    is_bullish = bool(amv_row["is_bullish"])
    trade_date = pd.Timestamp(amv_row["date"]).normalize()

    anchor_low = state.get("anchor_low")
    has_position = bool(state.get("current_etf")) and float(state.get("target_weight", 0.0)) > 0

    if pct <= params.short_threshold:
        state.update(
            {
                "regime": "SHORT",
                "anchor_date": None,
                "anchor_low": None,
                "target_weight": 0.0,
                "last_action": "SHORT_CLEAR",
            }
        )
        return {"action": "SHORT_CLEAR", "target_weight": 0.0, "reason": "amv_short_threshold"}

    if has_position and anchor_low is not None and low < float(anchor_low):
        state.update(
            {
                "regime": "NEUTRAL",
                "anchor_date": None,
                "anchor_low": None,
                "target_weight": 0.0,
                "last_action": "ANCHOR_BREAK_CLEAR",
            }
        )
        return {"action": "ANCHOR_BREAK_CLEAR", "target_weight": 0.0, "reason": "amv_anchor_break"}

    is_long_signal = pct >= params.long_threshold and is_bullish
    if is_long_signal and state.get("regime") != "LONG":
        state.update(
            {
                "regime": "LONG",
                "anchor_date": trade_date,
                "anchor_low": low,
                "target_weight": params.long_weight,
                "last_action": "LONG_SIGNAL",
            }
        )
        return {"action": "LONG_SIGNAL", "target_weight": params.long_weight, "reason": "amv_long_threshold"}

    if is_long_signal and state.get("regime") == "LONG" and params.roll_anchor_on_new_long_signal:
        state.update(
            {
                "anchor_date": trade_date,
                "anchor_low": low,
            }
        )
        return {"action": "HOLD_LONG", "target_weight": state.get("target_weight", params.long_weight), "reason": "roll_anchor"}

    if pct <= params.reduce_threshold and has_position:
        current_w = state.get("target_weight", params.long_weight)
        reduced_w = current_w * params.reduce_weight
        state.update({"target_weight": reduced_w, "last_action": "REDUCE"})
        return {"action": "REDUCE", "target_weight": reduced_w, "reason": "amv_reduce_threshold"}

    if has_position:
        return {"action": "HOLD_LONG", "target_weight": state.get("target_weight", params.long_weight), "reason": "hold"}

    return {"action": "WAIT", "target_weight": 0.0, "reason": "no_signal"}
