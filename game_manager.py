import discord
import json
import time
import os
import asyncio
from utils import CONFIG, format_game_embed
from typing import Dict, List, Any

game_list: Dict[str, Dict[str, Any]] = {}

async def fetch_game_list() -> List[Dict[str, Any]]:
    """Fetches the game list by running the external program."""
    try:
        exe_name = "devilutionx-gamelist.exe" if os.name == "nt" else "./devilutionx-gamelist"
        print(f"🔄 Running: {exe_name}")

        proc = await asyncio.create_subprocess_shell(
            exe_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 30)
        except asyncio.TimeoutError:
            proc.terminate()  # Kill the process if it takes too long
            print("⚠️ Timeout: devilutionx-gamelist took too long to respond.")
            return

        if stderr:
            print(f"⚠ Error Output from subprocess:\n{stderr.decode()}")

        output = stdout.decode().strip()
        print(f"📜 Raw output:\n{output if output else '⚠ No output received!'}")

        if not output:
            return []

        try:
            data = json.loads(output)
            if isinstance(data, list) and all(isinstance(game, dict) for game in data):
                print(f"✅ Successfully parsed JSON. {len(data)} game(s) found.")
                return data
            else:
                print(f"❌ JSON structure is not valid: {data}")
                return []
        except json.JSONDecodeError as e:
            print(f"❌ JSON Parsing Error: {e}")
            return []

    except Exception as e:
        print(f"❌ Error fetching game list: {e}")
        return []

async def fetch_game_list_with_retries(retries: int = 3, delay: int = 5) -> List[Dict[str, Any]]:
    """Fetches game list with retries if the result is empty."""
    for attempt in range(retries):
        games = await fetch_game_list()  # Try to fetch game list
        if games:  # If we got games, return them
            return games
        
        print(f"⚠️ Attempt {attempt + 1}: Received empty game list. Retrying in {delay}s...")
        await asyncio.sleep(delay)

    print("❌ No games found after multiple attempts. Assuming closure.")
    return []  # Return empty list if still no data after retries

async def refresh_game_list(client: discord.Client) -> None:
    """Fetches and updates the game list from the external source."""
    print("🔄 Refreshing game list...")

    channel = client.get_channel(CONFIG["discord_channel_id"])
    if not isinstance(channel, discord.TextChannel):  # Validate channel type
        print("❌ Channel not found or invalid! Aborting refresh.")
        return

    games = await fetch_game_list_with_retries()
    current_time = time.time()

    print(f"📥 Fetched {len(games)} games from external source.")

    # Process newly fetched games
    for game in games:
        if not isinstance(game, dict):  # Ensure game data is a dictionary
            print(f"⚠️ Invalid game format: {game}")
            continue

        game_id = game.get("id", "").upper()
        if not game_id:  # Ensure game ID is valid
            print(f"⚠️ Skipping game with missing ID: {game}")
            continue

        if game_id in game_list:
            game_list[game_id]["last_seen"] = current_time
            print(f"✅ Updated last_seen for {game_id}.")
            continue

        # Add new game entry
        game["first_seen"] = current_time
        game["last_seen"] = current_time
        game_list[game_id] = game

        print(f"➕ New game added: {game_id}")

        # Create and send embed
        embed = format_game_embed(game)
        img_path = f"images/{game['type']}.png"

        try:
            if os.path.exists(img_path):
                file = discord.File(img_path, filename=f"{game['type']}.png")
                embed.set_thumbnail(url=f"attachment://{game['type']}.png")  
                game_list[game_id]["message"] = await channel.send(embed=embed, file=file)
                print(f"📤 Sent embed with image for {game_id}.")
            else:
                game_list[game_id]["message"] = await channel.send(embed=embed)
                print(f"📤 Sent embed for {game_id} (no image).")

        except Exception as e:
            print(f"❌ Error sending embed for {game_id}: {e}")

    # Handle expired games
    expired_games = []
    for game_id, game in list(game_list.items()):
        time_since_last_seen = current_time - game["last_seen"]

        print(f"⏳ Checking expiration for {game_id}: last seen {time_since_last_seen:.2f}s ago (TTL: {CONFIG['game_ttl']}s)")

        if time_since_last_seen >= CONFIG["game_ttl"]:
            try:
                if "message" not in game or not game["message"]:
                    print(f"⚠️ Warning: No message object for {game_id}. Skipping.")
                    continue

                embed = format_game_embed(game)  # Generate the updated embed (turns red)
                
                bot_permissions = None
                if isinstance(channel, discord.TextChannel) and channel.guild:
                    bot_permissions = channel.permissions_for(channel.guild.me)
                else:
                    print(f"⚠ Error: Cannot check permissions for {CONFIG['discord_channel_id']} (Invalid channel type)")
                    continue
                
                if not bot_permissions.manage_messages:
                    print(f"🚨 Missing permission to edit messages in {channel.name}.")
                    continue
                
                await game["message"].edit(embed=embed)  # Update the message in Discord
                print(f"🔴 Marked game {game_id} as expired and updated embed.")

            except discord.errors.NotFound:
                print(f"⚠️ Warning: Message for game {game_id} not found. It may have been deleted.")

            except discord.errors.Forbidden:
                print(f"🚨 Error: Missing permission to edit messages in {channel.name}.")

            except Exception as e:
                print(f"❌ Error updating embed for expired game {game_id}: {e}")

            expired_games.append(game_id)  # Mark for removal


    # Remove expired games
    for game_id in expired_games:
        del game_list[game_id]
        print(f"🗑 Removed expired game {game_id} from tracking.")

    # Update bot status with the number of active games
    current_online = len(game_list)
    activity = discord.Activity(name=f"Games online: {current_online}", type=discord.ActivityType.watching)
    await client.change_presence(activity=activity)
    print(f"🎮 Updated bot status: Watching {current_online} games online.")

    print("✅ Game list refresh complete.")
