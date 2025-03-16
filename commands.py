import discord
from utils import CONFIG, format_time_hhmmss, save_config, is_bot_owner
from discord.ext import commands
from stats import get_game_statistics


async def setup_commands(client: commands.Bot) -> None:
    tree = client.tree

    # ✅ Toggle Debug Mode
    @tree.command(name="toggle_debug", description="Toggle debug mode")
    async def toggle_debug(interaction: discord.Interaction) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["debug"] = not CONFIG.get("debug", False)
        save_config()

        await interaction.response.send_message(
            f"✅ Debug mode {'enabled' if CONFIG['debug'] else 'disabled'}."
        )

    # ✅ Set Refresh Time
    @tree.command(name="set_refresh_time", description="Set bot refresh time")
    async def set_refresh_time(interaction: discord.Interaction, seconds: int) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["refresh_time"] = seconds
        save_config()

        await interaction.response.send_message(
            f"✅ Refresh time updated to {seconds} seconds."
        )

    # ✅ Set Game TTL
    @tree.command(name="set_game_ttl", description="Set game timeout duration")
    async def set_game_ttl(interaction: discord.Interaction, seconds: int) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["game_ttl"] = seconds
        save_config()

        await interaction.response.send_message(
            f"✅ Game TTL updated to {seconds} seconds."
        )

    # ✅ Add Game Type
    @tree.command(name="add_game_type", description="Add a new game type")
    async def add_game_type(
        interaction: discord.Interaction, code: str, name: str
    ) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["game_types"][code.upper()] = name
        save_config()

        await interaction.response.send_message(
            f"✅ Added game type: `{code.upper()}` - {name}"
        )

    # ✅ Set Discord Channel ID
    @tree.command(name="set_channel", description="Set the bot's Discord channel")
    async def set_channel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["discord_channel_id"] = channel.id
        save_config()

        await interaction.response.send_message(
            f"✅ Discord channel set to {channel.mention}."
        )

    # ✅ Add a Bot Owner
    @tree.command(name="add_bot_owner", description="Add a bot owner by user ID")
    async def add_bot_owner(interaction: discord.Interaction, user_id: int) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["bot_owners"].append(user_id)
        save_config()

        await interaction.response.send_message(
            f"✅ User with ID `{user_id}` added as a bot owner."
        )

    # ✅ Remove a Bot Owner
    @tree.command(name="remove_bot_owner", description="Remove a bot owner by user ID")
    async def remove_bot_owner(interaction: discord.Interaction, user_id: int) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        if user_id in CONFIG["bot_owners"]:
            CONFIG["bot_owners"].remove(user_id)
            save_config()
            await interaction.response.send_message(
                f"✅ Removed user with ID `{user_id}` from bot owners."
            )
        else:
            await interaction.response.send_message(
                f"⚠ User with ID `{user_id}` is not a bot owner.", ephemeral=True
            )

    # ✅ Add Difficulty
    @tree.command(name="add_difficulty", description="Add a new difficulty level")
    async def add_difficulty(interaction: discord.Interaction, difficulty: str) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["difficulties"].append(difficulty)
        save_config()

        await interaction.response.send_message(f"✅ Added difficulty: `{difficulty}`.")

    # ✅ Remove Difficulty
    @tree.command(name="remove_difficulty", description="Remove a difficulty level")
    async def remove_difficulty(
        interaction: discord.Interaction, difficulty: str
    ) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        if difficulty in CONFIG["difficulties"]:
            CONFIG["difficulties"].remove(difficulty)
            save_config()
            await interaction.response.send_message(
                f"✅ Removed difficulty: `{difficulty}`."
            )
        else:
            await interaction.response.send_message(
                f"⚠ Difficulty `{difficulty}` not found.", ephemeral=True
            )

    # ✅ Set Tick Rate
    @tree.command(name="set_tick_rate", description="Set a tick rate")
    async def set_tick_rate(
        interaction: discord.Interaction, rate: int, name: str
    ) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["tick_rates"][str(rate)] = name
        save_config()

        await interaction.response.send_message(
            f"✅ Set tick rate `{rate}` to `{name}`."
        )

    # ✅ Remove Tick Rate
    @tree.command(name="remove_tick_rate", description="Remove a tick rate")
    async def remove_tick_rate(interaction: discord.Interaction, rate: int) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        rate_str = str(rate)
        if rate_str in CONFIG["tick_rates"]:
            del CONFIG["tick_rates"][rate_str]
            save_config()
            await interaction.response.send_message(f"✅ Removed tick rate `{rate}`.")
        else:
            await interaction.response.send_message(
                f"⚠ Tick rate `{rate}` not found.", ephemeral=True
            )

    # ✅ Add Game Option
    @tree.command(name="add_game_option", description="Add a new game option")
    async def add_game_option(
        interaction: discord.Interaction, key: str, value: str
    ) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        CONFIG["game_options"][key] = value
        save_config()

        await interaction.response.send_message(
            f"✅ Added game option: `{key}` - {value}"
        )

    # ✅ Remove Game Option
    @tree.command(name="remove_game_option", description="Remove a game option")
    async def remove_game_option(interaction: discord.Interaction, key: str) -> None:
        if not is_bot_owner(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission.", ephemeral=True
            )
            return

        if key in CONFIG["game_options"]:
            del CONFIG["game_options"][key]
            save_config()
            await interaction.response.send_message(f"✅ Removed game option `{key}`.")
        else:
            await interaction.response.send_message(
                f"⚠ Game option `{key}` not found.", ephemeral=True
            )

    await client.tree.sync()

    # ✅ Game Statistics Command
    @tree.command(
        name="game_stats", description="Get game statistics for a specific time range."
    )
    async def game_stats(
        interaction: discord.Interaction, game_type: str, version: str, days: int = 7
    ) -> None:
        """Fetches statistics for a given game type and version within the given time range."""
        stats = get_game_statistics(game_type, version, days)

        if "message" in stats:
            await interaction.response.send_message(f"❌ {stats['message']}")
            return

        # Format total playtime using the utility function
        formatted_time = format_time_hhmmss(stats["total_playtime"])

        await interaction.response.send_message(
            f"📊 **Game Stats for {stats['game_type']} ({stats['version']}) - Last {stats['days']} Days**\n"
            f"🎮 **Games Played:** {stats['games_played']}\n"
            f"👥 **Unique Players:** {stats['unique_players']}\n"
            f"⏳ **Total Playtime:** {formatted_time}"
        )

    await client.tree.sync()
