"""Dark theme: palette, fonts and small colour/easing helpers."""
from __future__ import annotations

import tkinter.font as tkfont
from types import SimpleNamespace

# ---- Palette ---------------------------------------------------------------
BG = "#0e1120"
PANEL = "#161a2e"
PANEL_HI = "#1e2440"
PANEL_HOVER = "#272f52"
BORDER = "#2b3358"
CELL = "#1b2039"
CELL_HOVER = "#252c4d"

TEXT = "#eef0fa"
MUTED = "#8c95b8"
FAINT = "#5b6488"

X_COLOR = "#ff5d7a"
O_COLOR = "#2fd9c5"
ACCENT = "#6c5ce7"
ACCENT_HOVER = "#8173f0"
ACCENT_PRESS = "#5a4bd4"
GOLD = "#ffd166"
DANGER = "#ff5d6c"
DRAW = "#98a2c8"

SYMBOL_COLOR = {"X": X_COLOR, "O": O_COLOR}

_FONT_CANDIDATES = (
    "Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Cantarell",
    "DejaVu Sans", "Helvetica",
)


# ---- Fonts -----------------------------------------------------------------
def make_fonts(root) -> SimpleNamespace:
    """Create the shared font set (call once, after the Tk root exists)."""
    available = set(tkfont.families(root))
    family = next((f for f in _FONT_CANDIDATES if f in available), "Helvetica")

    def font(size: int, weight: str = "normal") -> tkfont.Font:
        return tkfont.Font(root=root, family=family, size=size, weight=weight)

    return SimpleNamespace(
        family=family,
        title=font(20, "bold"),
        status=font(18, "bold"),
        heading=font(13, "bold"),
        body=font(11),
        bold=font(11, "bold"),
        small=font(9),
        caption=font(8, "bold"),
        score=font(22, "bold"),
        badge=font(18, "bold"),
    )


# ---- Colour helpers --------------------------------------------------------
def _to_rgb(color: str):
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def blend(c1: str, c2: str, t: float) -> str:
    """Linear blend from c1 (t=0) to c2 (t=1)."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _to_rgb(c1)
    r2, g2, b2 = _to_rgb(c2)
    return "#%02x%02x%02x" % (
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t),
    )


# ---- Easing ----------------------------------------------------------------
def linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t
