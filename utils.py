import json
import discord
import os
import time
from typing import Dict, Any

def load_config() -> Dict[str, Any]:
    """Loads the bot configuration from file."""
    with open("config.json", "r") as f:
        data: Dict[str, Any] = json.load(f)
    return data

def save_config(config: Dict[str, Any]) -> None:
    """Saves the updated config to file."""
    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

def is_admin(interaction: discord.Interaction, config: Dict[str, Any]) -> bool:
    """Check if user is an admin or a bot owner."""
    if isinstance(interaction.user, discord.Member):  # Ensure it's a Member
        return interaction.user.guild_permissions.administrator or interaction.user.id in config["bot_owners"]
    return False  # Default to False if it's not a Member

def format_time_hhmmss(seconds: int) -> str:
    """Formats elapsed time as HH:MM:SS or DD:HH:MM:SS if over 24 hours."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days:02}:{hours:02}:{minutes:02}:{seconds:02}"  # DD:HH:MM:SS
    return f"{hours:02}:{minutes:02}:{seconds:02}"  # HH:MM:SS

def format_game_embed(game: Dict[str, Any], config: Dict[str, Any]) -> discord.Embed:
    """Formats the game data into a Discord embed."""
    embed = discord.Embed(color=discord.Colour.green())  # Default: Green for active

    current_time = time.time()
    expired = (current_time - game["last_seen"]) >= config["game_ttl"]

    # Game ID & Expired Status
    game_name = game["id"].upper()
    if expired:
        embed.colour = discord.Colour.red()  # Change to Red
        game_name = "❌"

    # Core Game Info
    difficulty = config["difficulties"][game["difficulty"]] if 0 <= game["difficulty"] < len(config["difficulties"]) else "Unknown"
    speed = config["tick_rates"].get(str(game["tick_rate"]), f"Custom ({game['tick_rate']})")
    players = ", ".join(game["players"])
    
    options = [config["game_options"].get(opt, opt) for opt in game if game.get(opt) and opt in config["game_options"]]
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
        f"🎮 {config['game_types'].get(game['type'], 'Unknown Game')} ({game['version']})\n"
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
