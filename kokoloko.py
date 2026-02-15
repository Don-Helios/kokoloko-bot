import discord
import asyncio
import time
from discord.ext import commands

import config
import logic
import views


# --- TESTING / DUMMY USERS ---
class DummyPlayer:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name
        self.mention = f"@{name}"
        self.name = name


# 🛠️ CONFIGURATION AREA 🛠️
# Option A: Create 16 Bots (Uncomment to enable)
TEST_DUMMIES = [DummyPlayer(id=9000 + i, name=f"Bot_{i}") for i in range(1, 17)]

# Option B: No Bots (Uncomment to disable)
# TEST_DUMMIES = []

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logic.load_data()
    print(f'🤖 KOKOLOKO: {bot.user} is ready!')


@bot.command()
async def toggle_auto(ctx):
    is_staff = discord.utils.get(ctx.author.roles, name=config.STAFF_ROLE_NAME) is not None
    if not is_staff:
        await ctx.send("🚫 Staff only.")
        return

    current = logic.draft_state.get("auto_mode", 0)
    new_mode = (current + 1) % 3
    logic.draft_state["auto_mode"] = new_mode

    modes = [
        "🔴 **INTERACTIVE** (Normal Game)",
        "🟢 **AUTO PUBLIC** (Spams Discord)",
        "🤫 **AUTO SILENT** (Terminal Logs Only)"
    ]
    await ctx.send(f"⚡ **Mode switched to:** {modes[new_mode]}")


@bot.command()
async def summary(ctx):
    embeds_list = views.create_summary_embed(logic.draft_state)
    for embed in embeds_list:
        await ctx.send(embed=embed)


@bot.command()
async def start_draft(ctx, *members: discord.Member):
    real_players = list(members)
    final_players = []

    # --- STEP 1: ASK ABOUT DUMMIES ---
    if TEST_DUMMIES:
        embed_dummy = discord.Embed(
            title="🤖 Test Configuration",
            description=f"I found {len(TEST_DUMMIES)} dummy bots defined.\nDo you want to include them in this draft?",
            color=0x34495e
        )
        dummy_view = views.DummyCheckView()
        msg_dummy = await ctx.send(embed=embed_dummy, view=dummy_view)

        await dummy_view.wait()

        if dummy_view.value is None:
            await msg_dummy.edit(content="❌ Timed out.", embed=None, view=None)
            return

        if dummy_view.value is True:
            final_players = real_players + TEST_DUMMIES
        else:
            final_players = real_players
    else:
        final_players = real_players

    if not final_players:
        await ctx.send("❌ No players! Mention someone or enable Dummies in the code.")
        return

    # --- STEP 2: ASK FOR MODE ---
    embed = discord.Embed(
        title="🔧 Draft Configuration",
        description="Please select the execution mode for this draft:",
        color=0x9b59b6
    )
    embed.add_field(name="🔴 Interactive", value="Standard game. Players click buttons.", inline=False)
    embed.add_field(name="🟢 Auto Public", value="Bot picks everything. Good for visual testing.", inline=False)
    embed.add_field(name="🤫 Auto Silent", value="No spam. Results in terminal only.", inline=False)

    view = views.ModeSelectionView()
    msg = await ctx.send(embed=embed, view=view)

    await view.wait()

    if view.value is None:
        await msg.edit(content="❌ Timed out. Draft cancelled.", embed=None, view=None)
        return

    selected_mode = view.value

    # --- STEP 3: INITIALIZE ---
    logic.initialize_draft(final_players)
    logic.draft_state["auto_mode"] = selected_mode

    names = ", ".join([p.display_name for p in final_players])

    if selected_mode != 2:
        await ctx.send(f"🏆 **Draft Started!** (Cap: {config.MAX_POINTS} pts)\n**Round 1**\nOrder: {names}")
    else:
        print("🏆 [SILENT] Draft Started!")

    await next_turn(ctx.channel)


async def next_turn(channel):
    state = logic.draft_state

    # 1. Round Logic
    if state["current_index"] >= len(state["order"]):
        if state["round"] >= config.TOTAL_POKEMON:
            if state["active"]:
                await channel.send("🏁 **Draft Complete!**")
                embeds_list = views.create_summary_embed(state)
                for embed in embeds_list:
                    await channel.send(embed=embed)
                state["active"] = False
                print("🏁 [SILENT] Draft Complete - Summary sent to Discord.")
            return

        state["round"] += 1
        state["order"].reverse()
        state["current_index"] = 0

        mode = state.get("auto_mode", 0)
        if mode != 2:
            await channel.send(f"🔁 **End of Round!** Snake order for Round {state['round']}...")
            await asyncio.sleep(1)
        else:
            print(f"--- STARTING ROUND {state['round']} ---")

    player = state["order"][state["current_index"]]
    pick_num = len(state["rosters"][player.id]) + 1

    if pick_num > config.TOTAL_POKEMON:
        state["current_index"] += 1
        await next_turn(channel)
        return

    state["burned"] = []

    rerolls_used = state["rerolls"].get(player.id, 0)
    can_reroll = (config.MAX_REROLLS - rerolls_used) > 0

    mode = state.get("auto_mode", 0)

    # --- PATH A: AUTO SILENT (Mode 2) ---
    if mode == 2:
        valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=False)
        name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=False)

        if name:
            state["rosters"][player.id].append({'name': name, 'tier': tier})
            state["points"][player.id] += tier
            pts_left = config.MAX_POINTS - state["points"][player.id]
            print(f"[R{state['round']}] Pick #{pick_num} {player.display_name}: {name} (T{tier}) - Left: {pts_left}")
        else:
            print(f"⚠️ [SILENT ERROR] No valid pokemon for {player.display_name}")

        state["current_index"] += 1
        await asyncio.sleep(0.01)
        await next_turn(channel)
        return

        # --- PATH B: AUTO PUBLIC (Mode 1) ---
    if mode == 1 or not can_reroll:
        valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=False)
        name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=False)

        if not name:
            await channel.send(f"⚠️ **CRITICAL:** No valid pokemon (Auto-Mode).")
        else:
            state["rosters"][player.id].append({'name': name, 'tier': tier})
            state["points"][player.id] += tier

            footer_txt = "⚡ Auto-Mode" if mode == 1 else "🔒 0 Rerolls left"

            embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
            embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
            embed.set_footer(text=f"{footer_txt} | Budget: {config.MAX_POINTS - state['points'][player.id]}")
            await channel.send(f"{player.mention}", embed=embed)

            if mode == 1:
                await asyncio.sleep(0.5)

                # --- PATH C: INTERACTIVE (Mode 0) ---
    else:
        expiry_roll = int(time.time()) + config.ROLL_TIMEOUT
        odds_data = logic.calculate_tier_percentages(player.id, pick_num, is_reroll=False)
        odds_grid_str = views.format_odds_grid(odds_data)

        embed_start = views.create_roll_embed(player, pick_num, expiry_roll, odds_grid_str)
        roll_view = views.RollView(player)
        start_msg = await channel.send(f"{player.mention}", embed=embed_start, view=roll_view)

        await roll_view.wait()

        if not roll_view.clicked:
            embed_start.description = "⏰ **Time Expired** - Auto rolling..."
            embed_start.color = 0xe74c3c
            await start_msg.edit(embed=embed_start, view=None)
            await asyncio.sleep(1)
        else:
            embed_start.description = f"**Rolling...** 🎰\n\n**Odds:**\n{odds_grid_str}"
            embed_start.color = 0xf1c40f
            await start_msg.edit(embed=embed_start, view=None)

        current_is_reroll = False

        while True:
            current_rerolls = state["rerolls"].get(player.id, 0)
            current_left = config.MAX_REROLLS - current_rerolls
            pts_left = config.MAX_POINTS - state["points"].get(player.id, 0)

            valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=current_is_reroll)
            name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=current_is_reroll)

            if not name:
                await channel.send(f"⚠️ **CRITICAL:** No valid pokemon.")
                break

            if current_left <= 0 and current_is_reroll:
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier

                embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
                embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
                embed.set_footer(text="0 Re-rolls left.")
                await channel.send(f"{player.mention}", embed=embed)
                break

            expiry_decision = int(time.time()) + config.DECISION_TIMEOUT

            embed = discord.Embed(
                title=f"Pick #{pick_num} • {player.display_name}",
                description=f"⏳ **Decide in** <t:{expiry_decision}:R>\n(Round {state['round']})",
                color=0xF1C40F
            )
            embed.add_field(name="Rolled", value=f"**{name}**", inline=True)
            embed.add_field(name="Tier", value=f"{tier}", inline=True)
            embed.add_field(name="Budget", value=f"{pts_left} pts left", inline=False)
            embed.set_footer(text=f"Re-rolls left: {current_left}/{config.MAX_REROLLS}")

            view = views.DraftView(player)
            await channel.send(f"{player.mention}", embed=embed, view=view)

            await view.wait()

            if view.value == "REROLL":
                state["rerolls"][player.id] += 1
                new_left = config.MAX_REROLLS - state["rerolls"][player.id]
                clicker = view.clicked_by.display_name if view.clicked_by else "Staff"

                await channel.send(f"🔄 **{clicker}** re-rolled! ({new_left} left). Rolling again...")
                state["burned"].append(name)
                current_is_reroll = True
                await asyncio.sleep(1)
                continue

            else:
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier

                msg_txt = f"✅ **{view.clicked_by.display_name}**" if view.value == "KEEP" else "⏰ Timeout:"
                await channel.send(f"{msg_txt} accepted **{name}**.")
                break

    state["current_index"] += 1
    await asyncio.sleep(1)
    await next_turn(channel)


if __name__ == "__main__":
    if config.TOKEN:
        bot.run(config.TOKEN)
    else:
        print("❌ Error: TOKEN missing")