import discord
import config
import logic
import logging
import io
import asyncio
import aiohttp
from PIL import Image

logger = logging.getLogger("views")

# ==========================================
# 💬 CENTRALIZED TEXT DICTIONARY (TRANSLATE HERE)
# ==========================================
# All plain text messages sent by the bot are stored here.
# Centralizing this makes it much easier to change the bot's language or tone
# later without having to hunt through the logical loops.
MSG = {
    # --- Kokoloko.py (Commands & Setup) ---
    "err_thread": "🚫 Por favor usa este comando en el hilo `{thread}`.",
    "err_staff": "🚫 Staff only.",
    "mode_names": ["🔴 **INTERACTIVO**", "🟢 **AUTO ACEPTAR**", "🤫 **SIMULACIÓN RÁPIDA**"],
    "mode_switch": "⚡ **Modo:** {mode}",
    "setup_dummies_title": "🤖 CONFIGURACIÓN",
    "setup_dummies_desc": "¿Incluir los {count} dummies?",
    "timeout": "❌ Expiró el tiempo",
    "err_no_players": "❌ ¡Necesitas incluir a los jugadores!",
    "setup_mode_title": "🔧 Modo",
    "setup_mode_desc": "Selecciona el modo:",
    "announce_parent": "📢 ¡El Kokoloko Draft acaba de iniciar! Entra en el hilo {thread_mention} para ver la selección || {ping_text} ||",
    "draft_started": "🏆 **¡Draft iniciado!** (ID: `{draft_id}`)\nOrden: {names}",
    "err_draft_active": "🚫 ¡Ya hay un draft en curso! Usa `!cancel_draft` para detenerlo primero.",
    "draft_cancelled": "🛑 **El draft ha sido cancelado forzosamente por un administrador.**",
    "err_no_active_draft": "⚠️ No hay ningún draft activo en este momento.",
    "err_draft_role": "🚫 Solo los miembros con el rol 'Draft' pueden usar este comando.",

    # --- Engine.py (Game Flow & Turns) ---
    "draft_complete": "🏁 **¡Draft Finalizado!**",
    "end_of_round": "🔁 **¡Fin de la ronda!**",
    "err_critical_pool": "⚠️ **ERROR:** No hay Pokémon válidos.",
    "roll_timeout": "⏰ **Tiempo agotado** - Lanzamiento automático...",
    "rolling": "**Rolling...** 🎰\n\n**Probabilidades:**\n{odds}",
    "fakeout_spoiler": "||✨ ¡Golpe crítico! Has sacado el tazo dorado✨: **{name}** (Tier {tier})||\n\n*...Espera...* **algo se aproxima...**",
    "fakeout_delibird": "✋ **¡Delibird usó Sorpresa!**",
    "fakeout_reveal": " 🤡 {mention}, tu **verdadero Pokémon es** ...",
    "action_reroll": "🔄 **{clicker}** utilizó un reintento! (le quedan {left}).",
    "action_keep": "✅ **{clicker}** aceptó **{name}**.",
    "action_timeout": "⏰ Tiempo agotado: se aceptó automáticamente **{name}**.",
    "err_api_fatal": "🚨 **FATAL:** Discord API is continuously rejecting our connection. The draft has paused.",
    "err_bot_crash": "🚨 A bot error occurred. The draft loop has paused. Check `kokoloko.log` for details.",
    "dm_out_of_rerolls": "🔔 **Aviso:** ¡Te has quedado sin reintentos! \nA partir de ahora tus Pokémon serán aceptados automáticamente y ya no recibirás recordatorios de turno.",
    "announce_round_summary": "📢 Terminó la Ronda #{round_num} del Kokoloko Draft y así van los equipos de los coaches hasta el momento:",
    "announce_draft_complete_parent": "🏁 **¡El Kokoloko Draft ha concluido!** Estos son los equipos finales de todos los coaches:"
}


# ==========================================
# 🎨 FORMATTERS & UTILS
# ==========================================

def format_odds_grid(odds_data):
    """
    Formats the tier probabilities into a clean text grid.
    Used before the user clicks "Jala la palanca" so they know their odds.
    """
    if not odds_data: return "⚠️ Sin Tiers Válidas"
    items = []
    for tier, pct in odds_data.items():
        if tier >= 240:
            icon = "🔥"
        elif tier <= 40:
            icon = "⚪"
        else:
            icon = "🔹"
        items.append(f"{icon} **T{tier}:** `{pct:.1f}%`")

    # Arrange into two columns
    grid_rows = []
    for i in range(0, len(items), 2):
        left = items[i]
        right = items[i + 1] if (i + 1) < len(items) else ""
        grid_rows.append(f"{left} \u2003 {right}")
    return "\n".join(grid_rows)


# ==========================================
# 🖼️ EMBEDS
# ==========================================

def create_roll_embed(player, pick_num, expiry_time, odds_grid_str):
    """Standard pre-roll embed asking the user to start their turn."""
    return discord.Embed(
        title=f"🃏 Pokémon #{pick_num} • {player.display_name}",
        description=f"¡Toca el botón para girar!\n⏳ **Lanzamiento automático en** <t:{expiry_time}:R>\n\n**Probabilidades:**\n{odds_grid_str}",
        color=0x2ecc71
    )


def create_fake_embed(player, name, tier, sprite_url):
    """
    The 'Fake Out' Easter Egg Embed.
    Uses Gold Color (0xFFD700) to mimic a high-value/Critical hit.
    Image is set as a large banner via set_image() to maximize dramatic effect.
    """
    embed = discord.Embed(
        title=f"✨ ¡GOLPE CRÍTICO! • {player.display_name}",
        description=f"has sacado el tazo dorado✨:\n# **{name}**\n**(Tier {tier})**",
        color=0xFFD700
    )
    if sprite_url and sprite_url.startswith("http"):
        embed.set_image(url=sprite_url)
    return embed


def create_dm_embed(player, jump_url):
    """Embed sent via DM to ping players 3 turns in advance."""
    return discord.Embed(
        title="🔔 Kokoloko Draft",
        description=(
            f"¡Preparate, **{player.display_name}**! Te tocará elegir en **3 turnos**.\n\n"
            f":thread:  **[Entra aquí al hilo]({jump_url})**"
        ),
        color=0x3498db
    )


def create_auto_accept_embed(player, pick_num, name, tier, mode, pts_left, sprite_url):
    """Embed shown when a Pokémon is auto-accepted (Mode 1 or 0 rerolls)."""
    ft_text = "⚡ Aceptación automática" if mode == 1 else "🔒 Ya no te quedan reintentos"
    embed = discord.Embed(title=f"Pokémon #{pick_num} • {player.display_name}", color=0x95a5a6)
    embed.add_field(name="Aceptado Automáticamente", value=f"**{name}** (Tier {tier})")
    embed.set_footer(text=f"{ft_text} | Puntos: {pts_left} pts restantes")

    if sprite_url and sprite_url.startswith("http"):
        embed.set_thumbnail(url=sprite_url)
    return embed


def create_decision_embed(player, pick_num, name, tier, pts_left, curr_left, round_num, expiry_dec, sprite_url):
    """Main action embed showing the rolled Pokémon, asking Keep/Reroll."""
    embed = discord.Embed(
        title=f"Pokémon #{pick_num} • {player.display_name}",
        description=f"⏳ **Decide en** <t:{expiry_dec}:R>\n(Ronda {round_num})",
        color=0xF1C40F
    )
    embed.add_field(name="Pokémon", value=f"**{name}**", inline=True)
    embed.add_field(name="Tier", value=f"{tier}", inline=True)
    embed.add_field(name="Puntos", value=f"{pts_left} pts restantes", inline=False)
    embed.set_footer(text=f"Reintentos restantes: {curr_left}/{config.MAX_REROLLS}")

    if sprite_url and sprite_url.startswith("http"):
        embed.set_thumbnail(url=sprite_url)
    return embed


def create_personal_summary_embed(player, draft_state):
    """
    Generates a compact summary embed for a single player.
    Used by the mid-turn 'Resumen' button to avoid channel bloat.
    """
    roster = draft_state["rosters"].get(player.id, [])
    points_spent = draft_state["points"].get(player.id, 0)
    points_left = config.MAX_POINTS - points_spent
    rerolls_left = config.MAX_REROLLS - draft_state["rerolls"].get(player.id, 0)

    embed = discord.Embed(title=f"📊 Resumen Personal • {player.display_name}", color=0x3498db)

    p_list = "\n".join([f"• **{p['name']}** (Tier {p['tier']})" for p in roster]) if roster else "*(Sin Pokémon)*"
    val = f"{p_list}\n-------------------\n💰 **Pts:** {points_spent} (Restantes: {points_left})\n🎲 **Reintentos:** {rerolls_left}"

    embed.add_field(name="Tu Equipo Actual", value=val, inline=False)
    return embed


def create_summary_embed(draft_state):
    """
    Generates a Paginated Summary (List of Embeds) to avoid Discord char limits.
    Sent to the parent channel periodically and at the end of the draft.
    """
    if not draft_state["rosters"]:
        return [discord.Embed(title="📊 Sin información", description="El Draft no ha iniciado aún.")]
    embeds = []
    unique_players = []
    seen = set()
    for p in draft_state['order']:
        if p.id not in seen:
            seen.add(p.id)
            unique_players.append(p)

    CHUNK_SIZE = 6
    for i in range(0, len(unique_players), CHUNK_SIZE):
        chunk = unique_players[i:i + CHUNK_SIZE]
        page_num = (i // CHUNK_SIZE) + 1
        total_pages = (len(unique_players) + CHUNK_SIZE - 1) // CHUNK_SIZE
        embed = discord.Embed(title=f"📊 Resumen del Draft ({page_num}/{total_pages})", color=0x3498db)

        for player in chunk:
            roster = draft_state["rosters"].get(player.id, [])
            points_spent = draft_state["points"].get(player.id, 0)
            points_left = config.MAX_POINTS - points_spent
            rerolls_left = config.MAX_REROLLS - draft_state["rerolls"].get(player.id, 0)

            p_list = "\n".join([f"• **{p['name']}** ({p['tier']})" for p in roster]) if roster else "*(Sin Pokémon)*"
            val = f"{p_list}\n-------------------\n💰 **Pts:** {points_spent} (Restantes: {points_left})\n🎲 **Reintentos:** {rerolls_left}"
            if len(val) > 1020: val = val[:1015] + "..."
            embed.add_field(name=f"👤 {player.display_name}", value=val, inline=True)

        embeds.append(embed)
    return embeds


# ==========================================
# 🖼️ IMAGE PROCESSING (PILLOW)
# ==========================================

async def fetch_image(session, url):
    """Asynchronously downloads a sprite image and returns a Pillow Image object."""
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.error(f"Failed to fetch image {url}: {e}")
    return None


async def create_roster_image_file(roster, filename="roster.png"):
    """
    Downloads up to 10 sprites concurrently and stitches them into a 5x2 grid.
    Returns a discord.File object ready to be attached to a Discord message.
    """
    urls = [p['sprite'] for p in roster if p.get('sprite') and p['sprite'].startswith("http")]
    if not urls:
        return None

    # Concurrently fetch all images to speed up generation
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_image(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    images = [img for img in results if img]
    if not images:
        return None

    # Calculate grid dimensions (5 columns, 2 rows max)
    box_size = 100
    cols = 5
    rows = (len(images) + cols - 1) // cols
    bg_width = cols * box_size
    bg_height = rows * box_size

    # Create transparent background
    grid = Image.new("RGBA", (bg_width, bg_height), (255, 255, 255, 0))

    # Paste images into the grid
    for idx, img in enumerate(images):
        img.thumbnail((box_size, box_size))
        x = (idx % cols) * box_size + (box_size - img.width) // 2
        y = (idx // cols) * box_size + (box_size - img.height) // 2
        grid.paste(img, (x, y), img)

    # Save to a memory buffer instead of writing to disk
    buffer = io.BytesIO()
    grid.save(buffer, format="PNG")
    buffer.seek(0)

    return discord.File(fp=buffer, filename=filename)


# ==========================================
# 🔘 INTERACTIVE BUTTON VIEWS
# ==========================================

class DummyCheckView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None

    async def check_staff(self, interaction):
        if not discord.utils.get(interaction.user.roles, name=config.STAFF_ROLE_NAME):
            await interaction.response.send_message(MSG["err_staff"], ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Si, agregar Dummies", style=discord.ButtonStyle.success, emoji="🤖")
    async def confirm(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = True
        logger.debug(f"{interaction.user} selected YES to dummies.")

        # --- SHOCK ABSORBER ---
        # Prevents 404 Not Found error if the token expired or button was double-clicked
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="✅ **Dummies habilitados**", view=None, embed=None)
        except discord.errors.NotFound:
            logger.debug("Interaction token expired. Ignoring safely.")

        self.stop()

    @discord.ui.button(label="No, sin Dummies", style=discord.ButtonStyle.secondary, emoji="👤")
    async def cancel(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = False
        logger.debug(f"{interaction.user} selected NO to dummies.")

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="❌ **Dummies Deshabilitados**", view=None, embed=None)
        except discord.errors.NotFound:
            logger.debug("Interaction token expired. Ignoring safely.")

        self.stop()


class ModeSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None

    async def check_staff(self, interaction):
        if not discord.utils.get(interaction.user.roles, name=config.STAFF_ROLE_NAME):
            await interaction.response.send_message(MSG["err_staff"], ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Interactivo", style=discord.ButtonStyle.primary, emoji="🔴")
    async def mode_interactive(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 0
        logger.debug(f"{interaction.user} selected Interactive Mode.")

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="✅ **Interactivo**", view=None, embed=None)
        except discord.errors.NotFound:
            logger.debug("Interaction token expired. Ignoring safely.")

        self.stop()

    @discord.ui.button(label="Auto aceptar", style=discord.ButtonStyle.success, emoji="🟢")
    async def mode_public(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 1
        logger.debug(f"{interaction.user} selected Auto Public Mode.")

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="✅ **Auto aceptar**", view=None, embed=None)
        except discord.errors.NotFound:
            logger.debug("Interaction token expired. Ignoring safely.")

        self.stop()

    @discord.ui.button(label="Simulación rápida", style=discord.ButtonStyle.secondary, emoji="🤫")
    async def mode_silent(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 2
        logger.debug(f"{interaction.user} selected Auto Silent Mode.")

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="✅ **Simulación rápida**", view=None, embed=None)
        except discord.errors.NotFound:
            logger.debug("Interaction token expired. Ignoring safely.")

        self.stop()


class RollView(discord.ui.View):
    def __init__(self, coach_user):
        super().__init__(timeout=config.ROLL_TIMEOUT)
        self.coach = coach_user
        self.clicked = False

    async def disable_all(self, interaction):
        for child in self.children:
            child.disabled = True

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
        except discord.errors.NotFound:
            # Handles errors if the 5-second GIF delay causes the token to expire
            logger.debug("Interaction token expired or double-clicked. Ignoring safely.")
        except Exception as e:
            logger.error(f"Unexpected error in disable_all: {e}")

    @discord.ui.button(label="🎰 Jala la palanca", style=discord.ButtonStyle.primary, emoji="🎲")
    async def roll_button(self, interaction, button):
        if interaction.user.id != self.coach.id and not discord.utils.get(interaction.user.roles,
                                                                          name=config.STAFF_ROLE_NAME):
            return await interaction.response.send_message("🚫 No es tu turno.", ephemeral=True)
        self.clicked = True
        logger.debug(f"{interaction.user.display_name} initiated the roll.")
        await self.disable_all(interaction)
        self.stop()


class DraftView(discord.ui.View):
    def __init__(self, coach_user, show_summary=True):
        super().__init__(timeout=config.DECISION_TIMEOUT)
        self.coach = coach_user
        self.value = None
        self.clicked_by = None

        # Dynamically remove the Summary button if it has already been used this turn
        if not show_summary:
            for child in self.children:
                if getattr(child, "label", "") == "📊 Resumen":
                    self.remove_item(child)
                    break

    async def check_permissions(self, interaction):
        if interaction.user.id != self.coach.id and not discord.utils.get(interaction.user.roles,
                                                                          name=config.STAFF_ROLE_NAME):
            await interaction.response.send_message("🚫 Permission denied.", ephemeral=True)
            return False
        return True

    async def disable_all(self, interaction):
        for child in self.children:
            child.disabled = True

        try:
            # Check if Discord already processed this interaction (prevents double-click errors)
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
        except discord.errors.NotFound:
            # If the token expired due to lag or timing sequences, ignore it safely
            logger.debug("Interaction token expired or double-clicked. Ignoring safely.")
        except Exception as e:
            logger.error(f"Unexpected error in disable_all: {e}")

    @discord.ui.button(label="✅ Aceptar", style=discord.ButtonStyle.success)
    async def keep(self, interaction, button):
        if not await self.check_permissions(interaction): return
        self.value = "KEEP"
        self.clicked_by = interaction.user
        logger.debug(f"{interaction.user.display_name} chose to KEEP.")
        await self.disable_all(interaction)
        self.stop()

    @discord.ui.button(label="⟳ Reintentar", style=discord.ButtonStyle.danger)
    async def reroll(self, interaction, button):
        if not await self.check_permissions(interaction): return
        self.value = "REROLL"
        self.clicked_by = interaction.user
        logger.debug(f"{interaction.user.display_name} chose to REROLL.")
        await self.disable_all(interaction)
        self.stop()

    @discord.ui.button(label="📊 Resumen", style=discord.ButtonStyle.secondary)
    async def summary_btn(self, interaction, button):
        if not await self.check_permissions(interaction): return
        self.value = "SUMMARY"
        self.clicked_by = interaction.user
        logger.debug(f"{interaction.user.display_name} requested a mid-turn SUMMARY.")
        await self.disable_all(interaction)
        self.stop()