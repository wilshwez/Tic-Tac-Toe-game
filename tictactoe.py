#!/usr/bin/env python3
"""Tic-Tac-Toe - Dark Edition.

An upgrade of the original Tkinter project. Run with:  python tictactoe.py

The original class/method names (``TicTacToe``, ``on_button_click``, ``ai_move``,
``ai_move_easy/medium/hard``, ``check_winner``, ``reset_board``, ``update_score``,
``toggle_ai_mode``, ``set_ai_difficulty``) are kept. The untouched original lives
in ``legacy/tictactoe_original.py``.
"""
from __future__ import annotations

import math
import random
import sys
import time
import tkinter as tk
from typing import List, Optional, Tuple

from game import ai
from game import theme as T
from game.dialogs import HistoryDialog, LeaderboardDialog, SettingsDialog, ask_confirm
from game.logic import is_full, other, winning_line
from game.sounds import SoundManager
from game.storage import Storage
from game.widgets import (FlatButton, SegmentedControl, apply_ttk_dark_style, draw_mark,
                          recolor, round_rect)

FRAME_MS = 16
COMPUTER_NAME = "Computer"
HINT = "1\u20139 place  \u00b7  Ctrl+Z undo  \u00b7  Enter next round  \u00b7  Ctrl+T switch mode"
NEXT_ROUND_HINT = "Click the board or press Enter for the next round"


class TicTacToe:
    HUMAN_SYMBOL = "X"
    AI_SYMBOL = "O"

    def __init__(self, root: tk.Tk, storage: Optional[Storage] = None,
                 sound: Optional[SoundManager] = None):
        self.root = root
        self.root.title("Tic-Tac-Toe")
        self.root.configure(bg=T.BG)
        self.root.resizable(False, False)

        self.storage = storage or Storage()
        self.settings = self.storage.settings
        self.sound = sound or SoundManager(self.storage.data_dir, enabled=self.settings["sound"])
        self.sound.enabled = self.settings["sound"]

        # --- game state (names from the original project are kept) ---
        self.current_player = "X"
        self.board = [""] * 9                 # 3x3 board, row-major
        self.score = {"X": 0, "O": 0}         # session score tracker
        self.draws = 0
        self.ai_mode = self.settings["mode"] == "pvc"
        self.ai_difficulty = self.settings["difficulty"]
        self.first_player = "X"               # who opens the current round
        self.round_no = 1
        self.moves: List[Tuple[str, int]] = []
        self.undos = 0
        self.game_over = False
        self.result: Optional[dict] = None
        self._game_over_at = 0.0
        self._round_started: Optional[float] = None

        # --- interaction / animation state ---
        self._gen = 0                         # bumping this cancels running animations
        self._ai_job = None
        self._hover: Optional[int] = None
        self._pointer: Optional[Tuple[int, int]] = None
        self._closing = False

        self.fonts = T.make_fonts(root)
        apply_ttk_dark_style(root, self.fonts)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        logical_h = root.winfo_screenheight() / self.scale
        self.board_px = self.px(max(300, min(440, int(logical_h - 300))))

        self._build_ui()
        self._build_board()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._update_names()
        self._update_sound_button()
        self.diff_seg.set_enabled(self.ai_mode)
        self.update_score()
        self.reset_board()
        self._pulse()

    # ------------------------------------------------------------------ UI --
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def _caption(self, parent, text: str) -> tk.Label:
        return tk.Label(parent, text=text, font=self.fonts.caption, fg=T.MUTED, bg=T.BG, anchor="w")

    def _build_ui(self) -> None:
        f = self.fonts
        header = tk.Frame(self.root, bg=T.BG)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 8))
        header.columnconfigure(1, weight=1)

        logo = tk.Frame(header, bg=T.BG)
        logo.grid(row=0, column=0, sticky="w")
        tk.Label(logo, text="X", font=f.title, fg=T.X_COLOR, bg=T.BG).pack(side="left")
        tk.Label(logo, text="O", font=f.title, fg=T.O_COLOR, bg=T.BG).pack(side="left")
        tk.Label(logo, text="  Tic-Tac-Toe", font=f.title, fg=T.TEXT, bg=T.BG).pack(side="left")
        tk.Label(logo, text="  DARK EDITION", font=f.caption, fg=T.FAINT, bg=T.BG).pack(side="left", pady=(8, 0))

        bar = tk.Frame(header, bg=T.BG)
        bar.grid(row=0, column=2, sticky="e")
        self.btn_sound = FlatButton(bar, "", self.toggle_sound, kind="ghost", font=f.small, padx=12, pady=6)
        for text, command in (("Leaderboard", self.show_leaderboard), ("History", self.show_history),
                              ("Settings", self.show_settings)):
            FlatButton(bar, text, command, kind="ghost", font=f.small, padx=12, pady=6).pack(side="left", padx=(6, 0))
        self.btn_sound.pack(side="left", padx=(6, 0))

        body = tk.Frame(self.root, bg=T.BG)
        body.grid(row=1, column=0, padx=22, pady=(0, 18))

        # ---- left: status + board
        left = tk.Frame(body, bg=T.BG)
        left.grid(row=0, column=0, sticky="n")
        self.status_label = tk.Label(left, text="", font=f.status, bg=T.BG, fg=T.TEXT, anchor="w")
        self.status_label.pack(fill="x")
        self.sub_label = tk.Label(left, text="", font=f.small, fg=T.MUTED, bg=T.BG, anchor="w")
        self.sub_label.pack(fill="x", pady=(0, 10))
        self.canvas = tk.Canvas(left, width=self.board_px, height=self.board_px, bg=T.BG,
                                highlightthickness=0)
        self.canvas.pack()
        tk.Label(left, text=HINT, font=f.small, fg=T.FAINT, bg=T.BG, anchor="w",
                 wraplength=self.board_px).pack(fill="x", pady=(10, 0))

        # ---- right: mode, scoreboard, actions
        right = tk.Frame(body, bg=T.BG)
        right.grid(row=0, column=1, sticky="n", padx=(24, 0))
        tk.Frame(right, width=self.px(290), height=1, bg=T.BG).pack()

        self._caption(right, "GAME MODE").pack(fill="x")
        self.mode_seg = SegmentedControl(
            right, [("pvp", "2 Players"), ("pvc", "vs Computer")],
            "pvc" if self.ai_mode else "pvp", self.set_mode, font=f.body)
        self.mode_seg.pack(fill="x", pady=(4, 14))

        self._caption(right, "AI DIFFICULTY").pack(fill="x")
        self.diff_seg = SegmentedControl(
            right, [(d, d) for d in ai.DIFFICULTIES], self.ai_difficulty,
            self.set_ai_difficulty, font=f.body)
        self.diff_seg.pack(fill="x", pady=(4, 16))

        heading = tk.Frame(right, bg=T.BG)
        heading.pack(fill="x")
        self._caption(heading, "SCOREBOARD").pack(side="left")
        self.round_label = tk.Label(heading, text="", font=f.caption, fg=T.FAINT, bg=T.BG)
        self.round_label.pack(side="right")

        self.score_rows = {}
        self.name_labels = {}
        self.score_labels = {}
        self._make_score_row(right, "X")
        self._make_draw_row(right)
        self._make_score_row(right, "O")

        self.btn_undo = FlatButton(right, "Undo move   Ctrl+Z", self.undo_move, font=f.bold, pady=9)
        self.btn_undo.pack(fill="x", pady=(18, 0))
        self.btn_next = FlatButton(right, "Restart round", self.next_round, font=f.bold, pady=9)
        self.btn_next.pack(fill="x", pady=(8, 0))
        self.btn_reset_scores = FlatButton(right, "Reset scoreboard", self.reset_scores,
                                           kind="ghost", font=f.small, pady=6)
        self.btn_reset_scores.pack(fill="x", pady=(8, 0))

    def _make_score_row(self, parent, symbol: str) -> None:
        f = self.fonts
        row = tk.Frame(parent, bg=T.PANEL, highlightthickness=2, highlightbackground=T.BORDER,
                       highlightcolor=T.BORDER)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text=symbol, font=f.badge, fg=T.SYMBOL_COLOR[symbol], bg=T.PANEL,
                 width=2).pack(side="left", padx=(8, 4), pady=8)
        name = tk.Label(row, text="", font=f.bold, fg=T.TEXT, bg=T.PANEL, anchor="w", cursor="hand2")
        name.pack(side="left", fill="x", expand=True)
        name.bind("<Button-1>", lambda e, s=symbol: self.show_settings(focus=s.lower()))
        score = tk.Label(row, text="0", font=f.score, fg=T.TEXT, bg=T.PANEL, width=3, anchor="e")
        score.pack(side="right", padx=(4, 10))
        self.score_rows[symbol] = row
        self.name_labels[symbol] = name
        self.score_labels[symbol] = score

    def _make_draw_row(self, parent) -> None:
        f = self.fonts
        row = tk.Frame(parent, bg=T.PANEL, highlightthickness=2, highlightbackground=T.BORDER)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="=", font=f.badge, fg=T.DRAW, bg=T.PANEL, width=2).pack(side="left", padx=(8, 4), pady=8)
        tk.Label(row, text="Draws", font=f.bold, fg=T.MUTED, bg=T.PANEL, anchor="w").pack(
            side="left", fill="x", expand=True)
        self.draw_label = tk.Label(row, text="0", font=f.score, fg=T.DRAW, bg=T.PANEL, width=3, anchor="e")
        self.draw_label.pack(side="right", padx=(4, 10))

    def _build_board(self) -> None:
        c, B = self.canvas, self.board_px
        pad = gap = self.px(10)
        self.cell_size = (B - 2 * pad - 2 * gap) / 3
        self.cell_rects: List[Tuple[float, float, float, float]] = []
        self.cell_ids: List[int] = []
        round_rect(c, 1, 1, B - 1, B - 1, self.px(22), fill=T.PANEL, outline=T.BORDER, tags="bg")
        for i in range(9):
            x1 = pad + (i % 3) * (self.cell_size + gap)
            y1 = pad + (i // 3) * (self.cell_size + gap)
            rect = (x1, y1, x1 + self.cell_size, y1 + self.cell_size)
            self.cell_rects.append(rect)
            self.cell_ids.append(round_rect(c, *rect, self.px(14), fill=T.CELL, outline="", tags="cell"))
        c.bind("<Button-1>", self._on_click)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", self._on_leave)

    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<Key>", self._on_key)
        r.bind("<Return>", lambda e: self.game_over and self.next_round())
        r.bind("<KP_Enter>", lambda e: self.game_over and self.next_round())
        r.bind("<Control-z>", lambda e: self.undo_move())
        r.bind("<Control-Z>", lambda e: self.undo_move())
        r.bind("<Control-n>", lambda e: self.next_round())
        r.bind("<Control-t>", lambda e: self.toggle_ai_mode())

    # ------------------------------------------------------- board geometry --
    def _cell_center(self, i: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.cell_rects[i]
        return (x1 + x2) / 2, (y1 + y2) / 2

    def _hit_test(self, x: float, y: float) -> Optional[int]:
        for i, (x1, y1, x2, y2) in enumerate(self.cell_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i
        return None

    def _mark_style(self, symbol: str):
        color = T.SYMBOL_COLOR[symbol]
        return color, T.blend(color, T.CELL, 0.72), self.cell_size * 0.24, max(5.0, self.cell_size * 0.085)

    def _draw_mark(self, index: int, symbol: str, progress: float = 1.0) -> None:
        color, glow, radius, width = self._mark_style(symbol)
        tag = f"mark{index}"
        self.canvas.delete(tag)
        cx, cy = self._cell_center(index)
        draw_mark(self.canvas, cx, cy, radius, symbol, color, width, tags=("mark", tag),
                  progress=progress, glow=glow)

    def _render_static(self) -> None:
        """Redraw every mark in its final state (used after cancelling animations)."""
        self.canvas.delete("mark")
        for i, symbol in enumerate(self.board):
            if symbol:
                self._draw_mark(i, symbol)
        self._reset_cell_fills()

    def _reset_cell_fills(self) -> None:
        for item in self.cell_ids:
            self.canvas.itemconfigure(item, fill=T.CELL)

    # ------------------------------------------------------------ animation --
    def _tween(self, duration_ms: int, on_step, on_done=None, ease=T.ease_out_cubic) -> None:
        """Run on_step(progress 0..1) over duration_ms; skipped to the end if animations are off."""
        if self._closing:
            return
        if not self.settings["animations"] or duration_ms <= 0:
            on_step(1.0)
            if on_done:
                on_done()
            return
        gen = self._gen
        start = time.perf_counter()

        def tick() -> None:
            if self._closing or gen != self._gen:
                return
            t = (time.perf_counter() - start) * 1000.0 / duration_ms
            if t >= 1.0:
                on_step(1.0)
                if on_done:
                    on_done()
                return
            on_step(ease(t))
            self.root.after(FRAME_MS, tick)

        tick()

    def _cancel_animations(self) -> None:
        self._gen += 1
        self.canvas.delete("ghost", "winline", "confetti", "fade")
        self._render_static()

    def _animate_mark(self, index: int, symbol: str, on_done=None) -> None:
        self._tween(260, lambda p: self._draw_mark(index, symbol, p), on_done)

    def _fade_out_mark(self, index: int, symbol: str) -> None:
        if not self.settings["animations"]:
            return
        color, glow, radius, width = self._mark_style(symbol)
        tag = f"fade{index}"
        cx, cy = self._cell_center(index)
        draw_mark(self.canvas, cx, cy, radius, symbol, color, width, tags=("fade", tag), glow=glow)
        self._tween(200, lambda p: recolor(self.canvas, tag, T.blend(color, T.CELL, p), T.blend(glow, T.CELL, p)),
                    on_done=lambda: self.canvas.delete(tag), ease=T.linear)

    def _animate_win_line(self, line: Tuple[int, int, int]) -> None:
        (x1, y1), (x2, y2) = self._cell_center(line[0]), self._cell_center(line[2])
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        ext = self.cell_size * 0.36
        ax, ay, bx, by = x1 - ux * ext, y1 - uy * ext, x2 + ux * ext, y2 + uy * ext
        w = max(5.0, self.cell_size * 0.055)
        layers = ((w + self.px(12), T.blend(T.GOLD, T.CELL, 0.80)),
                  (w + self.px(6), T.blend(T.GOLD, T.CELL, 0.52)),
                  (w, T.GOLD))

        def step(p: float) -> None:
            self.canvas.delete("winline")
            if p > 0:
                ex, ey = ax + (bx - ax) * p, ay + (by - ay) * p
                for width, color in layers:
                    self.canvas.create_line(ax, ay, ex, ey, width=width, fill=color,
                                            capstyle="round", tags="winline")
            tint = T.blend(T.CELL, T.GOLD, 0.12 * p)
            for i in line:
                self.canvas.itemconfigure(self.cell_ids[i], fill=tint)

        self._tween(480, step, ease=T.ease_in_out)

    def _dim_marks(self) -> None:
        colors = {i: T.SYMBOL_COLOR[s] for i, s in enumerate(self.board) if s}

        def step(p: float) -> None:
            for i, color in colors.items():
                recolor(self.canvas, f"mark{i}", T.blend(color, T.DRAW, p),
                        T.blend(T.blend(color, T.CELL, 0.72), T.blend(T.DRAW, T.CELL, 0.72), p))

        self._tween(450, step, ease=T.linear)

    def _confetti(self) -> None:
        if not self.settings["animations"]:
            return
        B = self.board_px
        palette = (T.X_COLOR, T.O_COLOR, T.GOLD, T.ACCENT_HOVER, "#ffffff")
        parts = []
        for _ in range(70):
            x, y = random.uniform(B * 0.12, B * 0.88), random.uniform(-B * 0.12, B * 0.1)
            size = random.uniform(5, 10) * self.scale
            maker = self.canvas.create_rectangle if random.random() < 0.5 else self.canvas.create_oval
            item = maker(x, y, x + size, y + size * 0.6, fill=random.choice(palette), outline="",
                         tags="confetti")
            parts.append([x, y, random.uniform(-90, 90) * self.scale, random.uniform(40, 220) * self.scale,
                          size, item])
        duration, last = 2000, [0.0]

        def step(p: float) -> None:
            now = p * duration / 1000.0
            dt, last[0] = now - last[0], now
            for q in parts:
                q[3] += 520 * self.scale * dt          # gravity
                q[0] += q[2] * dt
                q[1] += q[3] * dt
                self.canvas.coords(q[5], q[0], q[1], q[0] + q[4], q[1] + q[4] * 0.6)

        self._tween(duration, step, on_done=lambda: self.canvas.delete("confetti"), ease=T.linear)

    def _pulse(self) -> None:
        """Gently pulse the border of the active player's scoreboard row."""
        if self._closing:
            return
        if self.settings["animations"] and not self.game_over:
            k = 0.5 + 0.5 * math.sin(time.monotonic() * 3.2)
            color = T.blend(T.BORDER, T.SYMBOL_COLOR[self.current_player], 0.45 + 0.55 * k)
            self.score_rows[self.current_player].configure(highlightbackground=color, highlightcolor=color)
        self.root.after(60, self._pulse)

    # ------------------------------------------------------- mouse / keyboard --
    def _ai_turn_now(self) -> bool:
        return self.ai_mode and self.current_player == self.AI_SYMBOL

    def _cell_clickable(self, index: int) -> bool:
        return not self.game_over and self.board[index] == "" and not self._ai_turn_now()

    def _on_motion(self, event) -> None:
        self._pointer = (event.x, event.y)
        index = self._hit_test(event.x, event.y)
        target = index if index is not None and self._cell_clickable(index) else None
        if target != self._hover:
            self._set_hover(target)
        self.canvas.configure(cursor="hand2" if (target is not None or (self.game_over and index is not None)) else "")

    def _on_leave(self, _event) -> None:
        self._pointer = None
        self._set_hover(None)
        self.canvas.configure(cursor="")

    def _set_hover(self, target: Optional[int]) -> None:
        if self._hover is not None:
            self.canvas.itemconfigure(self.cell_ids[self._hover], fill=T.CELL)
        self.canvas.delete("ghost")
        self._hover = target
        if target is not None:
            self.canvas.itemconfigure(self.cell_ids[target], fill=T.CELL_HOVER)
            symbol = self.current_player
            color = T.blend(T.SYMBOL_COLOR[symbol], T.CELL_HOVER, 0.78)
            _, _, radius, width = self._mark_style(symbol)
            cx, cy = self._cell_center(target)
            draw_mark(self.canvas, cx, cy, radius, symbol, color, width, tags=("ghost",))

    def _refresh_hover(self) -> None:
        self._set_hover(None)
        if self._pointer:
            index = self._hit_test(*self._pointer)
            if index is not None and self._cell_clickable(index):
                self._set_hover(index)

    def _on_click(self, event) -> None:
        if self.game_over:
            if time.monotonic() - self._game_over_at >= 0.45:   # ignore accidental double-clicks
                self.next_round()
            return
        index = self._hit_test(event.x, event.y)
        if index is None or self._ai_turn_now():
            return
        self._place_from_human(index)

    def _on_key(self, event) -> None:
        if event.state & 0x4:       # Ctrl+digit is not a move
            return
        key = event.keysym[3:] if event.keysym.startswith("KP_") else event.keysym
        if len(key) == 1 and key in "123456789" and not self.game_over and not self._ai_turn_now():
            self._place_from_human(int(key) - 1)

    def _place_from_human(self, index: int) -> None:
        if self.board[index] != "":
            self._reject(index)
        else:
            self.on_button_click(index)

    def _reject(self, index: int) -> None:
        self.sound.play("error")
        flash = T.blend(T.CELL, T.DANGER, 0.35)
        self._tween(300, lambda p: self.canvas.itemconfigure(self.cell_ids[index], fill=T.blend(flash, T.CELL, p)),
                    ease=T.linear)

    # ------------------------------------------------------------ game flow --
    def player_name(self, symbol: str) -> str:
        if symbol == "O" and self.ai_mode:
            return COMPUTER_NAME
        return self.settings["name_x"] if symbol == "X" else self.settings["name_o"]

    def check_winner(self) -> bool:
        """True if either player currently has three in a row."""
        return winning_line(self.board) is not None

    def on_button_click(self, index: int) -> bool:
        """Place the current player's mark on `index` (used by humans and the AI)."""
        if self.game_over or self.board[index] != "":
            return False
        symbol = self.current_player
        if self._round_started is None:
            self._round_started = time.monotonic()
        self.board[index] = symbol
        self.moves.append((symbol, index))
        self.sound.play("place_x" if symbol == "X" else "place_o")

        line = winning_line(self.board)
        if line or is_full(self.board):
            winner = symbol if line else None
            self._finish_round(winner)
            self._animate_mark(index, symbol, on_done=lambda: self._show_result(winner, line))
        else:
            self._animate_mark(index, symbol)
            self.current_player = other(symbol)
            self._update_status()
            self._update_buttons()
            self._refresh_score_highlight()
            self._refresh_hover()
            self._maybe_schedule_ai()
        return True

    def _finish_round(self, winner: Optional[str]) -> None:
        """Update scores, save the match and lock the board (visuals follow in _show_result)."""
        self.game_over = True
        self._game_over_at = time.monotonic()
        self._cancel_ai_job()
        duration = time.monotonic() - (self._round_started or time.monotonic())
        if winner:
            self.score[winner] += 1
        else:
            self.draws += 1
        self.result = {"winner": winner}
        self.storage.record_match(
            mode="pvc" if self.ai_mode else "pvp",
            difficulty=self.ai_difficulty if self.ai_mode else None,
            name_x=self.player_name("X"), name_o=self.player_name("O"),
            winner=winner or "draw", moves=self.moves, undos=self.undos, duration=duration)
        self.update_score()
        if winner:
            self._set_status(f"{self.player_name(winner)} wins!", T.GOLD, NEXT_ROUND_HINT)
        else:
            self._set_status("It's a draw!", T.DRAW, NEXT_ROUND_HINT)
        self._set_hover(None)
        self._update_buttons()
        self._refresh_score_highlight()

    def _show_result(self, winner: Optional[str], line) -> None:
        """Sound + win-line / confetti / dimming once the final mark has been drawn."""
        if winner is None:
            self.sound.play("draw")
            self._dim_marks()
            return
        human_lost = self.ai_mode and winner == self.AI_SYMBOL
        self.sound.play("lose" if human_lost else "win")
        if line:
            self._animate_win_line(line)
        if not human_lost:
            self._confetti()

    def reset_board(self) -> None:
        """Clear the board for a fresh round (scores are kept)."""
        self._cancel_ai_job()
        self.board = [""] * 9
        self.moves = []
        self.undos = 0
        self.game_over = False
        self.result = None
        self._round_started = None
        self.current_player = self.first_player
        self._cancel_animations()
        self._hover = None
        self.round_label.configure(text=f"ROUND {self.round_no}")
        self._update_status()
        self._update_buttons()
        self._refresh_score_highlight()
        self._refresh_hover()
        self._maybe_schedule_ai()

    def next_round(self) -> None:
        """Start the next round (after a result) or restart the current one."""
        if self.game_over:
            self.round_no += 1
            if self.settings["alternate_first"]:
                self.first_player = other(self.first_player)
        self.reset_board()

    def reset_scores(self) -> None:
        if not (self.score["X"] or self.score["O"] or self.draws):
            return
        if ask_confirm(self.root, self.fonts, "Reset scoreboard?",
                       "Scores for this session go back to zero. Leaderboard and match history are kept.",
                       "Reset"):
            self._zero_scores()
            self.reset_board()

    def _zero_scores(self) -> None:
        self.score = {"X": 0, "O": 0}
        self.draws = 0
        self.round_no = 1
        self.first_player = "X"
        self.update_score()

    # ----------------------------------------------------------------- undo --
    def can_undo(self) -> bool:
        if self.game_over or not self.moves:
            return False
        if self.ai_mode:     # there must be a human move to take back
            return any(symbol != self.AI_SYMBOL for symbol, _ in self.moves)
        return True

    def undo_move(self) -> None:
        """Take back the last move. Against the computer, its reply is taken back too."""
        if not self.can_undo():
            return
        self._cancel_ai_job()
        removed: List[Tuple[str, int]] = []
        while self.moves:
            symbol, index = self.moves.pop()
            self.board[index] = ""
            removed.append((symbol, index))
            if not self.ai_mode or symbol != self.AI_SYMBOL:
                break
        self.undos += 1
        self.current_player = removed[-1][0]       # the player whose move was taken back
        if not self.moves:
            self._round_started = None
        self._cancel_animations()
        for symbol, index in removed:
            self._fade_out_mark(index, symbol)
        self.sound.play("undo")
        self._update_status()
        self._update_buttons()
        self._refresh_score_highlight()
        self._refresh_hover()

    # ------------------------------------------------------------------- AI --
    def _maybe_schedule_ai(self) -> None:
        if self._ai_turn_now() and not self.game_over and not self._closing:
            delay = 480 if self.settings["animations"] else 120
            self._ai_job = self.root.after(delay, self._ai_turn)

    def _cancel_ai_job(self) -> None:
        if self._ai_job is not None:
            try:
                self.root.after_cancel(self._ai_job)
            except tk.TclError:
                pass
            self._ai_job = None

    def _ai_turn(self) -> None:
        self._ai_job = None
        if self._closing or self.game_over or not self._ai_turn_now():
            return
        self.ai_move()

    def ai_move(self) -> None:
        {"Easy": self.ai_move_easy, "Medium": self.ai_move_medium,
         "Hard": self.ai_move_hard}[self.ai_difficulty]()

    def ai_move_easy(self) -> None:
        self._play_ai_choice(ai.easy_move(list(self.board), self.AI_SYMBOL))

    def ai_move_medium(self) -> None:
        self._play_ai_choice(ai.medium_move(list(self.board), self.AI_SYMBOL))

    def ai_move_hard(self) -> None:
        self._play_ai_choice(ai.hard_move(list(self.board), self.AI_SYMBOL))

    def _play_ai_choice(self, index: Optional[int]) -> None:
        if index is not None:
            self.on_button_click(index)

    # ---------------------------------------------------- mode / difficulty --
    def set_mode(self, mode: str) -> None:
        self.ai_mode = mode == "pvc"
        self.settings["mode"] = mode
        self.mode_seg.set(mode)
        self.diff_seg.set_enabled(self.ai_mode)
        self._zero_scores()            # a different opponent => a fresh scoreboard
        self._update_names()
        self.reset_board()
        self.storage.save_settings()

    def toggle_ai_mode(self) -> None:
        """Switch between 2-player and vs-Computer mode."""
        self.set_mode("pvp" if self.ai_mode else "pvc")

    def set_ai_difficulty(self, difficulty: str) -> None:
        self.ai_difficulty = difficulty
        self.settings["difficulty"] = difficulty
        self.diff_seg.set(difficulty)
        self.reset_board()
        self.storage.save_settings()

    # ----------------------------------------------------- labels / buttons --
    def _set_status(self, text: str, color: str, sub: str) -> None:
        self.status_label.configure(text=text, fg=color)
        self.sub_label.configure(text=sub)

    def _update_status(self) -> None:
        if self.game_over:
            return
        symbol = self.current_player
        color = T.SYMBOL_COLOR[symbol]
        if self._ai_turn_now():
            self._set_status(f"{COMPUTER_NAME}'s turn", color, "Thinking\u2026")
        else:
            who = self.player_name(symbol)
            sub = "Click a cell or press 1\u20139" if self.ai_mode else f"Playing as {symbol}"
            self._set_status(f"{who}'s turn", color, sub)

    def update_score(self) -> None:
        """Refresh the scoreboard numbers."""
        self.score_labels["X"].configure(text=str(self.score["X"]))
        self.score_labels["O"].configure(text=str(self.score["O"]))
        self.draw_label.configure(text=str(self.draws))
        self._update_buttons()

    def _update_names(self) -> None:
        for symbol in ("X", "O"):
            self.name_labels[symbol].configure(text=self.player_name(symbol))

    def _update_buttons(self) -> None:
        if not hasattr(self, "btn_undo"):
            return
        self.btn_undo.set_enabled(self.can_undo())
        if self.game_over:
            self.btn_next.set_text("Next round  \u2192")
            self.btn_next.set_kind("primary")
        else:
            self.btn_next.set_text("Restart round")
            self.btn_next.set_kind("default")
        self.btn_reset_scores.set_enabled(bool(self.score["X"] or self.score["O"] or self.draws))

    def _refresh_score_highlight(self) -> None:
        for symbol, row in self.score_rows.items():
            if self.game_over:
                color = T.GOLD if self.result and self.result["winner"] == symbol else T.BORDER
            elif symbol == self.current_player:
                color = T.SYMBOL_COLOR[symbol]
            else:
                color = T.BORDER
            row.configure(highlightbackground=color, highlightcolor=color)

    # ---------------------------------------------------------- dialogs etc. --
    def toggle_sound(self) -> None:
        self.settings["sound"] = not self.settings["sound"]
        self.sound.enabled = self.settings["sound"]
        self._update_sound_button()
        self.storage.save_settings()

    def _update_sound_button(self) -> None:
        if not self.sound.available:
            self.btn_sound.set_text("Sound: N/A")
            self.btn_sound.set_enabled(False)
        else:
            self.btn_sound.set_text("Sound: On" if self.settings["sound"] else "Sound: Off")

    def show_settings(self, focus: str = "x") -> None:
        result = SettingsDialog(self.root, self.fonts, self.settings, self.ai_mode,
                                self.storage.data_dir, focus).show()
        if result:
            self.settings.update(result)
            self.sound.enabled = self.settings["sound"]
            self._update_names()
            self._update_sound_button()
            self._update_status()
            if self.game_over and self.result:
                winner = self.result["winner"]
                self.status_label.configure(
                    text=f"{self.player_name(winner)} wins!" if winner else "It's a draw!")
            self.storage.save_settings()

    def show_leaderboard(self) -> None:
        LeaderboardDialog(self.root, self.fonts, self.storage).show()

    def show_history(self) -> None:
        HistoryDialog(self.root, self.fonts, self.storage).show()

    def on_close(self) -> None:
        self._closing = True
        self._cancel_ai_job()
        try:
            self.storage.save_settings()
        finally:
            self.root.destroy()


def _enable_hidpi() -> None:
    """Crisp text on high-DPI Windows displays (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - older Windows
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _enable_hidpi()
    root = tk.Tk()
    TicTacToe(root)
    root.mainloop()


if __name__ == "__main__":
    main()
