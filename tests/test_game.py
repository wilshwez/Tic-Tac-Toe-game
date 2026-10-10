"""Run with:  python -m unittest discover -s tests -v

GUI tests need a display; they are skipped automatically when Tk can't open one
(e.g. on a headless server). On Linux you can run them with:  xvfb-run -a python -m unittest discover -s tests -v
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import ai  # noqa: E402
from game.logic import WIN_LINES, empty_cells, other, winner_of, winning_line  # noqa: E402
from game.sounds import SOUND_BUILDERS, SAMPLE_RATE, SoundManager, _write_wav  # noqa: E402
from game.storage import MAX_NAME_LEN, Storage, clean_name  # noqa: E402


def board_from(text: str):
    """'XO.|.X.|..O' -> board list."""
    return [("" if ch == "." else ch) for ch in text.replace("|", "")]


class LogicTests(unittest.TestCase):
    def test_all_eight_lines_detected(self):
        for line in WIN_LINES:
            b = [""] * 9
            for i in line:
                b[i] = "X"
            self.assertEqual(winning_line(b), line)
            self.assertEqual(winner_of(b), "X")

    def test_no_winner_and_helpers(self):
        b = board_from("XO.|.X.|..O")
        self.assertIsNone(winner_of(b))
        self.assertEqual(empty_cells(b), [2, 3, 5, 6, 7])
        self.assertEqual(other("X"), "O")


class AITests(unittest.TestCase):
    def test_easy_returns_legal_move(self):
        b = board_from("XOX|OXO|...")
        for _ in range(30):
            self.assertIn(ai.easy_move(list(b)), [6, 7, 8])
        self.assertIsNone(ai.easy_move(board_from("XOX|OXO|OXO")))

    def test_medium_wins_then_blocks(self):
        # O can win at 2
        self.assertEqual(ai.medium_move(board_from("OO.|XX.|X.."), "O"), 2)
        # X threatens 5, O must block (O has no win available)
        self.assertEqual(ai.medium_move(board_from("O..|XX.|..."), "O"), 5)

    def test_hard_takes_win_and_blocks(self):
        self.assertEqual(ai.hard_move(board_from("OO.|XX.|X.."), "O"), 2)
        self.assertEqual(ai.hard_move(board_from("O..|XX.|..."), "O"), 5)

    def test_minimax_scores_are_from_ai_perspective(self):
        # The original code had these inverted.
        self.assertGreater(ai.minimax(board_from("OOO|XX.|X.."), "X", "O"), 0)   # AI already won
        self.assertLess(ai.minimax(board_from("XXX|OO.|O.."), "O", "O"), 0)      # AI already lost
        self.assertEqual(ai.minimax(board_from("XOX|XOO|OXX"), "X", "O"), 0)     # full board draw

    def test_hard_never_loses_exhaustively(self):
        """Hard AI plays every possible opponent line, as O and as X, and never loses."""
        def explore(board, to_move, ai_symbol):
            win = winner_of(board)
            if win:
                self.assertEqual(win, ai_symbol, f"AI lost on {board}")
                return
            if not empty_cells(board):
                return
            if to_move == ai_symbol:
                move = ai.hard_move(list(board), ai_symbol, random.Random(1))
                board[move] = ai_symbol
                explore(board, other(to_move), ai_symbol)
                board[move] = ""
            else:
                for i in empty_cells(board):
                    board[i] = to_move
                    explore(board, other(to_move), ai_symbol)
                    board[i] = ""

        explore([""] * 9, "X", "O")   # human opens
        explore([""] * 9, "X", "X")   # AI opens

    def test_hard_beats_random_player(self):
        rng = random.Random(7)
        losses = 0
        for _ in range(60):
            b, turn = [""] * 9, "X"
            while not winner_of(b) and empty_cells(b):
                move = ai.hard_move(list(b), "O", rng) if turn == "O" else ai.easy_move(list(b), "X", rng)
                b[move] = turn
                turn = other(turn)
            losses += winner_of(b) == "X"
        self.assertEqual(losses, 0)

    def test_choose_move_validates_difficulty(self):
        with self.assertRaises(ValueError):
            ai.choose_move([""] * 9, "O", "Impossible")
        for d in ai.DIFFICULTIES:
            self.assertIn(ai.choose_move([""] * 9, "O", d), range(9))

    def test_ai_does_not_mutate_board(self):
        b = board_from("X..|.O.|...")
        snapshot = list(b)
        for d in ai.DIFFICULTIES:
            ai.choose_move(b, "O", d)
        self.assertEqual(b, snapshot)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, st, winner, mode="pvp", x="Ann", o="Bob", difficulty=None):
        return st.record_match(mode=mode, difficulty=difficulty, name_x=x, name_o=o, winner=winner,
                               moves=[("X", 0), ("O", 3), ("X", 1), ("O", 4), ("X", 2)], undos=1, duration=3.14)

    def test_clean_name(self):
        self.assertEqual(clean_name("  Wiz   ard \t"), "Wiz ard")
        self.assertEqual(clean_name("a" * 50), "a" * MAX_NAME_LEN)
        self.assertEqual(clean_name("\x00\x07", "Fallback"), "Fallback")

    def test_settings_roundtrip_and_sanitising(self):
        st = Storage(self.dir)
        st.settings.update(name_x="Wizard", sound=False, difficulty="Hard")
        st.save_settings()
        again = Storage(self.dir)
        self.assertEqual(again.settings["name_x"], "Wizard")
        self.assertFalse(again.settings["sound"])
        (self.dir / "settings.json").write_text(json.dumps(
            {"mode": "bogus", "difficulty": "Nightmare", "name_x": "Same", "name_o": "same", "sound": "yes"}))
        bad = Storage(self.dir).settings
        self.assertEqual((bad["mode"], bad["difficulty"], bad["sound"]), ("pvc", "Medium", True))
        self.assertNotEqual(bad["name_x"].casefold(), bad["name_o"].casefold())

    def test_pvp_leaderboard_ranking(self):
        st = Storage(self.dir)
        self._record(st, "X")                       # Ann beats Bob
        self._record(st, "X")                       # Ann beats Bob
        self._record(st, "draw")
        rows = st.leaderboard_rows()
        self.assertEqual([r["name"] for r in rows], ["Ann", "Bob"])
        ann, bob = rows
        self.assertEqual((ann["wins"], ann["draws"], ann["losses"], ann["points"]), (2, 1, 0, 7))
        self.assertEqual((bob["wins"], bob["draws"], bob["losses"], bob["points"]), (0, 1, 2, 1))
        self.assertAlmostEqual(ann["win_rate"], 200 / 3)
        self.assertEqual(ann["rank"], 1)

    def test_computer_games_tracked_per_difficulty_and_name_case_insensitive(self):
        st = Storage(self.dir)
        self._record(st, "X", mode="pvc", x="Wizard", o="Computer", difficulty="Hard")
        self._record(st, "O", mode="pvc", x="wizard", o="Computer", difficulty="Easy")
        self.assertEqual(len(st.leaderboard_rows("all")), 1)             # one person
        self.assertEqual(st.leaderboard_rows("Hard")[0]["wins"], 1)
        self.assertEqual(st.leaderboard_rows("Easy")[0]["losses"], 1)
        self.assertEqual(st.leaderboard_rows("human"), [])               # computer games excluded
        self.assertNotIn("Computer", [r["name"] for r in st.leaderboard_rows()])

    def test_persistence_and_history_content(self):
        st = Storage(self.dir)
        m = self._record(st, "X")
        again = Storage(self.dir)
        self.assertEqual(len(again.history), 1)
        self.assertEqual(again.history[0]["id"], m["id"])
        self.assertEqual(again.history[0]["moves"][0], ["X", 0])
        self.assertEqual(again.history[0]["undos"], 1)
        self.assertEqual(again.leaderboard_rows()[0]["name"], "Ann")
        self.assertEqual(self._record(again, "O")["id"], m["id"] + 1)

    def test_history_cap(self):
        st = Storage(self.dir)
        for _ in range(510):
            self._record(st, "draw")
        self.assertEqual(len(st.history), 500)
        self.assertEqual(st.leaderboard_rows()[0]["games"], 510)   # totals are never trimmed

    def test_corrupt_files_do_not_crash(self):
        (self.dir / "history.json").write_text("{not json")
        (self.dir / "leaderboard.json").write_text("[1,2,3]")
        st = Storage(self.dir)
        self.assertEqual(st.history, [])
        self.assertEqual(st.leaderboard_rows(), [])
        self.assertTrue((self.dir / "history.json.corrupt").exists())
        self._record(st, "X")                                     # still usable afterwards
        self.assertEqual(len(Storage(self.dir).history), 1)

    def test_clear_and_csv_export(self):
        st = Storage(self.dir)
        self._record(st, "X", x="Zoë, the \"Great\"")
        out = self.dir / "export.csv"
        self.assertEqual(st.export_history_csv(out), 1)
        with open(out, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[1][4], "Zoë, the \"Great\"")
        self.assertEqual(rows[1][6], "Zoë, the \"Great\"")
        self.assertEqual(rows[1][10], "X1 O4 X2 O5 X3")
        st.clear_history()
        st.clear_leaderboard()
        again = Storage(self.dir)
        self.assertEqual((again.history, again.leaderboard_rows()), ([], []))


class SoundTests(unittest.TestCase):
    def test_every_effect_is_a_valid_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, build in SOUND_BUILDERS.items():
                samples = build()
                self.assertTrue(samples, name)
                self.assertTrue(all(-1.0 <= s <= 1.0 for s in samples), f"{name} clips")
                path = Path(tmp) / f"{name}.wav"
                _write_wav(path, samples)
                with wave.open(str(path)) as wav:
                    self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()),
                                     (1, 2, SAMPLE_RATE))
                    self.assertEqual(wav.getnframes(), len(samples))

    def test_play_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SoundManager(Path(tmp), enabled=True)
            for name in list(SOUND_BUILDERS) + ["does-not-exist"]:
                manager.play(name)
            manager.enabled = False
            manager.play("win")


# ---------------------------------------------------------------------------
# GUI behaviour (skipped without a display)
# ---------------------------------------------------------------------------
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    HAVE_DISPLAY = True
except Exception:  # noqa: BLE001
    HAVE_DISPLAY = False


class _SilentSound:
    available = False
    enabled = False

    def play(self, name):
        pass


@unittest.skipUnless(HAVE_DISPLAY, "no display available for Tk")
class AppTests(unittest.TestCase):
    def setUp(self):
        from tictactoe import TicTacToe
        self._tmp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.storage = Storage(self._tmp.name)
        self.storage.settings.update(animations=False, mode="pvp", name_x="Ann", name_o="Bob")
        self.app = TicTacToe(self.root, storage=self.storage, sound=_SilentSound())

    def tearDown(self):
        self.app._closing = True
        self.root.destroy()
        self._tmp.cleanup()

    def play(self, *cells):
        for c in cells:
            self.assertTrue(self.app.on_button_click(c))

    def test_pvp_win_scores_and_saves(self):
        self.play(0, 3, 1, 4, 2)                      # X wins top row
        self.assertTrue(self.app.game_over)
        self.assertEqual(self.app.score, {"X": 1, "O": 0})
        self.assertEqual(self.app.score_labels["X"].cget("text"), "1")
        self.assertIn("Ann wins", self.app.status_label.cget("text"))
        self.assertEqual(len(self.storage.history), 1)
        self.assertEqual(self.storage.history[0]["winner"], "X")
        self.assertFalse(self.app.on_button_click(5))   # board locked
        self.assertEqual(self.storage.leaderboard_rows()[0]["name"], "Ann")

    def test_draw(self):
        self.play(0, 1, 2, 4, 3, 5, 7, 6, 8)           # X O X / O X O... full board, no winner
        self.assertTrue(self.app.game_over)
        self.assertEqual(self.app.draws, 1)
        self.assertEqual(self.storage.history[0]["winner"], "draw")

    def test_cannot_overwrite_cell(self):
        self.play(4)
        self.assertFalse(self.app.on_button_click(4))
        self.assertEqual(self.app.current_player, "O")

    def test_undo_pvp(self):
        self.assertFalse(self.app.can_undo())
        self.play(0, 4)
        self.app.undo_move()
        self.assertEqual(self.app.board[4], "")
        self.assertEqual(self.app.current_player, "O")
        self.app.undo_move()
        self.assertEqual(self.app.board, [""] * 9)
        self.assertEqual(self.app.current_player, "X")
        self.assertFalse(self.app.can_undo())

    def test_undo_disabled_after_game_over(self):
        self.play(0, 3, 1, 4, 2)
        self.assertFalse(self.app.can_undo())
        self.app.undo_move()
        self.assertEqual(len(self.storage.history), 1)

    def test_undo_counted_in_history(self):
        self.play(0, 3, 1, 4)            # X0 O3 X1 O4
        self.app.undo_move()             # O's 4 is taken back -> O to move again
        self.assertEqual(self.app.current_player, "O")
        self.play(5, 2)                  # O5, X2 -> X completes the top row
        self.assertTrue(self.app.game_over)
        self.assertEqual(self.storage.history[-1]["undos"], 1)
        self.assertEqual(self.storage.history[-1]["winner"], "X")
        self.assertEqual(self.storage.history[-1]["moves"],
                         [["X", 0], ["O", 3], ["X", 1], ["O", 5], ["X", 2]])

    def test_vs_computer_undo_takes_back_both_moves(self):
        self.app.set_mode("pvc")
        self.app.set_ai_difficulty("Easy")
        self.assertEqual(self.app.player_name("O"), "Computer")
        self.play(4)
        self.assertEqual(self.app.current_player, "O")
        self.app._cancel_ai_job()
        self.app._ai_turn()                              # computer replies
        self.assertEqual(len(self.app.moves), 2)
        self.app.undo_move()
        self.assertEqual(self.app.board, [""] * 9)
        self.assertEqual(self.app.current_player, "X")

    def test_undo_while_computer_is_thinking(self):
        self.app.set_mode("pvc")
        self.play(4)
        self.assertIsNotNone(self.app._ai_job)          # computer move is pending
        self.app.undo_move()
        self.assertIsNone(self.app._ai_job)
        self.assertEqual(self.app.board, [""] * 9)
        self.assertEqual(self.app.current_player, "X")

    def test_computer_opening_move_and_undo_guard(self):
        self.app.set_mode("pvc")
        self.app.set_ai_difficulty("Hard")
        self.app.first_player = "O"
        self.app.reset_board()
        self.assertEqual(self.app.current_player, "O")
        self.app._cancel_ai_job()
        self.app._ai_turn()                              # AI opens
        self.assertEqual(len([c for c in self.app.board if c]), 1)
        self.assertFalse(self.app.can_undo())            # nothing of the human's to take back
        self.assertEqual(self.app.current_player, "X")

    def test_alternate_first_player_and_restart(self):
        self.play(0, 3, 1, 4, 2)
        self.app.next_round()
        self.assertEqual((self.app.round_no, self.app.current_player), (2, "O"))
        self.play(0)                                      # mid-round restart keeps the opener
        self.app.next_round()
        self.assertEqual((self.app.round_no, self.app.current_player), (2, "O"))
        self.app.settings["alternate_first"] = False
        self.app.game_over = True
        self.app.next_round()
        self.assertEqual(self.app.current_player, "O")   # unchanged when alternation is off

    def test_mode_switch_resets_scores_difficulty_keeps_them(self):
        self.play(0, 3, 1, 4, 2)
        self.app.set_mode("pvc")
        self.assertEqual(self.app.score, {"X": 0, "O": 0})
        self.play(4)
        self.app.score["X"] = 2
        self.app.set_ai_difficulty("Hard")
        self.assertEqual(self.app.score["X"], 2)
        self.assertEqual(self.app.board, [""] * 9)

    def test_full_game_vs_hard_computer_never_lost_by_computer(self):
        self.app.set_mode("pvc")
        self.app.set_ai_difficulty("Hard")
        rng = random.Random(3)
        for _ in range(12):
            while not self.app.game_over:
                if self.app.current_player == "O":
                    self.app._cancel_ai_job()
                    self.app._ai_turn()
                else:
                    self.app.on_button_click(rng.choice(empty_cells(self.app.board)))
            self.assertNotEqual(self.app.result["winner"], "X")
            self.app.next_round()

    def test_animated_round_trip_does_not_error(self):
        """Run real tweens (confetti, win line, undo fade) through the Tk event loop."""
        self.app.settings["animations"] = True
        self.play(0, 3, 1, 4)
        self.app.undo_move()
        self.play(4, 2)
        deadline = self.root.tk.call("clock", "milliseconds") + 1200
        while self.root.tk.call("clock", "milliseconds") < deadline:
            self.root.update()
        self.assertTrue(self.app.game_over)
        self.assertTrue(self.app.canvas.find_withtag("winline"))
        self.app.next_round()
        self.root.update()
        self.assertFalse(self.app.canvas.find_withtag("winline"))
        self.assertFalse(self.app.canvas.find_withtag("confetti"))

    def test_mode_persisted(self):
        self.app.set_mode("pvc")
        self.app.set_ai_difficulty("Hard")
        saved = json.loads((Path(self._tmp.name) / "settings.json").read_text())
        self.assertEqual((saved["mode"], saved["difficulty"]), ("pvc", "Hard"))


if __name__ == "__main__":
    unittest.main()
