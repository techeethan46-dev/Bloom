"""/setup: one step-by-step screen for everything Bloom needs (channels and staff roles)."""
from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands

from config import PINK, ROLE_KEYS, ROLE_LABELS
from utils import card, card_view, divider, notice, text

from cogs.applications import ApplicationPanelView
from cogs.welcome import welcome_view

_ROLE_DESCRIPTIONS = {
    "founder": "Can review staff applications.",
    "co_owner": "Can review staff applications.",
    "vice_president": "Can review staff applications.",
}

# Each step saves as soon as you pick something, then moves on to the next one.
STEPS: list[dict] = [
    {"key": "welcome_channel_id", "kind": "channel", "emoji": "👋", "title": "Welcome channel",
     "desc": "New members get a welcome card here."},
    {"key": "review_channel_id", "kind": "channel", "emoji": "📋", "title": "Application review channel",
     "desc": "Staff applications arrive here with **Approve** and **Reject** buttons. Make it private."},
    *[
        {"key": key, "kind": "role", "emoji": "🎀", "title": f"{ROLE_LABELS[key]} role",
         "desc": _ROLE_DESCRIPTIONS.get(key, f"Your server's **{ROLE_LABELS[key]}** rank.")}
        for key in ROLE_KEYS
    ],
]
OVERVIEW = len(STEPS)


def current_id(settings: dict, step: dict) -> int | None:
    value = settings.get("roles", {}).get(step["key"]) if step["kind"] == "role" else settings.get(step["key"])
    return int(value) if value else None


def show(settings: dict, step: dict) -> str | None:
    value = current_id(settings, step)
    if not value:
        return None
    return f"<@&{value}>" if step["kind"] == "role" else f"<#{value}>"


class SetupView(ui.LayoutView):
    """One screen of the wizard. Every button and pick builds the next screen."""

    def __init__(self, cog: "Setup", guild: discord.Guild, settings: dict, step: int, error: str | None = None):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild = guild
        self.settings = settings
        self.step = step
        self.add_item(self._overview(error) if step >= OVERVIEW else self._step(error))

    # ------------------------------------------------------------ one step
    def _step(self, error: str | None) -> ui.Container:
        st = STEPS[self.step]
        now = show(self.settings, st)
        children: list[ui.Item] = [
            text(f"## 🌸 Bloom setup · step {self.step + 1} of {len(STEPS)}",
                 f"### {st['emoji']} {st['title']}", st["desc"],
                 f"**Now:** {now}" if now else "**Now:** *not set*",
                 f"⚠️ {error}" if error else None),
            divider(),
        ]
        children.append(ui.ActionRow(self._picker(st)))
        children.append(ui.ActionRow(*self._nav(has_value=bool(now))))
        return card(*children)

    def _picker(self, st: dict) -> ui.Item:
        value = current_id(self.settings, st)
        if st["kind"] == "role":
            picker = ui.RoleSelect(placeholder=f"Select the {st['title'].lower()}…")
            if value and self.guild.get_role(value):
                picker.default_values = [discord.SelectDefaultValue(id=value, type=discord.SelectDefaultValueType.role)]
        else:
            picker = ui.ChannelSelect(
                placeholder=f"Select the {st['title'].lower()}…",
                channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            )
            if value and self.guild.get_channel(value):
                picker.default_values = [discord.SelectDefaultValue(id=value, type=discord.SelectDefaultValueType.channel)]
        picker.callback = self._picked
        return picker

    def _nav(self, has_value: bool) -> list[ui.Item]:
        back = ui.Button(label="Back", emoji="◀️", style=discord.ButtonStyle.secondary, disabled=self.step == 0)
        nxt = ui.Button(label="Next", emoji="▶️", style=discord.ButtonStyle.primary)
        clear = ui.Button(label="Clear", emoji="🧹", style=discord.ButtonStyle.secondary, disabled=not has_value)
        back.callback = lambda i: self._go(i, self.step - 1)
        nxt.callback = lambda i: self._go(i, self.step + 1)
        clear.callback = self._clear
        return [back, nxt, clear]

    # ------------------------------------------------------------ the summary page
    def _overview(self, error: str | None) -> ui.Container:
        lines = []
        for i, st in enumerate(STEPS):
            lines.append(f"{st['emoji']} **{st['title']}** · {show(self.settings, st) or '*not set*'}")
        done = sum(1 for st in STEPS if current_id(self.settings, st))
        jump = ui.Select(
            placeholder="Change something…",
            options=[discord.SelectOption(label=st["title"], value=str(i), emoji=st["emoji"]) for i, st in enumerate(STEPS)],
        )
        jump.callback = self._jump
        panel = ui.Button(label="Post application panel", emoji="🌸", style=discord.ButtonStyle.success)
        preview = ui.Button(label="Preview welcome", emoji="👋", style=discord.ButtonStyle.secondary)
        panel.callback = self._post_panel
        preview.callback = self._preview
        return card(
            text("## 🌸 Bloom setup", f"**{done} of {len(STEPS)}** done",
                 f"⚠️ {error}" if error else None),
            divider(),
            text(*lines),
            divider(),
            ui.ActionRow(jump),
            ui.ActionRow(panel, preview),
        )

    # ------------------------------------------------------------ what the buttons do
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(view=notice("bad", "You need the **Manage Server** permission to change Bloom's setup."), ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction, step: int, error: str | None = None) -> None:
        settings = await self.cog.bot.database.get_guild_settings(self.guild.id)
        await interaction.response.edit_message(view=SetupView(self.cog, self.guild, settings, step, error))

    async def _go(self, interaction: discord.Interaction, step: int) -> None:
        await self._show(interaction, max(0, min(step, OVERVIEW)))

    async def _jump(self, interaction: discord.Interaction) -> None:
        await self._show(interaction, int(interaction.data["values"][0]))

    async def _picked(self, interaction: discord.Interaction) -> None:
        picked = interaction.data["values"][0]
        st = STEPS[self.step]
        db = self.cog.bot.database
        if st["kind"] == "role":
            roles = dict(self.settings.get("roles", {}))
            roles[st["key"]] = int(picked)
            await db.update_guild_settings(self.guild.id, {"roles": roles})
        else:
            await db.update_guild_settings(self.guild.id, {st["key"]: int(picked)})
        await self._show(interaction, self.step + 1)

    async def _clear(self, interaction: discord.Interaction) -> None:
        st = STEPS[self.step]
        db = self.cog.bot.database
        if st["kind"] == "role":
            roles = dict(self.settings.get("roles", {}))
            roles.pop(st["key"], None)
            await db.update_guild_settings(self.guild.id, {"roles": roles})
        else:
            await db.update_guild_settings(self.guild.id, {st["key"]: None})
        await self._show(interaction, self.step)

    async def _post_panel(self, interaction: discord.Interaction) -> None:
        if not current_id(self.settings, STEPS[1]):
            return await self._show(interaction, OVERVIEW, "Set the **application review channel** first, or applications have nowhere to go.")
        try:
            await interaction.channel.send(view=ApplicationPanelView(self.cog.bot))
        except discord.Forbidden:
            return await interaction.response.send_message(
                view=notice("bad", f"I can't post in {interaction.channel.mention}. Give me access to it, or run `/setup` in another channel.", "Couldn't post"),
                ephemeral=True,
            )
        await interaction.response.send_message(view=notice("ok", f"The staff application panel is now in {interaction.channel.mention}.", "Panel posted"), ephemeral=True)

    async def _preview(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(view=welcome_view(interaction.user), ephemeral=True)


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Set up Bloom for this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        configured = any(k in settings for k in ("welcome_channel_id", "review_channel_id", "roles"))
        await interaction.response.send_message(
            view=SetupView(self, interaction.guild, settings, OVERVIEW if configured else 0),
            ephemeral=True,
        )


async def setup(bot):  # discord.py extension entry point
    await bot.add_cog(Setup(bot))
