import asyncio
from collections import deque
import discord
import json
import logging
import math
import re
import time
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
channel: Optional[discord.TextChannel] = None

config: Dict[str, Any] = {
    'channel': 1061483226767556719,
    'game_ttl': 120,
    'refresh_seconds': 60,
    'banlist_file': './banlist',
    'gamelist_program': './devilutionx-gamelist'
}

def escape_discord_formatting_characters(text: str) -> str:
    return re.sub(r'([-\\*_#|~:@[\]()<>`])', r'\\\1', text)


def format_game_message(game: Dict[str, Any]) -> str:
    ended = time.time() - game['last_seen'] >= config['game_ttl']
    text = ''
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


def format_status_message(current_online: int) -> str:
    if current_online == 1:
        return 'There is currently **' + str(current_online) + '** public game.'
    return 'There are currently **' + str(current_online) + '** public games.'


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
    if config['banlist_file'] != '':
        try:
            with open(config['banlist_file'], 'r') as ban_list_file:
                words = set([line.strip().upper() for line in ban_list_file.read().split('\n') if line.strip()])

                for name in players:
                    for word in words:
                        if word in name.upper():
                            return True
        except:
            logger.warn('Unable to load banlist file')

    return False


async def update_message(message: discord.Message, text: str) -> Optional[discord.Message]:
    if message.content != text:
        try:
            message = await message.edit(content=text)
        except discord.errors.NotFound:
            return None
    return message


async def send_message(text: str) -> discord.Message:
    assert isinstance(channel, discord.TextChannel)
    return await channel.send(text)


async def background_task() -> None:
    known_games: Dict[str, Dict[str, Any]] = {}
    active_messages: Deque[discord.Message] = deque()

    last_refresh = 0.0
    while True:
        try:
            sleep_time = config['refresh_seconds'] - (time.time() - last_refresh)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            last_refresh = time.time()

            # Call the external program and get the output
            proc = await asyncio.create_subprocess_shell(
                config['gamelist_program'],
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

            logger.info('Refreshing game list - ' + str(len(games)) + ' games')

            for game in games:
                if any_player_name_is_invalid(game['players']) or any_player_name_contains_a_banned_word(game['players']):
                    continue

                key = game['id'].upper()
                if key in known_games:
                    known_games[key]['players'] = game['players']
                else:
                    known_games[key] = game
                    known_games[key]['first_seen'] = time.time()

                known_games[key]['last_seen'] = time.time()

            ended_games = [key for key, game in known_games.items() if time.time() - game['last_seen'] >= config['game_ttl']]

            for key in ended_games:
                if active_messages:
                    await update_message(active_messages.popleft(), format_game_message(known_games[key]))
                del known_games[key]

            message_index = 0
            for game in known_games.values():
                message_text = format_game_message(game)
                if message_index < len(active_messages):
                    message = await update_message(active_messages[message_index], message_text)
                    assert message is not None
                    active_messages[message_index] = message
                else:
                    message = await send_message(message_text)
                    assert message is not None
                    active_messages.append(message)
                message_index += 1

            game_count = len(known_games)
            if (len(active_messages) <= game_count):
                message = await send_message(format_status_message(game_count))
                assert message is not None
                active_messages.append(message)
            else:
                await update_message(active_messages[game_count], format_status_message(game_count))

            activity = discord.Activity(name='Games online: '+str(game_count), type=discord.ActivityType.watching)
            await client.change_presence(activity=activity)
        except discord.DiscordException as discord_error:
            logger.warn(repr(discord_error))


@client.event
async def on_ready() -> None:
    logger.info(f'We have logged in as {client.user}')

    maybeChannel = client.get_channel(config['channel'])
    assert isinstance(maybeChannel, discord.TextChannel)

    global channel
    channel = maybeChannel
    await background_task()


def run(runtimeConfig: Dict[str, Any]) -> None:
    assert 'token' in runtimeConfig

    for key, value in runtimeConfig.items():
        config[key] = value

    client.run(config['token'])


def main() -> None:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    with open('./discord_bot.json', 'r') as file:
        runtimeConfig = json.load(file)

    run(runtimeConfig)


if __name__ == '__main__':
    main()
