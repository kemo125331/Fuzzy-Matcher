"""
Record Linkage algorithm implementation using the recordlinkage library.
This provides statistical/probabilistic matching.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import pandas as pd

try:
    import recordlinkage as rl
    HAS_RECORDLINKAGE = True
except ImportError:
    HAS_RECORDLINKAGE = False

from .date_normalizer import parse_date_safe
from .itr_categorizer import categorize_itr
from ..constants import PREFIX_T1, PREFIX_T2


def match_with_recordlinkage(
    t1: pd.DataFrame,
    t2: pd.DataFrame,
    t1_last_col: str,
    t1_first_col: str,
    t1_date_col: str,
    t2_last_col: str,
    t2_first_col: str,
    t2_date_col: str,
    threshold: float = 0.85,
    show_all_matches: bool = False,
    progress_cb: Optional[Any] = None,
) -> pd.DataFrame:
    """
    Match using recordlinkage library (statistical/probabilistic approach).
    Returns results in the same format as match_tables.
    """
    if not HAS_RECORDLINKAGE:
        # Fallback: return empty DataFrame with error message
        return pd.DataFrame()
    
    try:
        # Prepare dataframes with standard column names for recordlinkage
        t1_clean = t1.copy()
        t2_clean = t2.copy()
        
        # Normalize dates
        t1_clean["__date"] = t1_clean[t1_date_col].apply(parse_date_safe)
        t2_clean["__date"] = t2_clean[t2_date_col].apply(parse_date_safe)
        
        # Filter out rows with invalid dates for blocking
        t1_clean = t1_clean[t1_clean["__date"].notna()].copy()
        t2_clean = t2_clean[t2_clean["__date"].notna()].copy()
        
        if len(t1_clean) == 0 or len(t2_clean) == 0:
            return pd.DataFrame()
        
        # Create blocking index (block on date for efficiency)
        indexer = rl.Index()
        indexer.block('__date')  # Block on date first
        candidate_pairs = indexer.index(t1_clean, t2_clean)
        
        if len(candidate_pairs) == 0:
            return pd.DataFrame()
        
        # Compare records
        compare = rl.Compare()
        
        # String comparisons for names
        compare.string(t1_last_col, t2_last_col, method='jarowinkler', threshold=0.7, label='last_name')
        compare.string(t1_first_col, t2_first_col, method='jarowinkler', threshold=0.7, label='first_name')
        
        # Exact date match
        compare.exact('__date', '__date', label='date_exact')
        
        # Compute comparison vectors
        features = compare.compute(candidate_pairs, t1_clean, t2_clean)
        
        # Classification: sum of scores
        # Each comparison returns 0-1, we want total >= threshold
        feature_sum = features.sum(axis=1)
        matches = feature_sum[feature_sum >= threshold]
        
        # Convert to results format
        results = []
        seen_pairs = set()
        
        for (idx1, idx2), score in matches.items():
            if not show_all_matches and (idx1, idx2) in seen_pairs:
                continue
            seen_pairs.add((idx1, idx2))
            
            r1 = t1_clean.loc[idx1]
            r2 = t2_clean.loc[idx2]
            
            # Get individual scores
            last_score = int(features.loc[(idx1, idx2), 'last_name'] * 100) if 'last_name' in features.columns else 0
            first_score = int(features.loc[(idx1, idx2), 'first_name'] * 100) if 'first_name' in features.columns else 0
            combined = int(score * 100)
            
            # Determine confidence
            if combined >= 90:
                confidence = "High"
            elif combined >= 80:
                confidence = "Medium"
            elif combined >= 70:
                confidence = "Low"
            else:
                confidence = "Very Low"
            
            # Build result row
            merged: Dict[str, Any] = {}
            
            for col in t1.columns:
                if not col.startswith("__"):
                    merged[f"{PREFIX_T1}{col}"] = r1[col] if col in r1.index else None
            
            for col in t2.columns:
                if not col.startswith("__"):
                    merged[f"{PREFIX_T2}{col}"] = r2[col] if col in r2.index else None
            
            merged["LastName_Score"] = last_score
            merged["FirstName_Score"] = first_score
            merged["Combined_Score"] = combined
            merged["Confidence"] = confidence
            
            # ITR bucket if available
            t1_itr_col = None
            for col in t1.columns:
                if "intent" in col.lower() or "itr" in col.lower():
                    t1_itr_col = col
                    break
            
            if t1_itr_col and f"{PREFIX_T1}{t1_itr_col}" in merged:
                from .itr_categorizer import categorize_itr
                merged["ITR_Bucket"] = categorize_itr(merged[f"{PREFIX_T1}{t1_itr_col}"])
            else:
                merged["ITR_Bucket"] = None
            
            results.append(merged)
            
            if progress_cb is not None and len(results) % 10 == 0:
                progress_cb(min(99, int(len(results) * 100 / max(1, len(matches)))))
        
        # Add unmatched GSS rows if show_all_matches
        if show_all_matches:
            matched_t1_indices = {idx1 for (idx1, idx2) in matches.index}
            for idx1, r1 in t1.iterrows():
                if idx1 not in matched_t1_indices:
                    merged: Dict[str, Any] = {}
                    for col in t1.columns:
                        if not col.startswith("__"):
                            merged[f"{PREFIX_T1}{col}"] = r1[col] if col in r1.index else None
                    for col in t2.columns:
                        if not col.startswith("__"):
                            merged[f"{PREFIX_T2}{col}"] = None
                    merged["LastName_Score"] = None
                    merged["FirstName_Score"] = None
                    merged["Combined_Score"] = None
                    merged["Confidence"] = "No Match"
                    merged["ITR_Bucket"] = None
                    results.append(merged)
        
        if progress_cb is not None:
            progress_cb(100)
        
        return pd.DataFrame(results)
    
    except Exception as e:
        # On error, return empty DataFrame
        import logging
        logging.getLogger(__name__).error(f"Record linkage error: {e}")
        return pd.DataFrame()

