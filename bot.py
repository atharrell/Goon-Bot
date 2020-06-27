# bot.py
import os
import random
import json
import csv

from riotwatcher import LolWatcher, ApiError

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Server list, used to make queues and settings independent between servers.
servers = {}

# Loads in environment variables for the whole bot, mostly just used to obscure the bot token
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
RIOT_TOKEN = os.getenv('RIOT_TOKEN')

lol_api = LolWatcher(RIOT_TOKEN)
region = 'na1'

# Generates a new bot/client for the bot, setting the command prefix
client = commands.Bot(command_prefix='!')

# Server object used to store per server queue and settings
class Server:
    def __init__(self, players={}, champions=[]):
        self.players = players
        self.queue = []
        self.champions = champions

# Dumps the json (data) into the file
def write_json(data, filename):
    with open(filename,'w') as f:
        json.dump(data, f, indent=4)

# Splits the input into champs.
def split_champs(champs):
    champs[len(champs)-1] = champs[len(champs)-1] + ","
    prev = ""
    new = []
    for champ in champs:
        if not champ.endswith(','):
            if prev != "":
                prev = prev + ' ' + champ.capitalize()
            else:
                prev = champ.capitalize()
        else:
            if prev != "":
                temp = champ.replace(",","")
                temp = temp.capitalize()
                current = prev + ' ' + temp
                prev = ""
            else:
                current = champ.replace(",","")
                current = current.capitalize()
            current = current.replace("'","")
            new.append(current)
    return new

# Gets the full list of champions
def get_champions():
    full_list = []
    with open('champion_list.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            full_list.append(row[0])
    return full_list

# Whenever the bot is started, set up the required roles and load/generate default settings for each server
@client.event
async def on_ready():
    # Checks the available roles for each guild and then adds any roles that are missing
    for guild in client.guilds:
        # Loads the settings from the json file of persisted settings if available, otherwise uses the default settings and writes a new
        # entry into the persisted settings file for that server.
        if guild.id not in servers:
            loaded = False
            with open('persistent_settings.json') as json_file:
                settings = json.load(json_file)['servers']
                for server in settings:
                    if server['guild_id'] == guild.id:
                        servers[guild.id] = Server(server['players'], server['champions'])
                        loaded = True
            # If there aren't settings to load generate a new settings entry in the json for this server
            if not loaded:
                with open('persistent_settings.json') as json_file:
                    settings = json.load(json_file)
                    temp = settings['servers']
                    server = {"guild_id": guild.id}
                    server['players'] = {}
                    server['champions'] = []
                    with open('champion_list.csv', newline='') as csvfile:
                        reader = csv.reader(csvfile)
                        for row in reader:
                            server['champions'].append(row[0])
                    servers[guild.id] = Server({},server['champions'])
                    temp.append(server)
                write_json(settings, 'persistent_settings.json')
        print(f'{client.user.name} has connected to {guild.name}!')

# Adds the player's summoner name to the list of players on this server and updates their name if they already had a name.
@client.command(name='summoner', help="!summoner {name} (Associates your discord id and league name so that your games can be searched.")
async def summoner(ctx, name=None):
    if name is None:
         await ctx.send(f'No name provided, please use the command in format ( !add name ) where name is your summoner name.')
    else:
        user = ctx.message.author
        server = servers[ctx.guild.id]
        server.players[user.id] = name
        with open('persistent_settings.json') as json_file:
            settings_file = json.load(json_file)
            settings = settings_file['servers']
            for server in settings:
                if server['guild_id'] == ctx.guild.id:
                    if str(user.id) not in server['players']:
                        server['players'][str(user.id)] = name
                        await ctx.send(f'Summoner name successfully added.')
                    else:
                        old = server['players'][str(user.id)]
                        server['players'][str(user.id)] = name
                        await ctx.send(f'Summoner name successfully updated from {old} to {name}.')
        write_json(settings_file, 'persistent_settings.json')

# Adds the player to the queue of players to play next.
@client.command(name='queue', help="!queue (Adds you to the queue of players to play next.)")
async def queue(ctx):
    server = servers[ctx.guild.id]
    if ctx.message.author.name not in server.queue:
        server.queue.append(ctx.message.author.name)
        await ctx.send(f'{ctx.message.author.name} successfully added to the queue.')
    else:
        await ctx.send(f'{ctx.message.author.name} already in queue not added again.')

# Gets the next player in the queue and removes them from the queue.
@client.command(name='next', help="!next (Gets the next player in the queue and removes them from the queue.)")
async def next(ctx):
    server = servers[ctx.guild.id]
    if len(server.queue) > 0:
        player = server.queue[len(server.queue) - 1]
        del server.queue[len(server.queue) - 1]
        await ctx.send(f'{player}')
    else:
        await ctx.send("No players in queue, cannot get next player.")

# Removes a set of champs from gauntlet list
@client.command(name='remove', help="!remove (champion, champion, ...) (Removes any number of champions from the gauntlet list.)")
async def remove(ctx, *champs):
    server = servers[ctx.guild.id]
    champs = split_champs(list(champs))
    removed = []

    # Decide which champs should be removed
    for champ in champs:
        if champ in server.champions:
            server.champions.remove(champ)
            removed.append(champ)
        else:
            full_list = get_champions()
            if champ in full_list:
                await ctx.send(f'{champ} has already been used in this gauntlet.')
            else:
                await ctx.send(f'{champ} is incorrectly spelled use !champions command to see full list of champions.')

    # Based on how many champs were removed format and send a message.
    if len(removed) == 1:
        await ctx.send(f'{removed[0]} has been removed from the gauntlet list.')
    elif len(removed) > 1:
        text = ""
        for i in range(0,len(removed)):
            if i < len(removed) - 1:
                text += removed[i] + ", "
            else:
                text += removed[i]
        await ctx.send(f'{text} have been removed from the gauntlet list.')
    else:
        await ctx.send(f'No champions removed.')

    # Refresh the champion list if the remaining number of champions is less than 20 as you need 20 for tournament draft also save
    # the new champion list to the persistent settings file in case the bot server goes down then the list is recoverable.
    if len(server.champions) < 20:
        with open('persistent_settings.json') as json_file:
            settings = json.load(json_file)
            for s in settings['servers']:
                    if s['guild_id'] == ctx.guild.id:
                        s['champions'] = []
                        with open('champion_list.csv', newline='') as csvfile:
                            reader = csv.reader(csvfile)
                            for row in reader:
                                s['champions'].append(row[0])
                        server.champions = s['champions'].copy()
        write_json(settings, 'persistent_settings.json')
    else:
        if len(removed) > 0:
            with open('persistent_settings.json') as json_file:
                settings = json.load(json_file)
                for s in settings['servers']:
                    if s['guild_id'] == ctx.guild.id:
                        champs = s['champions']
                        for champ in removed:
                            champs.remove(champ)
            write_json(settings, 'persistent_settings.json')

# Gets the next player in the queue and removes them from the queue.
@client.command(name='check', help="!check champion (Checks to see if the champion is available)")
async def check(ctx, *champ):
    server = servers[ctx.guild.id]
    full_name = ""
    for i in range(0,len(champ)):
        full_name += champ[i].capitalize()
        if i < len(champ) - 1:
            full_name += " "
    full_name = full_name.replace("'","")
    if full_name in server.champions:
        await ctx.send(f'{full_name} is available to play.')
    else:
        full_list = get_champions()
        if full_name in full_list:
            await ctx.send(f'{full_name} has already been used in this gauntlet.')
        else:
            await ctx.send(f'{full_name} is incorrectly spelled use !champions command to see full list of champions.')

# Returns a list of all champions
@client.command(name='champions', help="!champions (Returns a list of all champions)")
async def champions(ctx):
    full_list = ""
    with open('champion_list.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            full_list += row[0] + ", "
    await ctx.send(f'{full_list}')


# Returns a list of all available champions for this server
@client.command(name='available', help="!available (Returns a list of all available champions for this server)")
async def available(ctx):
    server = servers[ctx.guild.id]
    full_list = ""
    for champ in server.champions:
        full_list += champ + ", "
    await ctx.send(f'{full_list}')

# Returns a list of all available champions for this server
# @client.command(name='teams', help="!teams (Generates somewhat balanced teams if there are 10 or more players in the queue.)")
# async def teams(ctx):
    # server = servers[ctx.guild.id]
    # if len(server.queue) >= 1:
    #     members = server.queue[0:10].copy()
    #     for member in members:
    #         summoner = lol_api.summoner.by_name(region, member)
    #         ranked_stats = lol_api.league.by_summoner(region, summoner['id'])
    #         print(ranked_stats)

    # Something something need permanent Rito api key something something etc blah blah blah
client.run(DISCORD_TOKEN)