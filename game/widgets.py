"""Dark-themed widgets and canvas helpers.

Buttons are built from ``tk.Label`` on purpose: native ``tk.Button`` ignores
background colours on macOS, so this keeps the dark look identical everywhere.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence, Tuple

from . import theme as T


# ---- Buttons ---------------------------------------------------------------
class FlatButton(tk.Label):
    STYLES = {
        "default": dict(bg=T.PANEL_HI, hover=T.PANEL_HOVER, press=T.BORDER, fg=T.TEXT, border=T.BORDER),
        "primary": dict(bg=T.ACCENT, hover=T.ACCENT_HOVER, press=T.ACCENT_PRESS, fg="#ffffff", border=T.ACCENT),
        "danger": dict(bg=T.PANEL_HI, hover="#3a2030", press="#4a2638", fg="#ff7b88", border="#5c2a38"),
        "ghost": dict(bg=T.BG, hover=T.PANEL_HI, press=T.PANEL, fg=T.MUTED, border=T.BORDER),
    }

    def __init__(self, master, text: str, command: Optional[Callable[[], None]] = None,
                 kind: str = "default", font=None, padx: int = 14, pady: int = 8,
                 takefocus: bool = False, **kw):
        self.command = command
        self._kind = kind
        self._enabled = True
        self._hover = False
        self._pressed = False
        style = self.STYLES[kind]
        super().__init__(master, text=text, font=font, fg=style["fg"], bg=style["bg"],
                         padx=padx, pady=pady, bd=0, highlightthickness=1,
                         highlightbackground=style["border"], highlightcolor=T.ACCENT,
                         cursor="hand2", takefocus=takefocus, **kw)
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<FocusIn>", lambda e: self._paint())
        self.bind("<FocusOut>", lambda e: self._paint())

    def _set(self, hover=None, pressed=None) -> None:
        if hover is not None:
            self._hover = hover
        if pressed is not None:
            self._pressed = pressed
        self._paint()

    def _paint(self) -> None:
        style = self.STYLES[self._kind]
        if not self._enabled:
            self.configure(bg=T.PANEL, fg=T.FAINT, highlightbackground=T.PANEL, cursor="arrow")
            return
        bg = style["press"] if self._pressed else style["hover"] if self._hover else style["bg"]
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        border = T.ACCENT if focused else style["border"]
        self.configure(bg=bg, fg=style["fg"], highlightbackground=border, cursor="hand2")

    def _on_release(self, event) -> None:
        was_pressed = self._pressed
        self._set(pressed=False)
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if was_pressed and inside:
            self.invoke()

    def invoke(self) -> None:
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._paint()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self._paint()

    def set_text(self, text: str) -> None:
        self.configure(text=text)


class SegmentedControl(tk.Frame):
    """A row of mutually exclusive options, e.g. Easy | Medium | Hard."""

    def __init__(self, master, options: Sequence[Tuple[str, str]], value: str,
                 command: Callable[[str], None], font=None):
        super().__init__(master, bg=T.BORDER, highlightthickness=0, bd=0, padx=1, pady=1)
        self._command = command
        self._value = value
        self._enabled = True
        self._labels = {}
        self._hover = None
        for col, (key, text) in enumerate(options):
            label = tk.Label(self, text=text, font=font, padx=8, pady=7, bd=0, cursor="hand2")
            label.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 1, 0))
            self.columnconfigure(col, weight=1, uniform="seg")
            label.bind("<Button-1>", lambda e, k=key: self._choose(k))
            label.bind("<Enter>", lambda e, k=key: self._hovered(k))
            label.bind("<Leave>", lambda e: self._hovered(None))
            self._labels[key] = label
        self._paint()

    def _hovered(self, key) -> None:
        self._hover = key
        self._paint()

    def _choose(self, key: str) -> None:
        if not self._enabled or key == self._value:
            return
        self._value = key
        self._paint()
        self._command(key)

    def _paint(self) -> None:
        for key, label in self._labels.items():
            if not self._enabled:
                label.configure(bg=T.ACCENT_PRESS if key == self._value else T.PANEL,
                                fg=T.MUTED if key == self._value else T.FAINT, cursor="arrow")
            elif key == self._value:
                label.configure(bg=T.ACCENT, fg="#ffffff", cursor="arrow")
            else:
                label.configure(bg=T.PANEL_HOVER if key == self._hover else T.PANEL_HI,
                                fg=T.TEXT if key == self._hover else T.MUTED, cursor="hand2")

    def set(self, value: str) -> None:
        """Select a value programmatically (does not call the command)."""
        self._value = value
        self._paint()

    def get(self) -> str:
        return self._value

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._paint()


class CheckToggle(tk.Frame):
    """Checkbox row bound to a BooleanVar."""

    def __init__(self, master, text: str, variable: tk.BooleanVar, font=None, bg: str = T.BG):
        super().__init__(master, bg=bg, cursor="hand2")
        self._var = variable
        self.box = tk.Label(self, width=2, font=font, bd=0, highlightthickness=1,
                            highlightbackground=T.BORDER)
        self.box.pack(side="left")
        self.text = tk.Label(self, text=text, font=font, fg=T.TEXT, bg=bg, anchor="w")
        self.text.pack(side="left", padx=(10, 0))
        for widget in (self, self.box, self.text):
            widget.bind("<Button-1>", self._toggle)
        self._var.trace_add("write", lambda *a: self._paint())
        self._paint()

    def _toggle(self, _event=None) -> None:
        self._var.set(not self._var.get())

    def _paint(self) -> None:
        on = self._var.get()
        self.box.configure(text="\u2713" if on else "", bg=T.ACCENT if on else T.PANEL_HI,
                           fg="#ffffff", highlightbackground=T.ACCENT if on else T.BORDER)


def styled_entry(master, variable: tk.StringVar, font=None, width: int = 18, maxlen: Optional[int] = None) -> tk.Entry:
    options = {}
    if maxlen:
        options.update(validate="key",
                       validatecommand=(master.register(lambda proposed: len(proposed) <= maxlen), "%P"))
    return tk.Entry(master, textvariable=variable, font=font, width=width, bg=T.PANEL_HI, fg=T.TEXT,
                    insertbackground=T.TEXT, relief="flat", bd=0, highlightthickness=1,
                    highlightbackground=T.BORDER, highlightcolor=T.ACCENT,
                    disabledbackground=T.PANEL, disabledforeground=T.FAINT,
                    selectbackground=T.ACCENT, selectforeground="#ffffff", **options)


# ---- ttk (Treeview / Scrollbar) dark style ---------------------------------
def apply_ttk_dark_style(root, fonts) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Dark.Treeview", background=T.PANEL, fieldbackground=T.PANEL, foreground=T.TEXT,
                    borderwidth=0, relief="flat", rowheight=30, font=fonts.body)
    style.layout("Dark.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.map("Dark.Treeview", background=[("selected", T.ACCENT)], foreground=[("selected", "#ffffff")])
    style.configure("Dark.Treeview.Heading", background=T.PANEL_HI, foreground=T.MUTED, relief="flat",
                    borderwidth=0, font=fonts.bold, padding=(8, 7))
    style.map("Dark.Treeview.Heading", background=[("active", T.PANEL_HOVER)])
    style.configure("Dark.Vertical.TScrollbar", background=T.PANEL_HI, troughcolor=T.PANEL,
                    bordercolor=T.PANEL, arrowcolor=T.MUTED, lightcolor=T.PANEL_HI,
                    darkcolor=T.PANEL_HI, relief="flat")
    style.map("Dark.Vertical.TScrollbar", background=[("active", T.PANEL_HOVER)])


# ---- Canvas helpers --------------------------------------------------------
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw) -> int:
    """Rounded rectangle (a smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def draw_mark(canvas: tk.Canvas, cx: float, cy: float, r: float, symbol: str, color: str,
              width: float, tags: Tuple[str, ...] = (), progress: float = 1.0,
              glow: Optional[str] = None) -> None:
    """Draw an X or O centred at (cx, cy) with radius r.

    `progress` (0-1) draws it partially - X as two strokes, O as a sweeping arc -
    which is what powers the "draw-in" animation. Glow items are tagged "glow"
    and the main strokes "main" so they can be recoloured separately.
    """
    if progress <= 0:
        return
    glow_width = width + max(4, width * 0.9)

    if symbol == "X":
        strokes = []
        for (ax, ay), (bx, by), p in (
            ((cx - r, cy - r), (cx + r, cy + r), min(1.0, progress * 2)),
            ((cx + r, cy - r), (cx - r, cy + r), max(0.0, (progress - 0.5) * 2)),
        ):
            if p > 0:
                strokes.append((ax, ay, ax + (bx - ax) * p, ay + (by - ay) * p))
        for layer_color, layer_width, tag in ((glow, glow_width, "glow"), (color, width, "main")):
            if layer_color is None:
                continue
            for x1, y1, x2, y2 in strokes:
                canvas.create_line(x1, y1, x2, y2, width=layer_width, fill=layer_color,
                                   capstyle="round", tags=tuple(tags) + (tag,))
        return

    bbox = (cx - r, cy - r, cx + r, cy + r)
    for layer_color, layer_width, tag in ((glow, glow_width, "glow"), (color, width, "main")):
        if layer_color is None:
            continue
        if progress >= 1.0:
            canvas.create_oval(*bbox, outline=layer_color, width=layer_width, tags=tuple(tags) + (tag,))
        else:
            canvas.create_arc(*bbox, start=90, extent=-359.0 * progress, style="arc",
                              outline=layer_color, width=layer_width, tags=tuple(tags) + (tag,))


def recolor(canvas: tk.Canvas, tag: str, main: str, glow: Optional[str] = None) -> None:
    """Recolour items drawn by `draw_mark` that carry `tag`."""
    for item in canvas.find_withtag(tag):
        tags = canvas.gettags(item)
        color = glow if "glow" in tags else main
        if color is None:
            continue
        if canvas.type(item) == "line":
            canvas.itemconfigure(item, fill=color)
        else:
            canvas.itemconfigure(item, outline=color)
