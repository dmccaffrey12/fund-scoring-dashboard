"""
Fund Scoring Engine
===================
Calculates percentile-based scores for passive and active funds within their
Morningstar category peer group.

Passive system: 10 metrics, 90 raw points, rescaled *1.111 → 100-point scale
Active system:  16 metrics, 100 raw points
"""

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# CSV Column Name Mapping (exact YCharts export headers)
# ---------------------------------------------------------------------------

CSV_COLUMNS = {
    'symbol': 'Symbol',
    'name': 'Name',
    'index_fund': 'Index Fund',
    'category': 'Category Name',
    'expense_ratio': 'Net Expense Ratio',
    'tracking_error_3y': 'Tracking Error (vs Category) (3Y)',
    'tracking_error_5y': 'Tracking Error (vs Category) (5Y)',
    'tracking_error_10y': 'Tracking Error (vs Category) (10Y)',
    'r_squared_5y': 'R-Squared (vs Category) (5Y)',
    'aum': 'Share Class Assets Under Management',
    'downside_5y': 'Downside (vs Category) (5Y)',
    'downside_10y': 'Downside (vs Category) (10Y)',
    'max_drawdown_5y': 'Max Drawdown (5Y)',
    'max_drawdown_10y': 'Max Drawdown (10Y)',
    'info_ratio_3y': 'Information Ratio (vs Category) (3Y)',
    'info_ratio_5y': 'Information Ratio (vs Category) (5Y)',
    'info_ratio_10y': 'Information Ratio (vs Category) (10Y)',
    'sortino_3y': 'Historical Sortino (3Y)',
    'sortino_5y': 'Historical Sortino (5Y)',
    'sortino_10y': 'Historical Sortino (10Y)',
    'upside_5y': 'Upside (vs Category) (5Y)',
    'upside_10y': 'Upside (vs Category) (10Y)',
    'returns_3y': '3 Year Total Returns (Daily)',
    'returns_5y': '5 Year Total Returns (Daily)',
    'returns_10y': '10 Year Total Returns (Daily)',
}

# ---------------------------------------------------------------------------
# Metric Definitions
# ---------------------------------------------------------------------------

# Passive: 10 metrics totalling 90 raw points — rescaled *1.111 to reach 100
PASSIVE_METRICS = [
    ('expense_ratio',       40, 'lower'),
    ('tracking_error_3y',   10, 'lower'),
    ('tracking_error_5y',   10, 'lower'),
    ('tracking_error_10y',  10, 'lower'),
    ('r_squared_5y',         5, 'higher'),
    ('aum',                  6, 'higher'),
    ('downside_5y',          3, 'lower'),
    ('downside_10y',         2, 'lower'),
    ('max_drawdown_5y',      2, 'lower'),
    ('max_drawdown_10y',     2, 'lower'),
]

# Active: 16 metrics totalling 100 raw points
ACTIVE_METRICS = [
    ('expense_ratio',    25, 'lower'),
    ('info_ratio_3y',    10, 'higher'),
    ('info_ratio_5y',     6, 'higher'),
    ('info_ratio_10y',    4, 'higher'),
    ('sortino_3y',       10, 'higher'),
    ('sortino_5y',        6, 'higher'),
    ('sortino_10y',       4, 'higher'),
    ('max_drawdown_5y',   7, 'lower'),
    ('max_drawdown_10y',  3, 'lower'),
    ('downside_5y',       7, 'lower'),
    ('downside_10y',      3, 'lower'),
    ('returns_3y',        1, 'higher'),
    ('returns_5y',        1, 'higher'),
    ('returns_10y',       2, 'higher'),
    ('upside_5y',         6, 'higher'),
    ('upside_10y',        5, 'higher'),
]

PASSIVE_RESCALE = 1.111  # 90-point system → 100-point scale


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def calculate_percentile(df: pd.DataFrame, metric_col: str, category_col: str, direction: str) -> pd.Series:
    """
    Compute within-category percentile rank (0–1) for each row.

    Parameters
    ----------
    df          : DataFrame containing metric_col and category_col
    metric_col  : Column name to rank
    category_col: Column name for peer group (e.g. 'Category Name')
    direction   : 'higher' → higher values are better (rank ascending)
                  'lower'  → lower values are better (rank descending)

    Returns
    -------
    pd.Series of float percentile ranks (0–1), NaN where metric is missing.
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)

    for cat, group in df.groupby(category_col):
        valid_mask = group[metric_col].notna()
        if valid_mask.sum() == 0:
            continue

        values = group.loc[valid_mask, metric_col]
        n = len(values)

        # Vectorised count for each fund in the group
        if direction == 'higher':
            # Fraction of peers with value <= this fund's value
            ranks = values.apply(lambda v: (values <= v).sum() / n)
        else:
            # 'lower' direction: lower is better
            # Fraction of peers with value >= this fund's value
            ranks = values.apply(lambda v: (values >= v).sum() / n)

        result.loc[ranks.index] = ranks.values

    return result


def _compute_score(df: pd.DataFrame, metrics: list, rescale: float = 1.0) -> pd.Series:
    """
    Internal helper: weighted-average percentile score for a list of metrics.

    For each fund the available-weight denominator is the sum of weights for
    metrics where data exists, ensuring missing metrics don't suppress the score.
    """
    category_col = CSV_COLUMNS['category']
    n = len(df)

    # Pre-compute percentile series for every metric needed
    pct_cache = {}
    for key, _weight, direction in metrics:
        col = CSV_COLUMNS.get(key, key)
        if col in df.columns:
            pct_cache[key] = calculate_percentile(df, col, category_col, direction)
        else:
            pct_cache[key] = pd.Series(np.nan, index=df.index, dtype=float)

    # Weighted sum per row
    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight = pd.Series(0.0, index=df.index)

    for key, weight, _direction in metrics:
        pct = pct_cache[key]
        has_data = pct.notna()
        weighted_sum[has_data] += pct[has_data] * weight
        available_weight[has_data] += weight

    # Score = (weighted_sum / available_weight) * 100 * rescale
    # Where available_weight == 0, score is NaN
    score = pd.Series(np.nan, index=df.index, dtype=float)
    has_any = available_weight > 0
    score[has_any] = (weighted_sum[has_any] / available_weight[has_any]) * 100.0 * rescale

    return score


def score_funds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Take a raw CSV DataFrame (using YCharts column names) and return a copy
    with the following columns added:

        Fund_Type       : 'Passive' | 'Active'
        Score_Passive   : Passive system score (0–100), NaN for active funds*
        Score_Active    : Active system score (0–100), NaN for passive funds*
        Score_Final     : The appropriate score for each fund's type
        Score_Band      : 'STRONG' | 'REVIEW' | 'WEAK'

    * Both scores are always computed across the whole DataFrame for
      diagnostic purposes, but Score_Final picks the right one.

    Parameters
    ----------
    df : pd.DataFrame  — must contain the YCharts column headers defined in
                         CSV_COLUMNS.

    Returns
    -------
    pd.DataFrame with original columns plus score columns.
    """
    result = df.copy()

    index_fund_col = CSV_COLUMNS['index_fund']

    # Normalise Index Fund column — accept bool, 'True'/'False' strings, 1/0
    if result[index_fund_col].dtype == object:
        result['_is_passive'] = result[index_fund_col].astype(str).str.strip().str.lower() == 'true'
    else:
        result['_is_passive'] = result[index_fund_col].astype(bool)

    result['Fund_Type'] = result['_is_passive'].map({True: 'Passive', False: 'Active'})

    # Compute scores on the full DataFrame (category percentiles use all peers)
    result['Score_Passive'] = _compute_score(result, PASSIVE_METRICS, rescale=PASSIVE_RESCALE)
    result['Score_Active'] = _compute_score(result, ACTIVE_METRICS, rescale=1.0)

    # Select the right score for each fund
    result['Score_Final'] = np.where(
        result['_is_passive'],
        result['Score_Passive'],
        result['Score_Active']
    )

    result['Score_Band'] = result['Score_Final'].apply(get_score_band)

    result.drop(columns=['_is_passive'], inplace=True)
    return result


def get_score_band(score) -> str:
    """
    Map a numeric score to a categorical band.

    STRONG : score >= 80
    REVIEW : 60 <= score < 80
    WEAK   : score < 60  (or NaN)
    """
    if pd.isna(score):
        return 'WEAK'
    if score >= 80:
        return 'STRONG'
    if score >= 60:
        return 'REVIEW'
    return 'WEAK'


# ---------------------------------------------------------------------------
# Convenience helpers used by the Streamlit app
# ---------------------------------------------------------------------------

def load_and_score(path: str) -> pd.DataFrame:
    """Load a CSV file and return it scored."""
    df = pd.read_csv(path)
    return score_funds(df)


def get_metric_percentiles(scored_df: pd.DataFrame, symbol: str) -> dict:
    """
    Return a dict {metric_label: percentile_0_to_100} for a given fund,
    using the appropriate metric set for its type. Used for radar charts.
    """
    category_col = CSV_COLUMNS['category']
    row = scored_df[scored_df[CSV_COLUMNS['symbol']] == symbol]
    if row.empty:
        return {}

    row = row.iloc[0]
    fund_type = row.get('Fund_Type', 'Active')
    metrics = PASSIVE_METRICS if fund_type == 'Passive' else ACTIVE_METRICS

    result = {}
    cat_df = scored_df[scored_df[category_col] == row[category_col]]

    for key, weight, direction in metrics:
        col = CSV_COLUMNS.get(key, key)
        if col not in scored_df.columns:
            continue
        val = row.get(col)
        if pd.isna(val):
            continue
        cat_vals = cat_df[col].dropna()
        if len(cat_vals) == 0:
            continue
        if direction == 'higher':
            pct = (cat_vals <= val).sum() / len(cat_vals)
        else:
            pct = (cat_vals >= val).sum() / len(cat_vals)
        result[col] = round(pct * 100, 1)

    return result

# ---------------------------------------------------------------------------
# 2023 Combined System: 15 metrics totalling 100 points (all funds scored together)
# ---------------------------------------------------------------------------

SYSTEM_2023_METRICS = [
    ('ret_5y',     'Annualized 5 Year Total Returns (Monthly)',  9, 'higher'),
    ('ret_10y',    'Annualized 10 Year Total Returns (Monthly)', 9, 'higher'),
    ('alpha_5y',   'Alpha (vs Category) (5Y)',                   11, 'higher'),
    ('alpha_10y',  'Alpha (vs Category) (10Y)',                  11, 'higher'),
    ('maxdd_5y',   'Max Drawdown (5Y)',                          10, 'lower'),
    ('maxdd_10y',  'Max Drawdown (10Y)',                         10, 'lower'),
    ('up_5y',      'Upside (5Y)',                                 5, 'higher'),
    ('up_10y',     'Upside (10Y)',                                6, 'higher'),
    ('dn_5y',      'Downside (5Y)',                               7, 'lower'),
    ('dn_10y',     'Downside (10Y)',                              7, 'lower'),
    ('med_tenure',  'Median Manager Tenure',                     3, 'higher'),
    ('avg_tenure',  'Average Manager Tenure',                    3, 'higher'),
    ('sc_aum',      'Share Class Assets Under Management',       2.5, 'higher'),
    ('total_aum',   'Total Assets Under Management',             1.5, 'higher'),
    ('expense',     'Annual Report Expense Ratio',               5, 'lower'),
]
