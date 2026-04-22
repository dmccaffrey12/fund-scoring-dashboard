"""
Determinism / reproducibility regression tests.

Two archived runs built from the same inputs must produce byte-identical
dual-score tables and an empty month-over-month comparison (no score
movers, band changes, quadrant changes, or action-flag changes).

This guards against the class of bug where duplicate tickers,
unstable tie-break ordering, or non-deterministic percentile
computation leak spurious movement into the committee packet.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from dual_score_table import build_dual_score_table  # noqa: E402
from run_archive import create_run_archive, load_run  # noqa: E402
from run_comparison import compare_runs  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES = os.path.join(_HERE, "fixtures")
GOOD_2025 = os.path.join(_FIXTURES, "ycharts_2025_good.csv")
GOOD_2023 = os.path.join(_FIXTURES, "ycharts_2023_good.csv")


def _has_fixture_2023_scores() -> bool:
    """The sanitised 2023 fixture carries raw YCharts metrics but not the
    ``Score_2023`` pre-computed column; build_dual_score_table can still
    compute it on the fly. We only skip when the fixture files are missing."""
    return os.path.isfile(GOOD_2025) and os.path.isfile(GOOD_2023)


def _shuffled(path: str) -> pd.DataFrame:
    """Read a CSV and return a row-permuted copy (deterministic seed).

    Used to prove that output is invariant under input row ordering."""
    df = pd.read_csv(path)
    return df.sample(frac=1.0, random_state=17).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core invariants
# ---------------------------------------------------------------------------

def test_bundled_dual_table_is_deterministic_between_calls():
    """Two back-to-back calls on the same bundled inputs must produce an
    identical table — same rows, same column order, same values."""
    t1 = build_dual_score_table()
    t2 = build_dual_score_table()
    assert t1.equals(t2)
    # And the CSV serialisation must be byte-identical (archive parity).
    assert t1.to_csv(index=False) == t2.to_csv(index=False)


def test_dual_table_has_unique_symbols():
    """The dual-score table is a one-row-per-fund contract; duplicate
    Symbols break downstream month-over-month comparison."""
    t = build_dual_score_table()
    dupes = t[t["Symbol"].duplicated(keep=False)]
    assert dupes.empty, (
        f"Duplicate symbols leaked into dual table: "
        f"{sorted(set(dupes['Symbol']))}"
    )


def test_dual_table_invariant_to_input_row_order():
    """Shuffling the input CSVs must not change the output table."""
    if not _has_fixture_2023_scores():
        pytest.skip("2023 fixture not available")
    base_2025 = pd.read_csv(GOOD_2025)
    base_2023 = pd.read_csv(GOOD_2023)
    t_base = build_dual_score_table(
        df_2025=None, df_2023=None,  # use fixtures below instead
        path_2025=GOOD_2025, path_2023=GOOD_2023, how="inner",
    )

    shuf_2025 = base_2025.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuf_2023 = base_2023.sample(frac=1.0, random_state=11).reset_index(drop=True)
    # Pre-score 2025 via path so score_funds runs on the shuffled frame.
    shuf_path_2025 = os.path.join(tempfile.mkdtemp(), "s25.csv")
    shuf_path_2023 = os.path.join(os.path.dirname(shuf_path_2025), "s23.csv")
    shuf_2025.to_csv(shuf_path_2025, index=False)
    shuf_2023.to_csv(shuf_path_2023, index=False)

    t_shuf = build_dual_score_table(
        path_2025=shuf_path_2025, path_2023=shuf_path_2023, how="inner",
    )

    # Row order must match (sort is deterministic), and values must match.
    assert list(t_base["Symbol"]) == list(t_shuf["Symbol"])
    for col in t_base.columns:
        assert t_base[col].equals(t_shuf[col]), f"Column {col} differs under shuffle"


# ---------------------------------------------------------------------------
# Full archive round-trip (bundled defaults)
# ---------------------------------------------------------------------------

def test_two_archives_from_same_bundled_inputs_produce_no_movers():
    """The committee-packet smoke test that originally caught the bug:
    creating two dated archives from the same inputs must yield an empty
    comparison bundle."""
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, update_latest=False)
        create_run_archive(run_date="2026-02-15", runs_dir=tmp, update_latest=False)
        a = load_run("2026-01-15", runs_dir=tmp)
        b = load_run("2026-02-15", runs_dir=tmp)

        # Archived CSVs must be byte-equal.
        assert a["table"].equals(b["table"])

        res = compare_runs(latest=b, prior=a)
        assert len(res.score_movers) == 0, (
            "Spurious score movers on identical inputs: "
            f"{res.score_movers.head().to_dict(orient='records')}"
        )
        assert len(res.band_changes) == 0
        assert len(res.quadrant_changes) == 0
        assert len(res.action_flag_changes) == 0
        assert len(res.new_funds) == 0
        assert len(res.removed_funds) == 0
        assert res.summary["score_mover_count_by_metric"] == {}
        assert res.summary["band_change_count_by_column"] == {}
        assert res.summary["quadrant_change_count"] == 0
        assert res.summary["action_flag_change_count"] == 0


# ---------------------------------------------------------------------------
# Duplicate-Symbol guard
# ---------------------------------------------------------------------------

def _synthetic_dup_inputs():
    """Two minimal frames where the same Symbol appears in two Categories
    on each side — mirrors the YCharts quirk that caused the bug."""
    df_2025_raw = pd.DataFrame(
        [
            {
                "Symbol": "AAA", "Name": "Alpha", "Index Fund": False,
                "Category Name": "Large Growth",
                "Net Expense Ratio": 0.5, "Share Class Assets Under Management": 1e9,
                "Information Ratio (vs Category) (3Y)": 0.4,
                "Historical Sortino (3Y)": 1.2,
                "Max Drawdown (5Y)": -15.0, "Max Drawdown (10Y)": -20.0,
                "Upside (vs Category) (5Y)": 1.1,
                "Downside (vs Category) (5Y)": 0.9,
                "3 Year Total Returns (Daily)": 8.0,
                "5 Year Total Returns (Daily)": 7.5,
                "10 Year Total Returns (Daily)": 7.0,
                "R-Squared (vs Category) (5Y)": 0.95,
            },
            {
                "Symbol": "AAA", "Name": "Alpha", "Index Fund": False,
                "Category Name": "Mid-Cap Growth",
                "Net Expense Ratio": 0.5, "Share Class Assets Under Management": 1e9,
                "Information Ratio (vs Category) (3Y)": 0.2,
                "Historical Sortino (3Y)": 1.0,
                "Max Drawdown (5Y)": -15.0, "Max Drawdown (10Y)": -20.0,
                "Upside (vs Category) (5Y)": 1.0,
                "Downside (vs Category) (5Y)": 1.0,
                "3 Year Total Returns (Daily)": 8.0,
                "5 Year Total Returns (Daily)": 7.5,
                "10 Year Total Returns (Daily)": 7.0,
                "R-Squared (vs Category) (5Y)": 0.95,
            },
            {
                "Symbol": "BBB", "Name": "Beta", "Index Fund": False,
                "Category Name": "Large Growth",
                "Net Expense Ratio": 0.7, "Share Class Assets Under Management": 5e8,
                "Information Ratio (vs Category) (3Y)": 0.1,
                "Historical Sortino (3Y)": 0.8,
                "Max Drawdown (5Y)": -18.0, "Max Drawdown (10Y)": -22.0,
                "Upside (vs Category) (5Y)": 0.9,
                "Downside (vs Category) (5Y)": 1.1,
                "3 Year Total Returns (Daily)": 6.0,
                "5 Year Total Returns (Daily)": 6.5,
                "10 Year Total Returns (Daily)": 6.0,
                "R-Squared (vs Category) (5Y)": 0.9,
            },
        ]
    )
    df_2023 = pd.DataFrame(
        [
            {"Symbol": "AAA", "Name": "Alpha", "Category Name": "Large Growth",
             "Score_2023": 85.0, "Avail_Weight": 100.0},
            {"Symbol": "AAA", "Name": "Alpha", "Category Name": "Mid-Cap Growth",
             "Score_2023": 40.0, "Avail_Weight": 100.0},
            {"Symbol": "BBB", "Name": "Beta", "Category Name": "Large Growth",
             "Score_2023": 60.0, "Avail_Weight": 100.0},
        ]
    )
    return df_2025_raw, df_2023


def test_duplicate_symbols_are_collapsed_deterministically():
    """Duplicate-Symbol inputs must produce a unique-Symbol output, and
    the collapsed row must be the same one across repeated calls."""
    from scoring_engine import score_funds

    raw_2025, df_2023 = _synthetic_dup_inputs()
    scored_2025 = score_funds(raw_2025)

    t1 = build_dual_score_table(df_2025=scored_2025, df_2023=df_2023)
    t2 = build_dual_score_table(df_2025=scored_2025, df_2023=df_2023)
    assert t1.equals(t2)
    assert t1["Symbol"].is_unique
    # AAA's collapsed row takes the best-scoring duplicate on each side
    # (Score_2023_Final from the Large-Growth row = 85.0; Score_2025_Final
    # from the Mid-Cap-Growth row, the higher of the two on that side).
    aaa = t1[t1["Symbol"] == "AAA"].iloc[0]
    assert aaa["Score_2023_Final"] == 85.0
    # Category must come from a deterministic choice, not vary run to run.
    assert aaa["Category"] in {"Large Growth", "Mid-Cap Growth"}


def test_duplicate_symbol_run_comparison_is_empty_on_identical_inputs():
    """End-to-end: two archives built from the same duplicate-Symbol frames
    compare cleanly (no spurious movers)."""
    from scoring_engine import score_funds

    raw_2025, df_2023 = _synthetic_dup_inputs()
    scored_2025 = score_funds(raw_2025)
    table = build_dual_score_table(df_2025=scored_2025, df_2023=df_2023)

    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-03-01", runs_dir=tmp,
                           table=table.copy(), update_latest=False)
        create_run_archive(run_date="2026-04-01", runs_dir=tmp,
                           table=table.copy(), update_latest=False)
        a = load_run("2026-03-01", runs_dir=tmp)
        b = load_run("2026-04-01", runs_dir=tmp)
        res = compare_runs(latest=b, prior=a)

        assert len(res.score_movers) == 0
        assert len(res.band_changes) == 0
        assert len(res.quadrant_changes) == 0
        assert len(res.action_flag_changes) == 0
        assert len(res.new_funds) == 0
        assert len(res.removed_funds) == 0


# ---------------------------------------------------------------------------
# Tie-break stability
# ---------------------------------------------------------------------------

def test_tied_consensus_rank_orders_funds_by_symbol():
    """When Consensus_Rank ties, Symbol breaks the tie ascending — so the
    emitted ordering is stable regardless of the merge's internal order."""
    t = build_dual_score_table()
    tied = t[t["Consensus_Rank"].duplicated(keep=False)]
    if tied.empty:
        pytest.skip("no tied Consensus_Rank in bundled data")
    for _rank, group in tied.groupby("Consensus_Rank"):
        symbols = group["Symbol"].tolist()
        assert symbols == sorted(symbols), (
            f"Consensus_Rank tie group not sorted by Symbol: {symbols}"
        )


def test_top_n_score_sort_is_stable():
    """The excel/packet Top-N helpers must tie-break ascending on Symbol."""
    from excel_audit_export import _top_n_by_consensus, _top_n_by_score

    t = build_dual_score_table()
    a = _top_n_by_consensus(t, n=50)
    b = _top_n_by_consensus(t, n=50)
    assert a.equals(b)
    a2 = _top_n_by_score(t, "Score_2025_Final", n=50)
    b2 = _top_n_by_score(t, "Score_2025_Final", n=50)
    assert a2.equals(b2)


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-v"]))
