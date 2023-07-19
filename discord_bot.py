import discord
import subprocess
import json
import time
import asyncio
import datetime
import math
import re

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
currentOnline = 0
globalOnlineListMessage = -1
globalChannel = -1
gameTTL = 120 # games are marked as active for x seconds every time they show up

def escapeDiscordFormattingCharacters(text: str):
    return re.sub(r'([-\\*_#[\]()<>`])', r'\\\1', text)

def formatGame(game):
    global gameTTL
    ended = time.time() - game['last_seen'] >= gameTTL
    if ended:
        text = '~~' + game['id'].upper() + '~~'
    else:
        text = '**' + game['id'].upper() + '**'
    if game['type'] == 'DRTL':
        text += ' <:diabloico:760201452957335552>'
    elif game['type'] == 'DSHR':
        text += ' <:diabloico:760201452957335552> (spawn)'
    elif game['type'] == 'HRTL':
        text += ' <:hellfire:766901810580815932>'
    elif game['type'] == 'HSHR':
        text += ' <:hellfire:766901810580815932> (spawn)'
    elif game['type'] == 'IRON':
        text += ' Ironman'
    elif game['type'] == 'MEMD':
        text += ' <:one_ring:1061898681504251954>'
    elif game['type'] ==  'DRDX':
        text += ' <:diabloico:760201452957335552> X'
    elif game['type'] ==  'DWKD':
        text += ' <:mod_wkd:1097321063077122068> modDiablo'
    elif game['type'] ==  'HWKD':
        text += ' <:mod_wkd:1097321063077122068> modHellfire'
    else:
        text += ' ' + game['type']

    text += ' ' + game['version']

    if game['tick_rate'] == 20:
        text += ''
    elif game['tick_rate'] == 30:
        text += ' Fast'
    elif game['tick_rate'] == 40:
        text += ' Faster'
    elif game['tick_rate'] == 50:
        text += ' Fastest'
    else:
        text += ' speed: ' + str(game['tick_rate'])

    if game['difficulty'] == 0:
        text += ' Normal'
    elif game['difficulty'] == 1:
        text += ' Nightmare'
    elif game['difficulty'] == 2:
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

    text += '\nPlayers: **' + '**, **'.join([escapeDiscordFormattingCharacters(name) for name in game['players']]) + '**'
    text += '\nStarted: <t:' + str(round(game['first_seen'])) + ':R>'
    if ended:
        text += '\nEnded after: `' + formatTimeDelta(round((time.time() - game['first_seen']) / 60)) + '`'

    return text

async def updateStatusMessage():
    global currentOnline
    global globalChannel
    global globalOnlineListMessage
    if (globalOnlineListMessage != -1):
        try:
            await globalOnlineListMessage.delete()
        except discord.errors.NotFound:
            pass
        globalOnlineListMessage = -1
    text = 'There are currently **' + str(currentOnline) + '** public games.'
    if currentOnline == 1:
        text = 'There is currently **' + str(currentOnline) + '** public game.'
    globalOnlineListMessage = await globalChannel.send(text)

async def updateGameMessage(gameId):
    global globalChannel
    text = formatGame(gameList[gameId])
    if 'message' in gameList[gameId].keys():
        if (gameList[gameId]['message'].content != text):
            try:
                await gameList[gameId]['message'].edit(content=text)
            except discord.errors.NotFound:
                pass
        return
    gameList[gameId]['message'] = await globalChannel.send(text)

def formatTimeDelta(minutes):
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

    if (minutes > 0):
        text += ' and ' + formatTimeDelta(minutes)

    return text

async def endGameMessage(gameId):
    if 'message' in gameList[gameId].keys():
        try:
            await gameList[gameId]['message'].edit(content=formatGame(gameList[gameId]))
        except discord.errors.NotFound:
            pass

async def removeGameMessages(gameIds):
    for gameId in gameIds:
        if 'message' in gameList[gameId].keys():
            try:
                await gameList[gameId]['message'].delete()
            except discord.errors.NotFound:
                pass
            del gameList[gameId]['message']

gameList = {}
backgroundTaskRunning = 0
async def backgroundTask():
    global gameTTL
    global currentOnline
    lastRefresh = 0
    refreshSeconds = 60 #refresh gamelist every x seconds
    while True:
        await asyncio.sleep(1)
        if time.time() - lastRefresh >= refreshSeconds:
            lastRefresh = time.time()
            # Call the external program and get the output
            proc = await asyncio.create_subprocess_shell(
                './devilutionx-gamelist',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)

            stdout, stderr = await proc.communicate()
            output = stdout.decode()
            if not output:
                continue

            # Load the output as a JSON list
            games = json.loads(output)

            ct = datetime.datetime.now()
            print('[' + str(ct) + '] Refreshing game list - ' + str(len(games)) + ' games')

            for game in games:
                banned = False
                with open('./banlist', 'r') as file:
                    words = file.read().split('\n')
                    for word in words:
                        for name in game['players']:
                            if word.strip() and word.strip().upper() in name.upper():
                                banned = True
                                break
                if banned:
                    continue

                key = game['id'].upper()
                if key in gameList.keys():
                    del gameList[key]['players']
                    gameList[key]['players'] = game['players']
                    gameList[key]['last_seen'] = time.time()
                    continue

                gameList[key] = game
                gameList[key]['first_seen'] = time.time()
                gameList[key]['last_seen'] = time.time()

            endedGames = []
            for key in gameList:
                game = gameList[key]
                if time.time() - game['last_seen'] < gameTTL:
                    continue
                endedGames.append(key)
                await endGameMessage(key)

            for key in endedGames:
                del gameList[key]

            if len(endedGames) != 0:
                await removeGameMessages(gameList.keys())

            for gameId in gameList.keys():
                await updateGameMessage(gameId)

            if (currentOnline == len(gameList)) or len(endedGames) != 0:
                continue

            currentOnline = len(gameList)
            await updateStatusMessage()

            activity = discord.Activity(name='Games online: '+str(currentOnline), type=discord.ActivityType.watching)
            await client.change_presence(activity=activity)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    global globalChannel
    globalChannel = client.get_channel(1061483226767556719)
    await backgroundTask()

token = ''
with open('./discord_bot_token', 'r') as file:
    token = file.readline()

client.run(token)
