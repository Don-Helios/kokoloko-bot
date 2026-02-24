import discord
import config
import logic
import logging

logger = logging.getLogger("views")

# ==========================================
# 💬 CENTRALIZED TEXT DICTIONARY (TRANSLATE HERE)
# ==========================================
# All plain text messages sent by the bot are stored here.
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
    "announce_parent": "📢 ¡El Kokoloko Draft acaba de iniciar! Entra en el hilo {thread_mention} para ver la selección {ping_text}",
    "draft_started": "🏆 **¡Draft iniciado!**\nOrden: {names}",

    # --- Engine.py (Game Flow & Turns) ---
    "draft_complete": "🏁 **¡Draft Finalizado!**",
    "end_of_round": "🔁 **¡Fin de la ronda!** Orden para la ronda {round_num}...",
    "err_critical_pool": "⚠️ **ERROR:** No hay Pokémon válidos.",
    "roll_timeout": "⏰ **Tiempo agotado** - Lanzamiento automático...",
    "rolling": "**Rolling...** 🎰\n\n**Probabilidades:**\n{odds}",
    "fakeout_spoiler": "||✨ ¡Golpe crítico! Has sacado el tazo dorado✨: **{name}** (Tier {tier})||\n\n*...Espera... algo se aproxima...*",
    "fakeout_hariyama": "✋ **Delibird usó Sorpresa!**",
    "fakeout_reveal": "😅 {mention}, tu **verdadero Pokémon** ES...",
    "action_reroll": "🔄 **{clicker}** utilizó un reintento! (le quedan {left}).",
    "action_keep": "✅ **{clicker}** aceptó **{name}**.",
    "action_timeout": "⏰ Tiempo agotado: se aceptó automáticamente **{name}**.",
    "err_api_fatal": "🚨 **FATAL:** Discord API is continuously rejecting our connection. The draft has paused.",
    "err_bot_crash": "🚨 A bot error occurred. The draft loop has paused. Check `kokoloko.log` for details."
}

# ==========================================
# 🎨 FORMATTERS & UTILS
# ==========================================

def format_odds_grid(odds_data):
    """Formats the tier probabilities into a clean text grid."""
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
    """Standard pre-roll embed."""
    return discord.Embed(
        title=f"🃏 Pokémon #{pick_num} • {player.display_name}",
        description=f"¡Toca el botón para girar!\n⏳ **Lanzamiento automático en** <t:{expiry_time}:R>\n\n**Probabilidades:**\n{odds_grid_str}",
        color=0x2ecc71
    )

def create_fake_embed(player, name, tier):
    """
    The 'Fake Out' Easter Egg Embed.
    Uses Gold Color (0xFFD700) to mimic a high-value/Critical hit.
    """
    embed = discord.Embed(
        title=f"✨ ¡GOLPE CRÍTICO! • {player.display_name}",
        description=f"has sacado el tazo dorado✨:\n# **{name}**\n**(Tier {tier})**",
        color=0xFFD700
    )
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

def create_auto_accept_embed(player, pick_num, name, tier, mode, pts_left):
    """Embed shown when a Pokémon is auto-accepted (Mode 1 or 0 rerolls)."""
    ft_text = "⚡ Aceptación automática" if mode == 1 else "🔒 Ya no te quedan reintentos"
    embed = discord.Embed(title=f"Pokémon #{pick_num} • {player.display_name}", color=0x95a5a6)
    embed.add_field(name="Aceptado Automáticamente", value=f"**{name}** (Tier {tier})")
    embed.set_footer(text=f"{ft_text} | Puntos: {pts_left} pts restantes")
    return embed

def create_decision_embed(player, pick_num, name, tier, pts_left, curr_left, round_num, expiry_dec):
    """Embed shown showing the rolled Pokémon, asking Keep/Reroll."""
    embed = discord.Embed(
        title=f"Pokémon #{pick_num} • {player.display_name}",
        description=f"⏳ **Decide en** <t:{expiry_dec}:R>\n(Ronda {round_num})",
        color=0xF1C40F
    )
    embed.add_field(name="Pokémon", value=f"**{name}**", inline=True)
    embed.add_field(name="Tier", value=f"{tier}", inline=True)
    embed.add_field(name="Puntos", value=f"{pts_left} pts restantes", inline=False)
    embed.set_footer(text=f"Reintentos restantes: {curr_left}/{config.MAX_REROLLS}")
    return embed

def create_summary_embed(draft_state):
    """
    Generates a Paginated Summary (List of Embeds) to avoid Discord char limits.
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
        await interaction.response.edit_message(content="✅ **Dummies habilitados**", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="No, sin Dummies", style=discord.ButtonStyle.secondary, emoji="👤")
    async def cancel(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = False
        logger.debug(f"{interaction.user} selected NO to dummies.")
        await interaction.response.edit_message(content="❌ **Dummies Deshabilitados**", view=None, embed=None)
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
        await interaction.response.edit_message(content="✅ **Interactivo**", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="Auto aceptar", style=discord.ButtonStyle.success, emoji="🟢")
    async def mode_public(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 1
        logger.debug(f"{interaction.user} selected Auto Public Mode.")
        await interaction.response.edit_message(content="✅ **Auto aceptar*", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="Simulación rápida", style=discord.ButtonStyle.secondary, emoji="🤫")
    async def mode_silent(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 2
        logger.debug(f"{interaction.user} selected Auto Silent Mode.")
        await interaction.response.edit_message(content="✅ **Simulación rápida**", view=None, embed=None)
        self.stop()


class RollView(discord.ui.View):
    def __init__(self, coach_user):
        super().__init__(timeout=config.ROLL_TIMEOUT)
        self.coach = coach_user
        self.clicked = False

    async def disable_all(self, interaction):
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

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
    def __init__(self, coach_user):
        super().__init__(timeout=config.DECISION_TIMEOUT)
        self.coach = coach_user
        self.value = None
        self.clicked_by = None

    async def check_permissions(self, interaction):
        if interaction.user.id != self.coach.id and not discord.utils.get(interaction.user.roles,
                                                                          name=config.STAFF_ROLE_NAME):
            await interaction.response.send_message("🚫 Permission denied.", ephemeral=True)
            return False
        return True

    async def disable_all(self, interaction):
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

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