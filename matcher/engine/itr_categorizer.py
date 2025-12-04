
from __future__ import annotations
from typing import Optional


def categorize_itr(value) -> Optional[int]:
    """
    Bucket:
      0–7   -> 0
      8     -> 8
      9–10  -> 10
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None

    if v <= 7:
        return 0
    elif v == 8:
        return 8
    elif v >= 9:
        return 10
    return None
