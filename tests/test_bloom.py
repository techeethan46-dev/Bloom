"""Bloom tests. They use fakes for Discord and MongoDB, so no network or token is needed."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest
from aiohttp.test_utils import TestClient, TestServer
from bson import ObjectId
from discord import ui

from cogs import setup as setup_cog
from cogs.applications import Applications, ApplicationPanelView, ApplicationReviewView, StaffApplicationModal
from cogs.welcome import Welcome, welcome_view
from config import GREEN, PINK, ROLE_KEYS, ROSE
import health
from utils import has_any_bloom_role, notice


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
        oid = ObjectId()
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
        matching = [dict(d) for d in self.docs.values() if self._match(d, flt)]

        async def gen():
            for d in matching:
                yield d
        return gen()


class FakeDatabase:
    def __init__(self):
        self.settings = {}
        self.applications = FakeCollection()

    async def get_guild_settings(self, guild_id):
        return dict(self.settings.get(guild_id, {}))

    async def update_guild_settings(self, guild_id, update):
        self.settings.setdefault(guild_id, {}).update(update)


def make_bot():
    bot = MagicMock()
    bot.database = FakeDatabase()
    bot.add_view = MagicMock()
    return bot


def make_channel(cls=discord.TextChannel, cid=500):
    ch = MagicMock(spec=cls)
    ch.id = cid
    ch.mention = f"<#{cid}>"
    ch.send = AsyncMock(return_value=SimpleNamespace(id=999))
    return ch


def make_guild(channels=(), roles=()):
    guild = MagicMock()
    guild.id = 1
    guild.member_count = 42
    ch = {c.id: c for c in channels}
    ro = {r: SimpleNamespace(id=r) for r in roles}
    guild.get_channel = lambda i: ch.get(i)
    guild.get_role = lambda i: ro.get(i)
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


# ---------------------------------------------------------------- every screen is valid

def test_every_setup_screen_builds_and_fits_discords_limits():
    async def go():
        bot = make_bot()
        cog = setup_cog.Setup(bot)
        guild = make_guild([make_channel()], roles=[7])
        settings = {"welcome_channel_id": 500, "review_channel_id": 500, "roles": {"founder": 7}}
        for step in range(setup_cog.OVERVIEW + 1):
            view = setup_cog.SetupView(cog, guild, settings, step)
            components = view.to_components()  # discord.py checks the structure here
            assert components
            assert len(all_text(view)) < 4000
            assert view.total_children_count <= 40, step
    run(go())


def test_cards_use_bloom_pink():
    async def go():
        view = notice("ok", "hi", "Title")
        assert colour(view) == PINK
        view = notice("bad", "no")
        assert colour(view) == ROSE
        assert colour(ApplicationPanelView(make_bot())) == PINK
        assert "A new flower has joined Bloom" in all_text(welcome_view(make_user_with_guild()))
    run(go())


def make_user_with_guild():
    user = make_user()
    user.guild = SimpleNamespace(member_count=42)
    user.mention = "<@10>"
    return user


# ---------------------------------------------------------------- /setup

def test_setup_starts_at_step_one_then_at_the_summary():
    async def go():
        bot = make_bot()
        cog = setup_cog.Setup(bot)
        guild = make_guild()
        first = make_interaction(guild=guild)
        first.guild_id = 1
        await cog.setup.callback(cog, first)
        v = sent_view(first.response.send_message)
        assert "step 1 of 13" in all_text(v)
        assert first.response.send_message.call_args.kwargs["ephemeral"] is True

        await bot.database.update_guild_settings(1, {"welcome_channel_id": 500})
        again = make_interaction(guild=guild)
        await cog.setup.callback(cog, again)
        assert "Bloom setup" in all_text(sent_view(again.response.send_message))
        assert "step" not in all_text(sent_view(again.response.send_message)).split("\n")[0]
    run(go())


def test_picking_a_channel_and_a_role_saves_and_moves_on():
    async def go():
        bot = make_bot()
        cog = setup_cog.Setup(bot)
        guild = make_guild([make_channel(cid=500)], roles=[77])
        view = setup_cog.SetupView(cog, guild, {}, 0)
        picker = next(i for i in walk(view) if isinstance(i, ui.ChannelSelect))
        i = make_interaction(guild=guild, values=["500"])
        await picker.callback(i)
        assert (await bot.database.get_guild_settings(1))["welcome_channel_id"] == 500
        nxt = i.response.edit_message.call_args.kwargs["view"]
        assert "step 2 of 13" in all_text(nxt)

        role_view = setup_cog.SetupView(cog, guild, await bot.database.get_guild_settings(1), 2)  # Founder
        picker = next(i for i in walk(role_view) if isinstance(i, ui.RoleSelect))
        i = make_interaction(guild=guild, values=["77"])
        await picker.callback(i)
        assert (await bot.database.get_guild_settings(1))["roles"] == {"founder": 77}
        assert "Co-owner role" in all_text(i.response.edit_message.call_args.kwargs["view"])
    run(go())


def test_back_next_clear_and_jump():
    async def go():
        bot = make_bot()
        cog = setup_cog.Setup(bot)
        await bot.database.update_guild_settings(1, {"welcome_channel_id": 500, "roles": {"founder": 7}})
        guild = make_guild([make_channel()], roles=[7])
        settings = await bot.database.get_guild_settings(1)

        view = setup_cog.SetupView(cog, guild, settings, 0)
        assert find_button(view, "Back").disabled
        i = make_interaction(guild=guild)
        await find_button(view, "Next").callback(i)
        assert "step 2 of 13" in all_text(i.response.edit_message.call_args.kwargs["view"])

        i = make_interaction(guild=guild)
        await find_button(view, "Clear").callback(i)
        assert (await bot.database.get_guild_settings(1))["welcome_channel_id"] is None

        last = setup_cog.SetupView(cog, guild, settings, setup_cog.OVERVIEW - 1)
        i = make_interaction(guild=guild)
        await find_button(last, "Next").callback(i)
        assert "of 13** done" in all_text(i.response.edit_message.call_args.kwargs["view"])

        over = setup_cog.SetupView(cog, guild, settings, setup_cog.OVERVIEW)
        jump = next(i for i in walk(over) if isinstance(i, ui.Select) and not isinstance(i, (ui.RoleSelect, ui.ChannelSelect)))
        i = make_interaction(guild=guild, values=["2"])
        await jump.callback(i)
        assert "Founder role" in all_text(i.response.edit_message.call_args.kwargs["view"])

        # clearing a role leaves the other roles alone
        await bot.database.update_guild_settings(1, {"roles": {"founder": 7, "deputy": 8}})
        settings = await bot.database.get_guild_settings(1)
        rv = setup_cog.SetupView(cog, make_guild(roles=[7, 8]), settings, 2)
        await find_button(rv, "Clear").callback(make_interaction(guild=guild))
        assert (await bot.database.get_guild_settings(1))["roles"] == {"deputy": 8}
    run(go())


def test_only_people_with_manage_server_can_use_the_wizard():
    async def go():
        bot = make_bot()
        view = setup_cog.SetupView(setup_cog.Setup(bot), make_guild(), {}, 0)
        nope = make_interaction(user=make_user(manage=False))
        assert await view.interaction_check(nope) is False
        assert "Manage Server" in all_text(sent_view(nope.response.send_message))
        assert await view.interaction_check(make_interaction()) is True
    run(go())


def test_post_panel_and_preview_welcome_from_the_summary():
    async def go():
        bot = make_bot()
        cog = setup_cog.Setup(bot)
        guild = make_guild([make_channel()])
        here = make_channel(cid=600)

        view = setup_cog.SetupView(cog, guild, {}, setup_cog.OVERVIEW)
        i = make_interaction(guild=guild, channel=here)
        await find_button(view, "Post application panel").callback(i)
        assert "review channel" in all_text(i.response.edit_message.call_args.kwargs["view"]), "needs the review channel first"
        here.send.assert_not_called()

        settings = {"review_channel_id": 500}
        view = setup_cog.SetupView(cog, guild, settings, setup_cog.OVERVIEW)
        i = make_interaction(guild=guild, channel=here)
        await find_button(view, "Post application panel").callback(i)
        posted = here.send.call_args.kwargs["view"]
        assert "Join the Bloom staff team" in all_text(posted)
        assert "Panel posted" in all_text(sent_view(i.response.send_message))

        here.send = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no"))
        i = make_interaction(guild=guild, channel=here)
        await find_button(view, "Post application panel").callback(i)
        assert "can't post" in all_text(sent_view(i.response.send_message))

        i = make_interaction(user=make_user_with_guild(), guild=guild)
        await find_button(view, "Preview welcome").callback(i)
        assert "A new flower has joined Bloom" in all_text(sent_view(i.response.send_message))
        assert i.response.send_message.call_args.kwargs["ephemeral"] is True
    run(go())


def test_only_one_command_is_left():
    async def go():
        from discord.ext import commands as c
        bot = c.Bot(command_prefix="!", intents=discord.Intents.none())
        await bot.add_cog(setup_cog.Setup(bot))
        await bot.add_cog(Welcome(bot))
        await bot.add_cog(Applications(bot))
        names = [cmd.name for cmd in bot.tree.get_commands()]
        assert names == ["setup"]
        cmd = bot.tree.get_command("setup")
        assert cmd.default_permissions.manage_guild
        assert cmd.guild_only
        await bot.close()
    run(go())


# ---------------------------------------------------------------- welcome

def test_welcome_goes_to_the_welcome_channel_without_pinging():
    async def go():
        bot = make_bot()
        channel = make_channel(cid=500)
        member = make_user_with_guild()
        member.guild.id = 1
        member.guild.get_channel = lambda i: channel if i == 500 else None
        cog = Welcome(bot)

        await cog.send_welcome(member)  # nothing set up: nothing happens
        channel.send.assert_not_called()

        await bot.database.update_guild_settings(1, {"welcome_channel_id": 500})
        await cog.send_welcome(member)
        kwargs = channel.send.call_args.kwargs
        assert "<@10>" in all_text(kwargs["view"]) and "member #42" in all_text(kwargs["view"])
        assert kwargs["allowed_mentions"].users is False

        channel.send = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no"))
        await cog.send_welcome(member)  # can't post there: no crash
    run(go())


# ---------------------------------------------------------------- applications

def modal_with(bot, **answers):
    modal = StaffApplicationModal(bot)
    for name in ("position", "availability", "experience", "why"):
        getattr(modal, name)._value = answers.get(name, f"my {name}")
    return modal


def test_application_goes_to_the_review_channel_with_buttons():
    async def go():
        bot = make_bot()
        review = make_channel(cid=500)
        guild = make_guild([review])
        i = make_interaction(user=make_user(uid=33), guild=guild)

        unset = modal_with(bot)
        await unset.on_submit(i)
        assert "aren't set up yet" in all_text(sent_view(i.response.send_message))

        await bot.database.update_guild_settings(1, {"review_channel_id": 500})
        i = make_interaction(user=make_user(uid=33), guild=guild)
        await modal_with(bot, position="Moderator", experience="2 years").on_submit(i)

        posted = review.send.call_args.kwargs["view"]
        txt = all_text(posted)
        assert "New staff application" in txt and "<@33>" in txt and "Moderator" in txt and "2 years" in txt
        assert {b.label for b in walk(posted) if isinstance(b, ui.Button)} == {"Approve", "Reject"}
        assert posted.is_persistent()
        doc = next(iter(bot.database.applications.docs.values()))
        assert doc["status"] == "pending" and doc["review_message_id"] == 999
        assert "submitted" in all_text(sent_view(i.response.send_message))
    run(go())


def pending_doc(bot, uid=33):
    async def add():
        res = await bot.database.applications.insert_one({
            "guild_id": 1, "user_id": uid, "position": "Mod", "availability": "evenings",
            "experience": "lots", "why": "I care", "status": "pending",
        })
        return await bot.database.applications.find_one({"_id": res.inserted_id})
    return add()


def test_only_leadership_can_decide_and_only_once():
    async def go():
        bot = make_bot()
        await bot.database.update_guild_settings(1, {"roles": {"vice_president": 88}})
        doc = await pending_doc(bot)
        view = ApplicationReviewView(bot, doc)

        rando = make_interaction(user=make_user(uid=5, roles=[1, 2]))
        await find_button(view, "Approve").callback(rando)
        assert "Only Bloom leadership" in all_text(sent_view(rando.response.send_message))
        assert bot.database.applications.docs[doc["_id"]]["status"] == "pending"

        leader = make_interaction(user=make_user(uid=6, roles=[88]))
        await find_button(view, "Approve").callback(leader)
        assert bot.database.applications.docs[doc["_id"]]["status"] == "approved"
        assert bot.database.applications.docs[doc["_id"]]["reviewed_by"] == 6
        done = leader.response.edit_message.call_args.kwargs["view"]
        assert "Approved" in all_text(done) and "<@6>" in all_text(done)
        assert not [b for b in walk(done) if isinstance(b, ui.Button)], "no buttons once decided"
        assert colour(done) == GREEN

        second = make_interaction(user=make_user(uid=7, admin=True))
        await find_button(view, "Reject").callback(second)  # an admin, but it was already decided
        assert "already decided" in all_text(sent_view(second.response.send_message))
        assert bot.database.applications.docs[doc["_id"]]["status"] == "approved"

        doc2 = await pending_doc(bot, uid=34)
        admin = make_interaction(user=make_user(uid=8, admin=True))
        await find_button(ApplicationReviewView(bot, doc2), "Reject").callback(admin)
        rejected = admin.response.edit_message.call_args.kwargs["view"]
        assert "Rejected" in all_text(rejected)
        assert colour(rejected) == ROSE
    run(go())


def test_buttons_come_back_after_a_restart():
    async def go():
        bot = make_bot()
        pending = await pending_doc(bot, uid=1)
        done = await pending_doc(bot, uid=2)
        bot.database.applications.docs[done["_id"]]["status"] = "approved"
        await Applications(bot).register_persistent_views()
        views = [c.args[0] for c in bot.add_view.call_args_list]
        assert any(isinstance(v, ApplicationPanelView) for v in views)
        reviews = [v for v in views if isinstance(v, ApplicationReviewView)]
        assert [v.application_id for v in reviews] == [str(pending["_id"])], "only pending ones"
        ids = {i.custom_id for i in walk(reviews[0]) if isinstance(i, ui.Button)}
        assert ids == {f"bloom:approve:{pending['_id']}", f"bloom:reject:{pending['_id']}"}
        assert ApplicationPanelView(bot).is_persistent()
    run(go())


def test_apply_button_opens_the_form():
    async def go():
        bot = make_bot()
        i = make_interaction()
        await find_button(ApplicationPanelView(bot), "Apply for staff").callback(i)
        assert isinstance(i.response.send_modal.call_args.args[0], StaffApplicationModal)
        for label_len in (len(t.label) for t in StaffApplicationModal(bot).children):
            assert label_len <= 45
    run(go())


def test_leadership_check_uses_the_mapped_roles():
    settings = {"roles": {"founder": 1, "moderator": 2}}
    member = SimpleNamespace(roles=[SimpleNamespace(id=2)])
    assert not has_any_bloom_role(member, settings, ("founder", "co_owner"))
    assert has_any_bloom_role(member, settings, ("moderator",))
    assert set(ROLE_KEYS) >= {"founder", "jailed"}


# ---------------------------------------------------------------- Render and UptimeRobot

def test_health_page_answers_for_uptimerobot():
    async def go():
        bot = SimpleNamespace(user=None)
        async with TestClient(TestServer(health.make_app(bot))) as client:
            for path in ("/", "/health"):
                r = await client.get(path)
                assert r.status == 200
                assert await r.json() == {"status": "online", "bot": "starting"}
            bot.user = "Bloom#1234"
            assert (await (await client.get("/health")).json())["bot"] == "Bloom#1234"
    run(go())
