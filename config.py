import os
from dotenv import load_dotenv

load_dotenv()

# --- SECRETS ---
TOKEN = os.getenv('DISCORD_TOKEN')
CSV_FILE = 'pokemon_data.csv'

# --- PERMISSIONS ---
STAFF_ROLE_NAME = "NPO-Draft Staff"

# --- GAME CONSTANTS ---
MAX_REROLLS = 10
MAX_POINTS = 1200
MIN_TIER_COST = 20
TOTAL_POKEMON = 10
ROLL_TIMEOUT = 60     # Tiempo para el botón "Click to Roll"
DECISION_TIMEOUT = 60 # NUEVO: Tiempo para decidir "Keep/Reroll"

# --- PROBABILITIES (Updated) ---
TIER_PROBS = {
    300: 0.50,   # 0.50%
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