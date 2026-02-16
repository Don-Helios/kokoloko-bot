import discord
from discord.ext import commands
import config
import logic
import views
import engine


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
    print(f'🤖 KOKOLOKO: {bot.user} is ready!')
    print(f'   - Fake Out Chance: {config.FAKE_OUT_CHANCE * 100}%')


@bot.command()
async def toggle_auto(ctx):
    """Command to cycle draft modes."""
    if not discord.utils.get(ctx.author.roles, name=config.STAFF_ROLE_NAME):
        return await ctx.send("🚫 Staff only.")

    current = logic.draft_state.get("auto_mode", 0)
    new_mode = (current + 1) % 3
    logic.draft_state["auto_mode"] = new_mode

    modes = ["🔴 **INTERACTIVE**", "🟢 **AUTO PUBLIC**", "🤫 **AUTO SILENT**"]
    await ctx.send(f"⚡ **Mode switched to:** {modes[new_mode]}")


@bot.command()
async def summary(ctx):
    """Command to show current draft state."""
    for embed in views.create_summary_embed(logic.draft_state):
        await ctx.send(embed=embed)


@bot.command()
async def start_draft(ctx, *members: discord.Member):
    """Main startup command."""
    real = list(members)
    final = []

    # 1. Check for Dummies
    if TEST_DUMMIES:
        e = discord.Embed(title="🤖 Setup", description=f"Include {len(TEST_DUMMIES)} dummies?", color=0x34495e)
        v = views.DummyCheckView()
        m = await ctx.send(embed=e, view=v)
        await v.wait()
        if v.value is None: return await m.edit(content="❌ Timeout", embed=None, view=None)
        final = real + TEST_DUMMIES if v.value else real
    else:
        final = real

    if not final: return await ctx.send("❌ No players!")

    # 2. Select Mode
    e = discord.Embed(title="🔧 Setup", description="Select Mode:", color=0x9b59b6)
    v = views.ModeSelectionView()
    m = await ctx.send(embed=e, view=v)
    await v.wait()
    if v.value is None: return await m.edit(content="❌ Timeout", embed=None, view=None)

    # 3. Initialize
    logic.initialize_draft(final)
    logic.draft_state["auto_mode"] = v.value

    if v.value != 2:
        names = ", ".join([p.display_name for p in final])
        await ctx.send(f"🏆 **Draft Started!**\nOrder: {names}")
    else:
        print("🏆 [SILENT] Started")

    await engine.next_turn(ctx.channel, bot)


if __name__ == "__main__":
    if config.TOKEN:
        bot.run(config.TOKEN)
    else:
        print("❌ Error: TOKEN missing in config.py")