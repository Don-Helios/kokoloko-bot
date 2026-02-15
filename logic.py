import os
import pandas as pd
import random
import config

# --- STATE MANAGEMENT ---
draft_state = {
    "active": False,
    "round": 1,
    "order": [],
    "current_index": 0,
    "rosters": {},
    "rerolls": {},
    "points": {},
    "burned": [],
    "auto_mode": 0
}

pokemon_db = pd.DataFrame()
root_map = {}


def normalize_root(row):
    """
    Extracts the 'Base Species' name (Family ID).
    Handles 'Mega', 'Primal', and suffixes like X/Y.
    """
    name = str(row['name']).lower().strip()

    # Check for Mega column OR Primal name
    is_mega_col = str(row['mega']).strip().upper() == 'Y'
    is_primal_name = name.startswith("primal ")

    if is_mega_col or is_primal_name:
        # 1. Remove Prefixes
        if name.startswith("mega "):
            name = name[5:].strip()
        elif name.startswith("primal "):
            name = name[7:].strip()

        # 2. Remove Suffixes (X/Y)
        if name.endswith(" x"):
            name = name[:-2].strip()
        elif name.endswith(" y"):
            name = name[:-2].strip()

    return name


def load_data():
    global pokemon_db, root_map
    if os.path.exists(config.CSV_FILE):
        pokemon_db = pd.read_csv(config.CSV_FILE)
        pokemon_db.columns = pokemon_db.columns.str.strip().str.lower()

        # 1. Clean Mega Column
        if 'mega' in pokemon_db.columns:
            pokemon_db['mega'] = pokemon_db['mega'].str.strip().str.upper()
        else:
            pokemon_db['mega'] = 'N'

        # 2. Create Root Name Column (The "Family" ID)
        pokemon_db['root_name'] = pokemon_db.apply(normalize_root, axis=1)

        # 3. Build fast lookup map
        root_map = dict(zip(pokemon_db['name'], pokemon_db['root_name']))

        print(f"✅ Logic: CSV Loaded ({len(pokemon_db)} rows).")
    else:
        print(f"❌ Logic Error: File {config.CSV_FILE} not found.")


def initialize_draft(players):
    draft_state["order"] = players
    draft_state["rosters"] = {p.id: [] for p in players}
    draft_state["rerolls"] = {p.id: 0 for p in players}
    draft_state["points"] = {p.id: 0 for p in players}
    draft_state["round"] = 1
    draft_state["current_index"] = 0
    draft_state["active"] = True
    draft_state["burned"] = []
    draft_state["auto_mode"] = 0


def get_mega_counts(user_id):
    roster = draft_state["rosters"].get(user_id, [])
    high = 0
    low = 0
    total = 0
    for p in roster:
        match = pokemon_db[pokemon_db['name'] == p['name']]
        if not match.empty:
            is_mega = match.iloc[0]['mega'] == 'Y'
            if is_mega:
                total += 1
                if p['tier'] >= 240:
                    high += 1
                else:
                    low += 1
    return total, high, low


def get_mega_status(user_id):
    total, high, low = get_mega_counts(user_id)
    if high >= 1: return 'NO_MEGAS'
    if low >= 2: return 'NO_MEGAS'
    if low == 1: return 'LOW_ONLY'
    return 'ALL_ALLOWED'


def get_valid_candidates(user_id, pick_number=None, is_reroll=False):
    candidates = pokemon_db.copy()

    # 1. Filter Burned & Global Picks
    all_picked = []
    for roster in draft_state["rosters"].values():
        for p in roster:
            all_picked.append(p['name'])
    excluded_names = set(draft_state['burned'] + all_picked)
    candidates = candidates[~candidates['name'].isin(excluded_names)]

    # 2. FAMILY DUPLICATE FILTER (Base vs Mega)
    user_roster = draft_state["rosters"].get(user_id, [])
    owned_roots = set()
    for p in user_roster:
        r_name = root_map.get(p['name'])
        if r_name:
            owned_roots.add(r_name)

    candidates = candidates[~candidates['root_name'].isin(owned_roots)]

    # 3. MEGA PITY RULE (Pick 6 + 0 Megas + NOT a reroll)
    mega_total, _, _ = get_mega_counts(user_id)
    if pick_number == 6 and mega_total == 0 and not is_reroll:
        candidates = candidates[candidates['mega'] == 'Y']
        return candidates

    # 4. Standard Mega Restrictions
    mega_status = get_mega_status(user_id)

    if mega_status == 'NO_MEGAS':
        candidates = candidates[candidates['mega'] != 'Y']
    elif mega_status == 'LOW_ONLY':
        condition = (candidates['mega'] != 'Y') | (candidates['tier'] < 240)
        candidates = candidates[condition]

    return candidates


def get_valid_tiers(user_id, pick_number, is_reroll=False):
    user_roster = draft_state["rosters"].get(user_id, [])
    points_spent = draft_state["points"].get(user_id, 0)

    valid_candidates_df = get_valid_candidates(user_id, pick_number, is_reroll)
    available_tiers = set(valid_candidates_df['tier'].unique())

    allowed = list(config.TIER_PROBS.keys())
    allowed = [t for t in allowed if t in available_tiers]

    # Rule A: High Tier Logic
    count_300 = sum(1 for p in user_roster if p['tier'] == 300)
    count_260 = sum(1 for p in user_roster if p['tier'] == 260)
    count_240 = sum(1 for p in user_roster if p['tier'] == 240)

    if count_300 > 0:
        for t in [300, 260, 240]:
            if t in allowed: allowed.remove(t)
    elif (count_260 + count_240) >= 2:
        for t in [300, 260, 240]:
            if t in allowed: allowed.remove(t)
    else:
        if count_260 > 0:
            if 300 in allowed: allowed.remove(300)
            if 260 in allowed: allowed.remove(260)
        elif count_240 > 0:
            if 300 in allowed: allowed.remove(300)

    # Rule B: Salary Cap
    points_remaining = config.MAX_POINTS - points_spent
    picks_remaining_total = config.TOTAL_POKEMON - (pick_number - 1)
    future_picks_needed = picks_remaining_total - 1

    reserve_cash = future_picks_needed * config.MIN_TIER_COST
    max_affordable_now = points_remaining - reserve_cash

    allowed = [t for t in allowed if t <= max_affordable_now]

    return allowed


def calculate_tier_percentages(user_id, pick_number, is_reroll=False):
    valid_tiers = get_valid_tiers(user_id, pick_number, is_reroll)
    current_sum = sum(config.TIER_PROBS[t] for t in valid_tiers)
    if current_sum == 0: return {}
    stats = {}
    for t in sorted(valid_tiers, reverse=True):
        raw_prob = (config.TIER_PROBS[t] / current_sum) * 100
        stats[t] = raw_prob
    return stats


def roll_pokemon(valid_tiers, user_id, pick_number, is_reroll=False):
    if not valid_tiers: return None, "NO_VALID_TIERS"

    current_sum = sum(config.TIER_PROBS[t] for t in valid_tiers)
    if current_sum == 0: return None, "ZERO_SUM"

    weights = [config.TIER_PROBS[t] / current_sum for t in valid_tiers]
    selected_tier = random.choices(valid_tiers, weights=weights, k=1)[0]

    candidates_pool = get_valid_candidates(user_id, pick_number, is_reroll)
    tier_pool = candidates_pool[candidates_pool['tier'] == selected_tier]

    if tier_pool.empty:
        return None, "EMPTY_TIER_POOL"

    picked = tier_pool.sample(n=1).iloc[0]
    return picked['name'], int(picked['tier'])