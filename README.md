# Tic-Tac-Toe — Dark Edition

An upgrade of the original Tkinter Tic-Tac-Toe project. Pure Python, **no third-party packages**.

## Run

```bash
python tictactoe.py          # Windows: py tictactoe.py
```

Requires Python 3.8+ with Tkinter (included with the python.org installers for Windows/macOS).
On Linux, if `import tkinter` fails: `sudo apt install python3-tk`.

## Features

| Feature | Details |
|---|---|
| **Dark UI** | Custom dark theme, flat controls, rounded canvas board, HiDPI-aware on Windows. |
| **Both game modes** | *2 Players* (hot-seat) or *vs Computer* — switch any time from the side panel. |
| **AI difficulty** | **Easy** random · **Medium** win/block/random · **Hard** unbeatable minimax (alpha-beta). |
| **Scoreboard** | Wins for X / O and draws, round counter, active-player highlight, winner highlight. |
| **Animations** | Marks draw themselves in, hover ghost preview, glowing win line, confetti, draw fade, undo fade, invalid-move flash. |
| **Sound effects** | Place X / place O / win / lose / draw / undo / error. Generated at first run — no audio files shipped. |
| **Leaderboard** | Persistent, ranked by points (win 3, draw 1). Filter: All · vs Human · Easy · Medium · Hard. |
| **Match history** | Every finished round is saved (latest 500) with full move list; replay any match move-by-move; export to CSV. |
| **Undo move** | Takes back your last move. Vs Computer it also takes back the computer's reply. |
| **Custom player names** | Click a name on the scoreboard, or open **Settings**. Names are remembered. |

### Controls

| Action | Mouse | Keyboard |
|---|---|---|
| Place a mark | click a cell | `1`–`9` (top-left → bottom-right) |
| Undo | **Undo move** | `Ctrl+Z` |
| Next / restart round | **Next round** or click the board after a result | `Enter` / `Ctrl+N` |
| Switch mode | **Game mode** control | `Ctrl+T` |

### Behaviour notes

- Who opens alternates each round (toggle in Settings). Against the computer, that means it sometimes plays first.
- Changing **mode** starts a fresh scoreboard (different opponent). Changing **difficulty** restarts the board but keeps the score — same as the original.
- Undo is disabled once a round has finished, because the result has already been saved to the leaderboard/history. Undos used in a round are recorded in its history entry.
- Names are max 14 characters; in 2-player mode the two names must differ (leaderboard entries are keyed by name, case-insensitively).
- The computer is not ranked on the leaderboard; your results against it are tracked per difficulty.

## Saved data

Stored as JSON in `data/` next to the game (or `~/.tictactoe_dark/` if the folder isn't writable):
`settings.json`, `leaderboard.json`, `history.json`. Delete a file to reset it. A corrupt file is moved aside
as `*.corrupt` and never crashes the game.

## Project layout

```
tictactoe.py            entry point + main window (class TicTacToe)
game/
  logic.py              pure rules: win lines, helpers
  ai.py                 Easy / Medium / Hard (minimax)
  storage.py            settings, leaderboard, history, CSV export
  sounds.py             WAV synthesis + cross-platform playback
  theme.py              palette, fonts, colour/easing helpers
  widgets.py            dark buttons, segmented control, canvas drawing
  dialogs.py            Settings, Leaderboard, History/replay, Confirm
tests/test_game.py      34 tests (logic, AI, storage, sounds, GUI behaviour)
legacy/                 the original files, untouched
requirements.txt        (no dependencies)
```

## Tests

```bash
python -m unittest discover -s tests -v
```

GUI tests are skipped automatically without a display. Headless Linux: `xvfb-run -a python -m unittest discover -s tests -v`.
The suite includes an exhaustive check that the Hard AI never loses, playing first or second against every possible opponent line.


