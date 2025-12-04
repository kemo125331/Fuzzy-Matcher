"""
Application-wide constants
"""

# Column prefixes
PREFIX_T1 = "T1_"
PREFIX_T2 = "T2_"
LABEL_GSS = "GSS "
LABEL_OPERA = "Opera "

# Matching algorithm constants
EXACT_DATE_NAME_BOOST = 3
EXACT_DATE_COMBINED_BOOST = 10
CLOSE_DATE_NAME_BOOST = 1
CLOSE_DATE_COMBINED_BOOST = 5
PHONETIC_BOOST = 15
DATE_TOLERANCE_THRESHOLD_REDUCTION = 8

# Confidence thresholds
CONFIDENCE_HIGH_THRESHOLD = 90
CONFIDENCE_MEDIUM_THRESHOLD = 80
CONFIDENCE_LOW_THRESHOLD = 70

# Multi-pass matching thresholds
MULTI_PASS_STRICT_THRESHOLD = 0  # No reduction for strict pass
MULTI_PASS_MEDIUM_THRESHOLD_REDUCTION = 10
MULTI_PASS_LENIENT_THRESHOLD_REDUCTION = 15

# Name length difference threshold (for quick filter)
MAX_NAME_LENGTH_DIFF_RATIO = 0.5

# Progress update frequency (update every N% instead of every row)
PROGRESS_UPDATE_INTERVAL_PERCENT = 1




