import os
from dotenv import load_dotenv

# Load environment variables from .env file for security
load_dotenv()

# ==========================================
# ⚙️ CONFIGURATION SETTINGS
# ==========================================

# --- BOT CREDENTIALS ---
# The token is loaded from the .env file to prevent leaking it in code sharing.
TOKEN = os.getenv('DISCORD_TOKEN')

# --- DATA SOURCE ---
# The CSV file must contain columns: 'Name', 'Mega' (Y/N), 'Tier' (Integer)
CSV_FILE = 'pokemon_data.csv'

# --- GAME RULES (RESTORED FROM YOUR UPLOAD) ---
MAX_POINTS = 1200       # Total salary cap per player
TOTAL_POKEMON = 10      # Number of Pokemon to draft
MAX_REROLLS = 10        # Maximum rerolls allowed per player

# --- ECONOMY SETTINGS ---
# Cost of the cheapest tier. Used to calculate "Reserve Cash"
# (e.g., preventing a player from spending so much they can't afford the last picks)
MIN_TIER_COST = 20

# --- TIMERS (Seconds) ---
ROLL_TIMEOUT = 60       # Time user has to click "Roll Dice"
DECISION_TIMEOUT = 60   # Time user has to decide "Keep" or "Reroll"

# --- PROBABILITIES (RESTORED FROM YOUR UPLOAD) ---
# Precise probability distribution for each Tier.
# If a Tier is unavailable (e.g. too expensive), the code dynamically
# redistributes that tier's probability to the remaining valid tiers.
TIER_PROBS = {
    300: 0.50,   # 0.50%  (Ubers)
    260: 1.00,   # 1.00%
    240: 1.50,   # 1.50%
    220: 3.00,   # 3.00%
    200: 7.50,   # 7.50%
    180: 10.00,  # 10.00%
    160: 12.25,  # 12.25%
    140: 15.00,  # 15.00%
    120: 15.00,  # 15.00%
    100: 12.25,  # 12.25%
    80:  10.00,  # 10.00%
    60:  7.50,   # 7.50%
    40:  3.00,   # 3.00%
    20:  1.50    # 1.50%
}

# --- PERMISSIONS ---
# The Role Name required to use Admin commands like !toggle_auto
STAFF_ROLE_NAME = "NPO-Draft Staff"

# --- EASTER EGGS ---
# 0.032 = 3.2% Chance for Delibird Fake Out to trigger on a pull of Tier 60 or less.
FAKE_OUT_CHANCE = 0.13

# ==========================================
# 🧵 THREAD & ANNOUNCEMENT SETTINGS
# ==========================================
# The exact name of the thread where the bot is allowed to operate.
THREAD_NAME = "kokoloko-draft"
# The exact name of the role to ping when a draft starts.
PING_ROLE_NAME = "Draft"

# ==========================================
# 📝 LOGGING SETTINGS
# ==========================================
# The file where detailed background DEBUG logs will be saved.
# The terminal will only show INFO and above to stay clean.
LOG_FILE = 'kokoloko.log'