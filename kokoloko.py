import discord
from discord.ext import commands
import config
import logic
import views
import engine
import logging
import sys

# ==========================================
# 📝 MASTER LOGGING SETUP
# ==========================================
formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)-8s | %(message)s')

file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger("kokoloko")


# ==========================================
# TEST DUMMIES
# ==========================================
class DummyPlayer:
    def __init__(self, id, name):
        self.id, self.display_name, self.mention, self.name = id, name, f"@{name}", name


TEST_DUMMIES = [DummyPlayer(9000 + i, f"Bot_{i}") for i in range(1, 17)]
# TEST_DUMMIES = [] # Uncomment to disable

# ==========================================
# STARTUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logic.load_data()
    logger.info(f'🤖 KOKOLOKO: {bot.user} is ready and connected to Discord!')
    logger.info(f'   - Fake Out Chance: {config.FAKE_OUT_CHANCE * 100}%')


@bot.command()
async def toggle_auto(ctx):
    """Command to cycle draft modes."""
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        return await ctx.send(views.MSG["err_thread"].format(thread=config.THREAD_NAME), delete_after=10)

    if not discord.utils.get(ctx.author.roles, name=config.STAFF_ROLE_NAME):
        logger.warning(f"Unauthorized toggle_auto attempt by {ctx.author}")
        return await ctx.send(views.MSG["err_staff"])

    current = logic.draft_state.get("auto_mode", 0)
    new_mode = (current + 1) % 3
    logic.draft_state["auto_mode"] = new_mode

    logger.info(f"Mode switched by {ctx.author} to {views.MSG['mode_names'][new_mode]}")
    await ctx.send(views.MSG["mode_switch"].format(mode=views.MSG['mode_names'][new_mode]))


@bot.command()
async def summary(ctx):
    """Command to show current draft state."""
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        return await ctx.send(views.MSG["err_thread"].format(thread=config.THREAD_NAME), delete_after=10)

    logger.info(f"Summary requested by {ctx.author}")
    for embed in views.create_summary_embed(logic.draft_state):
        await ctx.send(embed=embed)


@bot.command()
async def start_draft(ctx, *members: discord.Member):
    """Main startup command."""
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        logger.warning(f"Start attempt outside thread. Channel: {ctx.channel.name}")
        return await ctx.send(views.MSG["err_thread"].format(thread=config.THREAD_NAME), delete_after=10)

    logger.info(f"Draft initiation started by {ctx.author}")
    real = list(members)
    final = []

    if TEST_DUMMIES:
        e = discord.Embed(title=views.MSG["setup_dummies_title"],
                          description=views.MSG["setup_dummies_desc"].format(count=len(TEST_DUMMIES)), color=0x34495e)
        v = views.DummyCheckView()
        m = await ctx.send(embed=e, view=v)
        await v.wait()
        if v.value is None:
            logger.info("Draft setup cancelled (Timeout on Dummies check).")
            return await m.edit(content=views.MSG["timeout"], embed=None, view=None)
        final = real + TEST_DUMMIES if v.value else real
    else:
        final = real

    if not final:
        logger.warning("Draft failed to start: No players provided.")
        return await ctx.send(views.MSG["err_no_players"])

    e = discord.Embed(title=views.MSG["setup_mode_title"], description=views.MSG["setup_mode_desc"], color=0x9b59b6)
    v = views.ModeSelectionView()
    m = await ctx.send(embed=e, view=v)
    await v.wait()
    if v.value is None:
        logger.info("Draft setup cancelled (Timeout on Mode select).")
        return await m.edit(content=views.MSG["timeout"], embed=None, view=None)

    logic.initialize_draft(final)
    logic.draft_state["auto_mode"] = v.value
    logger.info(f"Draft initialized successfully. Mode: {v.value}, Players: {len(final)}")

    if v.value != 2:
        role_to_ping = discord.utils.get(ctx.guild.roles, name=config.PING_ROLE_NAME)
        ping_text = role_to_ping.mention if role_to_ping else f"@{config.PING_ROLE_NAME}"

        announcement_msg = views.MSG["announce_parent"].format(thread_mention=ctx.channel.mention, ping_text=ping_text)

        try:
            await ctx.channel.parent.send(announcement_msg)
            logger.info(f"Announcement sent to parent channel: {ctx.channel.parent.name}")
        except discord.Forbidden:
            logger.error("Failed to announce: Bot lacks 'Send Messages' permission in the parent channel.")
        except Exception as e:
            logger.error(f"Failed to send announcement: {e}")

        names = ", ".join([p.display_name for p in final])
        await ctx.send(views.MSG["draft_started"].format(names=names))
    else:
        logger.info("🏆 [SILENT] Started")

    await engine.next_turn(ctx.channel, bot)


if __name__ == "__main__":
    if config.TOKEN:
        logger.info("Starting bot...")
        bot.run(config.TOKEN)
    else:
        logger.critical("TOKEN missing in config.py")