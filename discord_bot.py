from typing import List, Dict, Any, Optional
import discord
import json
import time
import asyncio
import datetime
import math
import re
import warnings
from typing import Optional

# Constants
DISCORD_CHANNEL_ID = 1061483226767556719

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
current_online = 0
global_online_list_message: Optional[discord.Message] = None
global_channel: Optional[discord.TextChannel] = None
gameTTL = 120  # games are marked as active for x seconds every time they show up


def escape_discord_formatting_characters(text: str) -> str:
    return re.sub(r'([-\\*_#|~:@[\]()<>`])', r'\\\1', text)


def format_game(game: Dict[str, Any]) -> str:
    global gameTTL
    ended = time.time() - game['last_seen'] >= gameTTL
    text = '';
    if ended:
        text += '~~' + game['id'].upper() + '~~'
    else:
        text += '**' + game['id'].upper() + '**'
    match game['type']:
        case 'DRTL':
            text += ' <:diabloico:760201452957335552>'
        case 'DSHR':
            text += ' <:diabloico:760201452957335552> (spawn)'
        case 'HRTL':
            text += ' <:hellfire:766901810580815932>'
        case 'HSHR':
            text += ' <:hellfire:766901810580815932> (spawn)'
        case 'IRON':
            text += ' Ironman'
        case 'MEMD':
            text += ' <:one_ring:1061898681504251954>'
        case 'DRDX':
            text += ' <:diabloico:760201452957335552> X'
        case 'DWKD':
            text += ' <:mod_wkd:1097321063077122068> modDiablo'
        case 'HWKD':
            text += ' <:mod_wkd:1097321063077122068> modHellfire'
        case _:
            text += ' ' + game['type']

    text += ' ' + game['version']

    match game['tick_rate']:
        case 20:
            text += ''
        case 30:
            text += ' Fast'
        case 40:
            text += ' Faster'
        case 50:
            text += ' Fastest'
        case _:
            text += ' speed: ' + str(game['tick_rate'])

    match game['difficulty']:
        case 0:
            text += ' Normal'
        case 1:
            text += ' Nightmare'
        case 2:
            text += ' Hell'

    attributes = []
    if game['run_in_town']:
        attributes.append('Run in Town')
    if game['full_quests']:
        attributes.append('Quests')
    if game['theo_quest'] and game['type'] != 'DRTL':
        attributes.append('Theo Quest')
    if game['cow_quest'] and game['type'] != 'DRTL':
        attributes.append('Cow Quest')
    if game['friendly_fire']:
        attributes.append('Friendly Fire')

    if len(attributes) != 0:
        text += ' ('
        text += ', '.join(attributes)
        text += ')'

    text += '\nPlayers: **' + '**, **'.join([escape_discord_formatting_characters(name) for name in game['players']]) + '**'
    text += '\nStarted: <t:' + str(round(game['first_seen'])) + ':R>'
    if ended:
        text += '\nEnded after: `' + format_time_delta(round((time.time() - game['first_seen']) / 60)) + '`'

    return text


async def update_status_message() -> None:
    global current_online
    global global_channel
    global global_online_list_message
    if global_online_list_message is not None:
        try:
            await global_online_list_message.delete()
        except discord.errors.NotFound:
            pass
        global_online_list_message = None
    text = 'There are currently **' + str(current_online) + '** public games.'
    if current_online == 1:
        text = 'There is currently **' + str(current_online) + '** public game.'
    assert isinstance(global_channel, discord.TextChannel)
    global_online_list_message = await global_channel.send(text)


async def update_game_message(game_id: str) -> None:
    global global_channel
    text = format_game(game_list[game_id])
    if 'message' in game_list[game_id]:
        message = game_list[game_id]['message'];
        if isinstance(message, discord.Message):
            if message.content != text:
                try:
                    await message.edit(content=text)
                except discord.errors.NotFound:
                    pass
            return
    assert isinstance(global_channel, discord.TextChannel)
    game_list[game_id]['message'] = await global_channel.send(text)


def format_time_delta(minutes: int) -> str:
    if minutes < 2:
        return '1 minute'
    elif minutes < 60:
        return str(minutes) + ' minutes'

    text = ''
    if minutes < 120:
        text += '1 hour'
        minutes -= 60
    else:
        hours = math.floor(minutes / 60)
        text += str(hours) + ' hours'
        minutes -= hours * 60

    if minutes > 0:
        text += ' and ' + format_time_delta(minutes)

    return text


async def end_game_message(game_id: str) -> None:
    if 'message' in game_list[game_id]:
        message = game_list[game_id]['message'];
        if not isinstance(message, discord.Message):
            return
        try:
            await message.edit(content=format_game(game_list[game_id]))
        except discord.errors.NotFound:
            pass


async def remove_game_messages(game_ids: List[str]) -> None:
    for gameId in game_ids:
        if 'message' in game_list[gameId]:
            message = game_list[gameId]['message'];
            if not isinstance(message, discord.Message):
                continue
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass
            del game_list[gameId]['message']


def any_player_name_is_invalid(players: List[str]) -> bool:
    for name in players:
        # using the same restricted character list as DevilutionX, see
        #  https://github.com/diasurgical/devilutionX/blob/0eda8d9367e08cea08b2ad81e1ce534e927646d6/Source/DiabloUI/diabloui.cpp#L649
        if re.search(r'[,<>%&\\"?*#/: ]', name):
            return True

        for char in name:
            if ord(char) < 32 or ord(char) > 126:
                # ASCII control characters or anything outside the basic latin set aren't allowed
                #  in the current DevilutionX codebase, see
                #  https://github.com/diasurgical/devilutionX/blob/0eda8d9367e08cea08b2ad81e1ce534e927646d6/Source/DiabloUI/diabloui.cpp#L654
                return True

    return False


def any_player_name_contains_a_banned_word(players: List[str]) -> bool:
    with open('./banlist', 'r') as ban_list_file:
        words = set([line.strip().upper() for line in ban_list_file.read().split('\n') if line.strip()])

        for name in players:
            for word in words:
                if word in name.upper():
                    return True

    return False


game_list: Dict[str, Dict[str, Any]] = {}
background_task_running = 0


async def background_task() -> None:
    global gameTTL
    global current_online
    last_refresh = 0.0
    refresh_seconds = 60  # refresh gamelist every x seconds
    while True:
        try:
            sleep_time = refresh_seconds - (time.time() - last_refresh)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            last_refresh = time.time()

            # Call the external program and get the output
            proc = await asyncio.create_subprocess_shell(
                './devilutionx-gamelist',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), 30)
            except TimeoutError:
                proc.terminate()
                continue
            output = stdout.decode()
            if not output:
                continue

            # Load the output as a JSON list
            games = json.loads(output)

            ct = datetime.datetime.now()
            print('[' + str(ct) + '] Refreshing game list - ' + str(len(games)) + ' games')

            for game in games:
                if any_player_name_is_invalid(game['players']) or any_player_name_contains_a_banned_word(game['players']):
                    continue

                key = game['id'].upper()
                if key in game_list:
                    game_list[key]['players'] = game['players']
                    game_list[key]['last_seen'] = time.time()
                    continue

                game_list[key] = game
                game_list[key]['first_seen'] = time.time()
                game_list[key]['last_seen'] = time.time()

            ended_games = []
            for key, game in game_list.items():
                if time.time() - game['last_seen'] < gameTTL:
                    continue
                ended_games.append(key)
                await end_game_message(key)

            for key in ended_games:
                del game_list[key]

            if len(ended_games) != 0:
                await remove_game_messages(list(game_list.keys()))

            for gameId in game_list.keys():
                await update_game_message(gameId)

            if (current_online == len(game_list)) or len(ended_games) != 0:
                continue

            current_online = len(game_list)
            await update_status_message()

            activity = discord.Activity(name='Games online: '+str(current_online), type=discord.ActivityType.watching)
            await client.change_presence(activity=activity)
        except discord.errors.DiscordServerError as server_error:
            warnings.warn(repr(server_error))


@client.event
async def on_ready() -> None:
    print(f'We have logged in as {client.user}')
    global global_channel
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    assert isinstance(channel, discord.TextChannel)
    global_channel = channel
    await background_task()

with open('./discord_bot_token', 'r') as file:
    token = file.readline()

client.run(token)
