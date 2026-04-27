"""Tests for the inferred-category / inferred-fund-type discovery filters
added to ``build_replacement_workbench`` after PR #20.

The user's escalation: when researching a replacement for PRBLX (Active,
Large Blend, resolved to PRILX), the default discovery universe should be
*Active + Large Blend only* — passive Large Blend names like SPYM should
not surface unless the user explicitly overrides. The committee candidate
list, when uploaded, must remain authoritative (never silently drop
user-supplied symbols).
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from candidate_list_intake import parse_candidate_list  # noqa: E402
from printable_brief import render_printable_brief_html  # noqa: E402
from replacement_workbench import (  # noqa: E402
    build_replacement_workbench,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _prblx_dual_table() -> pd.DataFrame:
    """A scored universe that mirrors the production PRBLX scenario:
    PRILX is the alias target (Active, Large Blend) and several other
    Large Blend names exist — some Active, some Passive. The Active
    Large Blend names should be the only candidates surfaced by the
    default inferred filters."""
    return pd.DataFrame([
        # PRBLX -> PRILX is the current holding (Active, Large Blend).
        {"Symbol": "PRILX", "Name": "Parnassus Core Equity Inst",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 58.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Mid", "Consensus_Rank": 8,
         "Score_Gap": -2.0, "Rank_2023": 8, "Rank_2025": 8,
         "Action_Flag": "REVIEW", "Primary_Driver": "fees"},
        # Active Large Blend candidates — must surface in default discovery.
        {"Symbol": "ACTLB1", "Name": "Active Large Blend 1",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 90.0, "Score_2025_Final": 88.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": -2.0, "Rank_2023": 1, "Rank_2025": 2,
         "Action_Flag": "LEAD", "Primary_Driver": "alpha"},
        {"Symbol": "ACTLB2", "Name": "Active Large Blend 2",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 80.0, "Score_2025_Final": 82.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 2,
         "Score_Gap": 2.0, "Rank_2023": 3, "Rank_2025": 3,
         "Action_Flag": "LEAD", "Primary_Driver": "quality"},
        # Passive Large Blend (SPYM analogue) — must NOT surface in default
        # discovery for an Active replacement.
        {"Symbol": "SPYM", "Name": "SPDR Portfolio S&P 500",
         "Category": "Large Blend", "Fund_Type": "Passive",
         "Score_2023_Final": 99.0, "Score_2025_Final": 99.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 0,
         "Score_Gap": 0.0, "Rank_2023": 0, "Rank_2025": 0,
         "Action_Flag": "LEAD", "Primary_Driver": "track"},
        {"Symbol": "VOO", "Name": "Vanguard S&P 500 ETF",
         "Category": "Large Blend", "Fund_Type": "Passive",
         "Score_2023_Final": 98.0, "Score_2025_Final": 98.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 0.0, "Rank_2023": 1, "Rank_2025": 1,
         "Action_Flag": "LEAD", "Primary_Driver": "track"},
        # Different category, Active — must NOT surface.
        {"Symbol": "OFFCAT", "Name": "Off-Cat Active",
         "Category": "Small Value", "Fund_Type": "Active",
         "Score_2023_Final": 95.0, "Score_2025_Final": 95.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 0.0, "Rank_2023": 1, "Rank_2025": 1,
         "Action_Flag": "LEAD", "Primary_Driver": "value"},
    ])


def _prblx_alias_map() -> dict:
    return {"PRBLX": "PRILX"}


# ---------------------------------------------------------------------------
# Default behavior — Active Large Blend discovery for PRBLX
# ---------------------------------------------------------------------------

def test_prblx_default_discovery_returns_active_large_blend_only():
    """Entering PRBLX with no committee list and no overrides should pull
    Active + Large Blend candidates only. Passive Large Blend names (SPYM,
    VOO) and off-category names (OFFCAT) must not surface."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "ACTLB1" in syms
    assert "ACTLB2" in syms
    assert "SPYM" not in syms
    assert "VOO" not in syms
    assert "OFFCAT" not in syms

    summary = result.summary
    assert summary["inferred_category"] == "Large Blend"
    assert summary["inferred_fund_type"] == "Active"
    assert summary["category_filter_used"] is True
    assert summary["fund_type_filter_used"] is True
    assert summary["fund_type_filter"] == "Active"
    assert summary["filter_source"] == "inferred"


def test_prblx_alias_resolution_drives_inference():
    """The inferred values come from the alias-resolved row (PRILX), not
    the raw user input (PRBLX). The summary should still record the
    original ticker but pull category/fund_type from PRILX."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
    )
    assert result.summary["ticker"] == "PRBLX"
    assert result.summary["resolved_ticker"] == "PRILX"
    assert result.summary["alias_applied"] is True
    assert result.summary["inferred_category"] == "Large Blend"
    assert result.summary["inferred_fund_type"] == "Active"


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

def test_fund_type_override_passive_surfaces_passive_names():
    """Passing fund_type_override='Passive' inverts the default and yields
    only Passive Large Blend names — the user explicitly chose to research
    a passive replacement."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        fund_type_override="Passive",
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert set(syms) == {"SPYM", "VOO"}
    assert result.summary["fund_type_filter"] == "Passive"
    assert result.summary["fund_type_filter_source"] == "override"


def test_fund_type_override_all_includes_all_types():
    """fund_type_override='All' disables the fund-type filter entirely.
    Both Active and Passive Large Blend names should surface."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        fund_type_override="All",
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert {"ACTLB1", "ACTLB2", "SPYM", "VOO"}.issubset(set(syms))
    # Off-category is still excluded — only fund-type was relaxed.
    assert "OFFCAT" not in syms
    assert result.summary["fund_type_filter_used"] is False
    assert result.summary["fund_type_filter_source"] == "override_all"


def test_category_override_changes_pool():
    """category_override forces a different category. With override =
    'Small Value' and fund_type_override='All', only OFFCAT should
    appear."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        category_override="Small Value",
        fund_type_override="All",
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert syms == ["OFFCAT"]
    assert result.summary["category"] == "Small Value"
    assert result.summary["category_source"] == "override"


def test_apply_fund_type_filter_false_is_explicit_disable():
    """apply_fund_type_filter=False (without a fund_type_override) is a
    clean way for callers to keep legacy cross-type behavior."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        apply_fund_type_filter=False,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    # Active + Passive Large Blend names BOTH appear (still same-category).
    assert "ACTLB1" in syms
    assert "SPYM" in syms
    assert result.summary["fund_type_filter_used"] is False
    assert result.summary["fund_type_filter_source"] == "disabled"


# ---------------------------------------------------------------------------
# Committee-list authoritative behavior unaffected
# ---------------------------------------------------------------------------

def test_committee_list_keeps_user_supplied_symbols_even_against_filters():
    """When the user uploads a committee candidate list, the brief must
    show the user's symbols regardless of inferred category / fund type.
    Per PR #20: committee list is authoritative. The new inferred filters
    must NOT silently drop user-supplied committee candidates."""
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["ACTLB1", "SPYM", "OFFCAT"],
        "Name": ["Active Idea", "Passive Idea", "Off-Cat Idea"],
    }))
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        candidate_list=cl,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    # All three user-supplied symbols must appear, including the passive
    # SPYM and the off-category OFFCAT.
    assert set(syms) == {"ACTLB1", "SPYM", "OFFCAT"}
    summary = result.summary
    # Filters are reported as not forced.
    assert summary["filter_source"] == "committee_list"
    assert summary["candidate_universe_source"] == "committee_list"
    # Inferred values still surfaced for transparency in the brief.
    assert summary["inferred_category"] == "Large Blend"
    assert summary["inferred_fund_type"] == "Active"


def test_committee_list_filters_can_be_layered_when_explicitly_requested():
    """When the caller explicitly passes apply_fund_type_filter=True with
    a committee list, the filter DOES apply on top of the committee
    universe — this is the diagnostic-review path. SPYM (passive) should
    drop, ACTLB1 (active) should remain."""
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["ACTLB1", "SPYM"],
        "Name": ["Active Idea", "Passive Idea"],
    }))
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        candidate_list=cl,
        apply_fund_type_filter=True,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    # ACTLB1 surfaces; SPYM is filtered out by the explicit filter.
    # SPYM may still show as un-scored-in-list (Scored_In_Universe=False
    # row), but in this fixture SPYM IS scored, so it's the active filter
    # that drops it.
    assert "ACTLB1" in syms
    assert "SPYM" not in syms


# ---------------------------------------------------------------------------
# Graceful degrade
# ---------------------------------------------------------------------------

def test_unknown_fund_type_degrades_gracefully():
    """If the resolved holding has no Fund_Type metadata, the workbench
    should not blow up — the filter is simply not applied and the
    summary records 'unknown'."""
    dt = _prblx_dual_table()
    dt.loc[dt["Symbol"] == "PRILX", "Fund_Type"] = None
    result = build_replacement_workbench(
        dt, "PRBLX", top_n=10, alias_map=_prblx_alias_map(),
    )
    assert result.summary["inferred_fund_type"] is None
    assert result.summary["fund_type_filter_used"] is False
    # All Large-Blend names (active and passive) surface — no fund-type
    # filter was applied because we couldn't infer one.
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "ACTLB1" in syms
    assert "SPYM" in syms


def test_unknown_category_degrades_gracefully():
    """If the resolved holding is missing from the scored universe AND no
    override is supplied, no candidates surface and the summary is honest
    about the gap."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "NEVER_HEARD_OF_THIS",
        top_n=10, alias_map={},
    )
    assert result.summary["inferred_category"] is None
    assert result.summary["candidate_count"] == 0
    assert result.summary["category_source"] == "unknown"


# ---------------------------------------------------------------------------
# Brief & printable-brief filter labeling
# ---------------------------------------------------------------------------

def test_markdown_brief_labels_applied_filters_for_discovery():
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
    )
    md = result.brief_markdown
    # Methodology must surface the inferred discovery filters.
    assert "Discovery filters" in md
    assert "Large Blend" in md
    assert "Active" in md


def test_markdown_brief_labels_committee_list_as_unforced_filters():
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["ACTLB1"],
        "Name": ["Idea"],
    }))
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        candidate_list=cl,
    )
    md = result.brief_markdown
    assert "not forced" in md or "*not forced*" in md
    assert "committee list supplied" in md.lower()


def test_printable_brief_banner_labels_discovery_filters():
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
    )
    out = render_printable_brief_html(result)
    # The discovery banner must call out both the category and fund-type
    # filters so a printed page is self-explanatory.
    assert "Discovery filters" in out
    assert "Large Blend" in out
    assert "Active" in out


def test_printable_brief_banner_says_filters_not_forced_for_committee_list():
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["ACTLB1", "SPYM"],
        "Name": ["Active Idea", "Passive Idea"],
    }))
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        candidate_list=cl,
    )
    out = render_printable_brief_html(result)
    assert "Discovery filters" in out
    assert "not forced" in out


def test_printable_brief_banner_for_unknown_fund_type_does_not_crash():
    dt = _prblx_dual_table()
    dt.loc[dt["Symbol"] == "PRILX", "Fund_Type"] = None
    result = build_replacement_workbench(
        dt, "PRBLX", top_n=10, alias_map=_prblx_alias_map(),
    )
    out = render_printable_brief_html(result)
    # Unknown fund-type renders gracefully ('unknown') and the banner
    # still mentions the inferred category.
    assert "Discovery filters" in out
    assert "Large Blend" in out
    assert "unknown" in out.lower()


# ---------------------------------------------------------------------------
# Summary contract: keys exposed to callers / Streamlit page
# ---------------------------------------------------------------------------

def test_summary_exposes_inferred_keys():
    """The summary must expose stable keys that Streamlit / printable
    brief / PR-description tooling depend on."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
    )
    s = result.summary
    for key in (
        "inferred_category", "inferred_fund_type",
        "category_filter_used", "fund_type_filter_used",
        "fund_type_filter", "fund_type_filter_source",
        "category_filter_source", "filter_source",
        "fund_type_override_used", "category_override_used",
    ):
        assert key in s, f"summary missing key: {key}"


def test_apply_category_filter_false_disables_category_pool():
    """apply_category_filter=False with no category override means the
    pool is unrestricted by category — useful for cross-category
    discovery experiments."""
    result = build_replacement_workbench(
        _prblx_dual_table(), "PRBLX",
        top_n=10, alias_map=_prblx_alias_map(),
        apply_category_filter=False,
        apply_fund_type_filter=False,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    # Every Active and Passive scored name except the current holding
    # itself can appear.
    assert "OFFCAT" in syms
    assert result.summary["category_filter_used"] is False
    assert result.summary["category_filter_source"] == "disabled"
