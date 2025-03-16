import json
import os
import time
from typing import Dict, Any, Set

STATISTICS_FILE = "statistics.json"


def load_statistics() -> Dict[str, Any]:
    """Load the statistics file or initialize a new one."""
    if os.path.exists(STATISTICS_FILE):
        with open(STATISTICS_FILE, "r") as file:
            data: Any = json.load(file)
            if isinstance(data, dict):  # Ensure data is actually a dictionary
                return data
            else:
                print("⚠ Warning: Invalid format in statistics.json. Resetting data.")
                return {"games": {}}  # Reset if corrupted
    return {"games": {}}  # Initialize if file doesn't exist


def save_statistics(data: Dict[str, Any]) -> None:
    """Save statistics to file."""
    with open(STATISTICS_FILE, "w") as file:
        json.dump(data, file, indent=4)


def update_game_statistics(game: Dict[str, Any]) -> None:
    """Update game statistics when a new game is detected."""
    stats: Dict[str, Any] = load_statistics()

    key: str = f"{game['type']} ({game['version']})"
    if key not in stats["games"]:
        stats["games"][key] = {
            "unique_players": set(),
            "game_count": 0,
            "total_playtime_seconds": 0,
            "sessions": [],
        }

    # Ensure unique_players is a set before updating
    unique_players: Set[str] = set(stats["games"][key].get("unique_players", []))
    unique_players.update(game["players"])

    # Save updated values
    stats["games"][key]["unique_players"] = list(
        unique_players
    )  # Convert back to list for JSON
    stats["games"][key]["game_count"] += 1

    # Add session start time
    stats["games"][key]["sessions"].append(
        {
            "timestamp": int(time.time()),
            "players": game["players"],
            "duration": 0,  # Placeholder until the game ends
        }
    )

    save_statistics(stats)


def update_playtime_statistics(game: Dict[str, Any]) -> None:
    """Update total playtime when a game ends."""
    stats: Dict[str, Any] = load_statistics()

    key: str = f"{game['type']} ({game['version']})"
    if key in stats["games"]:
        playtime_seconds: int = int(time.time() - game["first_seen"])
        stats["games"][key]["total_playtime_seconds"] += playtime_seconds

        # Find session and update duration
        for session in stats["games"][key]["sessions"]:
            if session["players"] == game["players"] and session["duration"] == 0:
                session["duration"] = playtime_seconds
                break

    save_statistics(stats)


def get_game_statistics(game_type: str, version: str, days: int) -> Dict[str, Any]:
    """Retrieve statistics for a game type and version within a time range."""
    stats = load_statistics()
    key = f"{game_type} ({version})"

    if key not in stats["games"]:
        return {"message": f"No data found for {game_type} ({version})."}

    # Filter by time range
    cutoff_time = time.time() - (days * 86400)
    game_data = stats["games"][key]

    filtered_sessions = [
        s for s in game_data["sessions"] if s["timestamp"] >= cutoff_time
    ]
    total_time = sum(s["duration"] for s in filtered_sessions)
    unique_players = {player for s in filtered_sessions for player in s["players"]}

    return {
        "game_type": game_type,
        "version": version,
        "days": days,
        "games_played": len(filtered_sessions),
        "unique_players": len(unique_players),
        "total_playtime": total_time,
    }
