"""Fakes for Discord and MongoDB, shared by the tests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from bson import ObjectId
from discord import ui


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- fakes

class FakeCollection:
    def __init__(self):
        self.docs = {}

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    async def insert_one(self, doc):
        oid = doc.get("_id", ObjectId())
        self.docs[oid] = {**doc, "_id": oid}
        return SimpleNamespace(inserted_id=oid)

    async def find_one(self, flt):
        return next((dict(d) for d in self.docs.values() if self._match(d, flt)), None)

    async def find_one_and_update(self, flt, update, return_document=None):
        for oid, d in self.docs.items():
            if self._match(d, flt):
                d.update(update["$set"])
                return dict(d)
        return None

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs.values():
            if self._match(d, flt):
                d.update(update["$set"])

    async def delete_one(self, flt):
        for oid, d in list(self.docs.items()):
            if self._match(d, flt):
                del self.docs[oid]
                return

    def find(self, flt):
        return FakeCursor([dict(d) for d in self.docs.values() if self._match(d, flt)])


class FakeCursor:
    """Like MongoDB's cursor: .sort(), .limit(), and `async for`."""

    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key), reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __aiter__(self):
        async def gen():
            for d in self.docs:
                yield d
        return gen()


class FakeDatabase:
    def __init__(self):
        self.settings = {}
        self.applications = FakeCollection()
        self.composed = FakeCollection()

    async def get_guild_settings(self, guild_id):
        return dict(self.settings.get(guild_id, {}))

    async def update_guild_settings(self, guild_id, update):
        self.settings.setdefault(guild_id, {}).update(update)


def make_bot():
    bot = MagicMock()
    bot.database = FakeDatabase()
    bot.add_view = MagicMock()
    return bot


def make_channel(cls=discord.TextChannel, cid=500, name="general"):
    ch = MagicMock(spec=cls)
    ch.id = cid
    ch.name = name
    ch.mention = f"<#{cid}>"
    ch.send = AsyncMock(return_value=SimpleNamespace(id=999))
    return ch


def make_guild(channels=(), roles=()):
    guild = MagicMock()
    guild.id = 1
    guild.member_count = 42
    ch = {c.id: c for c in channels}
    ro = {(r.id if hasattr(r, "id") else r): (r if hasattr(r, "id") else SimpleNamespace(id=r, name=f"role{r}")) for r in roles}
    guild.channels = list(channels)
    guild.roles = list(ro.values())
    guild.get_channel = lambda i: ch.get(i)
    guild.get_role = lambda i: ro.get(i)
    guild.fetch_channel = AsyncMock(side_effect=lambda i: ch[i])
    return guild


class FakeUser(SimpleNamespace):
    def __str__(self):
        return "rose#0"


def make_user(uid=10, manage=True, admin=False, roles=()):
    return FakeUser(
        id=uid, mention=f"<@{uid}>", display_name="Rose",
        display_avatar=SimpleNamespace(url="https://cdn.discordapp.com/a.png"),
        guild_permissions=SimpleNamespace(manage_guild=manage, administrator=admin),
        roles=[SimpleNamespace(id=r) for r in roles],
    )


def make_interaction(user=None, guild=None, values=None, channel=None):
    user = user or make_user()
    return SimpleNamespace(
        user=user, guild=guild, guild_id=1, channel=channel, data={"values": values or []},
        response=SimpleNamespace(
            send_message=AsyncMock(), edit_message=AsyncMock(), send_modal=AsyncMock(), is_done=lambda: False,
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        message=None,
    )


def walk(view):
    return list(view.walk_children())


def find_button(view, label):
    return next(i for i in walk(view) if isinstance(i, ui.Button) and i.label == label)


def all_text(view):
    return "\n".join(i.content for i in walk(view) if isinstance(i, ui.TextDisplay))


def colour(view):
    c = next(i for i in walk(view) if isinstance(i, ui.Container)).accent_colour
    return int(getattr(c, "value", c))


def sent_view(mock):
    return mock.call_args.kwargs["view"]


