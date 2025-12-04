
from __future__ import annotations
import os
import re
import sys
import importlib.util
from typing import List, Dict, Any

import pandas as pd
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QProgressBar,
    QMessageBox,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QCheckBox,
)
from PyQt6.QtCore import Qt

from ..settings import DEFAULT_MATCH_THRESHOLD, FUZZY_ALGORITHM_NAMES
from ..config_manager import load_config, save_config
from ..file_loader import read_full
from ..engine import MatchConfig
from .theme_loader import apply_theme
from .threads import MatchWorker
from .preview_helpers import populate_table_from_dataframe
from .settings_dialog import SettingsDialog
from .plugins_dialog import PluginManagerDialog, PluginInfo


def load_plugins(cfg: Dict[str, Any], log=None) -> List[PluginInfo]:
    plugins: List[PluginInfo] = []
    base_dir = os.path.dirname(os.path.dirname(__file__))
    plugins_dir = os.path.join(base_dir, "plugins")
    if not os.path.isdir(plugins_dir):
        return plugins

    enabled_map = cfg.get("plugins", {})

    for fname in os.listdir(plugins_dir):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue
        path = os.path.join(plugins_dir, fname)
        mod_name = f"matcher_plugin_{os.path.splitext(fname)[0]}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            pname = getattr(mod, "PLUGIN_NAME", os.path.splitext(fname)[0])
            desc = getattr(mod, "PLUGIN_DESCRIPTION", "")
            stage = getattr(mod, "PLUGIN_STAGE", "post_match")
            enabled = enabled_map.get(pname, True)
            info = PluginInfo(
                name=pname,
                module=mod,
                enabled=enabled,
                description=desc,
                stage=stage,
            )
            plugins.append(info)
            if log:
                log(f"[Plugin] Loaded: {pname} (stage={stage}, enabled={enabled})")
        except Exception as e:
            if log:
                log(f"[Plugin] Failed to load {fname}: {e}")

    return plugins


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fuzzy Matcher V7.4.1 – GSS ↔ Opera")
        self.resize(1300, 800)

        self.cfg = load_config() or {}
        self.gss_df: pd.DataFrame | None = None
        self.opera_df: pd.DataFrame | None = None
        self.current_df: pd.DataFrame | None = None
        self.match_worker: MatchWorker | None = None
        self.plugins: List[PluginInfo] = []
        self._mapping_collapsed = False
        self._gss_automap_ok = False
        self._opera_automap_ok = False

        self._build_ui()
        self._apply_settings_to_ui()
        self.plugins = load_plugins(self.cfg, log=self.log)
        self._refresh_plugin_list()
        self.validate_ready_state()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        top_row = QHBoxLayout()
        lbl_title = QLabel("Fuzzy Matcher V7.4.1 – GSS ↔ Opera")
        top_row.addWidget(lbl_title)
        top_row.addStretch(1)
        btn_settings = QPushButton("Settings")
        top_row.addWidget(btn_settings)
        outer.addLayout(top_row)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(main_split, 1)

        # LEFT PANEL
        left = QWidget()
        left_layout = QVBoxLayout(left)

        files_box = QGroupBox("Files")
        fgrid = QGridLayout(files_box)

        fgrid.addWidget(QLabel("GSS File"), 0, 0)
        self.t1_path_edit = QLineEdit()
        btn_t1 = QPushButton("Browse")
        fgrid.addWidget(self.t1_path_edit, 0, 1)
        fgrid.addWidget(btn_t1, 0, 2)

        fgrid.addWidget(QLabel("Opera File"), 1, 0)
        self.t2_path_edit = QLineEdit()
        btn_t2 = QPushButton("Browse")
        fgrid.addWidget(self.t2_path_edit, 1, 1)
        fgrid.addWidget(btn_t2, 1, 2)

        self.btn_toggle_mapping = QPushButton("Hide Column Mapping")
        fgrid.addWidget(self.btn_toggle_mapping, 2, 0, 1, 3)

        left_layout.addWidget(files_box)

        self.map_box = QGroupBox("Column Mapping")
        mg = QGridLayout(self.map_box)

        mg.addWidget(QLabel("GSS Last"), 0, 0)
        self.t1_last = QComboBox()
        mg.addWidget(self.t1_last, 0, 1)

        mg.addWidget(QLabel("GSS First"), 1, 0)
        self.t1_first = QComboBox()
        mg.addWidget(self.t1_first, 1, 1)

        mg.addWidget(QLabel("GSS Arrival Date"), 2, 0)
        self.t1_date = QComboBox()
        mg.addWidget(self.t1_date, 2, 1)

        mg.addWidget(QLabel("GSS ITR"), 3, 0)
        self.t1_itr = QComboBox()
        mg.addWidget(self.t1_itr, 3, 1)

        mg.addWidget(QLabel("Opera Last"), 4, 0)
        self.t2_last = QComboBox()
        mg.addWidget(self.t2_last, 4, 1)

        mg.addWidget(QLabel("Opera First"), 5, 0)
        self.t2_first = QComboBox()
        mg.addWidget(self.t2_first, 5, 1)

        mg.addWidget(QLabel("Opera Date"), 6, 0)
        self.t2_date = QComboBox()
        mg.addWidget(self.t2_date, 6, 1)

        mg.addWidget(QLabel("Opera User"), 7, 0)
        self.t2_user = QComboBox()
        mg.addWidget(self.t2_user, 7, 1)

        left_layout.addWidget(self.map_box)

        preview_box = QGroupBox("Data Preview")
        pv_layout = QVBoxLayout(preview_box)

        self.gss_preview_label = QLabel("GSS Preview (first 5 rows)")
        self.gss_preview = QTableWidget()
        self.gss_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gss_preview.setColumnCount(0)
        self.gss_preview.setRowCount(0)
        self.gss_auto_label = QLabel("")

        self.opera_preview_label = QLabel("Opera Preview (first 5 rows)")
        self.opera_preview = QTableWidget()
        self.opera_preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.opera_preview.setColumnCount(0)
        self.opera_preview.setRowCount(0)
        self.opera_auto_label = QLabel("")

        pv_layout.addWidget(self.gss_preview_label)
        pv_layout.addWidget(self.gss_preview)
        pv_layout.addWidget(self.gss_auto_label)
        pv_layout.addSpacing(8)
        pv_layout.addWidget(self.opera_preview_label)
        pv_layout.addWidget(self.opera_preview)
        pv_layout.addWidget(self.opera_auto_label)

        left_layout.addWidget(preview_box)

        match_box = QGroupBox("Matching")
        g = QGridLayout(match_box)

        g.addWidget(QLabel("Base Algorithm"), 0, 0)
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(FUZZY_ALGORITHM_NAMES)
        # Set Ensemble as initial default (will be overridden by saved preference if exists)
        if "Ensemble" in FUZZY_ALGORITHM_NAMES:
            self.algo_combo.setCurrentText("Ensemble")
        self.algo_combo.setToolTip(
            "Ensemble (recommended): Combines multiple algorithms for best accuracy.\n"
            "Jaro-Winkler: Best for names with typos.\n"
            "Weighted Ratio: General purpose matching.\n"
            "Partial Ratio: Good for substring matches."
        )
        g.addWidget(self.algo_combo, 0, 1)

        g.addWidget(QLabel("Threshold"), 1, 0)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setValue(DEFAULT_MATCH_THRESHOLD)
        g.addWidget(self.threshold_spin, 1, 1)

        g.addWidget(QLabel("Date Tolerance (days)"), 2, 0)
        self.date_tolerance_spin = QSpinBox()
        self.date_tolerance_spin.setRange(0, 7)
        self.date_tolerance_spin.setValue(0)
        self.date_tolerance_spin.setToolTip("Allow dates within N days to match (0 = exact match only). Recommended: 1-3 days for better matching.")
        g.addWidget(self.date_tolerance_spin, 2, 1)

        self.show_all_matches_check = QCheckBox("Show all matches (not just best)")
        self.show_all_matches_check.setToolTip("If checked, shows all matches above threshold. If unchecked, shows only the best match per GSS row.")
        g.addWidget(self.show_all_matches_check, 3, 0, 1, 2)

        self.run_all_algorithms_check = QCheckBox("Run All Algorithms & Export Comparison")
        self.run_all_algorithms_check.setToolTip("If checked, runs all algorithms and exports each result to a separate Excel workbook for comparison.")
        g.addWidget(self.run_all_algorithms_check, 4, 0, 1, 2)

        self.btn_run = QPushButton("Run Match")
        self.btn_run.setEnabled(False)
        g.addWidget(self.btn_run, 4, 0, 1, 2)

        left_layout.addWidget(match_box)

        export_box = QGroupBox("Export")
        eg = QGridLayout(export_box)

        eg.addWidget(QLabel("Folder"), 0, 0)
        self.export_folder_edit = QLineEdit()
        btn_exp = QPushButton("...")
        eg.addWidget(self.export_folder_edit, 0, 1)
        eg.addWidget(btn_exp, 0, 2)

        eg.addWidget(QLabel("Base filename"), 1, 0)
        self.base_name_edit = QLineEdit("match_results")
        eg.addWidget(self.base_name_edit, 1, 1, 1, 2)

        left_layout.addWidget(export_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Idle")
        left_layout.addWidget(self.progress_bar)

        left_layout.addStretch(1)
        main_split.addWidget(left)

        # RIGHT PANEL
        right = QWidget()
        rlayout = QVBoxLayout(right)

        plug_box = QGroupBox("Plugins")
        pv = QVBoxLayout(plug_box)
        self.plugin_list = QListWidget()
        pv.addWidget(self.plugin_list)
        rlayout.addWidget(plug_box)

        rlayout.addWidget(QLabel("Log"))
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        rlayout.addWidget(self.log_edit)

        main_split.addWidget(right)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 2)

        # Connections
        btn_t1.clicked.connect(self.load_t1)
        btn_t2.clicked.connect(self.load_t2)
        btn_exp.clicked.connect(self.select_export_folder)
        self.btn_run.clicked.connect(self.run_match)
        self.btn_toggle_mapping.clicked.connect(self.toggle_mapping_visibility)
        btn_settings.clicked.connect(self.open_settings)
        self.plugin_list.itemDoubleClicked.connect(self.toggle_plugin_from_list)

        for cb in (
            self.t1_last,
            self.t1_first,
            self.t1_date,
            self.t1_itr,
            self.t2_last,
            self.t2_first,
            self.t2_date,
            self.t2_user,
            self.algo_combo,
        ):
            cb.currentIndexChanged.connect(self.validate_ready_state)

        self.threshold_spin.valueChanged.connect(self.validate_ready_state)

    @staticmethod
    def _normalize_column_hint(label: str) -> str:
        if not label:
            return ""
        hint = label.lower()
        hint = hint.replace("_", " ")
        hint = re.sub(r"[^a-z0-9]+", " ", hint)
        return hint.strip()

    def set_mapping_visible(self, visible: bool):
        self._mapping_collapsed = not visible
        self.map_box.setVisible(visible)
        if visible:
            self.btn_toggle_mapping.setText("Hide Column Mapping")
        else:
            self.btn_toggle_mapping.setText("Show Column Mapping")

    def toggle_mapping_visibility(self):
        self.set_mapping_visible(self._mapping_collapsed)

    def _maybe_auto_hide_mapping(self):
        if (
            not self._mapping_collapsed
            and self._gss_automap_ok
            and self._opera_automap_ok
        ):
            self.set_mapping_visible(False)

    def _set_combo_if_found(self, combo: QComboBox, text: str) -> bool:
        if not text:
            return False
        for idx in range(combo.count()):
            if combo.itemText(idx) == text:
                combo.setCurrentIndex(idx)
                return True
        target = text.strip().lower()
        for idx in range(combo.count()):
            if combo.itemText(idx).strip().lower() == target:
                combo.setCurrentIndex(idx)
                return True
        return False

    def _apply_saved_mapping(self, combo_map: Dict[str, QComboBox]) -> Dict[str, str]:
        applied: Dict[str, str] = {}
        col_map = self.cfg.get("column_map") or {}
        if not col_map:
            return applied
        for key, combo in combo_map.items():
            saved = col_map.get(key)
            if saved and self._set_combo_if_found(combo, saved):
                applied[key] = saved

        # If a saved mapping reuses the same column for multiple roles,
        # treat it as invalid so the auto-detector can re-map.
        if applied:
            used_values = list(applied.values())
            if len(set(used_values)) < len(used_values):
                # Clear any selections that came from a bad mapping
                for combo in combo_map.values():
                    if combo.count() > 0:
                        combo.setCurrentIndex(0)
                return {}

        return applied

    def _pick_column_by_patterns(
        self,
        normalized_cols: List[tuple[str, str]],
        pattern_groups: List[tuple[str, ...]],
        excludes: tuple[str, ...] = (),
        used_columns: set[str] | None = None,
    ) -> str | None:
        used = used_columns or set()
        for tokens in pattern_groups:
            for original, norm in normalized_cols:
                if original in used:
                    continue
                if excludes and any(ex in norm for ex in excludes):
                    continue
                if all(token in norm for token in tokens):
                    return original
        return None

    @staticmethod
    def _is_composite_name_column(label: str) -> bool:
        if not label:
            return False
        lower = label.strip().lower()
        return (
            "name" in lower
            and "first" not in lower
            and "last" not in lower
            and "surname" not in lower
        )

    @staticmethod
    def _needs_header_fix(df: pd.DataFrame) -> bool:
        if df.empty:
            return False
        invalid = 0
        for col in df.columns:
            text = str(col).strip().lower()
            if not text or text.startswith("unnamed"):
                invalid += 1
        return invalid >= max(1, len(df.columns) // 2)

    @staticmethod
    def _find_header_row_candidate(df: pd.DataFrame) -> int | None:
        probe = min(6, len(df))
        for idx in range(probe):
            row = df.iloc[idx]
            filled = [
                str(val).strip()
                for val in row.tolist()
                if isinstance(val, str) and str(val).strip()
            ]
            if len(filled) >= max(2, len(row) // 3):
                return idx
        return None

    @staticmethod
    def _promote_row_to_header(df: pd.DataFrame, row_idx: int) -> pd.DataFrame:
        header_row = df.iloc[row_idx]
        new_cols = []
        for i, value in enumerate(header_row.tolist()):
            text = str(value).strip()
            new_cols.append(text or f"Column_{i+1}")
        new_df = df.iloc[row_idx + 1 :].reset_index(drop=True)
        new_df.columns = new_cols
        return new_df

    def _auto_map_t1_columns(
        self,
        cols: List[str],
        used_columns: set[str] | None = None,
        skip_keys: set[str] | None = None,
    ):
        if not cols:
            return
        normalized = [(c, self._normalize_column_hint(c)) for c in cols]
        used = set(used_columns or ())
        skip = skip_keys or set()

        mapping = [
            (
                "t1_last",
                self.t1_last,
                [
                    ("last", "name"),
                    ("surname",),
                    ("guest", "last"),
                    ("lname",),
                ],
                (),
            ),
            (
                "t1_first",
                self.t1_first,
                [
                    ("first", "name"),
                    ("given", "name"),
                    ("fname",),
                    ("guest", "first"),
                ],
                (),
            ),
            (
                "t1_date",
                self.t1_date,
                [
                    ("arrival", "date"),
                    ("arrive", "date"),
                    ("check", "in"),
                    ("checkin",),
                    ("stay", "date"),
                    ("date", "arrival"),
                ],
                ("birth", "dob"),
            ),
            (
                "t1_itr",
                self.t1_itr,
                [
                    ("intent", "recommend"),
                    ("itr",),
                    ("recommend", "score"),
                    ("likelihood", "recommend"),
                ],
                (),
            ),
        ]

        for key, combo, patterns, excludes in mapping:
            if key in skip:
                continue
            match = self._pick_column_by_patterns(
                normalized, patterns, excludes, used
            )
            if match:
                self._set_combo_if_found(combo, match)
                used.add(match)

    def _auto_map_t2_columns(
        self,
        cols: List[str],
        used_columns: set[str] | None = None,
        skip_keys: set[str] | None = None,
    ):
        if not cols:
            return
        normalized = [(c, self._normalize_column_hint(c)) for c in cols]
        used = set(used_columns or ())
        skip = skip_keys or set()

        mapping = [
            (
                "t2_last",
                self.t2_last,
                [
                    ("last", "name"),
                    ("surname",),
                    ("guest", "last"),
                    ("lname",),
                ],
                (),
            ),
            (
                "t2_first",
                self.t2_first,
                [
                    ("first", "name"),
                    ("given", "name"),
                    ("fname",),
                    ("guest", "first"),
                ],
                (),
            ),
            (
                "t2_date",
                self.t2_date,
                [
                    ("activity", "date"),
                    ("stay", "date"),
                    ("business", "date"),
                    ("arrival", "date"),
                    ("date",),
                ],
                ("birth", "dob"),
            ),
            (
                "t2_user",
                self.t2_user,
                [
                    ("user", "id"),
                    ("userid",),
                    ("user",),
                    ("login",),
                    ("operator",),
                ],
                (),
            ),
        ]

        for key, combo, patterns, excludes in mapping:
            if key in skip:
                continue
            match = self._pick_column_by_patterns(
                normalized, patterns, excludes, used
            )
            if match:
                self._set_combo_if_found(combo, match)
                used.add(match)

    def _normalize_gss_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        normalized = df.copy()

        if self._needs_header_fix(normalized):
            header_idx = self._find_header_row_candidate(normalized)
            if header_idx is not None:
                normalized = self._promote_row_to_header(normalized, header_idx)

        name_candidates = [
            col for col in normalized.columns if self._is_composite_name_column(col)
        ]
        for col in name_candidates:
            series = normalized[col].fillna("").astype(str).str.strip()
            if not series.str.contains(",").any():
                continue
            # Split "LAST, FIRST" into two columns (limit to one split)
            split = series.str.split(pat=",", n=1, expand=True)
            last_part = split[0].str.strip()
            first_part = (
                split[1].str.strip()
                if split.shape[1] > 1
                else pd.Series([""] * len(series), index=series.index)
            )
            # Create standard "First name"/"Last name" columns for mapping/preview
            if "Last name" not in normalized.columns:
                normalized["Last name"] = last_part
            if "First name" not in normalized.columns:
                normalized["First name"] = first_part

            # Backwards-compatible aliases (if older configs expect these)
            if "GSS Last Name" not in normalized.columns:
                normalized["GSS Last Name"] = last_part
            if "GSS First Name" not in normalized.columns:
                normalized["GSS First Name"] = first_part

        return normalized

    def _normalize_opera_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df

        normalized = df.copy()

        if self._needs_header_fix(normalized):
            header_idx = self._find_header_row_candidate(normalized)
            if header_idx is not None:
                normalized = self._promote_row_to_header(normalized, header_idx)

        name_candidates = []
        for col in normalized.columns:
            norm = self._normalize_column_hint(str(col))
            if self._is_composite_name_column(col):
                name_candidates.append(col)
            elif "guest" in norm and "name" in norm and "first" not in norm and "last" not in norm:
                name_candidates.append(col)
            elif norm in ("name", "full name"):
                name_candidates.append(col)

        # First, provide consistent aliases for common core columns (from file_loader)
        # This ensures we use the correctly parsed LastName/FirstName from file_loader
        alias_map = [
            ("USERID", "Opera USERID"),
            ("User ID", "Opera USERID"),
            ("UserID", "Opera USERID"),
            ("LastName", "Opera LastName"),
            ("FirstName", "Opera FirstName"),
            ("Date", "Opera Date"),
        ]
        for source, alias in alias_map:
            if source in normalized.columns and alias not in normalized.columns:
                normalized[alias] = normalized[source]
        
        # Only split composite name columns if we don't already have separate LastName/FirstName
        # This prevents overwriting correctly parsed names from file_loader
        has_separate_names = "LastName" in normalized.columns and "FirstName" in normalized.columns
        if not has_separate_names:
            for col in name_candidates:
                series = normalized[col].fillna("").astype(str).str.strip()
                if series.empty:
                    continue
                if series.str.contains(",").any():
                    split = series.str.split(pat=",", n=1, expand=True)
                    last_part = split[0].str.strip()
                    first_part = (
                        split[1].str.strip()
                        if split.shape[1] > 1
                        else pd.Series([""] * len(series), index=series.index)
                    )
                else:
                    # For space-separated names, assume "Last First" format (common in Opera)
                    # But be cautious - if file_loader already parsed it, we shouldn't be here
                    split = series.str.split(None, n=1, expand=True)
                    if split.shape[1] == 0:
                        continue
                    # If only one token, treat as last name
                    if split.shape[1] == 1:
                        last_part = split[0].str.strip()
                        first_part = pd.Series([""] * len(series), index=series.index)
                    else:
                        # Two tokens: assume "Last First" (most common format)
                        last_part = split[0].str.strip()
                        first_part = split[1].str.strip()

                if "Opera Last Name" not in normalized.columns:
                    normalized["Opera Last Name"] = last_part
                if "Opera First Name" not in normalized.columns:
                    normalized["Opera First Name"] = first_part

        return normalized

    def _update_gss_preview(self):
        if hasattr(self, "gss_preview"):
            if self.gss_df is None or self.gss_df.empty:
                self.gss_preview.setRowCount(0)
                self.gss_preview.setColumnCount(0)
                self.gss_auto_label.setText("")
            else:
                preferred_cols = [
                    "First name",
                    "Last name",
                    "Arrival Date",
                    "Departure Date",
                    "Loyalty Program Tier",
                    "Intent to Recommend (Property)",
                    "Overall Comment",
                ]
                populate_table_from_dataframe(
                    self.gss_preview, self.gss_df, preferred_cols
                )

                self.gss_auto_label.setText(
                    f"Auto mapping: Last='{self.t1_last.currentText()}', "
                    f"First='{self.t1_first.currentText()}', "
                    f"Date='{self.t1_date.currentText()}', "
                    f"ITR='{self.t1_itr.currentText()}'"
                )

    def _update_opera_preview(self):
        if hasattr(self, "opera_preview"):
            if self.opera_df is None or self.opera_df.empty:
                self.opera_preview.setRowCount(0)
                self.opera_preview.setColumnCount(0)
                self.opera_auto_label.setText("")
            else:
                preferred_cols = [
                    "USERID",
                    "Date",
                    "Action",
                    "LastName",
                    "FirstName",
                ]
                populate_table_from_dataframe(
                    self.opera_preview, self.opera_df, preferred_cols
                )

                self.opera_auto_label.setText(
                    f"Auto mapping: Last='{self.t2_last.currentText()}', "
                    f"First='{self.t2_first.currentText()}', "
                    f"Date='{self.t2_date.currentText()}', "
                    f"User='{self.t2_user.currentText()}'"
                )

    def _persist_column_map(self):
        if self.gss_df is None or self.opera_df is None:
            return
        col_map = {
            "t1_last": self.t1_last.currentText().strip(),
            "t1_first": self.t1_first.currentText().strip(),
            "t1_date": self.t1_date.currentText().strip(),
            "t1_itr": self.t1_itr.currentText().strip(),
            "t2_last": self.t2_last.currentText().strip(),
            "t2_first": self.t2_first.currentText().strip(),
            "t2_date": self.t2_date.currentText().strip(),
            "t2_user": self.t2_user.currentText().strip(),
        }
        if any(not v for v in col_map.values()):
            return
        stored = self.cfg.setdefault("column_map", {})
        changed = False
        for key, value in col_map.items():
            if value and stored.get(key) != value:
                stored[key] = value
                changed = True
        if changed:
            save_config(self.cfg)

    def _apply_settings_to_ui(self):
        theme = self.cfg.get("theme", "dark")
        apply_theme(theme)

        alg = self.cfg.get("default_algorithm")
        if alg and alg in FUZZY_ALGORITHM_NAMES:
            self.algo_combo.setCurrentText(alg)
        else:
            # Default to Ensemble if no saved preference (best accuracy)
            if "Ensemble" in FUZZY_ALGORITHM_NAMES:
                self.algo_combo.setCurrentText("Ensemble")

        thr = int(self.cfg.get("default_threshold", DEFAULT_MATCH_THRESHOLD))
        self.threshold_spin.setValue(thr)
        
        date_tol = int(self.cfg.get("date_tolerance_days", 0))
        self.date_tolerance_spin.setValue(date_tol)

        if self.cfg.get("export_folder"):
            self.export_folder_edit.setText(self.cfg["export_folder"])
        if self.cfg.get("export_base"):
            self.base_name_edit.setText(self.cfg["export_base"])
        if self.cfg.get("last_t1_path"):
            self.t1_path_edit.setText(self.cfg["last_t1_path"])
        if self.cfg.get("last_t2_path"):
            self.t2_path_edit.setText(self.cfg["last_t2_path"])

    def log(self, msg: str):
        self.log_edit.append(msg)

    def _refresh_plugin_list(self):
        self.plugin_list.clear()
        for p in self.plugins:
            label = f"[{'ON' if p.enabled else 'OFF'}] {p.name} ({p.stage})"
            item = QListWidgetItem(label)
            if not p.enabled:
                item.setForeground(Qt.GlobalColor.gray)
            self.plugin_list.addItem(item)

    def toggle_plugin_from_list(self, item: QListWidgetItem):
        idx = self.plugin_list.row(item)
        if idx < 0 or idx >= len(self.plugins):
            return
        p = self.plugins[idx]
        p.enabled = not p.enabled
        self.cfg.setdefault("plugins", {})
        self.cfg["plugins"][p.name] = p.enabled
        save_config(self.cfg)
        self._refresh_plugin_list()
        self.log(
            f"[Plugin] {p.name} set to {'ENABLED' if p.enabled else 'DISABLED'}"
        )

    def validate_ready_state(self):
        self.btn_run.setEnabled(False)

        if self.gss_df is None or self.opera_df is None:
            return

        required_gss = [
            self.t1_last.currentText(),
            self.t1_first.currentText(),
            self.t1_date.currentText(),
        ]
        required_opera = [
            self.t2_last.currentText(),
            self.t2_first.currentText(),
            self.t2_date.currentText(),
            self.t2_user.currentText(),
        ]

        if any(not x or not x.strip() for x in required_gss + required_opera):
            return

        for col in required_gss:
            if col not in self.gss_df.columns:
                return
        for col in required_opera:
            if col not in self.opera_df.columns:
                return

        self._persist_column_map()
        self.btn_run.setEnabled(True)

    def load_t1(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GSS File", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        self.t1_path_edit.setText(path)
        self.cfg["last_t1_path"] = path
        save_config(self.cfg)

        df = read_full(path)
        if df is None or df.empty:
            QMessageBox.warning(self, "Error", "Failed to load GSS file.")
            return

        df = df.dropna(how="all")
        df = self._normalize_gss_dataframe(df)
        df = df.dropna(how="all")
        self.gss_df = df

        preferred_gss_cols = [
            "First name",
            "Last name",
            "Arrival Date",
            "Departure Date",
            "Loyalty Program Tier",
            "Intent to Recommend (Property)",
            "Overall Comment",
        ]

        # Use only preferred columns for mapping drop-downs when present
        cols_for_mapping = [
            c for c in df.columns if c in preferred_gss_cols
        ] or list(df.columns)

        for cb in (self.t1_last, self.t1_first, self.t1_date, self.t1_itr):
            cb.clear()
            cb.addItems(cols_for_mapping)

        applied = self._apply_saved_mapping(
            {
                "t1_last": self.t1_last,
                "t1_first": self.t1_first,
                "t1_date": self.t1_date,
                "t1_itr": self.t1_itr,
            }
        )
        self._auto_map_t1_columns(
            cols_for_mapping,
            used_columns=set(applied.values()),
            skip_keys=set(applied.keys()),
        )

        if (
            self.t1_last.currentText()
            and self.t1_first.currentText()
            and self.t1_date.currentText()
            and self.t1_last.currentText() in self.gss_df.columns
            and self.t1_first.currentText() in self.gss_df.columns
            and self.t1_date.currentText() in self.gss_df.columns
        ):
            self.log("[AutoMap] GSS columns auto-detected.")
            self._gss_automap_ok = True

        self._update_gss_preview()

        self.log("[GSS] File loaded and mapping combos updated.")
        self.validate_ready_state()

    def load_t2(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Opera File",
            "",
            "All Supported (*.xlsx *.xls *.csv *.txt);;Excel (*.xlsx *.xls);;Text/CSV (*.txt *.csv)",
        )
        if not path:
            return
        self.t2_path_edit.setText(path)
        self.cfg["last_t2_path"] = path
        save_config(self.cfg)

        df = read_full(path)
        if df is None or df.empty:
            QMessageBox.warning(self, "Error", "Failed to load Opera file.")
            return

        df = df.dropna(how="all")
        df = self._normalize_opera_dataframe(df)
        df = df.dropna(how="all")
        self.opera_df = df
        cols = list(df.columns)

        for cb in (self.t2_last, self.t2_first, self.t2_date, self.t2_user):
            cb.clear()
            cb.addItems(cols)

        applied = self._apply_saved_mapping(
            {
                "t2_last": self.t2_last,
                "t2_first": self.t2_first,
                "t2_date": self.t2_date,
                "t2_user": self.t2_user,
            }
        )
        self._auto_map_t2_columns(
            cols,
            used_columns=set(applied.values()),
            skip_keys=set(applied.keys()),
        )

        if (
            self.t2_last.currentText()
            and self.t2_first.currentText()
            and self.t2_date.currentText()
            and self.t2_user.currentText()
            and self.t2_last.currentText() in self.opera_df.columns
            and self.t2_first.currentText() in self.opera_df.columns
            and self.t2_date.currentText() in self.opera_df.columns
            and self.t2_user.currentText() in self.opera_df.columns
        ):
            self.log("[AutoMap] Opera columns auto-detected.")
            self._opera_automap_ok = True

        self._maybe_auto_hide_mapping()

        self._update_opera_preview()

        self.log("[Opera] File loaded and mapping combos updated.")
        self.validate_ready_state()

    def select_export_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select export folder", ""
        )
        if folder:
            self.export_folder_edit.setText(folder)
            self.cfg["export_folder"] = folder
            save_config(self.cfg)

    def run_match(self):
        if self.gss_df is None or self.opera_df is None:
            QMessageBox.warning(
                self, "Error", "Please load both GSS and Opera files."
            )
            return

        required_gss = [
            self.t1_last.currentText(),
            self.t1_first.currentText(),
            self.t1_date.currentText(),
        ]
        required_opera = [
            self.t2_last.currentText(),
            self.t2_first.currentText(),
            self.t2_date.currentText(),
            self.t2_user.currentText(),
        ]

        if any(not x or not x.strip() for x in required_gss + required_opera):
            QMessageBox.warning(
                self,
                "Mapping Error",
                "Some fields are not selected. Please map all required columns.",
            )
            return

        missing_cols: list[str] = []

        for col in required_gss:
            if col not in self.gss_df.columns:
                missing_cols.append(f"GSS: {col}")

        for col in required_opera:
            if col not in self.opera_df.columns:
                missing_cols.append(f"Opera: {col}")

        if missing_cols:
            QMessageBox.warning(
                self,
                "Mapping Error",
                "Some mapped columns do not exist in the loaded files:\n\n"
                + "\n".join(missing_cols),
            )
            return

        gss_rows = len(self.gss_df)
        op_rows = len(self.opera_df)
        if gss_rows > 10000 or op_rows > 10000:
            reply = QMessageBox.warning(
                self,
                "Large Dataset",
                f"GSS has {gss_rows} rows.\n"
                f"Opera has {op_rows} rows.\n\n"
                "Matching may take a long time.\nDo you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self._persist_column_map()
        
        # Validate and save algorithm as default
        current_alg = self.algo_combo.currentText()
        if not current_alg or current_alg not in FUZZY_ALGORITHM_NAMES:
            QMessageBox.warning(
                self,
                "Invalid Algorithm",
                f"Selected algorithm '{current_alg}' is not valid. Please select a valid algorithm.",
            )
            return
        
        if current_alg in FUZZY_ALGORITHM_NAMES:
            self.cfg["default_algorithm"] = current_alg
            save_config(self.cfg)

        mc = MatchConfig(
            t1_last=self.t1_last.currentText(),
            t1_first=self.t1_first.currentText(),
            t1_date=self.t1_date.currentText(),
            t1_itr=self.t1_itr.currentText(),
            t2_last=self.t2_last.currentText(),
            t2_first=self.t2_first.currentText(),
            t2_date=self.t2_date.currentText(),
            t2_userid=self.t2_user.currentText(),
            algorithm=current_alg,
            threshold=self.threshold_spin.value(),
            enable_pre_norm=self.cfg.get("name_pre_normalization", True),
            enable_enhanced_fuzzy=self.cfg.get("enhanced_fuzzy", True),
            enable_date_bonus=self.cfg.get("date_bonus", True),
            enable_phonetic=self.cfg.get("phonetic_matching", False),
            enable_variants=self.cfg.get("firstname_variants", True),
            enable_double_surname=self.cfg.get("double_surname", True),
            enable_safe_missing=self.cfg.get("safe_missing", True),
            show_all_matches=self.show_all_matches_check.isChecked(),
            date_tolerance_days=self.date_tolerance_spin.value(),
        )

        # Check if running all algorithms
        if self.run_all_algorithms_check.isChecked():
            self._run_all_algorithms(mc)
        else:
            mode = "all matches" if mc.show_all_matches else "best match only"
            date_tol = f"±{mc.date_tolerance_days} days" if mc.date_tolerance_days > 0 else "exact"
            self.log(f"[Match] Starting match: threshold={mc.threshold}, date_tolerance={date_tol}, mode={mode}")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Running...")
            self.btn_run.setEnabled(False)

            worker = MatchWorker(self.gss_df, self.opera_df, mc)
            self.match_worker = worker
            worker.progress_signal.connect(self.progress_bar.setValue)
            worker.finished_signal.connect(self.match_finished)
            worker.start()

    def _run_all_algorithms(self, base_config: MatchConfig):
        """Run all algorithms and export each to a separate workbook"""
        from matcher.settings import FUZZY_ALGORITHM_NAMES
        from matcher.engine import match_tables
        from matcher.engine.record_linkage_matcher import match_with_recordlinkage
        from PyQt6.QtWidgets import QApplication
        
        self.log("[Match] Running all algorithms for comparison...")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Running all algorithms...")
        self.btn_run.setEnabled(False)
        
        export_folder = self.export_folder_edit.text().strip()
        export_base = self.base_name_edit.text().strip() or "match_results"
        
        if not export_folder or not os.path.isdir(export_folder):
            QMessageBox.warning(
                self,
                "Export Folder Required",
                "Please set an export folder to save algorithm comparison results."
            )
            self.btn_run.setEnabled(True)
            return
        
        results = {}
        total_algorithms = len(FUZZY_ALGORITHM_NAMES)
        current = 0
        
        for alg_name in FUZZY_ALGORITHM_NAMES:
            current += 1
            self.log(f"[Match] Running algorithm {current}/{total_algorithms}: {alg_name}")
            self.progress_bar.setFormat(f"Running: {alg_name} ({current}/{total_algorithms})")
            self.progress_bar.setValue(int((current - 1) * 100 / total_algorithms))
            
            # Process events to keep UI responsive
            QApplication.processEvents()
            
            try:
                if alg_name == "Record Linkage":
                    # Use record linkage matcher
                    df = match_with_recordlinkage(
                        self.gss_df,
                        self.opera_df,
                        base_config.t1_last,
                        base_config.t1_first,
                        base_config.t1_date,
                        base_config.t2_last,
                        base_config.t2_first,
                        base_config.t2_date,
                        threshold=base_config.threshold / 100.0,
                        show_all_matches=base_config.show_all_matches,
                        progress_cb=None,
                    )
                else:
                    # Use standard matcher with this algorithm
                    alg_config = MatchConfig(
                        t1_last=base_config.t1_last,
                        t1_first=base_config.t1_first,
                        t1_date=base_config.t1_date,
                        t1_itr=base_config.t1_itr,
                        t2_last=base_config.t2_last,
                        t2_first=base_config.t2_first,
                        t2_date=base_config.t2_date,
                        t2_userid=base_config.t2_userid,
                        algorithm=alg_name,
                        threshold=base_config.threshold,
                        enable_pre_norm=base_config.enable_pre_norm,
                        enable_enhanced_fuzzy=base_config.enable_enhanced_fuzzy,
                        enable_date_bonus=base_config.enable_date_bonus,
                        enable_phonetic=base_config.enable_phonetic,
                        enable_variants=base_config.enable_variants,
                        enable_double_surname=base_config.enable_double_surname,
                        enable_safe_missing=base_config.enable_safe_missing,
                        show_all_matches=base_config.show_all_matches,
                        date_tolerance_days=base_config.date_tolerance_days,
                        enable_multi_pass=base_config.enable_multi_pass,
                    )
                    df = match_tables(self.gss_df, self.opera_df, alg_config, progress_cb=None)
                
                if df is not None and not df.empty:
                    results[alg_name] = df
                    self.log(f"[Match] {alg_name}: {len(df)} matches found")
                else:
                    self.log(f"[Match] {alg_name}: No matches found")
                    
            except Exception as e:
                self.log(f"[Match] {alg_name}: Error - {e}")
                import traceback
                traceback.print_exc()
            
            # Process events after each algorithm to keep UI responsive
            QApplication.processEvents()
        
        # Export all results to separate workbooks
        self.log("[Match] Exporting results to separate workbooks...")
        self._export_algorithm_comparison(results, export_folder, export_base)
        QApplication.processEvents()
        
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Done")
        self.btn_run.setEnabled(True)
        
        QMessageBox.information(
            self,
            "Algorithm Comparison Complete",
            f"Ran {len(results)} algorithms successfully.\n"
            f"Results exported to:\n{export_folder}\n\n"
            f"Each algorithm has its own Excel workbook for comparison."
        )
    
    def _export_algorithm_comparison(self, results: Dict[str, pd.DataFrame], export_folder: str, base_name: str):
        """Export each algorithm's results to a separate Excel workbook"""
        from matcher.plugins.export_customizer import post_match
        
        for alg_name, df in results.items():
            # Sanitize algorithm name for filename
            safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in alg_name)
            safe_name = safe_name.replace(' ', '_')
            
            # Create export context with modified base name
            export_base = f"{base_name}_{safe_name}"
            
            # Use the export plugin to create the workbook
            try:
                post_match(
                    df,
                    {
                        "export_folder": export_folder,
                        "export_base": export_base,
                        "log": self.log,
                        "config": self.cfg,
                    },
                )
                self.log(f"[Export] Exported {alg_name} to {export_base}_v7_4_1.xlsx")
            except Exception as e:
                self.log(f"[Export] Error exporting {alg_name}: {e}")

    def match_finished(self, df: pd.DataFrame):
        self.current_df = df
        self.btn_run.setEnabled(True)
        self.progress_bar.setFormat("Done")

        if df is None or df.empty:
            self.log("[Match] No matches found.")
            QMessageBox.information(
                self, "Match finished", "No matches found."
            )
            return

        self.log(f"[Match] Completed. {len(df)} matches.")

        for p in self.plugins:
            if not p.enabled:
                continue
            if hasattr(p.module, "post_match"):
                try:
                    p.module.post_match(
                        df,
                        {
                            "export_folder": self.export_folder_edit.text().strip(),
                            "export_base": self.base_name_edit.text().strip()
                            or "match_results",
                            "log": self.log,
                            "config": self.cfg,
                        },
                    )
                except Exception as e:
                    self.log(f"[Plugin:{p.name}] Error: {e}")

        self.log("[Match] All enabled plugins executed.")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, parent=self)
        if dlg.exec():
            self.cfg.update(dlg.get_settings())
            save_config(self.cfg)
            self._apply_settings_to_ui()
            self.log("[Settings] Updated.")
            self.validate_ready_state()

    def open_plugins(self):
        dlg = PluginManagerDialog(self.plugins, self.cfg, parent=self)
        dlg.exec()
        save_config(self.cfg)
        self._refresh_plugin_list()


def run_app():
    app = QApplication(sys.argv)
    cfg = load_config() or {}
    apply_theme(cfg.get("theme", "dark"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
