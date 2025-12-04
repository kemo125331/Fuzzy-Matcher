
from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal
import pandas as pd

from ..engine import MatchConfig, match_tables


class MatchWorker(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(object)

    def __init__(self, t1: pd.DataFrame, t2: pd.DataFrame, cfg: MatchConfig):
        super().__init__()
        self.t1 = t1
        self.t2 = t2
        self.cfg = cfg

    def run(self):
        def cb(p: int):
            self.progress_signal.emit(p)

        df = match_tables(self.t1, self.t2, self.cfg, progress_cb=cb)
        self.finished_signal.emit(df)
