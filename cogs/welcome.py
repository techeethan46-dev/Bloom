import discord
from discord import ui
from discord.ext import commands

from utils import card, card_view, text


def welcome_view(member: discord.Member) -> ui.LayoutView:
    """The welcome card for a new member."""
    count = member.guild.member_count
    return card_view(card(
        ui.Section(
            "## 🌸 A new flower has joined Bloom!",
            f"Welcome {member.mention}! We're so glad you're here.",
            "Please read the rules and make yourself at home.",
            accessory=ui.Thumbnail(member.display_avatar.url),
        ),
        text(f"-# You're member #{count:,}" if count else None),
    ), timeout=None)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.send_welcome(member)

    async def send_welcome(self, member: discord.Member):
        settings = await self.bot.database.get_guild_settings(member.guild.id)
        channel_id = settings.get("welcome_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            # The welcome shows the @mention but doesn't ping them.
            await channel.send(view=welcome_view(member), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass  # no permission to post there: skip quietly


async def setup(bot):
    await bot.add_cog(Welcome(bot))
