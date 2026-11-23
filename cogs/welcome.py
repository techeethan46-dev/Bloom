import discord
from discord.ext import commands
from utils import bloom_embed

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_welcome(self, member: discord.Member):
        settings = await self.bot.database.get_guild_settings(member.guild.id)
        channel_id = settings.get("welcome_channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return

        embed = bloom_embed(
            "A new flower has joined Bloom 🌸",
            f"Welcome {member.mention}!\n\nWe're glad you're here. Please read the rules and make yourself at home.",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member number", value=str(member.guild.member_count or "—"))
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

async def setup(bot):
    await bot.add_cog(Welcome(bot))
