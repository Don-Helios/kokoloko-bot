# Kokoloko Draft — a Discord bot

This repo consist of a Docker container cloned from my dev env repo and includes the .py files that describe a Discord bot.


The repo can be cloned to run a bot that manages a Kokoloko Draft, which is a self-coined term for a Pokémon Draft with semi-randomly picked Pokémon


## Features
* **Three Game Modes:** 
  * 🔴 **Interactive:** Players roll the dice and choose to Keep or Reroll their pulls.
  * 🟢 **Auto Mode:** The bot automatically rolls and accepts for players, broadcasting the pulls.
  * 🤫 **Fast Simulation:** The bot simulates the draft silently and instantly in the background.
* **Complex Drafting Logic:** Handles "Species protection" (prevents owning a base and Mega evolution of the same species), VIP Tier caps, and budget constraints (Salary Cap).
* **Easter Eggs:** Built-in "Fake Out" mechanic that randomly fakes a high-tier pull before revealing the real Pokémon.
* **Visual Summaries:** Generates multi-page embed summaries mid-draft, and uses Pillow (PIL) to stitch together a custom 5x2 PNG image of each player's final roster at the end.
* **Dual Deployment:** Ships with Docker Compose files for both background production running and interactive development.

## Prerequisites
* [Docker](https://docs.docker.com/get-docker/) and Docker Compose
* A Discord Bot Token (Get one from the [Discord Developer Portal](https://discord.com/developers/applications))
* A server with the specific roles and channels configured (see below).

## Setup & Installation

**1. Clone the repository:**
```bash
git clone [https://github.com/yourusername/kokoloko-draft.git](https://github.com/yourusername/kokoloko-draft.git)
cd kokoloko-draft
```
**2. Environment Variables:**

Create a .env file in the root directory and add your Discord bot token. (See .env.example).
```shell
DISCORD_TOKEN=your_bot_token_here
```
**3. Discord Server Configuration:**

For the bot to function securely and correctly, your Discord server must have the following configured to match config.py:

* A thread where the draft will take place.
* A role for administrators (e.g., Staff).
* A role for the players (e.g., Draft).

Note: The bot requires the *Server Members* Intent and *Message Content* Intent enabled in the Discord Developer Portal.

**4. Data File:**

* Ensure you have a pokemon_data.csv file in the root directory. 
* It must contain the following columns: 
  * name 
  * tier 
  * mega *[values need to be Y or N]*
  * sprite *[URL to a .png image]*
  
Note: the repo contains the list we used for our Draft, you can use that as a base to do yours


##  Running the Bot

This project is fully containerized. You do not need to install Python locally.

**Production Mode (Runs autonomously in the background):**
```bash
docker compose up -d --build
```
To stop production: docker compose down

**Development Mode (Keeps container idle for manual execution):**
```bash
# 1. Start the dev container
docker compose -f compose.dev.yaml up -d --build

# 2. Run the bot manually using the helper script
./run kokoloko.py
```

## Commands

All commands are restricted to the designated draft thread to prevent spam.

* ```!start_draft @user1 @user2...```	
  * Staff Role	
  * Initializes the setup menu to choose modes and dummies, then starts the draft loop.
* ```!summary```	
  * Draft Role	
  * Prints the current state of the draft (Points, Rerolls, Rosters) into the thread.
* ```!toggle_auto```	
  * Staff Role
  * Instantly switches the active draft between Interactive and Auto Public modes.
* ```!cancel_draft```	
  * Staff Role
  * Forcefully terminates an active draft loop.

## Python code estructure

* **kokoloko.py:** Main entry point and command listener.

* **engine.py:** The core game loop (turn management, timers, and sequence flow).

* **logic.py:** The "brain". Handles pool filtering, validation, probabilities, and RNG.

* **views.py:** UI components (Embeds, Buttons, Text Strings, Image Generation).

* **config.py:** Centralized configuration constants.