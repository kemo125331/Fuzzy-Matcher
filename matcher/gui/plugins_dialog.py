
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)


@dataclass
class PluginInfo:
    name: str
    module: Any
    enabled: bool
    description: str = ""
    stage: str = "post_match"


class PluginManagerDialog(QDialog):
    def __init__(self, plugins: List[PluginInfo], cfg: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugin Manager")
        self.plugins = plugins
        self.cfg = cfg or {}

        layout = QVBoxLayout(self)

        self.table = QTableWidget(len(self.plugins), 4)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Stage", "Enabled", "Description"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        for r, p in enumerate(self.plugins):
            self.table.setItem(r, 0, QTableWidgetItem(p.name))
            self.table.setItem(r, 1, QTableWidgetItem(p.stage))
            self.table.setItem(r, 2, QTableWidgetItem("Yes" if p.enabled else "No"))
            self.table.setItem(r, 3, QTableWidgetItem(p.description or ""))

        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.toggle_btn = QPushButton("Toggle Selected")
        close_btn = QPushButton("Close")
        self.toggle_btn.clicked.connect(self.toggle_selected)
        close_btn.clicked.connect(self.accept)
        btn_row.addStretch(1)
        btn_row.addWidget(self.toggle_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def toggle_selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.plugins):
            return

        p = self.plugins[row]
        p.enabled = not p.enabled
        self.table.setItem(row, 2, QTableWidgetItem("Yes" if p.enabled else "No"))

        self.cfg.setdefault("plugins", {})
        self.cfg["plugins"][p.name] = p.enabled
