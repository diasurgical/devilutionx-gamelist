import discord
import asyncio
from discord.ext import commands
from game_manager import refresh_game_list
from commands import setup_commands
from utils import load_config
from typing import Dict, Any

# Setup Discord Bot
intents = discord.Intents.default()
client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def on_ready() -> None:
    print(f"✅ Logged in as {client.user}")
    await setup_commands(client)
    client.loop.create_task(background_task())

async def background_task() -> None:
    """Periodically refreshes the game list with dynamically loaded config."""
    while True:
        await refresh_game_list(client, load_config())
        await asyncio.sleep(load_config()["refresh_time"])


# Run Bot
with open("./discord_bot_token", "r") as file:
    token = file.readline().strip()

client.run(token)
