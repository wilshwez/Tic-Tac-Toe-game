"""Sound effects with zero dependencies.

The WAV files are synthesised with the standard library the first time the game
runs (so the project ships without binary assets) and cached on disk.

Playback backends (first one available wins):
  * Windows: ``winsound``
  * macOS:   ``afplay``
  * Linux:   ``paplay`` / ``aplay`` / ``play`` (sox) / ``ffplay``
If none exists the game simply runs silently.
"""
from __future__ import annotations

import array
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional

SAMPLE_RATE = 22050
CACHE_DIRNAME = "sounds_v1"

Samples = List[float]


# ---- Synthesis -------------------------------------------------------------
def _tone(freq: float, ms: int, vol: float = 0.5, sweep_to: Optional[float] = None,
          square: bool = False, decay: float = 5.0) -> Samples:
    n = int(SAMPLE_RATE * ms / 1000)
    attack = max(1, int(SAMPLE_RATE * 0.004))
    release = max(1, int(SAMPLE_RATE * 0.006))
    out: Samples = []
    phase = 0.0
    for i in range(n):
        frac = i / n
        f = freq if sweep_to is None else freq + (sweep_to - freq) * frac
        phase += 2 * math.pi * f / SAMPLE_RATE
        if square:
            s = 0.55 if math.sin(phase) >= 0 else -0.55
        else:
            s = math.sin(phase) + 0.25 * math.sin(2 * phase)
        env = min(1.0, i / attack) * math.exp(-decay * frac) * min(1.0, (n - i) / release)
        out.append(s * env * vol)
    return out


def _rest(ms: int) -> Samples:
    return [0.0] * int(SAMPLE_RATE * ms / 1000)


def _seq(*parts: Samples) -> Samples:
    merged: Samples = []
    for part in parts:
        merged.extend(part)
    return merged


# Note frequencies (Hz)
C4, E4, G4 = 261.63, 329.63, 392.00
C5, E5, G5, C6 = 523.25, 659.25, 783.99, 1046.50

SOUND_BUILDERS: Dict[str, Callable[[], Samples]] = {
    "place_x": lambda: _tone(740, 90, 0.45, decay=6),
    "place_o": lambda: _tone(520, 100, 0.45, decay=6),
    "win": lambda: _seq(_tone(C5, 110, 0.5), _tone(E5, 110, 0.5), _tone(G5, 110, 0.5),
                        _tone(C6, 380, 0.5, decay=3)),
    "lose": lambda: _seq(_tone(G4, 170, 0.5), _tone(E4, 170, 0.5), _tone(C4, 420, 0.5, decay=3)),
    "draw": lambda: _seq(_tone(E4, 150, 0.45), _rest(40), _tone(E4, 260, 0.4, decay=4)),
    "undo": lambda: _tone(720, 150, 0.4, sweep_to=330, decay=3),
    "error": lambda: _tone(150, 110, 0.35, square=True, decay=3),
}


def _write_wav(path: Path, samples: Samples) -> None:
    pcm = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    if sys.byteorder == "big":  # WAV is little-endian
        pcm.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


# ---- Playback backends -----------------------------------------------------
def _detect_backend() -> Optional[Callable[[str], None]]:
    if sys.platform == "win32":
        try:
            import winsound

            flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            return lambda path: winsound.PlaySound(path, flags)
        except ImportError:
            return None

    commands = []
    if sys.platform == "darwin":
        commands.append(["afplay"])
    commands += [["paplay"], ["aplay", "-q"], ["play", "-q"],
                 ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]]
    for cmd in commands:
        if shutil.which(cmd[0]):
            running: List[subprocess.Popen] = []

            def run(path: str, cmd=cmd, running=running) -> None:
                running[:] = [p for p in running if p.poll() is None]   # reap finished players
                while len(running) >= 4:                                # never pile up processes
                    old = running.pop(0)
                    old.kill()
                    old.wait()
                running.append(subprocess.Popen(cmd + [path], stdin=subprocess.DEVNULL,
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            return run
    return None


class SoundManager:
    """Plays named effects. Never raises: audio problems must not break the game."""

    def __init__(self, cache_dir: Optional[Path] = None, enabled: bool = True):
        self.enabled = enabled
        self._paths: Dict[str, str] = {}
        self._backend = _detect_backend()
        self.available = False
        if self._backend is not None:
            self.available = self._prepare(Path(cache_dir) if cache_dir else None)

    def _prepare(self, base: Optional[Path]) -> bool:
        candidates = []
        if base is not None:
            candidates.append(base / CACHE_DIRNAME)
        candidates.append(Path(tempfile.gettempdir()) / "tictactoe_dark" / CACHE_DIRNAME)
        for folder in candidates:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                paths = {}
                for name, build in SOUND_BUILDERS.items():
                    path = folder / f"{name}.wav"
                    if not path.exists() or path.stat().st_size == 0:
                        _write_wav(path, build())
                    paths[name] = str(path)
                self._paths = paths
                return True
            except OSError:
                continue
        return False

    def play(self, name: str) -> None:
        if not (self.enabled and self.available):
            return
        path = self._paths.get(name)
        if not path:
            return
        try:
            self._backend(path)
        except Exception:  # noqa: BLE001 - audio must never crash the UI
            pass
