import json
import discord
import os
import time
from typing import Dict, Any
import re


def debug_print(
    *args: Any, sep: str = " ", end: str = "\n", file: Any = None, flush: bool = False
) -> None:
    """Prints messages only if debug mode is enabled."""
    if CONFIG.get("debug", False):
        print(*args, sep=sep, end=end, file=file, flush=flush)


FORBIDDEN_CHARS = r'[,<>%&\\"?*#/: ]'  # Characters not allowed


def sanitize_player_name(name: str) -> str:
    """Removes forbidden characters from a player's name."""
    return re.sub(FORBIDDEN_CHARS, "", name)  # Strip invalid characters


def load_banlist() -> set[str]:
    """Loads the banlist from file and returns a set of bad words."""
    try:
        with open("./banlist", "r") as file:
            return {line.strip().upper() for line in file if line.strip()}
    except FileNotFoundError:
        print("⚠ Warning: Banlist file not found. No words will be filtered.")
        return set()


BANNED_WORDS = load_banlist()


def censor_bad_words(name: str) -> str:
    """Replaces banned words in a player's name with asterisks."""
    name_upper = name.upper()
    for bad_word in BANNED_WORDS:
        if bad_word in name_upper:
            masked_word = "*" * len(bad_word)  # Replace with asterisks
            pattern = re.compile(
                re.escape(bad_word), re.IGNORECASE
            )  # Case-insensitive match
            name = pattern.sub(masked_word, name)  # Replace in original case
    return name


CONFIG: Dict[str, Any] = {}
CONFIG_FILE = "config.json"


def load_config() -> None:
    """Loads the bot configuration from file and stores it globally."""
    global CONFIG
    with open(CONFIG_FILE, "r") as f:
        CONFIG = json.load(f)


# Load Global config immediately
load_config()


def save_config() -> None:
    """Saves the current global config back to file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(CONFIG, f, indent=4)


def is_bot_owner(interaction: discord.Interaction) -> bool:
    """Check if user is a bot owner."""
    if isinstance(interaction.user, discord.Member):  # Ensure it's a Member
        return interaction.user.id in CONFIG["bot_owners"]
    return False  # Default to False if it's not a Member


def format_time_hhmmss(seconds: int) -> str:
    """Formats elapsed time as HH:MM:SS or DD:HH:MM:SS if over 24 hours."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"  # DD:HH:MM:SS
    return f"{hours:02}:{minutes:02}:{seconds:02}"  # HH:MM:SS


def format_game_embed(game: Dict[str, Any]) -> discord.Embed:
    """Formats the game data into a Discord embed."""
    embed = discord.Embed(color=discord.Colour.green())  # Default: Green for active

    current_time = time.time()
    expired = (current_time - game["last_seen"]) >= CONFIG["game_ttl"]

    # Game ID & Expired Status
    game_name = game["id"].upper()
    if expired:
        embed.colour = discord.Colour.red()  # Change to Red
        game_name = "❌"

    # Core Game Info
    difficulty = (
        CONFIG["difficulties"][game["difficulty"]]
        if 0 <= game["difficulty"] < len(CONFIG["difficulties"])
        else "Unknown"
    )
    speed = CONFIG["tick_rates"].get(
        str(game["tick_rate"]), f"Custom ({game['tick_rate']})"
    )
    players = ", ".join(
        censor_bad_words(sanitize_player_name(player)) for player in game["players"]
    )

    options = [
        CONFIG["game_options"].get(opt, opt)
        for opt in game
        if game.get(opt) and opt in CONFIG["game_options"]
    ]
    options_text = ", ".join(options) if options else "None"

    # Determine elapsed time display
    elapsed_seconds = int(current_time - game["first_seen"])
    elapsed_time = format_time_hhmmss(elapsed_seconds)

    if expired:
        time_display = f"🕒 `{elapsed_time}`"  # Duration game was open
    else:
        time_display = f"⏳ <t:{int(game['first_seen'])}:R>"  # Discord timestamp

    # Embed Content
    info_text = (
        f"🎮 {CONFIG['game_types'].get(game['type'], 'Unknown Game')} ({game['version']})\n"
        f"👥 {players}\n"
        f"🛡️ {difficulty} | ⚡ {speed}\n"
        f"🛠️ {options_text}\n"
        f"{time_display}"
    )

    embed.add_field(name=game_name, value=info_text, inline=False)

    # Thumbnail
    img_path = f"images/{game['type']}.png"
    if os.path.exists(img_path):
        embed.set_thumbnail(url=f"attachment://{game['type']}.png")

    return embed
