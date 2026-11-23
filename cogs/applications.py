import discord
from discord import app_commands
from discord.ext import commands

from config import APPLICATION_REVIEW_KEYS, ROLE_LABELS
from utils import bloom_embed, has_any_bloom_role

class StaffApplicationModal(discord.ui.Modal, title="Bloom Staff Application"):
    position = discord.ui.TextInput(
        label="Staff position",
        placeholder="Which role are you applying for?",
        max_length=80,
    )
    availability = discord.ui.TextInput(
        label="Availability",
        placeholder="When are you usually active?",
        max_length=150,
    )
    experience = discord.ui.TextInput(
        label="Experience",
        placeholder="Tell us about any relevant experience",
        style=discord.TextStyle.paragraph,
        max_length=700,
    )
    why = discord.ui.TextInput(
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
                "Applications are not configured yet. Please contact a server administrator.",
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
        application_id = str(result.inserted_id)

        embed = bloom_embed("New staff application 🌷", f"Applicant: {interaction.user.mention}\nApplication ID: `{application_id}`")
        embed.add_field(name="Position", value=str(self.position), inline=True)
        embed.add_field(name="Availability", value=str(self.availability), inline=True)
        embed.add_field(name="Experience", value=str(self.experience), inline=False)
        embed.add_field(name="Why Bloom?", value=str(self.why), inline=False)
        embed.set_footer(text=f"Applicant ID: {interaction.user.id} • Pending review")

        view = ApplicationReviewView(self.bot, application_id)
        message = await review_channel.send(embed=embed, view=view)
        await self.bot.database.applications.update_one(
            {"_id": result.inserted_id},
            {"$set": {"review_message_id": message.id, "review_channel_id": review_channel.id}},
        )
        await interaction.response.send_message(
            embed=bloom_embed(
                "Application submitted 🌸",
                "Your application has been sent to the Bloom leadership team for review. Please avoid sharing private personal information in applications.",
            ),
            ephemeral=True,
        )

class ApplicationPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Apply for staff", style=discord.ButtonStyle.primary, emoji="🌸", custom_id="bloom:apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StaffApplicationModal(self.bot))

class ApplicationReviewView(discord.ui.View):
    def __init__(self, bot: commands.Bot, application_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.application_id = application_id
        self.approve.custom_id = f"bloom:approve:{application_id}"
        self.reject.custom_id = f"bloom:reject:{application_id}"

    async def authorized(self, interaction: discord.Interaction) -> bool:
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        allowed = await has_any_bloom_role(interaction.user, settings, APPLICATION_REVIEW_KEYS)
        if not allowed and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only Bloom leadership can review applications.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="🌷")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.authorized(interaction):
            return
        await self.finish(interaction, "approved")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="✖")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.authorized(interaction):
            return
        await self.finish(interaction, "rejected")

    async def finish(self, interaction: discord.Interaction, status: str):
        from bson import ObjectId
        application = await self.bot.database.applications.find_one({"_id": ObjectId(self.application_id)})
        if not application or application.get("status") != "pending":
            return await interaction.response.send_message("This application has already been processed or no longer exists.", ephemeral=True)

        await self.bot.database.applications.update_one(
            {"_id": ObjectId(self.application_id)},
            {"$set": {
                "status": status,
                "reviewed_by": interaction.user.id,
                "reviewed_at": discord.utils.utcnow(),
            }},
        )
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green() if status == "approved" else discord.Color.red()
        embed.add_field(name="Decision", value=f"{status.title()} by {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def register_persistent_views(self):
        self.bot.add_view(ApplicationPanelView(self.bot))
        # Reconstruct review views for all pending applications.
        async def register_pending():
            cursor = self.bot.database.applications.find({"status": "pending"})
            async for item in cursor:
                self.bot.add_view(ApplicationReviewView(self.bot, str(item["_id"])))
        self.bot.loop.create_task(register_pending())

    @app_commands.command(name="bloom_application_panel", description="Post the staff application panel in this channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bloom_application_panel(self, interaction: discord.Interaction):
        embed = bloom_embed(
            "Join the Bloom staff team 🌸",
            "Interested in helping Bloom grow? Press the button below to submit a staff application. The leadership team will review it privately.",
        )
        await interaction.channel.send(embed=embed, view=ApplicationPanelView(self.bot))
        await interaction.response.send_message("Staff application panel posted.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Applications(bot))
