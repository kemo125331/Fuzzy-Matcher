
from PyQt6.QtWidgets import QApplication


def apply_theme(theme: str = "dark") -> None:
    app = QApplication.instance()
    if not app:
        return

    app.setStyle("Fusion")
    pal = app.palette()

    if theme == "light":
        app.setPalette(pal)
    else:
        pal.setColor(pal.ColorRole.Window, pal.color(pal.ColorRole.Window).darker(130))
        pal.setColor(pal.ColorRole.Base, pal.color(pal.ColorRole.Base).darker(140))
        pal.setColor(
            pal.ColorRole.AlternateBase,
            pal.color(pal.ColorRole.AlternateBase).darker(130),
        )
        pal.setColor(
            pal.ColorRole.Text,
            pal.color(pal.ColorRole.Text).lighter(150),
        )
        pal.setColor(
            pal.ColorRole.Button,
            pal.color(pal.ColorRole.Button).darker(130),
        )
        app.setPalette(pal)
