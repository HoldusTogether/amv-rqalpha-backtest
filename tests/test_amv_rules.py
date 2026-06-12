import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is on sys.path so `strategy.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.amv_rules import initial_state, decide_action, BandParams


def create_amv_row(
    pct_change: float,
    is_bullish: bool,
    low: float,
    date: str = "2024-01-15",
):
    return pd.Series(
        {
            "date": pd.Timestamp(date),
            "pct_change": pct_change,
            "is_bullish": is_bullish,
            "low": low,
            "open": 100.0,
            "high": 105.0,
            "close": 102.0 if is_bullish else 98.0,
        }
    )


# ---------------------------------------------------------------------------
# BandParams
# ---------------------------------------------------------------------------


class TestBandParams:
    def test_defaults(self):
        bp = BandParams()
        assert bp.long_threshold == 0.04
        assert bp.reduce_threshold == -0.015
        assert bp.short_threshold == -0.023
        assert bp.long_weight == 1.0
        assert bp.reduce_weight == 0.5
        assert bp.roll_anchor_on_new_long_signal is True

    def test_custom_values(self):
        bp = BandParams(long_threshold=0.05, reduce_weight=0.3)
        assert bp.long_threshold == 0.05
        assert bp.reduce_weight == 0.3
        # defaults still apply for unspecified fields
        assert bp.short_threshold == -0.023

    def test_frozen(self):
        bp = BandParams()
        with pytest.raises(Exception):
            bp.long_threshold = 0.06  # type: ignore


# ---------------------------------------------------------------------------
# initial_state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_returns_dict(self):
        state = initial_state()
        assert isinstance(state, dict)

    def test_default_values(self):
        state = initial_state()
        assert state["regime"] == "NEUTRAL"
        assert state["anchor_date"] is None
        assert state["anchor_low"] is None
        assert state["current_etf"] is None
        assert state["target_weight"] == 0.0
        assert state["last_action"] is None
        assert state["entry_price"] is None
        assert state["entry_date"] is None
        assert state["recent_etfs"] == []


# ---------------------------------------------------------------------------
# decide_action  --  LONG_SIGNAL
# ---------------------------------------------------------------------------


class TestDecideAction_LongSignal:
    def test_long_signal_from_neutral(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.05, is_bullish=True, low=100.0)
        result = decide_action(row, state)
        assert result["action"] == "LONG_SIGNAL"
        assert result["target_weight"] == 1.0
        assert result["reason"] == "amv_long_threshold"
        # state updates
        assert state["regime"] == "LONG"
        assert state["anchor_low"] == 100.0
        assert state["target_weight"] == 1.0

    def test_long_signal_exact_threshold(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.04, is_bullish=True, low=99.0)
        result = decide_action(row, state)
        assert result["action"] == "LONG_SIGNAL"

    def test_no_long_signal_below_threshold(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.03, is_bullish=True, low=100.0)
        result = decide_action(row, state)
        assert result["action"] == "WAIT"

    def test_no_long_signal_if_not_bullish(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.05, is_bullish=False, low=100.0)
        result = decide_action(row, state)
        assert result["action"] == "WAIT"

    def test_custom_long_weight(self):
        state = initial_state()
        params = BandParams(long_weight=0.8)
        row = create_amv_row(pct_change=0.05, is_bullish=True, low=100.0)
        result = decide_action(row, state, params)
        assert result["target_weight"] == 0.8


# ---------------------------------------------------------------------------
# decide_action  --  SHORT_CLEAR
# ---------------------------------------------------------------------------


class TestDecideAction_ShortClear:
    def test_short_clear_exact_threshold(self):
        state = initial_state()
        row = create_amv_row(pct_change=-0.023, is_bullish=False, low=95.0)
        result = decide_action(row, state)
        assert result["action"] == "SHORT_CLEAR"
        assert result["target_weight"] == 0.0
        assert result["reason"] == "amv_short_threshold"
        assert state["regime"] == "SHORT"
        assert state["anchor_low"] is None

    def test_short_clear_below_threshold(self):
        state = initial_state()
        row = create_amv_row(pct_change=-0.05, is_bullish=False, low=90.0)
        result = decide_action(row, state)
        assert result["action"] == "SHORT_CLEAR"

    def test_short_clear_overrides_long(self):
        """Even a bullish candle at short threshold fires SHORT_CLEAR."""
        state = initial_state()
        row = create_amv_row(pct_change=-0.03, is_bullish=True, low=95.0)
        result = decide_action(row, state)
        assert result["action"] == "SHORT_CLEAR"

    def test_short_clear_resets_position(self):
        """SHORT_CLEAR clears an existing long position."""
        state = initial_state()
        state.update(
            {
                "regime": "LONG",
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        row = create_amv_row(pct_change=-0.03, is_bullish=False, low=95.0)
        result = decide_action(row, state)
        assert result["action"] == "SHORT_CLEAR"
        assert state["target_weight"] == 0.0
        assert state["anchor_low"] is None


# ---------------------------------------------------------------------------
# decide_action  --  REDUCE
# ---------------------------------------------------------------------------


class TestDecideAction_Reduce:
    def test_reduce_with_position(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        # pct between short_threshold and reduce_threshold
        row = create_amv_row(pct_change=-0.02, is_bullish=False, low=101.0)
        result = decide_action(row, state)
        assert result["action"] == "REDUCE"
        assert result["target_weight"] == 0.5  # 1.0 * 0.5
        assert result["reason"] == "amv_reduce_threshold"

    def test_reduce_exact_threshold(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        row = create_amv_row(pct_change=-0.015, is_bullish=False, low=101.0)
        result = decide_action(row, state)
        assert result["action"] == "REDUCE"

    def test_no_reduce_without_position(self):
        state = initial_state()
        row = create_amv_row(pct_change=-0.02, is_bullish=False, low=101.0)
        result = decide_action(row, state)
        # SHORT_CLEAR triggers first (-0.02 <= -0.023? no, so falls through to WAIT)
        assert result["action"] == "WAIT"

    def test_reduce_with_custom_weight(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 0.8,
                "anchor_low": 100.0,
            }
        )
        params = BandParams(reduce_weight=0.3)
        row = create_amv_row(pct_change=-0.02, is_bullish=False, low=101.0)
        result = decide_action(row, state, params)
        assert result["target_weight"] == pytest.approx(0.8 * 0.3)


# ---------------------------------------------------------------------------
# decide_action  --  ANCHOR_BREAK_CLEAR
# ---------------------------------------------------------------------------


class TestDecideAction_AnchorBreak:
    def test_anchor_break_clears_position(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        row = create_amv_row(pct_change=0.01, is_bullish=True, low=99.0)
        result = decide_action(row, state)
        assert result["action"] == "ANCHOR_BREAK_CLEAR"
        assert result["target_weight"] == 0.0
        assert result["reason"] == "amv_anchor_break"
        assert state["target_weight"] == 0.0
        assert state["regime"] == "NEUTRAL"

    def test_no_anchor_break_without_position(self):
        state = initial_state()
        state["anchor_low"] = 100.0  # anchor set but no ETF held
        row = create_amv_row(pct_change=0.01, is_bullish=True, low=99.0)
        result = decide_action(row, state)
        assert result["action"] != "ANCHOR_BREAK_CLEAR"
        # should fall through to WAIT (no position, pct 0.01 < 0.04)

    def test_no_anchor_break_when_low_above(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        row = create_amv_row(pct_change=0.01, is_bullish=True, low=100.5)
        result = decide_action(row, state)
        assert result["action"] != "ANCHOR_BREAK_CLEAR"


# ---------------------------------------------------------------------------
# decide_action  --  HOLD_LONG
# ---------------------------------------------------------------------------


class TestDecideAction_HoldLong:
    def test_hold_when_in_position_no_signal(self):
        state = initial_state()
        state.update(
            {
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
            }
        )
        row = create_amv_row(pct_change=0.01, is_bullish=True, low=101.0)
        result = decide_action(row, state)
        assert result["action"] == "HOLD_LONG"
        assert result["target_weight"] == 1.0
        assert result["reason"] == "hold"

    def test_hold_long_roll_anchor(self):
        """Second LONG_SIGNAL while already LONG rolls the anchor."""
        state = initial_state()
        state.update(
            {
                "regime": "LONG",
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
                "anchor_date": pd.Timestamp("2024-01-10"),
            }
        )
        row = create_amv_row(
            pct_change=0.05,
            is_bullish=True,
            low=105.0,
            date="2024-01-15",
        )
        result = decide_action(row, state)
        assert result["action"] == "HOLD_LONG"
        assert result["reason"] == "roll_anchor"
        assert state["anchor_low"] == 105.0
        assert state["anchor_date"] == pd.Timestamp("2024-01-15")

    def test_hold_long_no_roll_when_disabled(self):
        params = BandParams(roll_anchor_on_new_long_signal=False)
        state = initial_state()
        state.update(
            {
                "regime": "LONG",
                "current_etf": "sh510300.xshg",
                "target_weight": 1.0,
                "anchor_low": 100.0,
                "anchor_date": pd.Timestamp("2024-01-10"),
            }
        )
        row = create_amv_row(
            pct_change=0.05,
            is_bullish=True,
            low=105.0,
            date="2024-01-15",
        )
        result = decide_action(row, state, params)
        # anchor should NOT roll; falls through to HOLD_LONG (hold)
        assert state["anchor_low"] == 100.0


# ---------------------------------------------------------------------------
# decide_action  --  WAIT
# ---------------------------------------------------------------------------


class TestDecideAction_Wait:
    def test_wait_no_position_no_signal(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.01, is_bullish=True, low=100.0)
        result = decide_action(row, state)
        assert result["action"] == "WAIT"
        assert result["target_weight"] == 0.0
        assert result["reason"] == "no_signal"

    def test_wait_near_zero(self):
        state = initial_state()
        row = create_amv_row(pct_change=0.0, is_bullish=True, low=100.0)
        result = decide_action(row, state)
        assert result["action"] == "WAIT"
