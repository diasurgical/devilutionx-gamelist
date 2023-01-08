import discord
import subprocess
import json

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!games'):
        # Call the external program and get the output
        output = subprocess.run(["./devilutionx-gamelist"], capture_output=True).stdout
        # Load the output as a JSON list
        games = json.loads(output)

        await message.channel.send('There are currently **' + str(len(games)) + '** public games.')

        # Print each name in the list
        for game in games:
            text = '**' + game['id'].upper() + '**';
            if game['type'] == 'DRTL':
                text += ' <:diabloico:760201452957335552>'
            elif game['type'] == 'HRTL':
                text += ' <:hellfire:766901810580815932>'
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

            text += '\nPlayers: **' + "**, **".join(game['players']) + '**'

            await message.channel.send(text)

token = ""
with open("./discord_bot_token", 'r') as file:
    token = file.readline()
file.close()

client.run(token)
