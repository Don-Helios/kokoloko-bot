import os
import pandas as pd
import random
import config

# ==========================================
# 🧠 GLOBAL STATE MANAGEMENT
# ==========================================
# This dictionary holds the entire game state in memory.
draft_state = {
    "active": False,  # Is a draft currently running?
    "round": 1,  # Current Round number (1 to TOTAL_POKEMON)
    "order": [],  # List of Player objects in Snake Order
    "current_index": 0,  # Index of the player whose turn it currently is
    "rosters": {},  # Dictionary: {user_id: [List of Pokemon Dicts]}
    "rerolls": {},  # Dictionary: {user_id: Int (Rerolls Used)}
    "points": {},  # Dictionary: {user_id: Int (Points Spent)}
    "burned": [],  # List of Pokemon names rejected/burned in the CURRENT turn
    "auto_mode": 0  # 0=Interactive, 1=Auto Public, 2=Auto Silent
}

# DataFrames to hold the CSV data and lookups
pokemon_db = pd.DataFrame()
root_map = {}  # Maps full names to their "Root Family Name" (e.g. "Mega Charizard X" -> "charizard")


# ==========================================
# 🔧 DATA HELPERS
# ==========================================

def normalize_root(row):
    """
    Determines the 'Family ID' (Root Name) for a Pokemon.
    Used to implement the rule: "You cannot own both Base and Mega of the same species."

    Logic:
    1. If it's a MEGA (Mega='Y'):
       - Strip 'mega ' prefix.
       - Strip ' x' or ' y' suffixes.
    2. If it's NOT a Mega:
       - Use the name as is.

    Note: Primal Groudon/Kyogre are handled by Tier Restrictions (High Caps), not name matching.
    """
    name = str(row['name']).lower().strip()
    is_mega = str(row['mega']).strip().upper() == 'Y'

    if is_mega:
        # Remove "mega " prefix
        if name.startswith("mega "):
            name = name[5:].strip()

        # Remove Suffixes (Variant X/Y)
        if name.endswith(" x"):
            name = name[:-2].strip()
        elif name.endswith(" y"):
            name = name[:-2].strip()

    return name


def load_data():
    """
    Loads the CSV file into pandas, normalizes columns, and builds the Root Map.
    Must be called on bot startup.
    """
    global pokemon_db, root_map
    if os.path.exists(config.CSV_FILE):
        pokemon_db = pd.read_csv(config.CSV_FILE)
        # Lowercase columns for consistency
        pokemon_db.columns = pokemon_db.columns.str.strip().str.lower()

        # Standardize Mega column to 'Y' or 'N'
        if 'mega' in pokemon_db.columns:
            pokemon_db['mega'] = pokemon_db['mega'].str.strip().str.upper()
        else:
            pokemon_db['mega'] = 'N'

        # Generate Root Names for Family Protection
        pokemon_db['root_name'] = pokemon_db.apply(normalize_root, axis=1)
        root_map = dict(zip(pokemon_db['name'], pokemon_db['root_name']))

        print(f"✅ Logic: CSV Loaded ({len(pokemon_db)} rows).")
    else:
        print(f"❌ Logic Error: File {config.CSV_FILE} not found.")


def initialize_draft(players):
    """Resets all draft state variables for a fresh game."""
    draft_state["order"] = players
    draft_state["rosters"] = {p.id: [] for p in players}
    draft_state["rerolls"] = {p.id: 0 for p in players}
    draft_state["points"] = {p.id: 0 for p in players}
    draft_state["round"] = 1
    draft_state["current_index"] = 0
    draft_state["active"] = True
    draft_state["burned"] = []


# ==========================================
# 🔍 VALIDATION LOGIC
# ==========================================

def get_mega_counts(user_id):
    """
    Counts how many Megas a user has, split by High Tier (>=240) and Low Tier (<240).
    Returns: (Total Megas, High Megas, Low Megas)
    """
    roster = draft_state["rosters"].get(user_id, [])
    high = 0
    low = 0
    total = 0
    for p in roster:
        # Check DB for Mega Status
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
    """
    Determines if a user is allowed to pick more Megas based on the Cap.
    Rule: Max 1 High Mega OR 2 Low Megas.
    """
    total, high, low = get_mega_counts(user_id)
    if high >= 1: return 'NO_MEGAS'  # Cap reached (High)
    if low >= 2: return 'NO_MEGAS'  # Cap reached (Low)
    if low == 1: return 'LOW_ONLY'  # Can only pick one more Low Mega
    return 'ALL_ALLOWED'


def get_valid_candidates(user_id, pick_number=None, is_reroll=False):
    """
    Returns the DataFrame of Pokemon allowed for this specific pick.
    Applies: Global Exclusion, Burned List, Family Protection, Pity Rule, Mega Caps.
    """
    candidates = pokemon_db.copy()

    # 1. REMOVE GLOBALLY PICKED POKEMON
    all_picked = []
    for roster in draft_state["rosters"].values():
        for p in roster:
            all_picked.append(p['name'])

    # Also remove pokemon "burned" (skipped) in this turn
    excluded_names = set(draft_state['burned'] + all_picked)
    candidates = candidates[~candidates['name'].isin(excluded_names)]

    # 2. FAMILY PROTECTION (ROOT NAME CHECK)
    # If user owns 'Charizard', remove all 'Mega Charizard X/Y'
    user_roster = draft_state["rosters"].get(user_id, [])
    owned_roots = set()
    for p in user_roster:
        r_name = root_map.get(p['name'])
        if r_name:
            owned_roots.add(r_name)

    # Filter out anything sharing a root name
    candidates = candidates[~candidates['root_name'].isin(owned_roots)]

    # 3. MEGA PITY RULE
    # Logic: If Pick #6, User has 0 Megas, and this is the FIRST roll (not reroll)
    mega_total, _, _ = get_mega_counts(user_id)
    if pick_number == 6 and mega_total == 0 and not is_reroll:
        # Force pool to ONLY be Megas
        candidates = candidates[candidates['mega'] == 'Y']
        return candidates

    # 4. STANDARD MEGA CAPS
    mega_status = get_mega_status(user_id)
    if mega_status == 'NO_MEGAS':
        candidates = candidates[candidates['mega'] != 'Y']
    elif mega_status == 'LOW_ONLY':
        # Allow Non-Megas OR Low Tier Megas
        condition = (candidates['mega'] != 'Y') | (candidates['tier'] < 240)
        candidates = candidates[condition]

    return candidates


def get_valid_tiers(user_id, pick_number, is_reroll=False):
    """
    Calculates which Tiers are clickable on the wheel.
    Applies: High Tier Rule (A) and Salary Cap (B).
    """
    user_roster = draft_state["rosters"].get(user_id, [])
    points_spent = draft_state["points"].get(user_id, 0)

    # Get available pool
    valid_candidates_df = get_valid_candidates(user_id, pick_number, is_reroll)
    available_tiers = set(valid_candidates_df['tier'].unique())

    allowed = list(config.TIER_PROBS.keys())
    allowed = [t for t in allowed if t in available_tiers]

    # --- RULE A: HIGH TIER RESTRICTIONS ---
    count_300 = sum(1 for p in user_roster if p['tier'] == 300)
    count_260 = sum(1 for p in user_roster if p['tier'] == 260)
    count_240 = sum(1 for p in user_roster if p['tier'] == 240)

    # Logic:
    # 1. Owning ONE Tier 300 bans all 300/260/240
    # 2. Owning TWO High Tiers (260/240) bans all 300/260/240
    if count_300 > 0:
        for t in [300, 260, 240]:
            if t in allowed: allowed.remove(t)
    elif (count_260 + count_240) >= 2:
        for t in [300, 260, 240]:
            if t in allowed: allowed.remove(t)
    else:
        # Intermediate Steps
        if count_260 > 0:
            if 300 in allowed: allowed.remove(300)
            if 260 in allowed: allowed.remove(260)
        elif count_240 > 0:
            if 300 in allowed: allowed.remove(300)

    # --- RULE B: SALARY CAP ---
    points_remaining = config.MAX_POINTS - points_spent
    picks_remaining_total = config.TOTAL_POKEMON - (pick_number - 1)
    future_picks_needed = picks_remaining_total - 1

    # Reserve cash calculation
    reserve_cash = future_picks_needed * config.MIN_TIER_COST
    max_affordable_now = points_remaining - reserve_cash

    # Remove too expensive tiers
    allowed = [t for t in allowed if t <= max_affordable_now]

    return allowed


def calculate_tier_percentages(user_id, pick_number, is_reroll=False):
    """Recalculates display percentages based on valid tiers."""
    valid_tiers = get_valid_tiers(user_id, pick_number, is_reroll)
    current_sum = sum(config.TIER_PROBS[t] for t in valid_tiers)
    if current_sum == 0: return {}
    stats = {}
    for t in sorted(valid_tiers, reverse=True):
        raw_prob = (config.TIER_PROBS[t] / current_sum) * 100
        stats[t] = raw_prob
    return stats


def roll_pokemon(valid_tiers, user_id, pick_number, is_reroll=False):
    """
    Executes the RNG roll.
    1. Weighted Random Choice of Tier.
    2. Uniform Random Choice of Pokemon within that Tier.
    """
    if not valid_tiers: return None, "NO_VALID_TIERS"
    current_sum = sum(config.TIER_PROBS[t] for t in valid_tiers)
    if current_sum == 0: return None, "ZERO_SUM"

    weights = [config.TIER_PROBS[t] / current_sum for t in valid_tiers]
    selected_tier = random.choices(valid_tiers, weights=weights, k=1)[0]

    candidates_pool = get_valid_candidates(user_id, pick_number, is_reroll)
    tier_pool = candidates_pool[candidates_pool['tier'] == selected_tier]

    if tier_pool.empty: return None, "EMPTY_TIER_POOL"
    picked = tier_pool.sample(n=1).iloc[0]
    return picked['name'], int(picked['tier'])


# --- EASTER EGG HELPER ---
def get_fake_candidate(user_id):
    """
    Finds a Pokemon that is UNAFFORDABLE (Tier > Current Budget).
    Used for the Hariyama Fake Out Easter Egg.
    """
    points_spent = draft_state["points"].get(user_id, 0)
    current_budget = config.MAX_POINTS - points_spent

    # Get all pokemon more expensive than we can afford
    candidates = pokemon_db[pokemon_db['tier'] > current_budget]
    if candidates.empty: return None, None

    # Sort descending to pick the most "shiny/expensive" bait possible
    candidates = candidates.sort_values(by='tier', ascending=False)
    picked = candidates.sample(n=1).iloc[0]
    return picked['name'], int(picked['tier'])