import os
import discord
from dotenv import load_dotenv

# Load the secrets
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Setup Permissions (Intents)
intents = discord.Intents.default()
intents.message_content = True # <--Lets the bot read the chat

# Create the Client
client = discord.Client(intents=intents)

# Event: Startup
@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

# Event: Message Received
@client.event
async def on_message(message):
    # Avoid auto-reply itself
    if message.author == client.user:
        return

    # Check for command
    if message.content.startswith('hola'):
        await message.channel.send("Soy... KOKOLOKOOOO ¡Estoy vivooo!✋🤪🤚")

#Run it
if TOKEN:
    client.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in .env")
