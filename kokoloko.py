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
# Create a standard format for the logs
formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)-8s | %(message)s')

# 1. File Handler: Captures EVERYTHING (DEBUG and above) for deep tracing
file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# 2. Console Handler: Captures ONLY INFO and above to keep terminal clean
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Attach both handlers to the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # Root must be DEBUG to allow the file handler to catch it
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Specific logger for this file
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
    # Enforce Thread Usage
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        return await ctx.send(f"🚫 Please use this command inside the `{config.THREAD_NAME}` thread.", delete_after=10)

    if not discord.utils.get(ctx.author.roles, name=config.STAFF_ROLE_NAME):
        logger.warning(f"Unauthorized toggle_auto attempt by {ctx.author}")
        return await ctx.send("🚫 Staff only.")

    current = logic.draft_state.get("auto_mode", 0)
    new_mode = (current + 1) % 3
    logic.draft_state["auto_mode"] = new_mode

    modes = ["🔴 **INTERACTIVE**", "🟢 **AUTO PUBLIC**", "🤫 **AUTO SILENT**"]
    logger.info(f"Mode switched by {ctx.author} to {modes[new_mode]}")
    await ctx.send(f"⚡ **Mode switched to:** {modes[new_mode]}")


@bot.command()
async def summary(ctx):
    """Command to show current draft state."""
    # Enforce Thread Usage
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        return await ctx.send(f"🚫 Please use this command inside the `{config.THREAD_NAME}` thread.", delete_after=10)

    logger.info(f"Summary requested by {ctx.author}")
    for embed in views.create_summary_embed(logic.draft_state):
        await ctx.send(embed=embed)


@bot.command()
async def start_draft(ctx, *members: discord.Member):
    """Main startup command."""
    # =========================================
    # 0. THREAD ENFORCEMENT
    # =========================================
    if not isinstance(ctx.channel, discord.Thread) or ctx.channel.name != config.THREAD_NAME:
        logger.warning(f"Start attempt outside thread. Channel: {ctx.channel.name}")
        return await ctx.send(f"🚫 Please start the draft from inside the `{config.THREAD_NAME}` thread.",
                              delete_after=10)

    logger.info(f"Draft initiation started by {ctx.author}")
    real = list(members)
    final = []

    # =========================================
    # 1. Check for Dummies
    # =========================================
    if TEST_DUMMIES:
        e = discord.Embed(title="🤖 Configuración", description=f"Incluir los {len(TEST_DUMMIES)} dummies?", color=0x34495e)
        v = views.DummyCheckView()
        m = await ctx.send(embed=e, view=v)
        await v.wait()
        if v.value is None:
            logger.info("Draft setup cancelled (Timeout on Dummies check).")
            return await m.edit(content="❌ Timeout", embed=None, view=None)
        final = real + TEST_DUMMIES if v.value else real
    else:
        final = real

    if not final:
        logger.warning("Draft failed to start: No players provided.")
        return await ctx.send("❌ No players!")

    # =========================================
    # 2. Select Mode
    # =========================================
    e = discord.Embed(title="🔧 Setup", description="Select Mode:", color=0x9b59b6)
    v = views.ModeSelectionView()
    m = await ctx.send(embed=e, view=v)
    await v.wait()
    if v.value is None:
        logger.info("Draft setup cancelled (Timeout on Mode select).")
        return await m.edit(content="❌ Timeout", embed=None, view=None)

    # =========================================
    # 3. Initialize
    # =========================================
    logic.initialize_draft(final)
    logic.draft_state["auto_mode"] = v.value
    logger.info(f"Draft initialized successfully. Mode: {v.value}, Players: {len(final)}")

    # =========================================
    # 4. Parent Channel Announcement
    # =========================================
    if v.value != 2:
        # Find the Draft role to ping
        role_to_ping = discord.utils.get(ctx.guild.roles, name=config.PING_ROLE_NAME)
        ping_text = role_to_ping.mention if role_to_ping else f"@{config.PING_ROLE_NAME}"

        announcement_msg = f"📢 A Kokoloko Draft is starting! Come over to the {ctx.channel.mention} thread to check it out {ping_text}"

        try:
            # Send the message to the parent channel (e.g. #drafts)
            await ctx.channel.parent.send(announcement_msg)
            logger.info(f"Announcement sent to parent channel: {ctx.channel.parent.name}")
        except discord.Forbidden:
            logger.error("Failed to announce: Bot lacks 'Send Messages' permission in the parent channel.")
        except Exception as e:
            logger.error(f"Failed to send announcement: {e}")

        # Send regular startup message in the thread
        names = ", ".join([p.display_name for p in final])
        await ctx.send(f"🏆 **Draft Started!**\nOrder: {names}")
    else:
        logger.info("🏆 [SILENT] Started")

    # Hand off to engine. (ctx.channel is the thread, so engine stays in the thread)
    await engine.next_turn(ctx.channel, bot)


if __name__ == "__main__":
    if config.TOKEN:
        logger.info("Starting bot...")
        bot.run(config.TOKEN)
    else:
        logger.critical("TOKEN missing in config.py")