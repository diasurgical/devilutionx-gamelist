import asyncio
from aiohttp.client_exceptions import ClientConnectorError
from collections import deque
import discord
import json
import logging
import math
import pathlib
import re
import time
from bot_db import BotDatabase
from datetime import datetime, UTC
from ipaddress import IPv6Address
from semver import compare
from typing import Any, Deque, Dict, Iterator, List, Optional
from ztapi_client import ZeroTierApiClient

logger = logging.getLogger(__name__)

ztid: str = 'a84ac5c10a7ebb5f'

config: Dict[str, Any] = {
    'channel': 1061483226767556719,
    'game_ttl': 120,
    'banlist_file': './banlist',
    'gamelist_file': './gamelist.json',
    'zt_token': '',
    'log_level': 'info'
}

def escape_discord_formatting_characters(text: str) -> str:
    return re.sub(r'([-\\*_#|~:@[\]()<>`])', r'\\\1', text)


def format_game_message(game: Dict[str, Any]) -> str:
    ended = 'ended' in game
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
    
    if compare(game['version'], "1.6.0") == -1:
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
    else:
        match game['tick_rate']:
            case 20:
                text += ''
            case 25:
                text += ' Fast'
            case 30:
                text += ' Faster'
            case 35:
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
    text += '\nStarted: <t:' + str(round(game['timestamp'])) + ':R>'
    if ended:
        text += '\nEnded after: `' + format_time_delta(round((game['ended'] - game['first_seen']) / 60)) + '`'

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


async def apply_ip_bans(network: Any, members: Any, db: BotDatabase, zt: ZeroTierApiClient) -> None:
    memberLookup = {}
    for member in members:
        memberId = member['config']['id']
        memberLookup[memberId] = member

    memberIds = await db.find_members_to_block()
    for memberId in memberIds:
        member = memberLookup[memberId]
        if member: await zt.tag_member(network, member, 'status', 'blocked')


async def dump_games(games: Any, db: BotDatabase) -> None:
    now = datetime.now(UTC)
    for game in games:
        for playerName in game['players']:
            gameName = game['id']
            await db.save_player_sighting(playerName, gameName, now)


async def dump_sightings(sightings: Any, db: BotDatabase) -> None:
    now = datetime.now(UTC)
    for sighting in sightings:
        ipv6 = IPv6Address(sighting['address'])
        playerName = sighting['name']
        await db.save_member_sighting(ipv6, playerName, now)


async def dump_members(network: Any, members: Any, db: BotDatabase) -> None:
    statusLookup = {}
    statusTag = network['tagsByName']['status']
    statusTagValues = statusTag['enums']
    for statusTagValue in statusTagValues:
        statusTagValueId = statusTagValues[statusTagValue]
        statusLookup[statusTagValueId] = statusTagValue

    statusTagId = statusTag['id']
    for member in members:
        id = member['config']['id']
        physicalAddress = member['physicalAddress'] or ''
        lastSeen = datetime.fromtimestamp(member['lastSeen'] / 1000)
        tags = [t for t in member['config']['tags'] if t[0] == statusTagId]
        tagValueId = tags[0][1] if len(tags) > 0 else statusTag['default']
        status = statusLookup[tagValueId]
        await db.save_zt_member(id, physicalAddress, lastSeen, status)


class GamebotClient(discord.Client):
    def __init__(self, *, intents: discord.Intents) -> None:
        intents.message_content = True
        super().__init__(intents=intents)
        self._last_game_update: float | None = None
        self._last_zt_update: float | None = None
        self._last_log: float | None = None


    async def _register_commands(self, db: BotDatabase, zt: ZeroTierApiClient | None) -> None:
        tree = discord.app_commands.CommandTree(self)

        def split_message(lines: List[str]) -> Iterator[str]:
            chunk: List[str] = []
            count = 0
            for line in lines:
                seplen = 0 if len(chunk) == 0 else 1
                if count + len(line) + seplen > 2000:
                    yield '\n'.join(chunk)
                    chunk = []
                    count = 0
                chunk.append(line)
                count += len(line) + seplen
            if len(chunk) > 0:
                yield '\n'.join(chunk)

        @tree.command(name='findplayer', description='Finds games a player was seen in.')
        @discord.app_commands.describe(name='The name of the player.')
        async def findplayer(interaction: discord.Interaction, name: str) -> None:
            playerSightings = await db.find_player_by_name(name)
            if len(playerSightings) == 0:
                await interaction.response.send_message(content='Player not found', ephemeral=True)
                return

            for chunk in split_message(playerSightings):
                r = not interaction.response.is_done()
                if r: await interaction.response.send_message(content=chunk, ephemeral=True)
                else: await interaction.followup.send(content=chunk, ephemeral=True)

        @tree.command(name='findztgame', description='Finds players that were seen playing in a game.')
        @discord.app_commands.describe(name='The name of the game.')
        async def findztgame(interaction: discord.Interaction, name: str) -> None:
            playerSightings = await db.find_game_by_name(name)
            if len(playerSightings) == 0:
                await interaction.response.send_message(content='Player not found', ephemeral=True)
                return

            for chunk in split_message(playerSightings):
                r = not interaction.response.is_done()
                if r: await interaction.response.send_message(content=chunk, ephemeral=True)
                else: await interaction.followup.send(content=chunk, ephemeral=True)

        @tree.command(name='findztmember', description='Finds info about a ZeroTier member.')
        @discord.app_commands.describe(ztmemberid='The ZeroTier Member ID (ztid) of the player.')
        async def findztmember(interaction: discord.Interaction, ztmemberid: str) -> None:
            ztMemberInfo = await db.find_zt_member_by_id(ztmemberid)
            if len(ztMemberInfo) == 0:
                await interaction.response.send_message(content='Member not found', ephemeral=True)
                return
            await interaction.response.send_message(content=ztMemberInfo, ephemeral=True)

        @tree.command(name='listztmembers', description='Lists info about recently seen ZeroTier members.')
        async def listztmembers(interaction: discord.Interaction) -> None:
            ztMembers = await db.list_zt_members()
            if len(ztMembers) == 0:
                await interaction.response.send_message(content='No members', ephemeral=True)
                return

            for chunk in split_message(ztMembers):
                r = not interaction.response.is_done()
                if r: await interaction.response.send_message(content=chunk, ephemeral=True)
                else: await interaction.followup.send(content=chunk, ephemeral=True)

        @tree.command(name='listbanned', description='List recently banned IP addresses.')
        async def listbanned(interaction: discord.Interaction) -> None:
            bans = await db.list_bans()
            if len(bans) == 0:
                await interaction.response.send_message(content='No IP bans', ephemeral=True)
                return

            for chunk in split_message(bans):
                r = not interaction.response.is_done()
                if r: await interaction.response.send_message(content=chunk, ephemeral=True)
                else: await interaction.followup.send(content=chunk, ephemeral=True)

        @tree.command(name='ztban', description='Bans an IP address from using ZeroTier.')
        @discord.app_commands.describe(ip='The physical IP address of the user.')
        async def ztban(interaction: discord.Interaction, ip: str) -> None:
            await db.ban(ip)
            await interaction.response.send_message(content=f'IP {ip} banned', ephemeral=True)

        @tree.command(name='revokeztban', description='Revokes a previously banned IP address so it can use ZeroTier.')
        @discord.app_commands.describe(ip='The physical IP address of the user.')
        async def revokeztban(interaction: discord.Interaction, ip: str) -> None:
            await db.remove_ban(ip)
            await interaction.response.send_message(content=f'Revoked ban on {ip}', ephemeral=True)

        if zt:
            @tree.command(name='setztstatus', description='Updates the value of the status tag for a ZeroTier member.')
            @discord.app_commands.describe(memberid='The ZeroTier Member ID (ztid) of the player.')
            @discord.app_commands.describe(status='The status of their membership.')
            async def setztstatus(interaction: discord.Interaction, memberid: str, status: str) -> None:
                if status not in ('allowed', 'blocked'):
                    await interaction.response.send_message(content='Invalid status: must be "allowed" or "blocked"', ephemeral=True)
                    return
                network = await zt.get_network(ztid)
                member = await zt.get_member(ztid, memberid)
                await zt.tag_member(network, member, 'status', status)
                await interaction.response.send_message(content=f'Status of member {memberid} updated to {status}', ephemeral=True)

        await tree.sync()


    async def _update_message(self, message: discord.Message, text: str) -> Optional[discord.Message]:
        if message.content != text:
            try:
                message = await message.edit(content=text)
            except discord.errors.NotFound:
                return None
        return message


    async def _send_message(self, text: str) -> discord.Message:
        assert isinstance(self._channel, discord.TextChannel)
        return await self._channel.send(text)


    async def _update_discord_channel(self, games: Any) -> None:
        now = time.monotonic()
        timestamp = time.time()
        known_games = self._known_games
        for game in games:
            if any_player_name_is_invalid(game['players']) or any_player_name_contains_a_banned_word(game['players']):
                continue

            key = game['id'].upper()
            if key in known_games:
                known_games[key]['players'] = game['players']
            else:
                known_games[key] = game
                known_games[key]['timestamp'] = timestamp
                known_games[key]['first_seen'] = now

            known_games[key]['last_seen'] = now

        ended_games = [key for key, game in known_games.items() if now - game['last_seen'] >= config['game_ttl']]

        active_messages = self._active_messages
        last_game_update = self._last_game_update
        last_log = self._last_log
        if active_messages and not games and not ended_games:
            if last_game_update and now - last_game_update >= 60 and (not last_log or now - last_log >= 60):
                logger.debug(f'No games seen in the last {round(now - last_game_update)} seconds.')
                self._last_log = now
            return

        active_games_text = '1 active game' if len(games) == 1 else f'{len(games)} active games'
        ended_games_text = '1 ended game' if len(ended_games) == 1 else f'{len(ended_games)} ended games'
        logger.debug(f'Updating game list with {active_games_text} and {ended_games_text}.')
        self._last_game_update = now

        try:
            for key in ended_games:
                known_games[key]['ended'] = now
                if active_messages:
                    message = active_messages.popleft()
                    try:
                        await self._update_message(message, format_game_message(known_games[key]))
                    except ClientConnectorError as e:
                        logger.warning('Connection error when attempting to mark a game as ended, assuming this is temporary and retrying next iteration.')
                        active_messages.appendleft(message)
                        continue
                del known_games[key]

            message_index = 0
            for game in known_games.values():
                message_text = format_game_message(game)
                if message_index < len(active_messages):
                    try:
                        maybeMessage = await self._update_message(active_messages[message_index], message_text)
                    except ClientConnectorError as e:
                        logger.warning('Connection error when attempting to update an active game message, assuming this is temporary and retrying next iteration.')
                        continue
                    assert maybeMessage is not None
                    active_messages[message_index] = maybeMessage
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
                except ClientConnectorError as e:
                    logger.warning('Connection error when attempting to update the game count message, assuming this is temporary and retrying next iteration.')
                    return

            activity = discord.Activity(name='Games online: '+str(game_count), type=discord.ActivityType.watching)
            await self.change_presence(activity=activity)
        except discord.DiscordException as discord_error:
            logger.warning(repr(discord_error))


    async def _process_games(self, db: BotDatabase) -> None:
        games = []
        sightings = []
        try:
            # Load the file as a JSON object
            with open(config['gamelist_file']) as file:
                gamelist_data = json.load(file)
                games = gamelist_data["games"]
                sightings = gamelist_data["player_sightings"]

            # Delete the file when we're done with it
            pathlib.Path.unlink(config['gamelist_file'])
        except FileNotFoundError:
            pass

        tasks = []
        tasks.append(self.loop.create_task(self._update_discord_channel(games)))
        if games: tasks.append(self.loop.create_task(dump_games(games, db)))
        if sightings: tasks.append(self.loop.create_task(dump_sightings(sightings, db)))
        await asyncio.gather(*tasks)


    async def _process_zt_members(self, zt: ZeroTierApiClient, db: BotDatabase) -> None:
        logger.debug('Querying ZeroTier API for member list')
        network = await zt.get_network(ztid)
        if not network: return
        members = await zt.get_members(ztid)
        if not members: return
        await dump_members(network, members, db)
        await apply_ip_bans(network, members, db, zt)


    async def _background_task(self) -> None:
        await self.wait_until_ready()

        logger.debug('Connection established for the first time, preparing for loop start.')

        maybeChannel = self.get_channel(config['channel'])
        assert isinstance(maybeChannel, discord.TextChannel)

        self._channel = maybeChannel
        self._known_games: Dict[str, Dict[str, Any]] = {}
        self._active_messages: Deque[discord.Message] = deque()

        async def main_loop(db: BotDatabase, zt: ZeroTierApiClient | None) -> None:
            while not self.is_closed():
                try:
                    await asyncio.sleep(1)

                    now = time.monotonic()
                    zt_api_is_ready = not self._last_zt_update or now - self._last_zt_update >= 60

                    tasks = []
                    tasks.append(self.loop.create_task(self._process_games(db)))
                    if zt and zt_api_is_ready:
                        tasks.append(self.loop.create_task(self._process_zt_members(zt, db)))
                        self._last_zt_update = now
                    tasks.append(self.loop.create_task(db.clean_up()))
                    await asyncio.gather(*tasks)
                except Exception as e:
                    logger.exception('Unknown exception occurred: ')

        try:
            async with BotDatabase() as db:
                async with ZeroTierApiClient(config['zt_token']) as zt:
                    maybeZt = zt if config['zt_token'] != '' else None
                    await self._register_commands(db, maybeZt)
                    while True:
                        logger.debug('Starting main loop')
                        await main_loop(db, maybeZt)
                        logger.debug('Connection lost, waiting for reconnect')
                        await self.wait_until_ready()
        except Exception as e:
            logger.exception('Unknown exception occurred: ')


    async def setup_hook(self) -> None:
        self.bg_task = self.loop.create_task(self._background_task())


    async def on_ready(self) -> None:
        logger.info(f'We have logged in as {self.user}')


def _translate_to_log_level(targetLevel: str) -> Optional[int]:
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


def set_log_level(targetLevel: str) -> None:
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
    handler = logging.StreamHandler()

    logging.basicConfig(
        level=logging.INFO,
        format='[{asctime}] [{levelname:<8}] {name}: {message}',
        datefmt='',
        style='{',
        handlers=(handler,),
        force=True)

    logger.setLevel(logging.DEBUG)

    with open('./discord_bot.json', 'r') as file:
        runtimeConfig = json.load(file)

    run(runtimeConfig)


if __name__ == '__main__':
    main()
