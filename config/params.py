"""Strategy parameters - single source of truth."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyParams:
    """Central strategy parameters."""
    # AMV threshold parameters (matching amv_band_strategy.py actual values)
    long_threshold: float = 0.035
    reduce_threshold: float = -0.02
    short_threshold: float = -0.03
    long_weight: float = 1.0
    reduce_weight: float = 0.5
    roll_anchor_on_new_long_signal: bool = True

    # Risk parameters
    stop_loss_pct: float = 0.08
    max_hold_days: int = 60
    take_profit_pct: float = 0.0

    # Momentum parameters
    momentum_window: int = 5
    top_n: int = 3
    diversity_strength: float = 0.5

    def to_band_params_dict(self) -> dict[str, Any]:
        """Return dict for BandParams constructor."""
        return {
            "long_threshold": self.long_threshold,
            "reduce_threshold": self.reduce_threshold,
            "short_threshold": self.short_threshold,
            "long_weight": self.long_weight,
            "reduce_weight": self.reduce_weight,
            "roll_anchor_on_new_long_signal": self.roll_anchor_on_new_long_signal,
        }

    def to_risk_params_dict(self) -> dict[str, Any]:
        """Return dict for RiskParams constructor."""
        return {
            "stop_loss_pct": self.stop_loss_pct,
            "max_hold_days": self.max_hold_days,
            "take_profit_pct": self.take_profit_pct,
        }
