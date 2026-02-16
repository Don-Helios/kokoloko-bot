import discord
import asyncio
import time
import random
import config
import logic
import views


async def next_turn(channel, bot_instance):
    """
    The Main Game Loop.
    Handles Round progression, Player Turns, and Mode Switching.
    """
    state = logic.draft_state

    # =========================================
    # 1. ROUND MANAGEMENT
    # =========================================
    # If index exceeds the number of players, the round is over.
    if state["current_index"] >= len(state["order"]):
        if state["round"] >= config.TOTAL_POKEMON:
            # GAME OVER: Send Summary and Stop.
            if state["active"]:
                await channel.send("🏁 **Draft Complete!**")
                for embed in views.create_summary_embed(state):
                    await channel.send(embed=embed)
                state["active"] = False
                print("🏁 [ENGINE] Draft Complete.")
            return

        # Prepare Next Round (Snake Draft Reversal)
        state["round"] += 1
        state["order"].reverse()
        state["current_index"] = 0

        mode = state.get("auto_mode", 0)
        if mode != 2:
            await channel.send(f"🔁 **End of Round!** Snake order for Round {state['round']}...")
            await asyncio.sleep(1)
        else:
            print(f"--- ROUND {state['round']} START ---")

    player = state["order"][state["current_index"]]
    pick_num = len(state["rosters"][player.id]) + 1

    # Skip players who are somehow already full
    if pick_num > config.TOTAL_POKEMON:
        state["current_index"] += 1
        await next_turn(channel, bot_instance)
        return

    # Reset Burned list (Pokemon skipped this turn)
    state["burned"] = []

    rerolls_used = state["rerolls"].get(player.id, 0)
    can_reroll = (config.MAX_REROLLS - rerolls_used) > 0
    mode = state.get("auto_mode", 0)

    # =========================================
    # PATH A: SILENT AUTO (Mode 2)
    # =========================================
    if mode == 2:
        valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=False)
        name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=False)
        if name:
            state["rosters"][player.id].append({'name': name, 'tier': tier})
            state["points"][player.id] += tier
            print(f"[R{state['round']}] P#{pick_num} {player.display_name}: {name}")
        else:
            print(f"⚠️ [SILENT] Error: No candidates for {player.display_name}")
        state["current_index"] += 1
        await asyncio.sleep(0.01)
        await next_turn(channel, bot_instance)
        return

        # =========================================
    # PATH B: PUBLIC AUTO (Mode 1)
    # =========================================
    if mode == 1 or not can_reroll:
        valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=False)
        name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=False)

        if not name:
            await channel.send("⚠️ **CRITICAL:** No valid pokemon.")
        else:
            state["rosters"][player.id].append({'name': name, 'tier': tier})
            state["points"][player.id] += tier
            ft = "⚡ Auto-Mode" if mode == 1 else "🔒 0 Rerolls left"
            embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
            embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
            embed.set_footer(text=f"{ft} | Budget: {config.MAX_POINTS - state['points'][player.id]}")
            await channel.send(f"{player.mention}", embed=embed)
            if mode == 1: await asyncio.sleep(0.5)

    # =========================================
    # PATH C: INTERACTIVE (Mode 0)
    # =========================================
    else:
        # 1. SHOW ROLL BUTTON
        expiry_roll = int(time.time()) + config.ROLL_TIMEOUT
        odds = logic.calculate_tier_percentages(player.id, pick_num, is_reroll=False)
        embed_start = views.create_roll_embed(player, pick_num, expiry_roll, views.format_odds_grid(odds))
        roll_view = views.RollView(player)
        start_msg = await channel.send(f"{player.mention}", embed=embed_start, view=roll_view)

        await roll_view.wait()

        if not roll_view.clicked:
            embed_start.description = "⏰ **Time Expired** - Auto rolling..."
            embed_start.color = 0xe74c3c
            await start_msg.edit(embed=embed_start, view=None)
            await asyncio.sleep(1)
        else:
            embed_start.description = f"**Rolling...** 🎰\n\n**Odds:**\n{views.format_odds_grid(odds)}"
            embed_start.color = 0xf1c40f
            await start_msg.edit(embed=embed_start, view=None)

        # 2. DECISION LOOP (Keep/Reroll)
        current_is_reroll = False
        while True:
            curr_rr = state["rerolls"].get(player.id, 0)
            curr_left = config.MAX_REROLLS - curr_rr
            pts_left = config.MAX_POINTS - state["points"].get(player.id, 0)

            # ROLL THE DICE
            v_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=current_is_reroll)
            name, tier = logic.roll_pokemon(v_tiers, player.id, pick_num, is_reroll=current_is_reroll)

            if not name:
                await channel.send("⚠️ **CRITICAL:** No valid pokemon.")
                break

            # Forced accept if out of rerolls mid-loop
            if curr_left <= 0 and current_is_reroll:
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier
                embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
                embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
                embed.set_footer(text="0 Re-rolls left.")
                await channel.send(f"{player.mention}", embed=embed)
                break

            # Show Result
            expiry_dec = int(time.time()) + config.DECISION_TIMEOUT
            embed = discord.Embed(
                title=f"Pick #{pick_num} • {player.display_name}",
                description=f"⏳ **Decide in** <t:{expiry_dec}:R>\n(Round {state['round']})",
                color=0xF1C40F
            )
            embed.add_field(name="Rolled", value=f"**{name}**", inline=True)
            embed.add_field(name="Tier", value=f"{tier}", inline=True)
            embed.add_field(name="Budget", value=f"{pts_left} pts left", inline=False)
            embed.set_footer(text=f"Re-rolls left: {curr_left}/{config.MAX_REROLLS}")

            view = views.DraftView(player)
            await channel.send(f"{player.mention}", embed=embed, view=view)
            await view.wait()

            if view.value == "REROLL":
                # Register Reroll
                state["rerolls"][player.id] += 1
                new_left = config.MAX_REROLLS - state["rerolls"][player.id]
                clicker = view.clicked_by.display_name if view.clicked_by else "Staff"

                await channel.send(f"🔄 **{clicker}** re-rolled! ({new_left} left).")
                state["burned"].append(name)
                current_is_reroll = True

                # --- FAKE OUT EASTER EGG ---
                # Trigger: "2 picks left" -> Penultimate Pick (9 of 10)
                is_penultimate = (pick_num == config.TOTAL_POKEMON - 1)

                if is_penultimate and random.random() < config.FAKE_OUT_CHANCE:
                    fake_name, fake_tier = logic.get_fake_candidate(player.id)
                    if fake_name:
                        # 1. Reveal Fake
                        fake_msg = await channel.send(embed=views.create_fake_embed(player, fake_name, fake_tier))
                        await asyncio.sleep(5)

                        # 2. Hariyama Message
                        await fake_msg.edit(
                            content="✋ **Hariyama used Fake Out!** You don't have enough points for that!", embed=None)
                        await asyncio.sleep(2)
                        await channel.send(f"😅 Just kidding {player.mention}, your **actual** pull always was...")
                        await asyncio.sleep(1)

                continue  # Loop back to roll again

            else:  # KEEP
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier
                txt = f"✅ **{view.clicked_by.display_name}**" if view.value == "KEEP" else "⏰ Timeout:"
                await channel.send(f"{txt} accepted **{name}**.")
                break

                # Next Player
    state["current_index"] += 1
    await asyncio.sleep(1)
    await next_turn(channel, bot_instance)