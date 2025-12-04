
from __future__ import annotations
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QCheckBox,
    QGroupBox,
)

from ..settings import FUZZY_ALGORITHM_NAMES, DEFAULT_MATCH_THRESHOLD


class SettingsDialog(QDialog):
    def __init__(self, cfg: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.cfg = cfg or {}

        layout = QVBoxLayout(self)

        # Theme
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.cfg.get("theme", "dark"))
        row1.addWidget(self.theme_combo)
        layout.addLayout(row1)

        # Base algorithm
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Base fuzzy algorithm:"))
        self.alg_combo = QComboBox()
        self.alg_combo.addItems(FUZZY_ALGORITHM_NAMES)
        self.alg_combo.setCurrentText(
            self.cfg.get("default_algorithm", FUZZY_ALGORITHM_NAMES[0])
        )
        row2.addWidget(self.alg_combo)
        layout.addLayout(row2)

        # Threshold
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Default threshold:"))
        self.th_spin = QSpinBox()
        self.th_spin.setRange(0, 100)
        self.th_spin.setValue(
            int(self.cfg.get("default_threshold", DEFAULT_MATCH_THRESHOLD))
        )
        row3.addWidget(self.th_spin)
        layout.addLayout(row3)

        # Name Intelligence box
        name_box = QGroupBox("Name Intelligence")
        nb = QVBoxLayout(name_box)

        self.cb_pre_norm = QCheckBox("Enable Name Pre-Normalization")
        self.cb_pre_norm.setChecked(self.cfg.get("name_pre_normalization", True))

        self.cb_enhanced = QCheckBox("Enhanced Fuzzy (token_sort + partial)")
        self.cb_enhanced.setChecked(self.cfg.get("enhanced_fuzzy", True))

        self.cb_date_bonus = QCheckBox("Date Match Bonus (+5)")
        self.cb_date_bonus.setChecked(self.cfg.get("date_bonus", True))

        self.cb_phonetic = QCheckBox("Phonetic Matching (Soundex-based)")
        self.cb_phonetic.setChecked(self.cfg.get("phonetic_matching", False))

        self.cb_variants = QCheckBox("First-Name Variant Normalization")
        self.cb_variants.setChecked(self.cfg.get("firstname_variants", True))

        self.cb_double = QCheckBox("Detect Compound / Double Surnames")
        self.cb_double.setChecked(self.cfg.get("double_surname", True))

        self.cb_missing = QCheckBox("Safe Missing-Name Handling")
        self.cb_missing.setChecked(self.cfg.get("safe_missing", True))

        for cb in (
            self.cb_pre_norm,
            self.cb_enhanced,
            self.cb_date_bonus,
            self.cb_phonetic,
            self.cb_variants,
            self.cb_double,
            self.cb_missing,
        ):
            nb.addWidget(cb)

        layout.addWidget(name_box)

        # Buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_settings(self) -> Dict[str, Any]:
        return {
            "theme": self.theme_combo.currentText(),
            "default_algorithm": self.alg_combo.currentText(),
            "default_threshold": self.th_spin.value(),
            "name_pre_normalization": self.cb_pre_norm.isChecked(),
            "enhanced_fuzzy": self.cb_enhanced.isChecked(),
            "date_bonus": self.cb_date_bonus.isChecked(),
            "phonetic_matching": self.cb_phonetic.isChecked(),
            "firstname_variants": self.cb_variants.isChecked(),
            "double_surname": self.cb_double.isChecked(),
            "safe_missing": self.cb_missing.isChecked(),
        }
