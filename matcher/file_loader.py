
from __future__ import annotations
import os
from typing import Optional

import pandas as pd


def read_full(path: str) -> Optional[pd.DataFrame]:
    """
    Supports:
      - Excel (.xlsx, .xls)
      - CSV
      - Opera TXT raw log format
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)

        if ext == ".csv":
            return pd.read_csv(path)

        if ext == ".txt":
            rows = []
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split(",")
                    if len(parts) < 6:
                        continue

                    user = parts[0].strip()
                    time = parts[1].strip()
                    date = parts[2].strip()
                    action = parts[4].strip()
                    tail = ",".join(parts[5:]).strip()

                    last = ""
                    first = ""

                    # Extract "Last, First" before the phrase "... has ..."
                    # Example tail:
                    #   "Gardiner, Norman has checked in Inspected room 0214 ..."
                    tail_lower = tail.lower()
                    idx = tail_lower.find(" has ")
                    if idx != -1:
                        name_part = tail[:idx].strip()
                        if "," in name_part:
                            segs = [x.strip() for x in name_part.split(",", 1)]
                            if len(segs) == 2:
                                last, first = segs
                        elif name_part:
                            # Single-token name – treat as last name only
                            last = name_part

                    rows.append(
                        {
                            "USERID": user,
                            "Time": time,
                            "Date": date,
                            "Action": action,
                            "LastName": last,
                            "FirstName": first,
                            "RawText": tail,
                        }
                    )

            if not rows:
                return None
            return pd.DataFrame(rows)

        return None
    except Exception as e:
        # Log error for debugging but don't expose to user unless critical
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Error loading file {path}: {e}")
        return None
