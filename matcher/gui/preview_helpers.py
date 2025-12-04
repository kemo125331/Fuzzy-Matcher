from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem


def populate_table_from_dataframe(
    table: QTableWidget,
    df: pd.DataFrame,
    preferred_columns: Optional[Iterable[str]] = None,
    max_rows: int = 5,
) -> None:
    """
    Fill a QTableWidget with a small preview of a DataFrame.
    """
    if df is None or df.empty:
        table.setRowCount(0)
        table.setColumnCount(0)
        return

    if preferred_columns:
        cols = [c for c in preferred_columns if c in df.columns]
        df_preview = df[cols] if cols else df
    else:
        df_preview = df

    df_head = df_preview.head(max_rows)

    table.setColumnCount(len(df_head.columns))
    table.setRowCount(len(df_head.index))
    table.setHorizontalHeaderLabels([str(c) for c in df_head.columns])

    for row_idx, (_, row) in enumerate(df_head.iterrows()):
        for col_idx, value in enumerate(row):
            item = QTableWidgetItem("" if value is None else str(value))
            table.setItem(row_idx, col_idx, item)





