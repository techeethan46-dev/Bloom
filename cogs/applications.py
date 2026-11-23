from __future__ import annotations

import discord
from bson import ObjectId
from discord import ui
from discord.ext import commands
from pymongo import ReturnDocument

from config import APPLICATION_REVIEW_KEYS, GREEN, PINK, ROSE
from utils import card, card_view, divider, has_any_bloom_role, notice, text


class StaffApplicationModal(ui.Modal, title="Bloom Staff Application"):
    position = ui.TextInput(
        label="Staff position",
        placeholder="Which role are you applying for?",
        max_length=80,
    )
    availability = ui.TextInput(
        label="Availability",
        placeholder="When are you usually active?",
        max_length=150,
    )
    experience = ui.TextInput(
        label="Experience",
        placeholder="Tell us about any relevant experience",
        style=discord.TextStyle.paragraph,
        max_length=700,
    )
    why = ui.TextInput(
        label="Why do you want to join the staff team?",
        style=discord.TextStyle.paragraph,
        max_length=700,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        review_channel_id = settings.get("review_channel_id")
        review_channel = interaction.guild.get_channel(int(review_channel_id)) if review_channel_id else None
        if not isinstance(review_channel, discord.TextChannel):
            return await interaction.response.send_message(
                view=notice("warn", "Applications aren't set up yet. Please tell a server administrator.", "Not ready yet"),
                ephemeral=True,
            )

        document = {
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "username": str(interaction.user),
            "position": str(self.position),
            "availability": str(self.availability),
            "experience": str(self.experience),
            "why": str(self.why),
            "status": "pending",
            "created_at": discord.utils.utcnow(),
            "review_message_id": None,
        }
        result = await self.bot.database.applications.insert_one(document)
        document["_id"] = result.inserted_id

        try:
            message = await review_channel.send(
                view=ApplicationReviewView(self.bot, document),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await self.bot.database.applications.delete_one({"_id": result.inserted_id})
            return await interaction.response.send_message(
                view=notice("bad", "I couldn't send your application to the review channel. Please tell a server administrator.", "Something went wrong"),
                ephemeral=True,
            )
        await self.bot.database.applications.update_one(
            {"_id": result.inserted_id},
            {"$set": {"review_message_id": message.id, "review_channel_id": review_channel.id}},
        )
        await interaction.response.send_message(
            view=notice(
                "ok",
                "Your application was sent to the Bloom leadership team for review. Please avoid sharing private personal information.",
                "Application submitted",
            ),
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        raise error


class ApplicationPanelView(ui.LayoutView):
    """The permanent "Apply" panel people press."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        apply_button = ui.Button(label="Apply for staff", emoji="🌸", style=discord.ButtonStyle.primary, custom_id="bloom:apply")
        apply_button.callback = self._apply
        self.add_item(card(
            text(
                "## 🌸 Join the Bloom staff team",
                "Want to help Bloom grow? Press the button below and tell us about yourself. The leadership team reads every application privately.",
            ),
            ui.ActionRow(apply_button),
            text("-# Takes about two minutes"),
        ))

    async def _apply(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StaffApplicationModal(self.bot))


def _application_card(doc: dict, application_id: str, buttons: list[ui.Button] | None = None) -> ui.Container:
    status = doc.get("status", "pending")
    color = {"pending": PINK, "approved": GREEN, "rejected": ROSE}[status]
    children: list[ui.Item] = [
        text("## 🌷 New staff application", f"**Applicant** · <@{doc['user_id']}>",
             f"-# Application `{application_id}`"),
        divider(),
        text(f"**Position** · {doc['position']}", f"**Availability** · {doc['availability']}"),
        text("**Experience**", doc["experience"]),
        text("**Why Bloom?**", doc["why"]),
    ]
    if status == "pending":
        children += [divider(), ui.ActionRow(*(buttons or []))]
        children.append(text(f"-# Applicant ID {doc['user_id']} · waiting for review"))
    else:
        verb = "Approved" if status == "approved" else "Rejected"
        icon = "🌷" if status == "approved" else "✖️"
        children += [divider(), text(f"{icon} **{verb}** by <@{doc.get('reviewed_by')}>",
                                    f"-# Applicant ID {doc['user_id']}")]
    return card(*children, color=color)


class ApplicationReviewView(ui.LayoutView):
    """The card in the review channel. Pending ones have Approve and Reject buttons and survive restarts."""

    def __init__(self, bot: commands.Bot, doc: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.doc = doc
        self.application_id = str(doc["_id"])
        buttons: list[ui.Button] = []
        if doc.get("status", "pending") == "pending":
            approve = ui.Button(label="Approve", emoji="🌷", style=discord.ButtonStyle.success, custom_id=f"bloom:approve:{self.application_id}")
            reject = ui.Button(label="Reject", emoji="✖️", style=discord.ButtonStyle.danger, custom_id=f"bloom:reject:{self.application_id}")
            approve.callback = lambda i: self._decide(i, "approved")
            reject.callback = lambda i: self._decide(i, "rejected")
            buttons = [approve, reject]
        self.add_item(_application_card(doc, self.application_id, buttons))

    async def _authorized(self, interaction: discord.Interaction) -> bool:
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        if has_any_bloom_role(interaction.user, settings, APPLICATION_REVIEW_KEYS) or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(view=notice("bad", "Only Bloom leadership can review applications.", "Leadership only"), ephemeral=True)
        return False

    async def _decide(self, interaction: discord.Interaction, status: str):
        if not await self._authorized(interaction):
            return
        # One atomic step, so two quick clicks can't both decide it.
        doc = await self.bot.database.applications.find_one_and_update(
            {"_id": ObjectId(self.application_id), "status": "pending"},
            {"$set": {"status": status, "reviewed_by": interaction.user.id, "reviewed_at": discord.utils.utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return await interaction.response.send_message(
                view=notice("warn", "This application was already decided, or it no longer exists.", "Already handled"), ephemeral=True)
        await interaction.response.edit_message(view=ApplicationReviewView(self.bot, doc))


class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def register_persistent_views(self):
        """After a restart, make the panel and every pending application's buttons work again."""
        self.bot.add_view(ApplicationPanelView(self.bot))
        async for doc in self.bot.database.applications.find({"status": "pending"}):
            self.bot.add_view(ApplicationReviewView(self.bot, doc))


async def setup(bot):
    await bot.add_cog(Applications(bot))
