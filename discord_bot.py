import asyncio
from aiohttp.client_exceptions import ClientConnectorDNSError
from collections import deque
import discord
import json
import logging
import math
import re
import time
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

config: Dict[str, Any] = {
    'channel': 1061483226767556719,
    'game_ttl': 120,
    'refresh_seconds': 60,
    'banlist_file': './banlist',
    'gamelist_program': './devilutionx-gamelist',
    'log_level': 'info'
}

def escape_discord_formatting_characters(text: str) -> str:
    return re.sub(r'([-\\*_#|~:@[\]()<>`])', r'\\\1', text)


def format_game_message(game: Dict[str, Any]) -> str:
    ended = time.time() - game['last_seen'] >= config['game_ttl']
    text = ''
    if ended:
        text += '~~' + str(game['id']).upper() + '~~'
    else:
        text += '**' + str(game['id']).upper() + '**'
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
            text += ' ' + str(game['type'])

    text += ' ' + str(game['version'])

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
            logger.warning('Unable to load banlist file')

    return False


class GamebotClient(discord.Client):
    def __init__(self, *, intents, **options):
        intents.message_content = True
        super().__init__(intents=intents, **options)

    async def _update_message(self, message: discord.Message, text: str) -> Optional[discord.Message]:
        if message.content != text:
            try:
                message = await message.edit(content=text)
            except discord.errors.NotFound:
                return None
        return message

    _channel: Optional[discord.TextChannel] = None

    async def _send_message(self, text: str) -> discord.Message:
        assert isinstance(self._channel, discord.TextChannel)
        return await self._channel.send(text)

    async def _background_task(self):
        await self.wait_until_ready()

        logger.debug('Connection established for the first time, preparing for loop start.')

        maybeChannel = self.get_channel(config['channel'])
        assert isinstance(maybeChannel, discord.TextChannel)

        self._channel = maybeChannel

        known_games: Dict[str, Dict[str, Any]] = {}
        active_messages: Deque[discord.Message] = deque()

        last_refresh = 0.0
        while True:
            logger.debug('Starting main loop')
            
            while not self.is_closed():
                try:
                    sleep_time = config['refresh_seconds'] - (time.time() - last_refresh)
                    if sleep_time > 0:
                        logger.debug('Waiting %d seconds before next poll', sleep_time)
                        await asyncio.sleep(sleep_time)
                    last_refresh = time.time()

                    logger.debug('attempting to call %s to get active games', config['gamelist_program'])
                    # Call the external program and get the output
                    proc = await asyncio.create_subprocess_shell(
                        config['gamelist_program'],
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE)

                    try:
                        stdout, stderr = await asyncio.wait_for(proc.communicate(), 30)
                    except TimeoutError:
                        proc.terminate()
                        logger.warning('Fetching active games failed, %s took too long to return', config['gamelist_program'])
                        continue
                    output = stdout.decode()
                    if not output:
                        errors = stderr.decode()
                        if errors:
                            logger.error(errors)
                        continue

                    # Load the output as a JSON list
                    games = json.loads(output)

                    logger.info('Refreshing game list - ' + str(len(games)) + ' games')

                    now = time.time()
                    for game in games:
                        if any_player_name_is_invalid(game['players']) or any_player_name_contains_a_banned_word(game['players']):
                            continue

                        key = game['id'].upper()
                        if key in known_games:
                            known_games[key]['players'] = game['players']
                        else:
                            known_games[key] = game
                            known_games[key]['first_seen'] = now

                        known_games[key]['last_seen'] = now

                    ended_games = [key for key, game in known_games.items() if now - game['last_seen'] >= config['game_ttl']]

                    for key in ended_games:
                        if active_messages:
                            message = active_messages.popleft()
                            try:
                                await self._update_message(message, format_game_message(known_games[key]))
                            except ClientConnectorDNSError as e:
                                logger.warning('DNS failure when attempting to mark a game as ended, assuming this is temporary and retrying next iteration.')
                                active_messages.appendleft(message)
                                continue
                        del known_games[key]

                    message_index = 0
                    for game in known_games.values():
                        message_text = format_game_message(game)
                        if message_index < len(active_messages):
                            try:
                                message = await self._update_message(active_messages[message_index], message_text)
                            except ClientConnectorDNSError as e:
                                logger.warning('DNS failure when attempting to update an active game message, assuming this is temporary and retrying next iteration.')
                                continue
                            assert message is not None
                            active_messages[message_index] = message
                        else:
                            message = await self._send_message(message_text)
                            assert message is not None
                            active_messages.append(message)
                        message_index += 1

                    game_count = len(known_games)
                    if (len(active_messages) <= game_count):
                        message = await self._send_message(format_status_message(game_count))
                        assert message is not None
                        active_messages.append(message)
                    else:
                        try:
                            await self._update_message(active_messages[game_count], format_status_message(game_count))
                        except ClientConnectorDNSError as e:
                            logger.warning('DNS failure when attempting to update the game count message, assuming this is temporary and retrying next iteration.')
                            continue

                    activity = discord.Activity(name='Games online: '+str(game_count), type=discord.ActivityType.watching)
                    await self.change_presence(activity=activity)
                except discord.DiscordException as discord_error:
                    logger.warning(repr(discord_error))
                except Exception as e:
                    logger.exception('Unknown exception occurred: ')

            logger.debug('Connection lost, waiting for reconnect')
            await self.wait_until_ready()


    async def setup_hook(self) -> None:
        self.bg_task = self.loop.create_task(self._background_task())


    async def on_ready(self):
        logger.info(f'We have logged in as {self.user}')


def _translate_to_log_level(targetLevel: str) -> Optional[str]:
    if targetLevel.lower() == 'trace':
        logger.warning('TRACE is not a supported log level by python\'s logging framework, using DEBUG instead')
        targetLevel = 'debug'

    match targetLevel.lower():
        case 'debug':
            return logging.DEBUG
        case 'info':
            return logging.INFO
        case 'warn' | 'warning':
            return logging.WARNING
        case 'error':
            return logging.ERROR
        case 'critical':
            return logging.CRITICAL
        
    return None


def set_log_level(targetLevel: str):
    loggerLevel = _translate_to_log_level(targetLevel)

    if loggerLevel:
        logger.setLevel(loggerLevel)

def run(runtimeConfig: Dict[str, Any]) -> None:
    assert 'token' in runtimeConfig

    for key, value in runtimeConfig.items():
        config[key] = value

    if 'log_level' in config:
        set_log_level(config['log_level'])

    client = GamebotClient(intents=discord.Intents.default())
    client.run(config['token'])


def main() -> None:
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    with open('./discord_bot.json', 'r') as file:
        runtimeConfig = json.load(file)

    run(runtimeConfig)


if __name__ == '__main__':
    main()
