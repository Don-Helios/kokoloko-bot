import discord
import config
import logic


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
        title=f"🎲 Pokémon #{pick_num} • {player.display_name}",
        description=f"¡Toca el botón para girar!\n⏳ **Auto-roll** <t:{expiry_time}:R>\n\n**Probabilidades:**\n{odds_grid_str}",
        color=0x2ecc71
    )


def create_fake_embed(player, name, tier):
    """
    The 'Fake Out' Easter Egg Embed.
    Uses Gold Color (0xFFD700) to mimic a high-value/Critical hit.
    """
    embed = discord.Embed(
        title=f"✨ ¡GOLPE CRÍTICO! • {player.display_name}",
        description=f"Has sacado el tazo dorado✨:\n# **{name}**\n**(Tier {tier})**",
        color=0xFFD700
    )
   # embed.set_footer(text="Espera... algo raro se aproxima...")
    return embed


def create_summary_embed(draft_state):
    """
    Generates a Paginated Summary (List of Embeds) to avoid Discord char limits.
    """
    if not draft_state["rosters"]:
        return [discord.Embed(title="📊 Sin información", description="El Draft no ha iniciado.")]
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
        embed = discord.Embed(title=f"📊 Resumen del Draft (Página {page_num}/{total_pages})", color=0x3498db)
        for player in chunk:
            roster = draft_state["rosters"].get(player.id, [])
            points_spent = draft_state["points"].get(player.id, 0)
            points_left = config.MAX_POINTS - points_spent
            rerolls_left = config.MAX_REROLLS - draft_state["rerolls"].get(player.id, 0)

            p_list = "\n".join([f"• **{p['name']}** ({p['tier']})" for p in roster]) if roster else "*(No tiene Pokémon aún)*"
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
            await interaction.response.send_message("🚫 Solo para Draft Staff.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Si, agregar dummies", style=discord.ButtonStyle.success, emoji="🤖")
    async def confirm(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = True
        await interaction.response.edit_message(content="✅ **Dummies Habilitados**", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="No, solo personas", style=discord.ButtonStyle.secondary, emoji="👤")
    async def cancel(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = False
        await interaction.response.edit_message(content="❌ **Dummies Deshabilitados**", view=None, embed=None)
        self.stop()


class ModeSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None

    async def check_staff(self, interaction):
        if not discord.utils.get(interaction.user.roles, name=config.STAFF_ROLE_NAME):
            await interaction.response.send_message("🚫 Staff only.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Interactivo", style=discord.ButtonStyle.primary, emoji="🔴")
    async def mode_interactive(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 0
        await interaction.response.edit_message(content="✅ **Interactivo**", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="Auto Aceptar", style=discord.ButtonStyle.success, emoji="🟢")
    async def mode_public(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 1
        await interaction.response.edit_message(content="✅ **Auto Aceptar**", view=None, embed=None)
        self.stop()

    @discord.ui.button(label="Simulación rápida", style=discord.ButtonStyle.secondary, emoji="🤫")
    async def mode_silent(self, interaction, button):
        if not await self.check_staff(interaction): return
        self.value = 2
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

    @discord.ui.button(label="🎲 TIRAR DADO", style=discord.ButtonStyle.primary, emoji="🎲")
    async def roll_button(self, interaction, button):
        if interaction.user.id != self.coach.id and not discord.utils.get(interaction.user.roles,
                                                                          name=config.STAFF_ROLE_NAME):
            return await interaction.response.send_message("🚫 No es tu turno.", ephemeral=True)
        self.clicked = True
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
        await self.disable_all(interaction)
        self.stop()

    @discord.ui.button(label="🎲 Reintentar", style=discord.ButtonStyle.danger)
    async def reroll(self, interaction, button):
        if not await self.check_permissions(interaction): return
        self.value = "REROLL"
        self.clicked_by = interaction.user
        await self.disable_all(interaction)
        self.stop()