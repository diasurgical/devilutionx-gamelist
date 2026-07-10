#!/usr/bin/env python3
"""
One-shot CLI tool to fetch and display current DevilutionX games.

This tool wraps the devilutionx-gamelist binary, which connects to the
DevilutionX ZeroTier network to discover active public games.

Requirements:
- The devilutionx-gamelist binary must be built first:
    cmake -S. -Bbuild -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j

- Internet connectivity is required to reach ZeroTier infrastructure
- First run may take longer as ZeroTier establishes network identity

The tool will timeout after 25 seconds by default if no games are found.
This can happen if:
- No public games are currently active
- Network connectivity issues prevent reaching ZeroTier
- The ZeroTier network is unavailable
"""

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


GAME_TYPES = {
    "DRTL": "Diablo",
    "DSHR": "Diablo (spawn)",
    "HRTL": "Hellfire",
    "HSHR": "Hellfire (spawn)",
    "IRON": "Ironman",
    "MEMD": "Memorial",
    "DRDX": "Diablo X",
    "DWKD": "modDiablo",
    "HWKD": "modHellfire",
}

DIFFICULTIES = ["Normal", "Nightmare", "Hell"]


def format_game(game: dict[str, Any], verbose: bool = False) -> str:
    """Format a game entry as a human-readable line."""
    game_id = str(game.get("id", "???")).upper()
    game_type = GAME_TYPES.get(str(game.get("type", "")), str(game.get("type", "???")))
    version = game.get("version", "?")
    diff_val = game.get("difficulty")
    difficulty = DIFFICULTIES[int(diff_val)] if diff_val in (0, 1, 2) else "?"
    players = game.get("players", [])
    assert isinstance(players, list)
    player_list = ", ".join(str(p) for p in players)

    attrs = []
    if game.get("run_in_town"):
        attrs.append("RiT")
    if game.get("full_quests"):
        attrs.append("Quests")
    if game.get("theo_quest") and game.get("type") != "DRTL":
        attrs.append("Theo")
    if game.get("cow_quest") and game.get("type") != "DRTL":
        attrs.append("Cow")
    if game.get("friendly_fire"):
        attrs.append("FF")

    tick_rate = game.get("tick_rate", 20)
    speed = ""
    if tick_rate == 30:
        speed = " Fast"
    elif tick_rate == 40:
        speed = " Faster"
    elif tick_rate == 50:
        speed = " Fastest"
    elif tick_rate not in (20, None):
        speed = f" speed:{tick_rate}"

    attr_str = f" ({', '.join(attrs)})" if attrs else ""
    line = f"{game_id}: {game_type} {version}{speed} {difficulty}{attr_str} - {player_list}"

    if verbose:
        line += f" [{game.get('address', '?')}]"

    return line


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and display current DevilutionX games")
    parser.add_argument("-t", "--timeout", type=int, default=25, help="Timeout in seconds (default: 25)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show game addresses")
    parser.add_argument("-j", "--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--binary", type=str, default="./build/devilutionx-gamelist",
                        help="Path to devilutionx-gamelist binary")
    args = parser.parse_args()

    binary = Path(args.binary)
    if not binary.exists():
        print(f"Error: Binary not found at {binary}", file=sys.stderr)
        print("Run: cmake -S. -Bbuild && cmake --build build -j", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "gamelist.json"
        stderr_file = Path(tmpdir) / "stderr.log"

        with open(stderr_file, "w") as stderr_log:
            proc = subprocess.Popen(
                [str(binary), str(output_file)],
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
            )

        try:
            start = time.time()
            while time.time() - start < args.timeout:
                # Check if process died unexpectedly
                if proc.poll() is not None:
                    break
                if output_file.exists():
                    time.sleep(1)  # Give it a moment to finish writing
                    break
                time.sleep(0.5)

            # Check for early process termination
            if proc.poll() is not None and proc.returncode != 0:
                stderr_content = stderr_file.read_text().strip()
                print("Error: devilutionx-gamelist failed to start", file=sys.stderr)
                if stderr_content:
                    print(stderr_content, file=sys.stderr)
                return 1

            if not output_file.exists():
                if args.verbose:
                    stderr_content = stderr_file.read_text().strip()
                    if stderr_content:
                        print("--- Binary output ---", file=sys.stderr)
                        print(stderr_content, file=sys.stderr)
                        print("---", file=sys.stderr)
                print("No games found (timeout waiting for network/games)", file=sys.stderr)
                return 0

            with open(output_file) as f:
                data = json.load(f)

            if args.json:
                print(json.dumps(data, indent=2))
            else:
                games = data.get("games", [])
                if not games:
                    print("No active games")
                else:
                    print(f"Found {len(games)} game(s):\n")
                    for game in games:
                        print(format_game(game, args.verbose))

        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    return 0


if __name__ == "__main__":
    sys.exit(main())
