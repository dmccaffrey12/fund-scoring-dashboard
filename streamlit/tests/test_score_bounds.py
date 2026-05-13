"""
Regression tests for the 0-100 bound on 2025 fund scores.

Previously, ``score_funds`` multiplied the Passive system by
``PASSIVE_RESCALE = 1.111`` on top of an already-normalized weighted-average
percentile, so top-quartile Passive funds could land at scores >100
(observed max ~109 in production exports). This module pins the invariant
that both Passive and Active 2025 scores are in [0, 100].
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from scoring_engine import (  # noqa: E402
    ACTIVE_METRICS,
    CSV_COLUMNS,
    PASSIVE_METRICS,
    PASSIVE_RESCALE,
    score_funds,
)


FIXTURE_2025 = os.path.join(_HERE, "fixtures", "ycharts_2025_good.csv")


def _scored_fixture() -> pd.DataFrame:
    return score_funds(pd.read_csv(FIXTURE_2025))


def test_passive_rescale_is_one():
    """PASSIVE_RESCALE must be 1.0 — the available-weight denominator already
    normalizes the score to 0-100. Any other value reintroduces the >100 bug."""
    assert PASSIVE_RESCALE == 1.0


def test_all_2025_scores_bounded_0_to_100_on_fixture():
    """No fund in the bundled 2025 fixture should produce Score_Passive,
    Score_Active, or Score_Final outside the [0, 100] range."""
    scored = _scored_fixture()
    for col in ("Score_Passive", "Score_Active", "Score_Final"):
        s = scored[col].dropna()
        assert (s >= 0).all(), f"{col} has values < 0"
        assert (s <= 100).all(), f"{col} has values > 100 (max={s.max():.4f})"


def _synthetic_passive_category():
    """Two passive funds in the same category: one dominates on every
    lower-is-better metric and ties on the higher-is-better metrics. The
    dominator's Score_Passive must be <= 100."""
    # Both funds carry every metric. TOP is best on every metric, BOT is worst,
    # so TOP's within-category percentile is 1.0 on all 10 metrics and its
    # Score_Passive must be exactly 100.0. The "lower is better" metrics
    # (expense ratio, tracking error, downside, max drawdown) follow the
    # engine's literal convention: smaller numeric values are scored better.
    top = {
        "Symbol": "TOP", "Name": "Top Passive", "Index Fund": True,
        "Category Name": "Synthetic Passive Cat",
        "Net Expense Ratio": 0.0,
        "Tracking Error (vs Category) (3Y)": 0.0,
        "Tracking Error (vs Category) (5Y)": 0.0,
        "Tracking Error (vs Category) (10Y)": 0.0,
        "R-Squared (vs Category) (5Y)": 1.0,
        "Share Class Assets Under Management": 1e12,
        "Downside (vs Category) (5Y)": 0.5,
        "Downside (vs Category) (10Y)": 0.5,
        "Max Drawdown (5Y)": 0.1,
        "Max Drawdown (10Y)": 0.15,
    }
    bot = {
        "Symbol": "BOT", "Name": "Bottom Passive", "Index Fund": True,
        "Category Name": "Synthetic Passive Cat",
        "Net Expense Ratio": 1.0,
        "Tracking Error (vs Category) (3Y)": 5.0,
        "Tracking Error (vs Category) (5Y)": 5.0,
        "Tracking Error (vs Category) (10Y)": 5.0,
        "R-Squared (vs Category) (5Y)": 0.5,
        "Share Class Assets Under Management": 1e6,
        "Downside (vs Category) (5Y)": 1.5,
        "Downside (vs Category) (10Y)": 1.5,
        "Max Drawdown (5Y)": 0.5,
        "Max Drawdown (10Y)": 0.6,
    }
    return pd.DataFrame([top, bot])


def test_top_percentile_passive_fund_caps_at_100():
    """A passive fund that is the best (or tied-best) on every metric in its
    category should top out at Score_Passive == 100, not 111.1."""
    scored = score_funds(_synthetic_passive_category())
    top = scored[scored["Symbol"] == "TOP"].iloc[0]
    assert top["Fund_Type"] == "Passive"
    # The "higher is better" metrics tie (both at the same R-squared/AUM),
    # which gives both funds percentile 1.0 on those metrics. The
    # "lower is better" metrics put TOP at percentile 1.0. So TOP should be
    # exactly 100.
    assert top["Score_Passive"] == 100.0, (
        f"Top-percentile passive fund scored {top['Score_Passive']:.4f}; "
        "expected exactly 100 — Passive scores must not exceed 100."
    )
    assert top["Score_Final"] == top["Score_Passive"]


def test_score_active_unaffected_by_rescale_change():
    """Active scoring never used the rescale; this test pins that the active
    side still produces sensible bounded scores."""
    scored = _scored_fixture()
    active = scored[scored["Fund_Type"] == "Active"]["Score_Active"].dropna()
    assert not active.empty
    assert active.max() <= 100.0
    assert active.min() >= 0.0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
