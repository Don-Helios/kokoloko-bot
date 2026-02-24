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
    try:
        state = logic.draft_state

        if state["current_index"] >= len(state["order"]):
            if state["round"] >= config.TOTAL_POKEMON:
                if state["active"]:
                    await channel.send(views.MSG["draft_complete"])
                    for embed in views.create_summary_embed(state):
                        await channel.send(embed=embed)
                    state["active"] = False
                    print("🏁 [ENGINE] Draft Complete.")
                    logger.info("🏁 Draft Complete - Summary sent.")
                return

            state["round"] += 1
            state["order"].reverse()
            state["current_index"] = 0

            mode = state.get("auto_mode", 0)
            if mode != 2:
                await channel.send(views.MSG["end_of_round"].format(round_num=state['round']))

                if state["round"] > 2:
                    logger.info(f"Displaying auto-summary for start of Round {state['round']}")
                    for embed in views.create_summary_embed(state):
                        await channel.send(embed=embed)

                logger.info(f"--- STARTING ROUND {state['round']} ---")
                await asyncio.sleep(1)
            else:
                print(f"--- ROUND {state['round']} START ---")
                logger.info(f"--- STARTING ROUND {state['round']} (Silent) ---")

        player = state["order"][state["current_index"]]
        pick_num = len(state["rosters"][player.id]) + 1

        if pick_num > config.TOTAL_POKEMON:
            state["current_index"] += 1
            await next_turn(channel, bot_instance)
            return

        state["burned"] = []
        rerolls_used = state["rerolls"].get(player.id, 0)
        can_reroll = (config.MAX_REROLLS - rerolls_used) > 0
        mode = state.get("auto_mode", 0)

        logger.info(f"[Turn Start] Round {state['round']}, Pick #{pick_num} for {player.display_name}")

        if mode == 0:
            target_round = state["round"]
            temp_idx = state["current_index"]
            is_reversed_sim = False
            upcoming_players = []

            for _ in range(3):
                temp_idx += 1
                if temp_idx >= len(state["order"]):
                    target_round += 1
                    temp_idx = 0
                    is_reversed_sim = not is_reversed_sim

                if target_round <= config.TOTAL_POKEMON:
                    if is_reversed_sim:
                        sim_player = state["order"][::-1][temp_idx]
                    else:
                        sim_player = state["order"][temp_idx]
                    upcoming_players.append(sim_player)

            if len(upcoming_players) == 3:
                target_player = upcoming_players[-1]
                if target_player != player and target_player not in upcoming_players[:-1]:
                    if hasattr(target_player, "send"):
                        try:
                            dm_embed = views.create_dm_embed(target_player, channel.jump_url)
                            await target_player.send(embed=dm_embed)
                            logger.info(f"Sent 3-turn warning DM to {target_player.display_name}")
                        except discord.Forbidden:
                            logger.warning(f"Could not send DM to {target_player.display_name} (DMs disabled).")
                        except Exception as e:
                            logger.error(f"Failed to send DM to {target_player.display_name}: {e}")

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

        if mode == 1 or not can_reroll:
            valid_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=False)
            name, tier = logic.roll_pokemon(valid_tiers, player.id, pick_num, is_reroll=False)

            if not name:
                logger.error(f"Critical Auto-Mode Error: No valid candidates for {player.display_name}")
                await channel.send(views.MSG["err_critical_pool"])
            else:
                state["rosters"][player.id].append({'name': name, 'tier': tier})
                state["points"][player.id] += tier
                pts_left = config.MAX_POINTS - state["points"][player.id]

                embed = views.create_auto_accept_embed(player, pick_num, name, tier, mode, pts_left)
                await channel.send(f"{player.mention}", embed=embed)

                logger.info(f"[Auto-Mode] Assigned {name} (T{tier}) to {player.display_name}")
                if mode == 1: await asyncio.sleep(0.5)

        else:
            expiry_roll = int(time.time()) + config.ROLL_TIMEOUT
            odds = logic.calculate_tier_percentages(player.id, pick_num, is_reroll=False)
            embed_start = views.create_roll_embed(player, pick_num, expiry_roll, views.format_odds_grid(odds))
            roll_view = views.RollView(player)

            start_msg = await channel.send(f"{player.mention}", embed=embed_start, view=roll_view)

            await roll_view.wait()

            if not roll_view.clicked:
                logger.info(f"Timeout on Roll Phase for {player.display_name}. Auto-rolling.")
                embed_start.description = views.MSG["roll_timeout"]
                embed_start.color = 0xe74c3c
                await start_msg.edit(embed=embed_start, view=None)
                await asyncio.sleep(1)
            else:
                logger.info(f"{player.display_name} clicked Roll Dice.")
                embed_start.description = views.MSG["rolling"].format(odds=views.format_odds_grid(odds))
                embed_start.color = 0xf1c40f
                await start_msg.edit(embed=embed_start, view=None)

            current_is_reroll = False
            while True:
                curr_rr = state["rerolls"].get(player.id, 0)
                curr_left = config.MAX_REROLLS - curr_rr
                pts_left = config.MAX_POINTS - state["points"].get(player.id, 0)

                v_tiers = logic.get_valid_tiers(player.id, pick_num, is_reroll=current_is_reroll)
                name, tier = logic.roll_pokemon(v_tiers, player.id, pick_num, is_reroll=current_is_reroll)

                if not name:
                    logger.error(f"Decision Phase Error: Pool Empty for {player.display_name}")
                    await channel.send(views.MSG["err_critical_pool"])
                    break

                logger.info(f"RNG generated: {name} (T{tier}) for {player.display_name}")

                if tier <= 60 and random.random() < config.FAKE_OUT_CHANCE:
                    fake_name, fake_tier = logic.get_fake_candidate(player.id, pick_num, current_is_reroll)

                    if fake_name:
                        logger.info(
                            f"✨ Easter Egg Triggered: Faking {player.display_name} with {fake_name} (T{fake_tier}) instead of actual {name} (T{tier})")

                        fake_embed = views.create_fake_embed(player, fake_name, fake_tier)
                        fake_msg = await channel.send(f"{player.mention}", embed=fake_embed)

                        await asyncio.sleep(7)

                        spoilered_text = views.MSG["fakeout_spoiler"].format(name=fake_name, tier=fake_tier)
                        await fake_msg.edit(content=spoilered_text, embed=None)

                        await asyncio.sleep(3)

                        await channel.send(views.MSG["fakeout_hariyama"])
                        await asyncio.sleep(2)

                        await channel.send(views.MSG["fakeout_reveal"].format(mention=player.mention))
                        await asyncio.sleep(1)

                if curr_left <= 0 and current_is_reroll:
                    state["rosters"][player.id].append({'name': name, 'tier': tier})
                    state["points"][player.id] += tier
                    pts_left = config.MAX_POINTS - state["points"][player.id]

                    embed = views.create_auto_accept_embed(player, pick_num, name, tier, mode, pts_left)
                    await channel.send(f"{player.mention}", embed=embed)

                    logger.info(f"Forced accept for {player.display_name} (0 rerolls left).")
                    break

                expiry_dec = int(time.time()) + config.DECISION_TIMEOUT
                embed = views.create_decision_embed(player, pick_num, name, tier, pts_left, curr_left, state['round'],
                                                    expiry_dec)

                view = views.DraftView(player)
                await channel.send(f"{player.mention}", embed=embed, view=view)
                await view.wait()

                if view.value == "REROLL":
                    state["rerolls"][player.id] += 1
                    new_left = config.MAX_REROLLS - state["rerolls"][player.id]
                    clicker = view.clicked_by.display_name if view.clicked_by else "Staff"

                    logger.info(f"🔄 {clicker} hit REROLL on {name}. Rerolls remaining: {new_left}")
                    await channel.send(views.MSG["action_reroll"].format(clicker=clicker, left=new_left))
                    state["burned"].append(name)
                    current_is_reroll = True
                    continue

                else:
                    state["rosters"][player.id].append({'name': name, 'tier': tier})
                    state["points"][player.id] += tier

                    if view.value == "KEEP":
                        msg = views.MSG["action_keep"].format(clicker=view.clicked_by.display_name, name=name)
                    else:
                        msg = views.MSG["action_timeout"].format(name=name)

                    logger.info(f"✅ {name} kept by {player.display_name} (Trigger: {view.value})")
                    await channel.send(msg)
                    break

        state["current_index"] += 1
        await asyncio.sleep(1)
        await next_turn(channel, bot_instance)

    except discord.HTTPException as e:
        logger.error(f"Discord API Error encountered. Retries left: {retries} | Details: {e}")
        if retries > 0:
            logger.info("Attempting to resume turn in 5 seconds...")
            await asyncio.sleep(5)
            await next_turn(channel, bot_instance, retries=retries - 1)
        else:
            logger.critical("Max API retries reached. Draft loop broken.")
            await channel.send(views.MSG["err_api_fatal"])

    except Exception as e:
        logger.error("An unexpected error crashed the engine loop:", exc_info=True)
        await channel.send(views.MSG["err_bot_crash"])