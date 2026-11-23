import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import health
from cogs.applications import Applications
from cogs.message import Message
from cogs.setup import Setup
from cogs.welcome import Welcome
from config import GUILD_ID
from database import Database
from utils import notice

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bloom")


class BloomBot(commands.Bot):
    def __init__(self, mongodb_uri: str):
        intents = discord.Intents.default()
        intents.members = True  # needed to welcome new members (turn on "Server Members Intent" in the Developer Portal)
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.database = Database(mongodb_uri)
        self.health_runner = None
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        await self.database.ping()
        await self.add_cog(Setup(self))
        await self.add_cog(Welcome(self))
        await self.add_cog(Message(self))
        await self.add_cog(Applications(self))

        # Start the web page first, so Render sees the open port straight away.
        self.health_runner = await health.start(self)

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s commands to development guild %s", len(synced), GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

        await self.get_cog("Applications").register_persistent_views()

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            view = notice("bad", "You need the **Manage Server** permission to use that.", "Not allowed")
        else:
            log.exception("Command failed", exc_info=error)
            view = notice("bad", "Something went wrong on my side. Please try again in a moment.", "Oops")
        if interaction.response.is_done():
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def close(self):
        if self.health_runner:
            await self.health_runner.cleanup()
        await self.database.close()
        await super().close()


def main():
    token = os.getenv("DISCORD_TOKEN")
    mongodb_uri = os.getenv("MONGODB_URI")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env or Render environment.")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI is missing. Add it to your .env or Render environment.")
    BloomBot(mongodb_uri).run(token, log_handler=None)


if __name__ == "__main__":
    main()
