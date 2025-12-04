
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
import re

import pandas as pd


def parse_date_safe(value) -> Optional[datetime]:
    """
    Enhanced date parser that handles multiple formats and edge cases.
    Tries multiple parsing strategies for better date matching.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    
    # Convert to string
    s = str(value).strip()
    if not s or s.lower() in ('nan', 'none', 'null', ''):
        return None
    
    # Try Excel serial number format (common in Excel exports)
    try:
        if isinstance(value, (int, float)) and 1 <= value <= 100000:
            # Excel date serial number (days since 1900-01-01)
            excel_epoch = datetime(1899, 12, 30)
            dt = excel_epoch + pd.Timedelta(days=int(value))
            return dt
    except Exception:
        pass
    
    # Try pandas parsing with multiple strategies
    strategies = [
        # Strategy 1: Try with dayfirst=False (US format: MM/DD/YYYY)
        lambda: pd.to_datetime(s, errors="raise", dayfirst=False, infer_datetime_format=True),
        # Strategy 2: Try with dayfirst=True (European format: DD/MM/YYYY)
        lambda: pd.to_datetime(s, errors="raise", dayfirst=True, infer_datetime_format=True),
        # Strategy 3: Try with format hints for common patterns
        lambda: _try_common_formats(s),
        # Strategy 4: Try with fuzzy parsing (more lenient)
        lambda: pd.to_datetime(s, errors="raise", infer_datetime_format=False, fuzzy=True),
    ]
    
    for strategy in strategies:
        try:
            dt = strategy()
            if isinstance(dt, pd.Timestamp):
                return dt.to_pydatetime()
            if isinstance(dt, datetime):
                return dt
        except Exception:
            continue
    
    # Last resort: try regex-based parsing for common patterns
    dt = _regex_date_parse(s)
    if dt:
        return dt
    
    return None


def _try_common_formats(date_str: str) -> datetime:
    """Try parsing with common date format patterns"""
    common_formats = [
        "%Y-%m-%d",           # 2024-01-15
        "%d/%m/%Y",           # 15/01/2024
        "%m/%d/%Y",           # 01/15/2024
        "%d-%m-%Y",           # 15-01-2024
        "%m-%d-%Y",           # 01-15-2024
        "%Y/%m/%d",           # 2024/01/15
        "%d.%m.%Y",           # 15.01.2024
        "%m.%d.%Y",           # 01.15.2024
        "%d %m %Y",           # 15 01 2024
        "%m %d %Y",           # 01 15 2024
        "%Y %m %d",           # 2024 01 15
        "%d/%m/%y",           # 15/01/24
        "%m/%d/%y",           # 01/15/24
        "%d-%m-%y",           # 15-01-24
        "%m-%d-%y",           # 01-15-24
        "%d.%m.%y",           # 15.01.24
        "%m.%d.%y",           # 01.15.24
        "%d %B %Y",           # 15 January 2024
        "%B %d, %Y",          # January 15, 2024
        "%d %b %Y",           # 15 Jan 2024
        "%b %d, %Y",          # Jan 15, 2024
    ]
    
    for fmt in common_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    
    raise ValueError(f"Could not parse date: {date_str}")


def _regex_date_parse(date_str: str) -> Optional[datetime]:
    """Fallback regex-based date parsing for edge cases"""
    # Remove common prefixes/suffixes
    date_str = re.sub(r'^(date|on|at|from|to):?\s*', '', date_str, flags=re.IGNORECASE)
    date_str = date_str.strip()
    
    # Pattern 1: DD/MM/YYYY or MM/DD/YYYY (ambiguous)
    match = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', date_str)
    if match:
        d1, d2, year = match.groups()
        d1, d2, year = int(d1), int(d2), int(year)
        # Try both interpretations, prefer valid date
        for day, month in [(d1, d2), (d2, d1)]:
            try:
                if 1 <= month <= 12 and 1 <= day <= 31:
                    dt = datetime(year, month, day)
                    return dt
            except ValueError:
                continue
    
    # Pattern 2: DD/MM/YY or MM/DD/YY (2-digit year)
    match = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{2})$', date_str)
    if match:
        d1, d2, yy = match.groups()
        d1, d2, yy = int(d1), int(d2), int(yy)
        # Assume years 00-30 are 2000-2030, 31-99 are 1931-1999
        year = 2000 + yy if yy <= 30 else 1900 + yy
        for day, month in [(d1, d2), (d2, d1)]:
            try:
                if 1 <= month <= 12 and 1 <= day <= 31:
                    dt = datetime(year, month, day)
                    return dt
            except ValueError:
                continue
    
    # Pattern 3: YYYY-MM-DD (ISO format)
    match = re.match(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$', date_str)
    if match:
        year, month, day = map(int, match.groups())
        try:
            if 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day)
        except ValueError:
            pass
    
    # Pattern 4: Extract date from datetime string
    match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
    if match:
        year, month, day = map(int, match.groups())
        try:
            if 1 <= month <= 12 and 1 <= day <= 31:
                return datetime(year, month, day)
        except ValueError:
            pass
    
    return None
