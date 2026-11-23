import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import Database
from config import GUILD_ID
from cogs.admin import Admin
from cogs.welcome import Welcome
from cogs.applications import Applications

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bloom")

TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env or Render environment.")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing. Add it to your .env or Render environment.")

intents = discord.Intents.default()
intents.members = True

class BloomBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.database = Database(MONGODB_URI)

    async def setup_hook(self):
        await self.database.ping()
        await self.add_cog(Admin(self))
        await self.add_cog(Welcome(self))
        await self.add_cog(Applications(self))

        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %s commands to development guild %s", len(synced), GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %s global commands", len(synced))

        # Re-register persistent application review views after restarts.
        self.get_cog("Applications").register_persistent_views()

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_member_join(self, member: discord.Member):
        welcome = self.get_cog("Welcome")
        await welcome.send_welcome(member)

    async def close(self):
        await self.database.close()
        await super().close()
        
from aiohttp import web
import asyncio

async def health(request):
    return web.json_response({
        "status": "online",
        "bot": str(bot.user) if bot.user else "starting"
    })

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        int(os.getenv("PORT", 10000))
    )
    await site.start()

    return runner
    
bot = BloomBot()
bot.run(TOKEN, log_handler=None)
