"""A tiny web page so Render stays happy and UptimeRobot can ping the bot."""
import os

from aiohttp import web


def make_app(bot) -> web.Application:
    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "online", "bot": str(bot.user) if bot.user else "starting"})

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    return app


async def start(bot) -> web.AppRunner:
    runner = web.AppRunner(make_app(bot))
    await runner.setup()
    # Render gives the port in the PORT variable.
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()
    return runner
