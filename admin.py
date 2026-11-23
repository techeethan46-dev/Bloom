import discord
from discord import app_commands
from discord.ext import commands

from config import ROLE_KEYS, ROLE_LABELS
from utils import bloom_embed, role_mentions

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def admin_only():
        return app_commands.checks.has_permissions(manage_guild=True)

    @app_commands.command(name="bloom_setup", description="Initialize Bloom bot settings for this server.")
    @admin_only()
    async def bloom_setup(self, interaction: discord.Interaction):
        await self.bot.database.update_guild_settings(
            interaction.guild_id,
            {"initialized": True},
        )
        embed = bloom_embed(
            "Bloom is ready to be configured 🌸",
            "Next, configure the welcome/review channels and map your server roles.",
        )
        embed.add_field(
            name="Next steps",
            value="`/bloom_config` — set channels\n`/bloom_roles` — map staff roles\n`/bloom_application_panel` — publish applications",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="bloom_config", description="Set Bloom's welcome and staff application review channels.")
    @admin_only()
    @app_commands.describe(welcome_channel="Where new-member welcomes are sent", review_channel="Private channel for staff application reviews")
    async def bloom_config(
        self,
        interaction: discord.Interaction,
        welcome_channel: discord.TextChannel,
        review_channel: discord.TextChannel,
    ):
        await self.bot.database.update_guild_settings(
            interaction.guild_id,
            {
                "welcome_channel_id": welcome_channel.id,
                "review_channel_id": review_channel.id,
            },
        )
        await interaction.response.send_message(
            embed=bloom_embed(
                "Configuration saved 🌷",
                f"Welcome channel: {welcome_channel.mention}\nApplication review channel: {review_channel.mention}",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="bloom_roles", description="Map an existing Discord role to a Bloom staff role.")
    @admin_only()
    @app_commands.describe(role_key="Bloom role type", role="The existing Discord role to map")
    @app_commands.choices(role_key=[
        app_commands.Choice(name=ROLE_LABELS[key], value=key) for key in ROLE_KEYS
    ])
    async def bloom_roles(
        self,
        interaction: discord.Interaction,
        role_key: app_commands.Choice[str],
        role: discord.Role,
    ):
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "I cannot manage or assign that role because it is above or equal to my highest role. Move my bot role above it first.",
                ephemeral=True,
            )
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        roles = settings.get("roles", {})
        roles[role_key.value] = role.id
        await self.bot.database.update_guild_settings(
            interaction.guild_id,
            {"roles": roles},
        )
        await interaction.response.send_message(
            embed=bloom_embed(
                "Role mapping updated 🌸",
                f"**{ROLE_LABELS[role_key.value]}** is now mapped to {role.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="bloom_role_list", description="Show Bloom's configured role mappings.")
    @admin_only()
    async def bloom_role_list(self, interaction: discord.Interaction):
        settings = await self.bot.database.get_guild_settings(interaction.guild_id)
        await interaction.response.send_message(
            embed=bloom_embed("Bloom role directory", role_mentions(settings)),
            ephemeral=True,
        )

    @app_commands.command(name="bloom_welcome_test", description="Preview the welcome message.")
    @admin_only()
    async def bloom_welcome_test(self, interaction: discord.Interaction):
        embed = bloom_embed(
            "Welcome to Bloom! 🌸",
            f"We're happy to have you here, {interaction.user.mention}!\n\nPlease take a moment to read the server rules and get familiar with our community.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
