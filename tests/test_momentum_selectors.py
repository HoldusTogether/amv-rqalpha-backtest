"""Unit tests for strategy/momentum_selectors."""
from __future__ import annotations

import random
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategy.momentum_selectors import (
    _pick_weighted_top_n,
    build_etf_concept_map,
    load_concept_etf_map,
    select_etf_by_concept_momentum,
    select_etf_by_momentum,
)

# ---------------------------------------------------------------------------
# Helpers to build test DataFrames
# ---------------------------------------------------------------------------


def _make_etf_daily(closes_by_oid: dict[str, list[float]], days=None) -> pd.DataFrame:
    """Build an etf_daily DataFrame from {oid: [close, ...]} dict.

    If *days* is provided it must be the same length as each value list.
    Otherwise dates are auto-generated (one row per entry, consecutive days).
    """
    rows = []
    for oid, closes in closes_by_oid.items():
        if days is None:
            days = pd.date_range("2024-01-01", periods=len(closes), freq="D")
        for i, c in enumerate(closes):
            rows.append({"order_book_id": oid, "date": days[i], "close": c})
    return pd.DataFrame(rows)


def _make_concept_daily(closes_by_concept: dict[str, list[float]], days=None) -> pd.DataFrame:
    """Build a concept_daily DataFrame from {concept: [close, ...]} dict."""
    rows = []
    for concept, closes in closes_by_concept.items():
        if days is None:
            days = pd.date_range("2024-01-01", periods=len(closes), freq="D")
        for i, c in enumerate(closes):
            rows.append({"concept": concept, "date": days[i], "close": c})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# select_etf_by_momentum
# ---------------------------------------------------------------------------


class TestSelectEtfByMomentum:
    def test_selects_highest_momentum_window_5(self):
        """ETF_A rises 10% over 5 days, ETF_B only 2% -> pick ETF_A."""
        # 5 trading days needed; window=2 gives us enough data in 10 rows
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        df = _make_etf_daily(
            {
                "512680.XSHG": [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
                "512480.XSHG": [100, 100.2, 100.4, 100.6, 100.8, 101, 101.2, 101.4, 101.6, 101.8],
            },
            days=days,
        )
        result = select_etf_by_momentum(df, days[-1], window=5)
        assert result["order_book_id"] == "512680.XSHG"
        # After cutoff filter (last_date - 10 days), each ETF has 5 rows.
        # iloc[-5] picks the first of those 5 rows (value=110).
        # momentum = 118/110 - 1 = 0.072727...
        assert result["momentum"] > 0.07

    def test_selects_highest_momentum_window_1(self):
        """window=1 uses single-day return (close[-1]/close[-2] - 1)."""
        days = pd.date_range("2024-01-01", periods=5, freq="B")
        df = _make_etf_daily(
            {
                "512680.XSHG": [100, 100, 100, 101, 101],  # last-day return = 0%
                "512480.XSHG": [100, 100, 100, 100, 105],  # last-day return = 5%
            },
            days=days,
        )
        result = select_etf_by_momentum(df, days[-1], window=1)
        assert result["order_book_id"] == "512480.XSHG"

    def test_fallback_when_no_data(self):
        """Empty DataFrame returns default fallback (510050.XSHG)."""
        df = pd.DataFrame(columns=["order_book_id", "date", "close"])
        result = select_etf_by_momentum(df, pd.Timestamp("2024-01-15"), window=5)
        assert result["order_book_id"] == "510050.XSHG"
        assert result["momentum"] == 0.0
        assert result["etf_name"] == "上证50ETF"

    def test_fallback_when_not_enough_history(self):
        """Each ETF has only 1 row (< window=5) -> fallback."""
        df = _make_etf_daily({"512680.XSHG": [100]})
        result = select_etf_by_momentum(df, pd.Timestamp("2024-01-15"), window=5)
        assert result["order_book_id"] == "510050.XSHG"

    def test_negative_momentum_picks_least_negative(self):
        """All ETFs decline; should pick the one that declined the least."""
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        df = _make_etf_daily(
            {
                "512680.XSHG": list(range(100, 80, -2)),   # drops 20%
                "512480.XSHG": list(range(100, 90, -1)),   # drops 10%
            },
            days=days,
        )
        result = select_etf_by_momentum(df, days[-1], window=5)
        assert result["order_book_id"] == "512480.XSHG"

    def test_returns_etf_name_when_present(self):
        """If the DataFrame has an etf_name column it should be returned."""
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        df = _make_etf_daily(
            {
                "512680.XSHG": [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
            },
            days=days,
        )
        df["etf_name"] = "人工智能ETF"
        result = select_etf_by_momentum(df, days[-1], window=5)
        assert result["etf_name"] == "人工智能ETF"

    def test_trade_date_filtering(self):
        """Only data up to trade_date is considered."""
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        # ETF_B is flat until day 9, then skyrockets on day 10
        df = _make_etf_daily(
            {
                "512680.XSHG": [100] * 10,  # flat
                "512480.XSHG": [100, 102, 104, 106, 108, 110, 112, 114, 116, 200],
            },
            days=days,
        )
        # Query at day 8 -> ETF_B hasn't surged yet
        result = select_etf_by_momentum(df, days[7], window=5)
        # At day 8, ETF_B close history: 100,102,104,106,108  -> mom = 108/100-1 = 0.08
        # ETF_A is flat -> mom = 0
        assert result["order_book_id"] == "512480.XSHG"


# ---------------------------------------------------------------------------
# select_etf_by_concept_momentum
# ---------------------------------------------------------------------------


class TestSelectEtfByConceptMomentum:
    @pytest.fixture
    def concept_map(self) -> dict:
        return {
            "AI概念": ("512680.XSHG", "人工智能ETF"),
            "半导体": ("512480.XSHG", "半导体ETF"),
            "新能源": ("159795.SZSE", "新能源车ETF"),
            "5G概念": ("159819.SZSE", "5G通信ETF"),
        }

    @pytest.fixture
    def days(self):
        return pd.date_range("2024-01-01", periods=10, freq="B")

    def test_selects_strongest_etf(self, concept_map, days):
        """AI概念 surges -> its ETF (512680) should win."""
        df = _make_concept_daily(
            {
                "AI概念": [100, 104, 108, 112, 116, 120, 124, 128, 132, 136],
                "半导体": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
                "新能源": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
                "5G概念": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
            },
            days=days,
        )
        result = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=5, top_n=3,
            rng=random.Random(42),
        )
        assert result["order_book_id"] == "512680.XSHG"
        assert result["concept"] == "AI概念"
        assert result["momentum"] > 0

    def test_aggregates_multiple_concepts_per_etf(self):
        """When two concepts map to the same ETF, their momenta are averaged."""
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        concept_map = {
            "AI概念": ("512680.XSHG", "人工智能ETF"),
            "云计算": ("512680.XSHG", "云计算ETF"),
            "5G概念": ("159819.SZSE", "5G通信ETF"),
        }
        # AI rises 20%, cloud rises 0%, 5G rises 10%
        df = _make_concept_daily(
            {
                "AI概念": [100] * 5 + [100, 105, 110, 115, 120],
                "云计算": [100] * 10,
                "5G概念": [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
            },
            days=days,
        )
        result = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=5, top_n=3,
            rng=random.Random(42),
        )
        # 512680 avg = (AI_mom + cloud_mom)/2, 5G only has 5G_mom
        # AI 5-day mom = 120/100 - 1 = 0.20, cloud = 0 -> avg = 0.10
        # 5G 5-day mom = 118/100 - 1 = 0.18
        # 5G should win with higher avg
        assert result["order_book_id"] == "159819.SZSE"

    def test_avoid_etfs_penalty(self, concept_map, days):
        """An ETF in avoid_etfs should be penalized and likely not selected."""
        # AI is strongest, but 512680 is in avoid_etfs
        df = _make_concept_daily(
            {
                "AI概念": [100, 104, 108, 112, 116, 120, 124, 128, 132, 136],
                "半导体": [100, 102, 104, 106, 108, 110, 112, 114, 116, 118],
                "新能源": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                "5G概念": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            },
            days=days,
        )
        # Without avoidance, AI (512680) should win — force with top_n=1
        result_free = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=5, top_n=1, rng=random.Random(0),
        )
        assert result_free["order_book_id"] == "512680.XSHG"

        # With full avoidance (strength=1.0), it should pick something else
        rng = random.Random(42)
        with patch("strategy.momentum_selectors._pick_weighted_top_n", wraps=_pick_weighted_top_n) as mock_fn:
            result_avoid = select_etf_by_concept_momentum(
                df, concept_map, days[-1], window=5,
                avoid_etfs={"512680.XSHG"}, diversity_strength=1.0, top_n=3,
            )
        # The heavily penalized 512680 should drop; 512480 (semiconductor) should win
        assert result_avoid["order_book_id"] != "512680.XSHG"

    def test_fallback_when_no_data(self, concept_map):
        """Empty concept_daily returns fallback to 5G概念 or default."""
        df = pd.DataFrame(columns=["date", "concept", "close", "return"])
        result = select_etf_by_concept_momentum(
            df, concept_map, pd.Timestamp("2024-01-15"), window=5,
        )
        # Falls back to 5G概念 mapping
        assert result["order_book_id"] == "159819.SZSE"
        assert result["momentum"] == 0.0
        assert result["concept"] == ""

    def test_fallback_when_no_matching_concepts(self):
        """Data exists but none of the concepts are in concept_map."""
        days = pd.date_range("2024-01-01", periods=10, freq="B")
        concept_map = {"AI概念": ("512680.XSHG", "人工智能ETF")}
        df = _make_concept_daily(
            {"未知概念": [100] * 10},  # not in concept_map
            days=days,
        )
        result = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=5,
        )
        # Falls back to 5G概念 (not in map) -> default 510050.XSHG
        assert result["order_book_id"] == "510050.XSHG"

    def test_fallback_when_not_enough_history(self, concept_map, days):
        """Each concept has only 1 row (< window=5) -> fallback."""
        df = _make_concept_daily({"AI概念": [100]})
        result = select_etf_by_concept_momentum(
            df, concept_map, pd.Timestamp("2024-01-15"), window=5,
        )
        assert result["order_book_id"] == "159819.SZSE"  # 5G概念 fallback

    def test_window_1_single_day(self, concept_map, days):
        """window=1 uses single-day return."""
        df = _make_concept_daily(
            {
                "AI概念": [100, 100, 100, 101, 101, 101, 101, 101, 101, 101],
                "半导体": [100, 100, 100, 100, 100, 100, 100, 100, 100, 105],
                "新能源": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
                "5G概念": [100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
            },
            days=days,
        )
        result = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=1, top_n=3,
            rng=random.Random(42),
        )
        assert result["order_book_id"] == "512480.XSHG"

    def test_returns_correct_fields(self, concept_map, days):
        """Result dict contains all expected keys."""
        df = _make_concept_daily(
            {
                "AI概念": [100] * 10,
                "半导体": [100] * 10,
                "新能源": [100] * 10,
                "5G概念": [100] * 10,
            },
            days=days,
        )
        result = select_etf_by_concept_momentum(
            df, concept_map, days[-1], window=5, top_n=3,
            rng=random.Random(42),
        )
        assert "order_book_id" in result
        assert "momentum" in result
        assert "max_momentum" in result
        assert "etf_name" in result
        assert "concept" in result


# ---------------------------------------------------------------------------
# _pick_weighted_top_n
# ---------------------------------------------------------------------------


class TestPickWeightedTopN:
    def test_empty_list_fallback(self):
        """Empty ranked list returns default fallback."""
        result = _pick_weighted_top_n([], top_n=3)
        assert result == ("510050.XSHG", "")

    def test_single_candidate(self):
        """Only one candidate -> always returns it."""
        ranked = [("512680.XSHG", 0.05, "AI概念")]
        result = _pick_weighted_top_n(ranked, top_n=3)
        assert result == ("512680.XSHG", "AI概念")

    def test_deterministic_with_seed(self):
        """Same RNG seed -> same selection."""
        ranked = [
            ("A", 0.10, "c1"),
            ("B", 0.05, "c2"),
            ("C", 0.02, "c3"),
        ]
        results = []
        for _ in range(10):
            rng = random.Random(12345)
            results.append(_pick_weighted_top_n(ranked, top_n=3, rng=rng))
        assert len(set(results)) == 1  # all identical

    def test_top_n_limits_candidates(self):
        """Only top_n candidates are considered."""
        ranked = [
            ("A", 0.10, "c1"),
            ("B", 0.09, "c2"),
            ("C", 0.08, "c3"),
            ("D", 0.01, "c4"),
        ]
        rng = random.Random(999)
        result = _pick_weighted_top_n(ranked, top_n=2, rng=rng)
        # Only A and B are candidates
        assert result[0] in ("A", "B")

    def test_negative_momentum_uses_min_weight(self):
        """Negative momentum gets minimum weight (0.01), not excluded."""
        ranked = [
            ("A", -0.05, "c1"),
            ("B", -0.03, "c2"),
        ]
        rng = random.Random(42)
        result = _pick_weighted_top_n(ranked, top_n=2, rng=rng)
        # Both get weight 0.01, so equal probability -> deterministic
        assert result[0] in ("A", "B")

    def test_highest_momentum_favored(self):
        """With very high weight difference, the strongest is selected almost always."""
        ranked = [
            ("A", 1.0, "c1"),   # very strong
            ("B", 0.001, "c2"),  # very weak
        ]
        hits = 0
        trials = 100
        for i in range(trials):
            rng = random.Random(i)
            result = _pick_weighted_top_n(ranked, top_n=2, rng=rng)
            if result[0] == "A":
                hits += 1
        # A should be selected in >95% of trials
        assert hits >= 95


# ---------------------------------------------------------------------------
# build_etf_concept_map
# ---------------------------------------------------------------------------


class TestBuildEtfConceptMap:
    def test_basic_reverse_mapping(self):
        """Simple concept->ETF map produces correct reverse map."""
        concept_map = {
            "AI概念": ("512680.XSHG", "人工智能ETF"),
            "半导体": ("512480.XSHG", "半导体ETF"),
        }
        result = build_etf_concept_map(concept_map)
        assert "512680.XSHG" in result
        assert "512480.XSHG" in result
        assert "AI概念" in result["512680.XSHG"]
        assert "半导体" in result["512480.XSHG"]

    def test_multiple_concepts_same_etf(self):
        """Two concepts mapping to one ETF -> that ETF has two concepts."""
        concept_map = {
            "AI概念": ("512680.XSHG", "人工智能ETF"),
            "云计算": ("512680.XSHG", "云计算ETF"),
            "半导体": ("512480.XSHG", "半导体ETF"),
        }
        result = build_etf_concept_map(concept_map)
        assert sorted(result["512680.XSHG"]) == sorted(["AI概念", "云计算"])
        assert result["512480.XSHG"] == ["半导体"]

    def test_empty_map(self):
        """Empty concept_map produces empty reverse map."""
        result = build_etf_concept_map({})
        assert result == {}


# ---------------------------------------------------------------------------
# load_concept_etf_map
# ---------------------------------------------------------------------------


class TestLoadConceptEtfMap:
    def test_loads_and_deduplicates_by_priority(self, tmp_path):
        """CSV with duplicate concepts keeps only the highest-priority one."""
        csv_path = tmp_path / "concept_etf_map.csv"
        csv_path.write_text(
            "concept,order_book_id,etf_name,priority\n"
            "AI概念,512680.XSHG,人工智能ETF,1\n"
            "AI概念,510770.XSHG,AI主题ETF,2\n"
            "半导体,512480.XSHG,半导体ETF,1\n",
            encoding="utf-8",
        )
        result = load_concept_etf_map(csv_path)
        assert result["AI概念"] == ("512680.XSHG", "人工智能ETF")
        assert result["半导体"] == ("512480.XSHG", "半导体ETF")

    def test_returns_dict_format(self, tmp_path):
        """Result is {concept: (order_book_id, etf_name)}."""
        csv_path = tmp_path / "concept_etf_map.csv"
        csv_path.write_text(
            "concept,order_book_id,etf_name,priority\n"
            "新能源,159795.SZSE,新能源车ETF,1\n",
            encoding="utf-8",
        )
        result = load_concept_etf_map(csv_path)
        assert isinstance(result, dict)
        assert isinstance(result["新能源"], tuple)
        assert len(result["新能源"]) == 2
