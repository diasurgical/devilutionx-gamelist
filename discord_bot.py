import discord
import subprocess
import json
import time
import asyncio
import datetime

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
backgroundRunning = 0
globalOnlineListMessage = -1

def generateGameList(games):
    text = 'There are currently **' + str(len(games)) + '** public games.'

    if len(games) != 0:
        text += '\n\n';

    # Print each name in the list
    for ID in games:
        game = games[ID]
        text += '**' + game['id'].upper() + '**';
        if game['type'] == 'DRTL':
            text += ' <:diabloico:760201452957335552>'
        elif game['type'] == 'HRTL':
            text += ' <:hellfire:766901810580815932>'
        elif game['type'] == 'MEMD':
            text += ' <:one_ring:1061898681504251954>'
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
        if game['theo_quest'] and game['type'] != 'DRTL':
            attributes.append('Theo Quest')
        if game['cow_quest'] and game['type'] != 'DRTL':
            attributes.append('Cow Quest')
        if game['friendly_fire']:
            attributes.append('Friendly Fire')

        if len(attributes) != 0:
            text += ' ('
            text += ", ".join(attributes)
            text += ')'

        text += '\nPlayers: **' + "**, **".join(game['players']) + '**\n\n'
    return text

async def listMessages():
	try:
		global globalOnlineListMessage
		async for m in client.get_channel(1061483226767556719).history(limit=5):
			globalOnlineListMessage = m
	except Exception as err:
		print("Got some exception in listMessages()")
		print(str(err))
	pass

gameList = {}
backgroundTaskRunning = 0
async def backgroundTask():
    await listMessages()
    lastRefresh = 0
    refreshSeconds = 60 #refresh gamelist every x seconds
    aliveTime = 120 #games are marked as active for x seconds every time they show up
    while True:
        await asyncio.sleep(1)
        if time.time() - lastRefresh >= refreshSeconds:
            lastRefresh = time.time()
            # Call the external program and get the output
            output = subprocess.run(["./devilutionx-gamelist"], capture_output=True).stdout
            # Load the output as a JSON list
            games = json.loads(output)
            tmpGameList = {}
            for game in games:
                key = game['id'].upper()
                gameList[key] = game
                gameList[key]["lastOnline"] = time.time()

            for key in gameList:
                game = gameList[key]
                if time.time() - game["lastOnline"] <= aliveTime:
                    tmpGameList[key] = game

            await globalOnlineListMessage.edit(content=generateGameList(tmpGameList))
            activity = discord.Activity(name='Games online: '+str(len(tmpGameList)), type=discord.ActivityType.watching)
            await client.change_presence(activity=activity)
            ct = datetime.datetime.now()
            print("[" + str(ct) + "] Refreshing game list - " + str(len(tmpGameList)) + " games")


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    global backgroundTaskRunning
    if backgroundTaskRunning == 0:
        backgroundTaskRunning = 1
        await backgroundTask()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    #if message.content.startswith('!games'):

token = ""
with open("./discord_bot_token", 'r') as file:
    token = file.readline()

client.run(token)
