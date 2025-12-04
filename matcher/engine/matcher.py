
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional, Dict, Any, Tuple, List

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

# Optional imports for advanced algorithms
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False

try:
    import recordlinkage as rl
    HAS_RECORDLINKAGE = True
except ImportError:
    HAS_RECORDLINKAGE = False

try:
    from metaphone import doublemetaphone
    HAS_METAPHONE = True
except ImportError:
    HAS_METAPHONE = False

from .date_normalizer import parse_date_safe
from .itr_categorizer import categorize_itr
from .name_normalizer import (
    normalize_component,
    canonical_first_name,
    soundex_code,
)
from ..constants import (
    PREFIX_T1,
    PREFIX_T2,
    EXACT_DATE_NAME_BOOST,
    EXACT_DATE_COMBINED_BOOST,
    CLOSE_DATE_NAME_BOOST,
    CLOSE_DATE_COMBINED_BOOST,
    PHONETIC_BOOST,
    DATE_TOLERANCE_THRESHOLD_REDUCTION,
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    CONFIDENCE_LOW_THRESHOLD,
    MULTI_PASS_MEDIUM_THRESHOLD_REDUCTION,
    MULTI_PASS_LENIENT_THRESHOLD_REDUCTION,
    MAX_NAME_LENGTH_DIFF_RATIO,
    PROGRESS_UPDATE_INTERVAL_PERCENT,
)


@dataclass
class MatchConfig:
    t1_last: str
    t1_first: str
    t1_date: str
    t1_itr: str | None
    t2_last: str
    t2_first: str
    t2_date: str
    t2_userid: str
    algorithm: str
    threshold: int
    enable_pre_norm: bool
    enable_enhanced_fuzzy: bool
    enable_date_bonus: bool
    enable_phonetic: bool
    enable_variants: bool
    enable_double_surname: bool
    enable_safe_missing: bool
    show_all_matches: bool = False
    date_tolerance_days: int = 0  # Allow dates within N days (0 = exact match only)
    enable_multi_pass: bool = True  # Multi-pass matching for better coverage


@dataclass
class NormalizedRow:
    """Pre-computed normalized data for a row"""
    last_norm: str
    first_norm: str
    last_raw: str
    first_raw: str
    last_len: int
    first_len: int
    last_first_char: str
    first_first_char: str
    last_soundex: Optional[str]
    first_soundex: Optional[str]


def _base_fuzzy(a: str, b: str, algorithm: str) -> int:
    if not a and not b:
        return 100
    if not a or not b:
        return 0
    if algorithm == "Partial Ratio":
        return fuzz.partial_ratio(a, b)
    elif algorithm == "Jaro-Winkler":
        # Jaro-Winkler is better for names (0-100 scale, convert from 0-1)
        similarity = JaroWinkler.similarity(a, b)
        return int(round(similarity * 100))
    return fuzz.WRatio(a, b)


def _enhanced_fuzzy(a: str, b: str) -> int:
    if not a and not b:
        return 100
    if not a or not b:
        return 0
    ts = fuzz.token_sort_ratio(a, b)
    pr = fuzz.partial_ratio(a, b)
    return int(round(ts * 0.6 + pr * 0.4))


def _ensemble_score(a: str, b: str) -> int:
    """
    Ensemble scoring: combine multiple algorithms for better accuracy.
    Different algorithms catch different error types:
    - Jaro-Winkler: transpositions, common typos
    - Weighted Ratio: general similarity
    - Token Sort: word order differences
    - Partial Ratio: substring matches
    """
    if not a and not b:
        return 100
    if not a or not b:
        return 0
    
    scores = []
    
    # Jaro-Winkler (best for names)
    jw_score = int(round(JaroWinkler.similarity(a, b) * 100))
    scores.append(jw_score)
    
    # Weighted Ratio (general purpose)
    wr_score = fuzz.WRatio(a, b)
    scores.append(wr_score)
    
    # Token Sort Ratio (handles word order)
    ts_score = fuzz.token_sort_ratio(a, b)
    scores.append(ts_score)
    
    # Partial Ratio (substring matching)
    pr_score = fuzz.partial_ratio(a, b)
    scores.append(pr_score)
    
    # Combine: use weighted average (Jaro-Winkler gets more weight for names)
    # Or use max score (more lenient) or median (more robust to outliers)
    # Using weighted average with emphasis on Jaro-Winkler for names
    ensemble = int(round(
        jw_score * 0.35 +  # Jaro-Winkler weighted highest (good for names)
        wr_score * 0.30 +  # Weighted Ratio
        ts_score * 0.20 +  # Token Sort
        pr_score * 0.15    # Partial Ratio
    ))
    
    return ensemble


# Global semantic model (lazy loaded)
_semantic_model = None

def _get_semantic_model():
    """Lazy load semantic model to avoid loading on import"""
    global _semantic_model
    if _semantic_model is None and HAS_SEMANTIC:
        try:
            # Use a lightweight model for names
            _semantic_model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        except Exception:
            pass
    return _semantic_model

def _semantic_score(a: str, b: str) -> int:
    """Semantic similarity using sentence transformers"""
    if not HAS_SEMANTIC:
        # Fallback to Jaro-Winkler if semantic matching not available
        return int(round(JaroWinkler.similarity(a, b) * 100))
    
    model = _get_semantic_model()
    if model is None:
        return int(round(JaroWinkler.similarity(a, b) * 100))
    
    try:
        embeddings = model.encode([a, b])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return int(round(similarity * 100))
    except Exception:
        # Fallback on error
        return int(round(JaroWinkler.similarity(a, b) * 100))

def _double_metaphone_score(a: str, b: str) -> int:
    """Double Metaphone phonetic matching"""
    if not HAS_METAPHONE:
        # Fallback to Soundex if Double Metaphone not available
        from .name_normalizer import soundex_code
        code1 = soundex_code(a)
        code2 = soundex_code(b)
        return 100 if code1 and code1 == code2 else 0
    
    try:
        dm1 = doublemetaphone(a)
        dm2 = doublemetaphone(b)
        
        # Check primary codes
        if dm1[0] and dm2[0] and dm1[0] == dm2[0]:
            return 100
        # Check secondary codes
        if dm1[1] and dm2[1] and dm1[1] == dm2[1]:
            return 90
        # Check cross-match (primary vs secondary)
        if (dm1[0] and dm2[1] and dm1[0] == dm2[1]) or (dm1[1] and dm2[0] and dm1[0] == dm2[0]):
            return 85
        
        # If no match, use fuzzy as fallback
        return int(round(JaroWinkler.similarity(a, b) * 100))
    except Exception:
        return int(round(JaroWinkler.similarity(a, b) * 100))

def _fuzzy_score(a: str, b: str, cfg: MatchConfig) -> int:
    """Calculate fuzzy score based on selected algorithm"""
    if cfg.enable_enhanced_fuzzy and cfg.algorithm != "Ensemble":
        # Enhanced fuzzy already uses ensemble (token_sort + partial)
        return _enhanced_fuzzy(a, b)
    elif cfg.algorithm == "Ensemble":
        # New ensemble mode: use multiple algorithms
        return _ensemble_score(a, b)
    elif cfg.algorithm == "Semantic Matching":
        return _semantic_score(a, b)
    elif cfg.algorithm == "Double Metaphone":
        return _double_metaphone_score(a, b)
    elif cfg.algorithm == "Record Linkage":
        # Record Linkage is handled separately in match_tables
        # Fallback to Jaro-Winkler for individual name scoring
        return int(round(JaroWinkler.similarity(a, b) * 100))
    return _base_fuzzy(a, b, cfg.algorithm)


def _prepare_name(last: str, first: str, cfg: MatchConfig) -> Tuple[str, str]:
    """Normalize a single name pair"""
    last = "" if last is None else str(last)
    first = "" if first is None else str(first)

    if cfg.enable_pre_norm:
        last_norm = normalize_component(last, enable_compound=cfg.enable_double_surname)
        first_norm_raw = normalize_component(first, enable_compound=False)
    else:
        last_norm = last.strip().lower()
        first_norm_raw = first.strip().lower()

    if cfg.enable_variants:
        first_norm = canonical_first_name(first_norm_raw)
    else:
        first_norm = first_norm_raw

    return last_norm, first_norm


def _precompute_normalized_data(
    df: pd.DataFrame,
    last_col: str,
    first_col: str,
    cfg: MatchConfig,
) -> Dict[Any, NormalizedRow]:
    """Pre-compute all normalized names and metadata for a dataframe"""
    normalized = {}
    
    for idx, row in df.iterrows():
        last_raw = str(row.get(last_col, "") or "")
        first_raw = str(row.get(first_col, "") or "")
        
        last_norm, first_norm = _prepare_name(last_raw, first_raw, cfg)
        
        # Pre-compute metadata for quick filtering
        last_len = len(last_norm)
        first_len = len(first_norm)
        last_first_char = last_norm[0] if last_norm else ""
        first_first_char = first_norm[0] if first_norm else ""
        
        # Pre-compute soundex if phonetic matching is enabled
        last_soundex = soundex_code(last_norm) if cfg.enable_phonetic and last_norm else None
        first_soundex = soundex_code(first_norm) if cfg.enable_phonetic and first_norm else None
        
        normalized[idx] = NormalizedRow(
            last_norm=last_norm,
            first_norm=first_norm,
            last_raw=last_raw,
            first_raw=first_raw,
            last_len=last_len,
            first_len=first_len,
            last_first_char=last_first_char,
            first_first_char=first_first_char,
            last_soundex=last_soundex,
            first_soundex=first_soundex,
        )
    
    return normalized


def _quick_filter(
    t1_norm: NormalizedRow,
    t2_norm: NormalizedRow,
    cfg: MatchConfig,
) -> bool:
    """
    Phase 1: Quick filter to eliminate obviously poor matches.
    Returns True if candidate should proceed to detailed scoring.
    """
    # Must have at least one name
    if not t1_norm.last_norm and not t1_norm.first_norm:
        return False
    if not t2_norm.last_norm and not t2_norm.first_norm:
        return False
    
    # Safe missing check
    if cfg.enable_safe_missing:
        if not t1_norm.last_norm or not t2_norm.last_norm:
            return False
    
    # Quick length check: if names are too different in length, unlikely to match well
    if t1_norm.last_norm and t2_norm.last_norm:
        len_diff_ratio = abs(t1_norm.last_len - t2_norm.last_len) / max(t1_norm.last_len, t2_norm.last_len, 1)
        if len_diff_ratio > MAX_NAME_LENGTH_DIFF_RATIO:
            return False
    
    if t1_norm.first_norm and t2_norm.first_norm:
        len_diff_ratio = abs(t1_norm.first_len - t2_norm.first_len) / max(t1_norm.first_len, t2_norm.first_len, 1)
        if len_diff_ratio > MAX_NAME_LENGTH_DIFF_RATIO:
            return False
    
    # First character check: if both have names, first char should match (case-insensitive)
    # This is a very quick filter, but allow phonetic matches to pass
    if t1_norm.last_norm and t2_norm.last_norm:
        if t1_norm.last_first_char and t2_norm.last_first_char:
            if t1_norm.last_first_char != t2_norm.last_first_char:
                # First chars don't match - only allow if phonetic codes match
                if cfg.enable_phonetic and t1_norm.last_soundex and t2_norm.last_soundex:
                    if t1_norm.last_soundex != t2_norm.last_soundex:
                        return False
                    # Phonetic codes match, allow through
                else:
                    # No phonetic matching or no soundex codes, reject
                    return False
    
    return True


def _detailed_scoring(
    t1_norm: NormalizedRow,
    t2_norm: NormalizedRow,
    date_diff: int,
    cfg: MatchConfig,
) -> Tuple[int, int, int]:
    """
    Phase 2: Detailed fuzzy scoring.
    Returns (last_score, first_score, combined_score)
    """
    # Fuzzy scores
    last_score = _fuzzy_score(t1_norm.last_norm, t2_norm.last_norm, cfg)
    first_score = _fuzzy_score(t1_norm.first_norm, t2_norm.first_norm, cfg) if (t1_norm.first_norm or t2_norm.first_norm) else 0

    # When dates match (even with tolerance), be more lenient with names
    if date_diff == 0:
        # Exact date match: boost to name scores
        last_score = min(100, last_score + EXACT_DATE_NAME_BOOST)
        first_score = min(100, first_score + EXACT_DATE_NAME_BOOST)
    elif date_diff <= cfg.date_tolerance_days:
        # Close date match: small boost
        last_score = min(100, last_score + CLOSE_DATE_NAME_BOOST)
        first_score = min(100, first_score + CLOSE_DATE_NAME_BOOST)

    # Calculate combined score with adaptive weighting
    if cfg.enable_safe_missing and (not t1_norm.first_norm or not t2_norm.first_norm):
        combined = last_score
    else:
        # Adaptive weighting: weight based on name length and quality
        # Longer/more unique names get more weight
        last_weight = 0.5  # Default
        first_weight = 0.5  # Default
        
        # Adjust weights based on name lengths (longer = more reliable)
        total_len = (t1_norm.last_len + t2_norm.last_len) + (t1_norm.first_len + t2_norm.first_len)
        if total_len > 0:
            last_portion = (t1_norm.last_len + t2_norm.last_len) / total_len
            first_portion = (t1_norm.first_len + t2_norm.first_len) / total_len
            
            # If one name is significantly longer, weight it more (but cap at 70/30)
            if last_portion > 0.6:
                last_weight = min(0.7, last_portion)
                first_weight = 1.0 - last_weight
            elif first_portion > 0.6:
                first_weight = min(0.7, first_portion)
                last_weight = 1.0 - first_weight
            else:
                # Balanced lengths, use default 50/50
                last_weight = 0.5
                first_weight = 0.5
        
        combined = int(round((last_score * last_weight) + (first_score * first_weight)))

    # Date matching bonus (stronger for exact matches)
    if cfg.enable_date_bonus:
        if date_diff == 0:
            combined = min(100, combined + EXACT_DATE_COMBINED_BOOST)
        elif date_diff <= cfg.date_tolerance_days:
            combined = min(100, combined + CLOSE_DATE_COMBINED_BOOST)

    # Phonetic bonus (only if under threshold)
    if cfg.enable_phonetic and combined < cfg.threshold:
        if t1_norm.last_soundex and t2_norm.last_soundex and t1_norm.last_soundex == t2_norm.last_soundex:
            combined = min(100, combined + PHONETIC_BOOST)

    return last_score, first_score, combined


def _get_confidence_band(score: int) -> Tuple[str, int, int]:
    """
    Returns (confidence_level, min_score, max_score) for a given score.
    Uses confidence bands instead of hard thresholds.
    """
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        return ("High", CONFIDENCE_HIGH_THRESHOLD, 100)
    elif score >= CONFIDENCE_MEDIUM_THRESHOLD:
        return ("Medium", CONFIDENCE_MEDIUM_THRESHOLD, CONFIDENCE_HIGH_THRESHOLD - 1)
    elif score >= CONFIDENCE_LOW_THRESHOLD:
        return ("Low", CONFIDENCE_LOW_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD - 1)
    else:
        return ("Very Low", 0, CONFIDENCE_LOW_THRESHOLD - 1)


def _create_no_match_entry(
    r1: pd.Series,
    t1: pd.DataFrame,
    t2: pd.DataFrame,
    cfg: MatchConfig,
) -> Dict[str, Any]:
    """
    Create a 'No Match' entry for a GSS row with empty Opera fields.
    Extracted to avoid code duplication.
    """
    merged: Dict[str, Any] = {}
    # Copy T1 columns
    for col in t1.columns:
        if not col.startswith("__"):
            merged[f"{PREFIX_T1}{col}"] = r1.get(col)
    # Add empty T2 columns
    for col in t2.columns:
        if not col.startswith("__"):
            merged[f"{PREFIX_T2}{col}"] = None
    merged["LastName_Score"] = None
    merged["FirstName_Score"] = None
    merged["Combined_Score"] = None
    merged["Confidence"] = "No Match"
    if cfg.t1_itr and f"{PREFIX_T1}{cfg.t1_itr}" in merged:
        merged["ITR_Bucket"] = categorize_itr(merged[f"{PREFIX_T1}{cfg.t1_itr}"])
    else:
        merged["ITR_Bucket"] = None
    return merged


def match_tables(
    t1: pd.DataFrame,
    t2: pd.DataFrame,
    cfg: MatchConfig,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> pd.DataFrame:
    """
    Main matching function. Handles Record Linkage separately, 
    all other algorithms use the standard matching pipeline.
    """
    # Handle Record Linkage separately (it uses a different approach)
    if cfg.algorithm == "Record Linkage":
        from .record_linkage_matcher import match_with_recordlinkage
        return match_with_recordlinkage(
            t1,
            t2,
            cfg.t1_last,
            cfg.t1_first,
            cfg.t1_date,
            cfg.t2_last,
            cfg.t2_first,
            cfg.t2_date,
            threshold=cfg.threshold / 100.0,
            show_all_matches=cfg.show_all_matches,
            progress_cb=progress_cb,
        )

    t1 = t1.copy()
    t2 = t2.copy()

    # Normalize dates
    t1["__date"] = t1[cfg.t1_date].apply(parse_date_safe)
    t2["__date"] = t2[cfg.t2_date].apply(parse_date_safe)
    t2["__date_key"] = t2["__date"].apply(lambda dt: dt.date() if dt else None)

    # Pre-compute all normalized names (OPTIMIZATION 1: Do once, reuse)
    t1_normalized = _precompute_normalized_data(t1, cfg.t1_last, cfg.t1_first, cfg)
    t2_normalized = _precompute_normalized_data(t2, cfg.t2_last, cfg.t2_first, cfg)

    # Build date index for Opera rows
    t2_by_date: Dict[date, list[tuple[int, pd.Series]]] = {}
    for idx, row in t2.iterrows():
        date_key = row.get("__date_key")
        if date_key is None:
            continue
        t2_by_date.setdefault(date_key, []).append((idx, row))

    results = []
    total = len(t1)
    if total == 0 or len(t2) == 0:
        return pd.DataFrame()

    # Global deduplication: track which GSS-Opera pairs we've already added
    # Only needed when show_all_matches is enabled
    global_seen_pairs = set() if cfg.show_all_matches else None

    for i1, r1 in t1.iterrows():
        matching_rows = []  # Collect all matches above threshold

        date1 = r1["__date"]
        date1_obj = date1.date() if date1 else None
        
        if date1_obj is None:
            # No date in GSS row
            if cfg.show_all_matches:
                merged = _create_no_match_entry(r1, t1, t2, cfg)
                results.append(merged)
            # Throttled progress update
            if progress_cb is not None and (i1 + 1) % max(1, total // (100 // PROGRESS_UPDATE_INTERVAL_PERCENT)) == 0:
                pct = int((i1 + 1) * 100 / total)
                progress_cb(pct)
            continue

        # Get pre-computed normalized data for this GSS row
        t1_norm = t1_normalized.get(i1)
        if not t1_norm:
            if progress_cb is not None:
                pct = int((i1 + 1) * 100 / total)
                progress_cb(pct)
            continue

        # Find candidates within date tolerance
        candidates = []
        seen_indices = set()
        if cfg.date_tolerance_days >= 0:
            if date1_obj in t2_by_date:
                for cand in t2_by_date[date1_obj]:
                    if cand[0] not in seen_indices:
                        candidates.append(cand)
                        seen_indices.add(cand[0])
            
            if cfg.date_tolerance_days > 0:
                for day_offset in range(1, cfg.date_tolerance_days + 1):
                    check_date = date1_obj - timedelta(days=day_offset)
                    if check_date in t2_by_date:
                        for cand in t2_by_date[check_date]:
                            if cand[0] not in seen_indices:
                                candidates.append(cand)
                                seen_indices.add(cand[0])
                    check_date = date1_obj + timedelta(days=day_offset)
                    if check_date in t2_by_date:
                        for cand in t2_by_date[check_date]:
                            if cand[0] not in seen_indices:
                                candidates.append(cand)
                                seen_indices.add(cand[0])

        if not candidates:
            if cfg.show_all_matches:
                merged = _create_no_match_entry(r1, t1, t2, cfg)
                results.append(merged)
            # Throttled progress update
            if progress_cb is not None and (i1 + 1) % max(1, total // (100 // PROGRESS_UPDATE_INTERVAL_PERCENT)) == 0:
                pct = int((i1 + 1) * 100 / total)
                progress_cb(pct)
            continue

        # TWO-PHASE MATCHING (OPTIMIZATION 3)
        for i2, r2 in candidates:
            date2 = r2["__date"]
            if date2 is None:
                continue

            date2_obj = date2.date()
            date_diff = abs((date1_obj - date2_obj).days)

            # Get pre-computed normalized data for this Opera row
            t2_norm = t2_normalized.get(i2)
            if not t2_norm:
                continue

            # PHASE 1: Quick filter (OPTIMIZATION 2: Early exit conditions)
            if not _quick_filter(t1_norm, t2_norm, cfg):
                continue

            # PHASE 2: Detailed scoring
            last_score, first_score, combined = _detailed_scoring(t1_norm, t2_norm, date_diff, cfg)

            # Multi-pass matching: different thresholds based on match quality
            if cfg.enable_multi_pass:
                # Pass 1: Strict (exact date, high threshold) -> High confidence
                if date_diff == 0 and combined >= cfg.threshold:
                    confidence_level = "High"
                # Pass 2: Medium (date tolerance, medium threshold) -> Medium confidence
                elif date_diff <= cfg.date_tolerance_days and combined >= max(0, cfg.threshold - MULTI_PASS_MEDIUM_THRESHOLD_REDUCTION):
                    confidence_level = "Medium"
                # Pass 3: Lenient (date tolerance, lower threshold) -> Low confidence
                elif date_diff <= cfg.date_tolerance_days and combined >= max(0, cfg.threshold - MULTI_PASS_LENIENT_THRESHOLD_REDUCTION):
                    confidence_level = "Low"
                else:
                    # Below all thresholds, skip
                    continue
            else:
                # Single-pass: use original logic
                confidence_level, min_score, max_score = _get_confidence_band(combined)
                effective_threshold = cfg.threshold
                if date_diff <= cfg.date_tolerance_days:
                    effective_threshold = max(0, cfg.threshold - DATE_TOLERANCE_THRESHOLD_REDUCTION)
                if combined < effective_threshold:
                    continue

            # Store this match
            matching_rows.append((i2, r2, last_score, first_score, combined, date_diff, confidence_level))

        # Process matches
        if cfg.show_all_matches:
            # Deduplicate: keep only one match per Opera row per GSS row
            # Prefer: exact date match (date_diff=0), then highest score
            seen_pairs = {}  # (i1, idx2) -> best match
            for match in matching_rows:
                idx2 = match[0]
                pair_key = (i1, idx2)
                if pair_key not in seen_pairs:
                    seen_pairs[pair_key] = match
                else:
                    # Keep the better match: exact date first, then highest score
                    existing = seen_pairs[pair_key]
                    existing_date_diff = existing[5]
                    new_date_diff = match[5]
                    existing_score = existing[4]
                    new_score = match[4]
                    
                    # Prefer exact date match (date_diff=0)
                    if new_date_diff == 0 and existing_date_diff != 0:
                        seen_pairs[pair_key] = match
                    elif existing_date_diff == 0 and new_date_diff != 0:
                        # Keep existing
                        pass
                    elif new_score > existing_score:
                        # Same date match quality, prefer higher score
                        seen_pairs[pair_key] = match
            rows_to_add = list(seen_pairs.values())
            if not matching_rows:
                merged = _create_no_match_entry(r1, t1, t2, cfg)
                results.append(merged)
        else:
            if matching_rows:
                matching_rows.sort(key=lambda x: (x[5], -x[4]))  # date_diff (0=exact), then -score
                rows_to_add = [matching_rows[0]]
            else:
                rows_to_add = []

        for idx2, r2, ls, fs, combined, date_diff, conf_level in rows_to_add:
            # Global deduplication check (only when show_all_matches is enabled)
            if global_seen_pairs is not None:
                pair_key = (i1, idx2)
                if pair_key in global_seen_pairs:
                    continue  # Skip duplicate GSS-Opera pair
                global_seen_pairs.add(pair_key)
            
            merged: Dict[str, Any] = {}

            for col in t1.columns:
                if not col.startswith("__"):
                    merged[f"{PREFIX_T1}{col}"] = r1.get(col)

            for col in t2.columns:
                if not col.startswith("__"):
                    merged[f"{PREFIX_T2}{col}"] = r2.get(col)

            merged["LastName_Score"] = ls
            merged["FirstName_Score"] = fs
            merged["Combined_Score"] = combined
            merged["Confidence"] = conf_level

            if cfg.t1_itr and f"{PREFIX_T1}{cfg.t1_itr}" in merged:
                merged["ITR_Bucket"] = categorize_itr(merged[f"{PREFIX_T1}{cfg.t1_itr}"])
            else:
                merged["ITR_Bucket"] = None

            results.append(merged)

        # Throttled progress update
        if progress_cb is not None:
            if (i1 + 1) % max(1, total // (100 // PROGRESS_UPDATE_INTERVAL_PERCENT)) == 0 or (i1 + 1) == total:
                pct = int((i1 + 1) * 100 / total)
                progress_cb(pct)

    return pd.DataFrame(results)
