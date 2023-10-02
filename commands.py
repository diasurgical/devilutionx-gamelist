import discord
from utils import load_config, save_config, is_admin
from discord.ext import commands
from typing import Dict, Any

async def setup_commands(client: commands.Bot) -> None:
    tree = client.tree

    @tree.command(name="set_refresh_time", description="Set bot refresh time")
    async def set_refresh_time(interaction: discord.Interaction, seconds: int) -> None:
        config = load_config()

        if not is_admin(interaction, config):
            await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
            return
        
        config["refresh_time"] = seconds
        save_config(config)  
        
        await interaction.response.send_message(f"✅ Refresh time updated to {seconds} seconds.")

    @tree.command(name="set_game_ttl", description="Set game timeout duration")
    async def set_game_ttl(interaction: discord.Interaction, seconds: int) -> None:
        config = load_config()

        if not is_admin(interaction, config):
            await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
            return

        config["game_ttl"] = seconds
        save_config(config)  

        await interaction.response.send_message(f"✅ Game TTL updated to {seconds} seconds.")

    @tree.command(name="add_game_type", description="Add a new game type")
    async def add_game_type(interaction: discord.Interaction, code: str, name: str) -> None:
        config = load_config()

        if not is_admin(interaction, config):
            await interaction.response.send_message("❌ You do not have permission.", ephemeral=True)
            return
        
        config["game_types"][code.upper()] = name
        save_config(config)  

        await interaction.response.send_message(f"✅ Added game type: `{code.upper()}` - {name}")

    await client.tree.sync()
