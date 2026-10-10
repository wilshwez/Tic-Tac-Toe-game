"""Persistent data: settings, leaderboard and match history (JSON on disk).

Files live in ``<project>/data`` (or ``~/.tictactoe_dark`` if the project folder
is read-only). Writes are atomic and a corrupt file never crashes the game - it
is moved aside as ``*.corrupt`` and a fresh one is started.
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ai import DIFFICULTIES

MAX_NAME_LEN = 14
HISTORY_LIMIT = 500
SCHEMA_VERSION = 1

# Leaderboard buckets: games vs another human, or vs the computer per difficulty.
MODE_KEYS = ("human",) + DIFFICULTIES

DEFAULT_SETTINGS: Dict[str, Any] = {
    "mode": "pvc",              # "pvp" (two players) or "pvc" (vs computer)
    "difficulty": "Medium",
    "name_x": "Player 1",
    "name_o": "Player 2",
    "sound": True,
    "animations": True,
    "alternate_first": True,    # who opens alternates every round
}


def clean_name(raw: Any, fallback: str = "") -> str:
    """Normalise a player name: no control chars, collapsed spaces, max length."""
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(raw or ""))
    text = re.sub(r"\s+", " ", text).strip()[:MAX_NAME_LEN].strip()
    return text or fallback


def default_data_dir() -> Path:
    """Project-local data dir, falling back to the home directory."""
    local = Path(__file__).resolve().parent.parent / "data"
    try:
        local.mkdir(parents=True, exist_ok=True)
        probe = local / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return local
    except OSError:
        fallback = Path.home() / ".tictactoe_dark"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (ValueError, OSError):
        try:  # keep the unreadable file for inspection instead of losing it
            os.replace(path, path.with_name(path.name + ".corrupt"))
        except OSError:
            pass
        return default


def _write_json_atomic(path: Path, data: Any) -> Optional[str]:
    """Write JSON atomically. Returns an error string, or None on success."""
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_name, path)
        return None
    except OSError as exc:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        return str(exc)


def _blank_record() -> Dict[str, int]:
    return {"wins": 0, "draws": 0, "losses": 0}


class Storage:
    """Loads and saves settings, leaderboard and match history."""

    def __init__(self, data_dir: Optional[os.PathLike] = None):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.last_error: Optional[str] = None

        self.settings_path = self.data_dir / "settings.json"
        self.leaderboard_path = self.data_dir / "leaderboard.json"
        self.history_path = self.data_dir / "history.json"

        self.settings = self._load_settings()
        self._players: Dict[str, Dict[str, Any]] = self._load_leaderboard()
        self.history: List[Dict[str, Any]] = []
        self._next_id = 1
        self._load_history()

    # ---- settings ----------------------------------------------------------
    def _load_settings(self) -> Dict[str, Any]:
        raw = _read_json(self.settings_path, {})
        raw = raw if isinstance(raw, dict) else {}
        s = dict(DEFAULT_SETTINGS)
        if raw.get("mode") in ("pvp", "pvc"):
            s["mode"] = raw["mode"]
        if raw.get("difficulty") in DIFFICULTIES:
            s["difficulty"] = raw["difficulty"]
        s["name_x"] = clean_name(raw.get("name_x"), DEFAULT_SETTINGS["name_x"])
        s["name_o"] = clean_name(raw.get("name_o"), DEFAULT_SETTINGS["name_o"])
        if s["name_x"].casefold() == s["name_o"].casefold():
            s["name_o"] = "Player 2" if s["name_x"].casefold() != "player 2" else "Player 1"
        for key in ("sound", "animations", "alternate_first"):
            if isinstance(raw.get(key), bool):
                s[key] = raw[key]
        return s

    def save_settings(self) -> None:
        self.last_error = _write_json_atomic(self.settings_path, self.settings)

    # ---- leaderboard -------------------------------------------------------
    def _load_leaderboard(self) -> Dict[str, Dict[str, Any]]:
        raw = _read_json(self.leaderboard_path, {})
        players: Dict[str, Dict[str, Any]] = {}
        src = raw.get("players", {}) if isinstance(raw, dict) else {}
        if not isinstance(src, dict):
            return players
        for key, entry in src.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("records"), dict):
                continue
            records = {}
            for mode_key in MODE_KEYS:
                rec = entry["records"].get(mode_key)
                if isinstance(rec, dict):
                    clean = _blank_record()
                    for field in clean:
                        value = rec.get(field)
                        clean[field] = value if isinstance(value, int) and value >= 0 else 0
                    records[mode_key] = clean
            name = clean_name(entry.get("name"), str(key))
            players[str(key)] = {"name": name, "records": records}
        return players

    def save_leaderboard(self) -> None:
        payload = {"version": SCHEMA_VERSION, "players": self._players}
        self.last_error = _write_json_atomic(self.leaderboard_path, payload)

    def _bump(self, name: str, mode_key: str, result: str) -> None:
        key = name.casefold()
        entry = self._players.setdefault(key, {"name": name, "records": {}})
        entry["name"] = name  # keep the most recently typed capitalisation
        rec = entry["records"].setdefault(mode_key, _blank_record())
        rec[{"win": "wins", "draw": "draws", "loss": "losses"}[result]] += 1

    def leaderboard_rows(self, mode_filter: str = "all") -> List[Dict[str, Any]]:
        """Ranked rows. `mode_filter` is "all" or one of MODE_KEYS.

        Ranking: points (win=3, draw=1) then win rate then wins then name.
        """
        keys = MODE_KEYS if mode_filter == "all" else (mode_filter,)
        rows: List[Dict[str, Any]] = []
        for entry in self._players.values():
            wins = draws = losses = 0
            for k in keys:
                rec = entry["records"].get(k)
                if rec:
                    wins += rec["wins"]
                    draws += rec["draws"]
                    losses += rec["losses"]
            games = wins + draws + losses
            if games == 0:
                continue
            rows.append({
                "name": entry["name"], "wins": wins, "draws": draws, "losses": losses,
                "games": games, "win_rate": wins * 100.0 / games, "points": 3 * wins + draws,
            })
        rows.sort(key=lambda r: (-r["points"], -r["win_rate"], -r["wins"], r["name"].casefold()))
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows

    def clear_leaderboard(self) -> None:
        self._players = {}
        self.save_leaderboard()

    # ---- history -----------------------------------------------------------
    def _load_history(self) -> None:
        raw = _read_json(self.history_path, {})
        matches = raw.get("matches", []) if isinstance(raw, dict) else []
        clean: List[Dict[str, Any]] = []
        for m in matches if isinstance(matches, list) else []:
            if (isinstance(m, dict) and isinstance(m.get("moves"), list)
                    and m.get("winner") in ("X", "O", "draw") and isinstance(m.get("id"), int)):
                clean.append(m)
        self.history = clean[-HISTORY_LIMIT:]
        stored_next = raw.get("next_id") if isinstance(raw, dict) else None
        highest = max((m["id"] for m in self.history), default=0)
        self._next_id = max(highest + 1, stored_next if isinstance(stored_next, int) else 1)

    def save_history(self) -> None:
        payload = {"version": SCHEMA_VERSION, "next_id": self._next_id, "matches": self.history}
        self.last_error = _write_json_atomic(self.history_path, payload)

    def record_match(self, *, mode: str, difficulty: Optional[str], name_x: str, name_o: str,
                     winner: str, moves: List[tuple], undos: int = 0,
                     duration: float = 0.0) -> Dict[str, Any]:
        """Store a finished round in the history and update the leaderboard.

        `winner` is "X", "O" or "draw". `moves` is [(symbol, cell_index), ...].
        In "pvc" mode Player X is the human and the computer is not ranked.
        """
        match = {
            "id": self._next_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "difficulty": difficulty if mode == "pvc" else None,
            "player_x": name_x,
            "player_o": name_o,
            "winner": winner,
            "moves": [[s, int(i)] for s, i in moves],
            "undos": int(undos),
            "duration": round(float(duration), 1),
        }
        self._next_id += 1
        self.history.append(match)
        del self.history[:-HISTORY_LIMIT]

        def result_for(symbol: str) -> str:
            return "draw" if winner == "draw" else ("win" if winner == symbol else "loss")

        if mode == "pvc":
            self._bump(name_x, difficulty if difficulty in DIFFICULTIES else "Medium", result_for("X"))
        else:
            self._bump(name_x, "human", result_for("X"))
            self._bump(name_o, "human", result_for("O"))
        self.save_history()
        self.save_leaderboard()
        return match

    def clear_history(self) -> None:
        self.history = []
        self.save_history()

    @staticmethod
    def winner_name(match: Dict[str, Any]) -> str:
        if match["winner"] == "draw":
            return "Draw"
        return match["player_x"] if match["winner"] == "X" else match["player_o"]

    def export_history_csv(self, path: os.PathLike) -> int:
        """Write the history to a CSV file. Returns the number of rows."""
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM: Excel-friendly
            writer = csv.writer(fh)
            writer.writerow(["id", "timestamp", "mode", "difficulty", "player_x", "player_o",
                             "result", "moves", "undos", "duration_s", "move_sequence"])
            for m in self.history:
                sequence = " ".join(f"{s}{i + 1}" for s, i in m["moves"])
                writer.writerow([
                    m["id"], m["timestamp"],
                    "vs computer" if m["mode"] == "pvc" else "2 players",
                    m.get("difficulty") or "", m["player_x"], m["player_o"],
                    self.winner_name(m), len(m["moves"]), m.get("undos", 0),
                    m.get("duration", 0), sequence,
                ])
        return len(self.history)
