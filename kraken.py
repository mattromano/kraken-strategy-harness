"""Thin wrapper around the `kraken` CLI — binary resolution + JSON command runner.

Shared by data.py (market data) and paper.py (paper trading). Stdlib only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_BIN_CACHE: str | None = None


def kraken_bin() -> str:
    """Locate the `kraken` executable on PATH, falling back to ~/.cargo/bin."""
    global _BIN_CACHE
    if _BIN_CACHE:
        return _BIN_CACHE
    found = shutil.which("kraken") or str(Path.home() / ".cargo" / "bin" / "kraken")
    if not Path(found).is_file():
        raise FileNotFoundError(
            "could not find the 'kraken' CLI on PATH or in ~/.cargo/bin. "
            "Install it: https://github.com/krakenfx/kraken-cli"
        )
    _BIN_CACHE = found
    return found


def run_json(args: list[str]) -> dict | list:
    """Run `kraken <args> -o json` and return parsed JSON. Raises on failure."""
    cmd = [kraken_bin(), *args, "-o", "json"]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"kraken command failed ({' '.join(args)}):\n{proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"kraken returned non-JSON output for ({' '.join(args)}):\n{proc.stdout[:300]}") from e
