import discord
import asyncio
import time
import random
import config
import logic
import views
import logging

logger = logging.getLogger("engine")


async def next_turn(channel, bot_instance, retries=3):
    """
    The Main Game Loop.
    Handles Round progression, Player Turns, and Mode Switching.
    Added a retry parameter to gracefully handle Discord API 503 drops.
    """
    try:
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
                    logger.info("🏁 Draft Complete - Summary sent.")
                return

            # Prepare Next Round (Snake Draft Reversal)
            state["round"] += 1
            state["order"].reverse()
            state["current_index"] = 0

            mode = state.get("auto_mode", 0)
            if mode != 2:
                await channel.send(f"🔁 **End of Round!** Snake order for Round {state['round']}...")

                # ==========================================
                # AUTO-SUMMARY LOGIC
                # ==========================================
                # Displays the summary exactly at the beginning of Round 3 and beyond
                if state["round"] > 2:
                    logger.info(f"Displaying auto-summary for start of Round {state['round']}")
                    for embed in views.create_summary_embed(state):
                        await channel.send(embed=embed)
                # ==========================================

                logger.info(f"--- STARTING ROUND {state['round']} ---")
                await asyncio.sleep(1)
            else:
                print(f"--- ROUND {state['round']} START ---")
                logger.info(f"--- STARTING ROUND {state['round']} (Silent) ---")

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

        logger.info(f"[Turn Start] Round {state['round']}, Pick #{pick_num} for {player.display_name}")

        # =========================================
        # 🔔 UPCOMING TURN NOTIFICATION (DM)
        # =========================================
        # Simulate exactly 3 turns into the future to DM the upcoming player.
        # Only do this in Interactive mode, otherwise it will spam everyone instantly.
        if mode == 0:
            target_round = state["round"]
            temp_idx = state["current_index"]
            is_reversed_sim = False

            upcoming_players = []

            # Walk forward 3 steps to build a list of the next 3 players
            for _ in range(3):
                temp_idx += 1
                if temp_idx >= len(state["order"]):
                    target_round += 1
                    temp_idx = 0
                    is_reversed_sim = not is_reversed_sim  # The order flips every new round!

                if target_round <= config.TOTAL_POKEMON:
                    if is_reversed_sim:
                        # If we spilled into a reversed round, we read the array backwards
                        sim_player = state["order"][::-1][temp_idx]
                    else:
                        sim_player = state["order"][temp_idx]
                    upcoming_players.append(sim_player)

            if len(upcoming_players) == 3:
                target_player = upcoming_players[-1]  # The person exactly 3 turns away

                # OVERLAP CHECK: Snake drafts cause back-to-back turns.
                # If the target is currently picking, or up in 1 or 2 turns, do NOT spam them again.
                if target_player != player and target_player not in upcoming_players[:-1]:
                    # Ensure it's a real user (DummyPlayer has no 'send' method)
                    if hasattr(target_player, "send"):
                        try:
                            dm_embed = discord.Embed(
                                title="🔔 Kokoloko Draft Alert",
                                description=(
                                    f"Get ready, **{target_player.display_name}**! You are up in exactly **3 turns**.\n\n"
                                    f"👉 **[Click here to go to the draft thread]({channel.jump_url})**"
                                ),
                                color=0x3498db
                            )
                            await target_player.send(embed=dm_embed)
                            logger.info(f"Sent 3-turn warning DM to {target_player.display_name}")
                        except discord.Forbidden:
                            logger.warning(f"Could not send DM to {target_player.display_name} (DMs disabled).")
                        except Exception as e:
                            logger.error(f"Failed to send DM to {target_player.display_name}: {e}")

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

                pts_left = config.MAX_POINTS - state["points"][player.id]
                logger.info(
                    f"[R{state['round']}] Pick #{pick_num} {player.display_name}: {name} (T{tier}) - Left: {pts_left}")
            else:
                print(f"⚠️ [SILENT] Error: No candidates for {player.display_name}")
                logger.error(f"⚠️ [SILENT ERROR] No valid pokemon for {player.display_name}")

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
                logger.error(f"Critical Auto-Mode Error: No valid candidates for {player.display_name}")
                await channel.send("⚠️ **CRITICAL:** No valid pokemon.")
            else:
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier
                ft = "⚡ Auto-Mode" if mode == 1 else "🔒 0 Rerolls left"
                embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
                embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
                embed.set_footer(text=f"{ft} | Budget: {config.MAX_POINTS - state['points'][player.id]}")
                await channel.send(f"{player.mention}", embed=embed)

                logger.info(f"[Auto-Mode] Assigned {name} (T{tier}) to {player.display_name}")
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

            # This channel.send is usually where the Discord 503 API crash happens. Protected by the Try block!
            start_msg = await channel.send(f"{player.mention}", embed=embed_start, view=roll_view)

            await roll_view.wait()

            if not roll_view.clicked:
                logger.info(f"Timeout on Roll Phase for {player.display_name}. Auto-rolling.")
                embed_start.description = "⏰ **Time Expired** - Auto rolling..."
                embed_start.color = 0xe74c3c
                await start_msg.edit(embed=embed_start, view=None)
                await asyncio.sleep(1)
            else:
                logger.info(f"{player.display_name} clicked Roll Dice.")
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
                    logger.error(f"Decision Phase Error: Pool Empty for {player.display_name}")
                    await channel.send("⚠️ **CRITICAL:** No valid pokemon.")
                    break

                logger.info(f"RNG generated: {name} (T{tier}) for {player.display_name}")

                # ==========================================
                # ✨ FAKE OUT EASTER EGG (NEW LOGIC)
                # ==========================================
                # Trigger: Rolled a <= 60 tier AND hit the 3.2% chance (Irrespective of turn number)
                if tier <= 60 and random.random() < config.FAKE_OUT_CHANCE:
                    fake_name, fake_tier = logic.get_fake_candidate(player.id, pick_num, current_is_reroll)

                    if fake_name:
                        logger.info(
                            f"✨ Easter Egg Triggered: Faking {player.display_name} with {fake_name} (T{fake_tier}) instead of actual {name} (T{tier})")

                        # 1. Reveal Fake Embed (Golden/Shiny)
                        fake_embed = views.create_fake_embed(player, fake_name, fake_tier)
                        fake_msg = await channel.send(f"{player.mention}", embed=fake_embed)

                        # Wait exactly 7 seconds with the golden message
                        await asyncio.sleep(7)

                        # 2. Hide the fake pull in a spoiler and add the suspense message.
                        # Discord cannot spoiler an embed directly after sending, so we convert it to spoilered text.
                        spoilered_text = f"||✨ CRITICAL HIT! You pulled the legendary: **{fake_name}** (Tier {fake_tier})||\n\n*...Wait... something feels off...*"
                        await fake_msg.edit(content=spoilered_text, embed=None)

                        # Wait exactly 3 seconds for the panic to set in
                        await asyncio.sleep(3)

                        # 3. Hariyama Message Drop as a new message to continue the flow
                        await channel.send("✋ **Hariyama used Fake Out!**")
                        await asyncio.sleep(2)

                        # 4. Transition to actual pull
                        await channel.send(f"😅 Just kidding {player.mention}, your **actual** pull is...")
                        await asyncio.sleep(1)
                # ==========================================

                # Forced accept if out of rerolls mid-loop
                if curr_left <= 0 and current_is_reroll:
                    state["rosters"][player.id].append({'name': name, 'tier': tier})
                    state["points"][player.id] += tier
                    embed = discord.Embed(title=f"Pick #{pick_num} • {player.display_name}", color=0x95a5a6)
                    embed.add_field(name="Auto-Accepted", value=f"**{name}** (Tier {tier})")
                    embed.set_footer(text="0 Re-rolls left.")
                    await channel.send(f"{player.mention}", embed=embed)
                    logger.info(f"Forced accept for {player.display_name} (0 rerolls left).")
                    break

                # Show Result (This is now the REAL pull, which appears immediately if no fake-out happened)
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

                    logger.info(f"🔄 {clicker} hit REROLL on {name}. Rerolls remaining: {new_left}")
                    await channel.send(f"🔄 **{clicker}** re-rolled! ({new_left} left).")
                    state["burned"].append(name)
                    current_is_reroll = True

                    continue  # Loop back to roll again

                else:  # KEEP
                    state["rosters"][player.id].append({'name': name, 'tier': tier})
                    state["points"][player.id] += tier
                    txt = f"✅ **{view.clicked_by.display_name}**" if view.value == "KEEP" else "⏰ Timeout:"
                    logger.info(f"✅ {name} kept by {player.display_name} (Trigger: {view.value})")
                    await channel.send(f"{txt} accepted **{name}**.")
                    break

        # Next Player
        state["current_index"] += 1
        await asyncio.sleep(1)
        await next_turn(channel, bot_instance)

    # =========================================
    # ⚠️ MASTER ERROR CATCHER & AUTO-RETRY
    # =========================================
    except discord.HTTPException as e:
        # This catches the 503 Service Unavailable API Error (and other disconnects)
        logger.error(f"Discord API Error encountered. Retries left: {retries} | Details: {e}")
        if retries > 0:
            logger.info("Attempting to resume turn in 5 seconds...")
            await asyncio.sleep(5)
            # Re-fire the turn, keeping track of the retry countdown
            await next_turn(channel, bot_instance, retries=retries - 1)
        else:
            logger.critical("Max API retries reached. Draft loop broken.")
            await channel.send(
                "🚨 **FATAL:** Discord API is continuously rejecting our connection. The draft has paused.")

    except Exception as e:
        # Catches entirely unexpected code bugs
        logger.error("An unexpected error crashed the engine loop:", exc_info=True)
        await channel.send("🚨 A bot error occurred. The draft loop has paused. Check `kokoloko.log` for details.")