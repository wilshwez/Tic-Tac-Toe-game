"""Modal dialogs: Settings, Leaderboard, Match history (with replay), Confirm."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk
from typing import Any, Dict, List, Optional

from . import theme as T
from .logic import winning_line
from .storage import MAX_NAME_LEN, Storage, clean_name
from .widgets import (CheckToggle, FlatButton, SegmentedControl, draw_mark, round_rect,
                      styled_entry)


class BaseDialog(tk.Toplevel):
    """Dark modal window centred over its parent."""

    def __init__(self, parent: tk.Misc, title: str, fonts, resizable: bool = False):
        super().__init__(parent)
        self.withdraw()
        self.fonts = fonts
        self.parent = parent
        self.result: Any = None
        self.configure(bg=T.BG)
        self.title(title)
        self.transient(parent)
        self.resizable(resizable, resizable)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())

    def show(self) -> Any:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        px, py = self.parent.winfo_rootx(), self.parent.winfo_rooty()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.focus_set()
        self.wait_window(self)
        return self.result

    def cancel(self) -> None:
        self.result = None
        self.destroy()

    def heading(self, parent, text: str) -> tk.Label:
        return tk.Label(parent, text=text, font=self.fonts.heading, fg=T.TEXT, bg=T.BG, anchor="w")

    def caption(self, parent, text: str, bg: str = T.BG) -> tk.Label:
        return tk.Label(parent, text=text, font=self.fonts.caption, fg=T.MUTED, bg=bg, anchor="w")


# ---- Confirm ----------------------------------------------------------------
class ConfirmDialog(BaseDialog):
    def __init__(self, parent, fonts, title: str, message: str, confirm_text: str = "Confirm",
                 danger: bool = True):
        super().__init__(parent, title, fonts)
        body = tk.Frame(self, bg=T.BG, padx=26, pady=22)
        body.pack(fill="both", expand=True)
        self.heading(body, title).pack(anchor="w")
        tk.Label(body, text=message, font=fonts.body, fg=T.MUTED, bg=T.BG, justify="left",
                 wraplength=340, anchor="w").pack(anchor="w", pady=(8, 20))
        row = tk.Frame(body, bg=T.BG)
        row.pack(anchor="e")
        FlatButton(row, "Cancel", self.cancel, font=fonts.body, takefocus=True).pack(side="left", padx=(0, 8))
        self.ok = FlatButton(row, confirm_text, self._ok, kind="danger" if danger else "primary",
                             font=fonts.bold, takefocus=True)
        self.ok.pack(side="left")

    def _ok(self) -> None:
        self.result = True
        self.destroy()


def ask_confirm(parent, fonts, title: str, message: str, confirm_text: str = "Confirm",
                danger: bool = True) -> bool:
    return bool(ConfirmDialog(parent, fonts, title, message, confirm_text, danger).show())


# ---- Settings ---------------------------------------------------------------
class SettingsDialog(BaseDialog):
    """Player names + preferences. `result` is a dict, or None if cancelled."""

    def __init__(self, parent, fonts, settings: Dict[str, Any], ai_mode: bool, data_dir,
                 focus: str = "x"):
        super().__init__(parent, "Settings", fonts)
        self.ai_mode = ai_mode
        self.settings = settings
        body = tk.Frame(self, bg=T.BG, padx=28, pady=24)
        body.pack(fill="both", expand=True)

        self.heading(body, "Settings").grid(row=0, column=0, columnspan=2, sticky="w")

        self.caption(body, "PLAYERS").grid(row=1, column=0, columnspan=2, sticky="w", pady=(18, 6))
        self.var_x = tk.StringVar(value=settings["name_x"])
        self.var_o = tk.StringVar(value="Computer" if ai_mode else settings["name_o"])
        tk.Label(body, text="Player X", font=fonts.body, fg=T.X_COLOR, bg=T.BG, anchor="w").grid(
            row=2, column=0, sticky="w", pady=4)
        self.entry_x = styled_entry(body, self.var_x, fonts.body, width=20, maxlen=MAX_NAME_LEN)
        self.entry_x.grid(row=2, column=1, sticky="ew", padx=(16, 0), pady=4, ipady=5)
        tk.Label(body, text="Player O", font=fonts.body, fg=T.O_COLOR, bg=T.BG, anchor="w").grid(
            row=3, column=0, sticky="w", pady=4)
        self.entry_o = styled_entry(body, self.var_o, fonts.body, width=20, maxlen=MAX_NAME_LEN)
        self.entry_o.grid(row=3, column=1, sticky="ew", padx=(16, 0), pady=4, ipady=5)
        if ai_mode:
            self.entry_o.configure(state="disabled")
            tk.Label(body, text="Player O is the computer in \u201cvs Computer\u201d mode.",
                     font=fonts.small, fg=T.FAINT, bg=T.BG, anchor="w").grid(
                row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        body.columnconfigure(1, weight=1)

        self.caption(body, "PREFERENCES").grid(row=5, column=0, columnspan=2, sticky="w", pady=(20, 8))
        self.var_sound = tk.BooleanVar(value=settings["sound"])
        self.var_anim = tk.BooleanVar(value=settings["animations"])
        self.var_alt = tk.BooleanVar(value=settings["alternate_first"])
        for r, (text, var) in enumerate((("Sound effects", self.var_sound),
                                         ("Animations", self.var_anim),
                                         ("Alternate who goes first each round", self.var_alt)), start=6):
            CheckToggle(body, text, var, fonts.body).grid(row=r, column=0, columnspan=2, sticky="w", pady=4)

        tk.Label(body, text=f"Saved data: {data_dir}", font=fonts.small, fg=T.FAINT, bg=T.BG,
                 anchor="w", justify="left", wraplength=380).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(18, 0))

        self.error = tk.Label(body, text="", font=fonts.small, fg=T.DANGER, bg=T.BG, anchor="w")
        self.error.grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 0))

        buttons = tk.Frame(body, bg=T.BG)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(10, 0))
        FlatButton(buttons, "Cancel", self.cancel, font=fonts.body, takefocus=True).pack(side="left", padx=(0, 8))
        FlatButton(buttons, "Save", self._save, kind="primary", font=fonts.bold, takefocus=True).pack(side="left")

        self.bind("<Return>", lambda e: self._save())
        target = self.entry_o if (focus == "o" and not ai_mode) else self.entry_x
        self.after(50, lambda: (target.focus_set(), target.select_range(0, "end")))

    def _save(self) -> None:
        name_x = clean_name(self.var_x.get())
        name_o = clean_name(self.var_o.get())
        if not name_x:
            self.error.configure(text="Player X needs a name.")
            return
        if not self.ai_mode:
            if not name_o:
                self.error.configure(text="Player O needs a name.")
                return
            if name_x.casefold() == name_o.casefold():
                self.error.configure(text="The two players need different names.")
                return
        self.result = {
            "name_x": name_x,
            "name_o": self.settings["name_o"] if self.ai_mode else name_o,
            "sound": bool(self.var_sound.get()),
            "animations": bool(self.var_anim.get()),
            "alternate_first": bool(self.var_alt.get()),
        }
        self.destroy()


# ---- Leaderboard ------------------------------------------------------------
class LeaderboardDialog(BaseDialog):
    FILTERS = (("all", "All"), ("human", "vs Human"), ("Easy", "Easy"), ("Medium", "Medium"), ("Hard", "Hard"))
    COLUMNS = (("rank", "#", 44, "center"), ("name", "Player", 170, "w"), ("wins", "W", 52, "center"),
               ("draws", "D", 52, "center"), ("losses", "L", 52, "center"), ("games", "Games", 78, "center"),
               ("rate", "Win %", 76, "center"), ("points", "Pts", 60, "center"))

    def __init__(self, parent, fonts, storage: Storage):
        super().__init__(parent, "Leaderboard", fonts)
        self.storage = storage
        body = tk.Frame(self, bg=T.BG, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        self.heading(body, "Leaderboard").pack(anchor="w")
        tk.Label(body, text="Win = 3 pts, draw = 1 pt. Computer games are tracked per difficulty.",
                 font=fonts.small, fg=T.MUTED, bg=T.BG, anchor="w").pack(anchor="w", pady=(2, 12))

        self.filter = SegmentedControl(body, self.FILTERS, "all", lambda key: self._refresh(key), font=fonts.small)
        self.filter.pack(anchor="w", pady=(0, 12))

        holder = tk.Frame(body, bg=T.BORDER, padx=1, pady=1)
        holder.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(holder, columns=[c[0] for c in self.COLUMNS], show="headings",
                                 style="Dark.Treeview", height=10, selectmode="browse")
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.empty = tk.Label(body, text="", font=fonts.body, fg=T.MUTED, bg=T.BG)
        self.empty.pack(pady=(10, 0))

        buttons = tk.Frame(body, bg=T.BG)
        buttons.pack(fill="x", pady=(14, 0))
        FlatButton(buttons, "Clear leaderboard", self._clear, kind="danger", font=fonts.small,
                   takefocus=True).pack(side="left")
        FlatButton(buttons, "Close", self.cancel, kind="primary", font=fonts.bold, padx=22,
                   takefocus=True).pack(side="right")
        self._refresh("all")

    def _refresh(self, key: str) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self.storage.leaderboard_rows(key)
        for row in rows:
            self.tree.insert("", "end", values=(
                row["rank"], row["name"], row["wins"], row["draws"], row["losses"],
                row["games"], f"{row['win_rate']:.0f}%", row["points"]))
        if rows:
            self.empty.configure(text="")
        else:
            self.empty.configure(text="No finished games here yet \u2014 play a round to get on the board.")

    def _clear(self) -> None:
        if ask_confirm(self, self.fonts, "Clear leaderboard?",
                       "This permanently removes all win/draw/loss totals. Match history is kept.",
                       "Clear"):
            self.storage.clear_leaderboard()
            self._refresh(self.filter.get())


# ---- Match history + replay ---------------------------------------------------
class HistoryDialog(BaseDialog):
    COLUMNS = (("when", "Date", 156, "w"), ("mode", "Mode", 140, "w"), ("x", "X", 100, "w"),
               ("o", "O", 100, "w"), ("result", "Result", 100, "w"), ("moves", "Moves", 70, "center"))
    REPLAY = 250

    def __init__(self, parent, fonts, storage: Storage):
        super().__init__(parent, "Match history", fonts)
        self.storage = storage
        self.matches: Dict[str, Dict[str, Any]] = {}
        self.current: Optional[Dict[str, Any]] = None
        self.step = 0

        body = tk.Frame(self, bg=T.BG, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        self.heading(body, "Match history").grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(body, text="Select a match to replay it move by move. The latest 500 rounds are kept.",
                 font=fonts.small, fg=T.MUTED, bg=T.BG, anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

        holder = tk.Frame(body, bg=T.BORDER, padx=1, pady=1)
        holder.grid(row=2, column=0, sticky="nsew")
        self.tree = ttk.Treeview(holder, columns=[c[0] for c in self.COLUMNS], show="headings",
                                 style="Dark.Treeview", height=12, selectmode="browse")
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=False)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        side = tk.Frame(body, bg=T.BG)
        side.grid(row=2, column=1, sticky="n", padx=(20, 0))
        self.caption(side, "REPLAY").pack(anchor="w", pady=(0, 6))
        self.canvas = tk.Canvas(side, width=self.REPLAY, height=self.REPLAY, bg=T.BG, highlightthickness=0)
        self.canvas.pack()
        self.info = tk.Label(side, text="", font=fonts.small, fg=T.MUTED, bg=T.BG, justify="left",
                             wraplength=self.REPLAY, anchor="w")
        self.info.pack(anchor="w", pady=(10, 0), fill="x")
        self.step_label = tk.Label(side, text="", font=fonts.bold, fg=T.TEXT, bg=T.BG)
        self.step_label.pack(pady=(8, 6))
        controls = tk.Frame(side, bg=T.BG)
        controls.pack()
        for text, delta in (("\u00ab", "start"), ("\u2039", -1), ("\u203a", 1), ("\u00bb", "end")):
            FlatButton(controls, text, lambda d=delta: self._move_step(d), font=fonts.heading, padx=14,
                       pady=3, takefocus=True).pack(side="left", padx=3)

        self.status = tk.Label(body, text="", font=fonts.small, fg=T.MUTED, bg=T.BG, anchor="w")
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        buttons = tk.Frame(body, bg=T.BG)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        FlatButton(buttons, "Export CSV\u2026", self._export, font=fonts.small, takefocus=True).pack(side="left")
        FlatButton(buttons, "Clear history", self._clear, kind="danger", font=fonts.small,
                   takefocus=True).pack(side="left", padx=(8, 0))
        FlatButton(buttons, "Close", self.cancel, kind="primary", font=fonts.bold, padx=22,
                   takefocus=True).pack(side="right")
        body.columnconfigure(0, weight=1)

        self._populate()

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.matches = {}
        for match in reversed(self.storage.history):  # newest first
            iid = str(match["id"])
            self.matches[iid] = match
            try:
                when = datetime.fromisoformat(match["timestamp"]).strftime("%d %b %Y %H:%M")
            except ValueError:
                when = match["timestamp"]
            mode = f"vs CPU ({match.get('difficulty')})" if match["mode"] == "pvc" else "2 players"
            self.tree.insert("", "end", iid=iid, values=(
                when, mode, match["player_x"], match["player_o"],
                Storage.winner_name(match), len(match["moves"])))
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.status.configure(text="")
        else:
            self.current = None
            self.step = 0
            self._draw_replay()
            self.status.configure(text="No matches saved yet.")

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.current = self.matches.get(selection[0])
        self.step = len(self.current["moves"]) if self.current else 0
        self._draw_replay()

    def _move_step(self, delta) -> None:
        if not self.current:
            return
        total = len(self.current["moves"])
        if delta == "start":
            self.step = 0
        elif delta == "end":
            self.step = total
        else:
            self.step = max(0, min(total, self.step + delta))
        self._draw_replay()

    def _draw_replay(self) -> None:
        c = self.canvas
        c.delete("all")
        size, pad, gap = self.REPLAY, 6, 6
        cell = (size - 2 * pad - 2 * gap) / 3
        moves = self.current["moves"] if self.current else []
        board = [""] * 9
        order = {}
        for number, (symbol, index) in enumerate(moves[:self.step], 1):
            board[index] = symbol
            order[index] = number
        line = winning_line(board) if (self.current and self.step == len(moves)) else None

        for i in range(9):
            x1 = pad + (i % 3) * (cell + gap)
            y1 = pad + (i // 3) * (cell + gap)
            fill = T.blend(T.CELL, T.GOLD, 0.18) if line and i in line else T.CELL
            round_rect(c, x1, y1, x1 + cell, y1 + cell, 10, fill=fill, outline="")
            if board[i]:
                color = T.SYMBOL_COLOR[board[i]]
                draw_mark(c, x1 + cell / 2, y1 + cell / 2, cell * 0.24, board[i], color, cell * 0.085,
                          glow=T.blend(color, fill, 0.72))
                c.create_text(x1 + 9, y1 + 9, text=str(order[i]), anchor="nw", fill=T.MUTED, font=self.fonts.caption)

        if self.current:
            m = self.current
            total = len(moves)
            self.step_label.configure(text=f"Move {self.step} / {total}")
            who = "vs Computer" + (f" ({m.get('difficulty')})" if m.get("difficulty") else "") if m["mode"] == "pvc" else "2 players"
            undo_text = f" \u00b7 {m['undos']} undo{'s' if m['undos'] != 1 else ''}" if m.get("undos") else ""
            self.info.configure(text=f"{m['player_x']} (X) vs {m['player_o']} (O)\n{who}{undo_text}\n"
                                     f"Result: {Storage.winner_name(m)}")
        else:
            self.step_label.configure(text="")
            self.info.configure(text="")

    def _export(self) -> None:
        if not self.storage.history:
            self.status.configure(text="Nothing to export yet.", fg=T.MUTED)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")],
                                            initialfile="tictactoe_history.csv", title="Export match history")
        if not path:
            return
        try:
            count = self.storage.export_history_csv(path)
            self.status.configure(text=f"Exported {count} matches to {path}", fg=T.MUTED)
        except OSError as exc:
            self.status.configure(text=f"Export failed: {exc}", fg=T.DANGER)

    def _clear(self) -> None:
        if ask_confirm(self, self.fonts, "Clear match history?",
                       "This permanently deletes every saved match. Leaderboard totals are kept.", "Clear"):
            self.storage.clear_history()
            self._populate()
