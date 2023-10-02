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

def format_game_embed(game: Dict[str, Any], config: Dict[str, Any]) -> discord.Embed:
    """Formats the game data into a Discord embed."""
    embed = discord.Embed(title=game["id"].upper(), colour=discord.Colour.green())  # Default: Green for active

    # Check if game has expired
    current_time = time.time()
    if current_time - game["last_seen"] >= config["game_ttl"]:
        embed.colour = discord.Colour.red()  # Change to Red
        embed.title = f"❌ Game Closed: {game['id'].upper()}"

    # Game Type & Version
    game_title = config["game_types"].get(game["type"], "Unknown Game")
    embed.set_author(name=f"{game_title} {game['version']}")

    # Compact Field Formatting
    difficulty = config["difficulties"][game["difficulty"]] if 0 <= game["difficulty"] < len(config["difficulties"]) else "Unknown"
    speed = config["tick_rates"].get(str(game["tick_rate"]), f"Custom ({game['tick_rate']})")
    players = ", ".join(game["players"])

    # Ensure only active options are included
    options = [config["game_options"].get(opt, opt) for opt in game if game.get(opt) and opt in config["game_options"]]
    options_text = ", ".join(options) if options else "None"

    # Move game name into the field title instead of the embed title
    game_name = game["id"].upper()

    # Create a single compact field with all essential info
    info_text = (
        f"🎮 {config['game_types'].get(game['type'], 'Unknown Game')} ({game['version']})\n"
        f"👥 {players}\n"
        f"🛡️ {difficulty} | ⚡ {speed}\n"
        f"🛠️ {options_text}"
    )

    # Create the embed without a title
    embed = discord.Embed(color=discord.Color.green())  # Default: Green for active

    # Mark as expired if necessary
    current_time = time.time()
    if current_time - game["last_seen"] >= config["game_ttl"]:
        embed.colour = discord.Colour.red()  # Change to Red
        game_name = f"❌ (Closed)"

    embed.add_field(name=game_name, value=info_text, inline=False)

    # Thumbnail
    img_path = f"images/{game['type']}.png"
    if os.path.exists(img_path):
        embed.set_thumbnail(url=f"attachment://{game['type']}.png")

    return embed


