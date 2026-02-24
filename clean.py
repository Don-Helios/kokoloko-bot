import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# Make sure 'DISCORD_TOKEN' matches the exact variable name in your .env file
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up intents (message_content is mandatory to read the "si/no" reply)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')


@bot.command(name='limpiar_usuario')
@commands.has_permissions(manage_messages=True)
async def limpiar_usuario(ctx, usuario: discord.Member):
    """
    Deletes ALL messages sent by a specific user/bot in the current channel.
    Usage: !limpiar_usuario @BotName
    """
    await ctx.send(
        f"Estas seguro de que quieres borrar TODOS los mensajes de {usuario.mention} en este canal? Responde 'si' para confirmar o 'no' para cancelar. Tienes 30 segundos.")

    def check_response(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['si', 'no']

    try:
        msg = await bot.wait_for('message', check=check_response, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Tiempo agotado. Operacion cancelada.")
        return

    if msg.content.lower() == 'no':
        await ctx.send("Operacion cancelada.")
        return

    # Reminder regarding API limits
    aviso = await ctx.send(
        "Iniciando el borrado. Esto tomara tiempo si hay mensajes con mas de 14 dias de antiguedad debido a los limites de la API de Discord.")

    def is_target(message):
        return message.author == usuario

    # limit=None scans the entire channel history
    deleted = await ctx.channel.purge(limit=None, check=is_target)

    await aviso.delete()
    confirmacion = await ctx.send(f"Operacion terminada. Se borraron {len(deleted)} mensajes de {usuario.mention}.")
    await confirmacion.delete(delay=5)


@limpiar_usuario.error
async def limpiar_usuario_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Error: Te falto mencionar al usuario o bot. Uso correcto: !limpiar_usuario @nombre")
    elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MemberNotFound):
        await ctx.send("Error: No pude encontrar a ese usuario. Asegurate de mencionarlo correctamente usando el @.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("Error: No tienes permiso de Administrar Mensajes para usar este comando.")
    else:
        print(f"Unexpected error in limpiar_usuario: {error}")


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: Could not find DISCORD_TOKEN in .env file.")