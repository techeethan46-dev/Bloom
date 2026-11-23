from pymongo import AsyncMongoClient
from config import DATABASE_NAME

class Database:
    def __init__(self, uri: str):
        self.client = AsyncMongoClient(uri)
        self.db = self.client[DATABASE_NAME]

    async def ping(self):
        await self.client.admin.command("ping")

    async def close(self):
        await self.client.close()

    @property
    def guilds(self):
        return self.db["guild_settings"]

    @property
    def applications(self):
        return self.db["staff_applications"]

    @property
    def composed(self):
        return self.db["composed_messages"]

    async def get_guild_settings(self, guild_id: int) -> dict:
        return await self.guilds.find_one({"_id": guild_id}) or {}

    async def update_guild_settings(self, guild_id: int, update: dict):
        await self.guilds.update_one(
            {"_id": guild_id},
            {"$set": update},
            upsert=True,
        )
