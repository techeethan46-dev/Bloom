"""Tests for /message: reading what people type, the limits, the builder, posting and editing."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord import ui

import compose
from cogs import message as message_cog
from cogs.message import BannerModal, BuilderView, CardModal, Draft, Message
from config import PINK
from fakes import (
    all_text, colour, find_button, make_bot, make_channel, make_guild, make_interaction, make_user, run,
    sent_view, walk,
)

GUILD_CHANNELS = [make_channel(cid=500, name="rules"), make_channel(cid=501, name="┃📜・announcements")]
ROLES = [SimpleNamespace(id=7, name="VIP"), SimpleNamespace(id=8, name="Staff"), SimpleNamespace(id=9, name="Staff")]


def guild():
    return make_guild(GUILD_CHANNELS, roles=ROLES)


# ---------------------------------------------------------------- reading what people type

def test_colors():
    assert compose.parse_color("") == (None, None)
    assert compose.parse_color("  ") == (None, None)
    assert compose.parse_color("#E8A7C8") == (0xE8A7C8, None)
    assert compose.parse_color("e8a7c8") == (0xE8A7C8, None)
    assert compose.parse_color("f80") == (0xFF8800, None)
    assert compose.parse_color("Pink") == (0xE8A7C8, None)
    value, error = compose.parse_color("not a color")
    assert value is None and "isn't a color" in error and "pink" in error


def test_images_must_be_https_links():
    assert compose.parse_image("") == (None, None)
    assert compose.parse_image(" https://i.imgur.com/a.png ") == ("https://i.imgur.com/a.png", None)
    for bad in ("http://x.com/a.png", "ftp://x.com", "imgur.com/a.png", "not a link", "https://"):
        assert "must be a link starting with https://" in compose.parse_image(bad, "banner picture")[1], bad


def test_buttons():
    assert compose.parse_buttons("") == ([], None)
    buttons, error = compose.parse_buttons("Join the group | https://www.roblox.com/groups/1\nRules|https://x.com/r")
    assert error is None and buttons == [
        {"label": "Join the group", "url": "https://www.roblox.com/groups/1"}, {"label": "Rules", "url": "https://x.com/r"}]
    for bad in ("no pipe here", "| https://x.com", "Label | http://x.com", "Label |"):
        assert "must look like" in compose.parse_buttons(bad)[1], bad
    assert "up to 5" in compose.parse_buttons("\n".join(f"b{i} | https://x.com/{i}" for i in range(6)))[1]


def test_typed_channels_and_roles_become_links_and_back():
    g = guild()
    assert compose.resolve_mentions("Read #rules and #announcements first", g) == "Read <#500> and <#501> first"
    assert compose.resolve_mentions("Ask @VIP", g) == "Ask <@&7>"
    assert compose.resolve_mentions("Ask @Staff", g) == "Ask @Staff", "two roles share a name: left alone"
    assert compose.resolve_mentions("hi @everyone @here #nothere", g) == "hi @everyone @here #nothere"
    assert compose.resolve_mentions("(#rules)", g) == "(<#500>)"
    assert compose.resolve_mentions("mail a#rules", g) == "mail a#rules", "only after a space or bracket"
    assert compose.readable_mentions("Read <#500> and ask <@&7>", g) == "Read #rules and ask @VIP"
    assert compose.readable_mentions("<@&8> <#999>", g) == "<@&8> <#999>", "ambiguous or unknown ones stay as they are"
    # the round trip
    text = "See #rules, ask @VIP"
    assert compose.readable_mentions(compose.resolve_mentions(text, g), g) == text


def test_labels():
    assert compose.label({"type": "banner"}) == "Banner image"
    assert compose.label({"type": "card", "text": "## 📜 **Server** rules\nbe kind"}) == "📜 Server rules"
    assert compose.label({"type": "card", "text": "\n\n- hello"}) == "hello"
    assert compose.label({"type": "card", "text": "###"}) == "Card"


# ---------------------------------------------------------------- rendering and limits

def card_block(text="## Hi", **extra):
    return {"type": "card", "text": text, "color": None, "thumb": None, "image": None, "buttons": [], **extra}


def test_render_blocks_makes_valid_pink_cards():
    async def go():
        blocks = [
            {"type": "banner", "image": "https://x.com/b.png", "color": None},
            card_block("## Rules\n- be kind", color=0x112233, thumb="https://x.com/t.png", image="https://x.com/i.png",
                       buttons=[{"label": "Join", "url": "https://x.com/j"}]),
            card_block("plain"),
        ]
        view = compose.render_blocks(blocks)
        assert view.to_components()
        containers = [i for i in view.children if isinstance(i, ui.Container)]
        assert [int(c.accent_colour.value if hasattr(c.accent_colour, "value") else c.accent_colour) for c in containers] == [PINK, 0x112233, PINK]
        assert [b.label for b in walk(view) if isinstance(b, ui.Button)] == ["Join"]
        assert all(b.style == discord.ButtonStyle.link for b in walk(view) if isinstance(b, ui.Button))
        assert any(isinstance(i, ui.Thumbnail) for i in walk(view))
        assert sum(isinstance(i, ui.MediaGallery) for i in walk(view)) == 2
    run(go())


def test_limits():
    async def go():
        assert compose.problem([]) == "Add at least one card or banner first."
        assert compose.problem([card_block("ok")]) is None
        assert "up to 8 blocks" in compose.problem([card_block("x")] * 9)
        long = compose.problem([card_block("x" * 3801)])
        assert "Too long" in long and "3,800" in long and "3,801" in long
        busy = [card_block("x", thumb="https://x.com/t.png", image="https://x.com/i.png",
                           buttons=[{"label": str(n), "url": "https://x.com/"} for n in range(5)])] * 6
        assert "too many parts" in compose.problem(busy)
        assert compose.component_count([card_block("x")]) == 2  # the card and its text
    run(go())


# ---------------------------------------------------------------- the builder

def setup_builder(mode="post", blocks=None, selected=None):
    bot = make_bot()
    cog = Message(bot)
    g = guild()
    draft = Draft(mode=mode, guild_id=1, channel_id=500, message_id=None, blocks=blocks or [], selected=selected)
    cog.drafts[10] = draft
    return bot, cog, g, draft


def fill(modal, **answers):
    for item in modal.children:
        key = {"Text": "body", "Color": "color", "Small": "thumb", "Big": "image", "Butt": "buttons", "Pict": "image", "Edge": "color"}
        name = next(n for n in ("body", "color", "thumb", "image", "buttons") if getattr(modal, n, None) is item)
        item._value = answers.get(name, item.default or "")
    return modal


def test_every_builder_screen_is_valid():
    async def go():
        bot, cog, g, draft = setup_builder()
        for blocks, selected in (([], None), ([card_block("## A")], 0), ([card_block("## A"), {"type": "banner", "image": "https://x.com/b.png", "color": None}], 1)):
            draft.blocks, draft.selected = blocks, selected
            view = BuilderView(cog, draft, g, 10)
            assert view.to_components()
            assert len(all_text(view)) < 4000 and view.total_children_count <= 40
        # nothing to post yet: Post and Preview are off
        draft.blocks, draft.selected = [], None
        view = BuilderView(cog, draft, g, 10)
        assert find_button(view, "Post message").disabled and find_button(view, "Preview").disabled
        assert "Nothing yet" in all_text(view)
        assert colour(view) == PINK
    run(go())


def test_add_a_card_with_links_and_it_shows_in_the_list():
    async def go():
        bot, cog, g, draft = setup_builder()
        view = BuilderView(cog, draft, g, 10)
        i = make_interaction(guild=g)
        await find_button(view, "Add card").callback(i)
        modal = i.response.send_modal.call_args.args[0]
        assert isinstance(modal, CardModal) and modal.title == "New card"
        assert all(len(t.label) <= 45 for t in modal.children), "Discord rejects form labels over 45 characters"

        fill(modal, body="## 📜 Rules\nRead #rules, ask @VIP", color="pink", buttons="Join | https://x.com/j")
        m = make_interaction(guild=g)
        await modal.on_submit(m)
        block = draft.blocks[0]
        assert block["text"] == "## 📜 Rules\nRead <#500>, ask <@&7>" and block["color"] == 0xE8A7C8
        assert block["buttons"] == [{"label": "Join", "url": "https://x.com/j"}]
        assert draft.selected == 0
        screen = m.response.edit_message.call_args.kwargs["view"]
        assert "**1.** 📄 📜 Rules" in all_text(screen)
    run(go())


def test_bad_input_shows_a_message_and_changes_nothing():
    async def go():
        bot, cog, g, draft = setup_builder()
        view = BuilderView(cog, draft, g, 10)
        for answers, expected in (
            ({"body": "text", "color": "zzz"}, "isn't a color"),
            ({"body": ""}, "needs some text"),
            ({"body": "x", "thumb": "http://x.com/a.png"}, "small picture must be a link"),
            ({"body": "x", "image": "nope"}, "big picture must be a link"),
            ({"body": "x", "buttons": "broken"}, "must look like"),
            ({"body": "x" * 3801}, "Too long"),
        ):
            i = make_interaction(guild=g)
            await find_button(view, "Add card").callback(i)
            modal = fill(i.response.send_modal.call_args.args[0], **answers)
            m = make_interaction(guild=g)
            await modal.on_submit(m)
            assert expected in all_text(m.response.edit_message.call_args.kwargs["view"]), answers
            assert draft.blocks == []
    run(go())


def test_banner():
    async def go():
        bot, cog, g, draft = setup_builder()
        view = BuilderView(cog, draft, g, 10)
        i = make_interaction(guild=g)
        await find_button(view, "Add banner").callback(i)
        modal = i.response.send_modal.call_args.args[0]
        assert isinstance(modal, BannerModal)
        assert all(len(t.label) <= 45 for t in modal.children)

        bad = make_interaction(guild=g)
        await fill(modal, image="").on_submit(bad)
        assert "link to the banner picture" in all_text(bad.response.edit_message.call_args.kwargs["view"])
        await fill(modal, image="https://x.com/b.png", color="#112233").on_submit(make_interaction(guild=g))
        assert draft.blocks == [{"type": "banner", "image": "https://x.com/b.png", "color": 0x112233}]
    run(go())


def test_pick_edit_move_and_delete():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("## One"), card_block("## Two"), card_block("## Three")], selected=0)
        view = BuilderView(cog, draft, g, 10)
        assert find_button(view, "Up").disabled and not find_button(view, "Down").disabled

        i = make_interaction(guild=g)
        await find_button(view, "Down").callback(i)
        assert [b["text"] for b in draft.blocks] == ["## Two", "## One", "## Three"] and draft.selected == 1
        view = BuilderView(cog, draft, g, 10)

        picker = next(x for x in walk(view) if isinstance(x, ui.Select))
        i = make_interaction(guild=g, values=["2"])
        await picker.callback(i)
        assert draft.selected == 2
        view = BuilderView(cog, draft, g, 10)
        assert find_button(view, "Down").disabled

        # Edit opens the form with the old text filled in, and #links turned back into names
        draft.blocks[2] = card_block("Read <#500>", buttons=[{"label": "Go", "url": "https://x.com/"}], color=0x112233)
        i = make_interaction(guild=g)
        await find_button(view, "Edit").callback(i)
        modal = i.response.send_modal.call_args.args[0]
        assert modal.title == "Edit card"
        assert modal.body.default == "Read #rules" and modal.color.default == "#112233" and modal.buttons.default == "Go | https://x.com/"
        await fill(modal, body="Changed").on_submit(make_interaction(guild=g))
        assert draft.blocks[2]["text"] == "Changed" and len(draft.blocks) == 3

        view = BuilderView(cog, draft, g, 10)
        i = make_interaction(guild=g)
        await find_button(view, "Delete").callback(i)
        assert len(draft.blocks) == 2 and draft.selected == 1
        for _ in range(2):
            view = BuilderView(cog, draft, g, 10)
            await find_button(view, "Delete").callback(make_interaction(guild=g))
        assert draft.blocks == [] and draft.selected is None
    run(go())


def test_preview_is_private_and_shows_what_will_be_posted():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("## Hello {user}")])
        view = BuilderView(cog, draft, g, 10)
        i = make_interaction(guild=g)
        await find_button(view, "Preview").callback(i)
        assert i.response.send_message.call_args.kwargs["ephemeral"] is True
        assert "## Hello {user}" in all_text(sent_view(i.response.send_message)), "no placeholders in normal messages"

        draft.blocks = [card_block("x" * 3900)]
        i = make_interaction(guild=g)
        await find_button(BuilderView(cog, draft, g, 10), "Preview").callback(i)
        assert "Too long" in all_text(i.response.edit_message.call_args.kwargs["view"])
    run(go())


def test_only_people_with_manage_server_and_a_live_draft_can_use_it():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("x")], selected=0)
        view = BuilderView(cog, draft, g, 10)
        nope = make_interaction(user=make_user(manage=False), guild=g)
        assert await view.interaction_check(nope) is False
        assert "Manage Server" in all_text(sent_view(nope.response.send_message))

        cog.drafts[10] = Draft(mode="post", guild_id=1, channel_id=500)  # they started another builder
        old = make_interaction(guild=g)
        assert await view.interaction_check(old) is False
        assert "expired" in all_text(sent_view(old.response.send_message))
    run(go())


def test_cancel_throws_the_draft_away():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("x")], selected=0)
        i = make_interaction(guild=g)
        await find_button(BuilderView(cog, draft, g, 10), "Cancel").callback(i)
        assert 10 not in cog.drafts
        assert "Nothing was posted" in all_text(i.response.edit_message.call_args.kwargs["view"])
    run(go())


# ---------------------------------------------------------------- posting and editing

def test_post_sends_the_message_without_pinging_and_remembers_it():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("## Rules"), {"type": "banner", "image": "https://x.com/b.png", "color": None}], selected=0)
        channel = GUILD_CHANNELS[0]
        channel.mention = "<#500>"
        channel.send = AsyncMock(return_value=SimpleNamespace(id=777, jump_url="https://discord.com/channels/1/500/777"))
        i = make_interaction(guild=g)
        await find_button(BuilderView(cog, draft, g, 10), "Post message").callback(i)

        kwargs = channel.send.call_args.kwargs
        assert "## Rules" in all_text(kwargs["view"]) and kwargs["allowed_mentions"].roles is False
        saved = bot.database.composed.docs["777"]
        assert saved["channel_id"] == 500 and saved["guild_id"] == 1 and saved["blocks"] == draft.blocks and saved["author_id"] == 10
        assert 10 not in cog.drafts
        done = all_text(i.response.edit_message.call_args.kwargs["view"])
        assert "Posted!" in done and "<#500>" in done and "/message edit" in done
    run(go())


def test_a_failed_post_keeps_the_draft_and_says_why():
    async def go():
        bot, cog, g, draft = setup_builder(blocks=[card_block("x")], selected=0)
        channel = GUILD_CHANNELS[0]
        channel.send = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "Missing Access"))
        i = make_interaction(guild=g)
        await find_button(BuilderView(cog, draft, g, 10), "Post message").callback(i)
        screen = all_text(i.response.edit_message.call_args.kwargs["view"])
        assert "couldn't post" in screen and "Missing Access" in screen
        assert cog.drafts[10] is draft and not bot.database.composed.docs
    run(go())


def test_create_command_opens_a_private_builder_for_the_chosen_channel():
    async def go():
        bot = make_bot()
        cog = Message(bot)
        g = guild()
        i = make_interaction(guild=g, channel=GUILD_CHANNELS[1])
        await cog.create.callback(cog, i, None)
        assert "will be posted in <#501>" in all_text(sent_view(i.response.send_message))
        assert i.response.send_message.call_args.kwargs["ephemeral"] is True
        assert cog.drafts[10].channel_id == 501

        i = make_interaction(guild=g, channel=GUILD_CHANNELS[1])
        await cog.create.callback(cog, i, GUILD_CHANNELS[0])
        assert cog.drafts[10].channel_id == 500
    run(go())


async def seeded(bot, message_id="777", blocks=None, guild_id=1):
    await bot.database.composed.insert_one({
        "_id": message_id, "guild_id": guild_id, "channel_id": 500, "author_id": 10,
        "blocks": blocks or [card_block("## Old rules")], "created_at": 1,
    })


def test_edit_opens_the_old_message_and_saving_updates_it():
    async def go():
        bot = make_bot()
        cog = Message(bot)
        g = guild()
        await seeded(bot)
        live = SimpleNamespace(id=777, edit=AsyncMock(), jump_url="https://discord.com/channels/1/500/777")
        channel = GUILD_CHANNELS[0]
        channel.fetch_message = AsyncMock(return_value=live)

        i = make_interaction(guild=g)
        await cog.edit.callback(cog, i, "777")
        draft = cog.drafts[10]
        assert draft.mode == "edit" and draft.message_id == 777 and draft.blocks[0]["text"] == "## Old rules"
        assert "EDITING A MESSAGE" in all_text(sent_view(i.response.send_message))

        draft.blocks[0]["text"] = "## New rules"
        i = make_interaction(guild=g)
        await find_button(BuilderView(cog, draft, g, 10), "Save changes").callback(i)
        assert "## New rules" in all_text(live.edit.call_args.kwargs["view"])
        assert bot.database.composed.docs["777"]["blocks"][0]["text"] == "## New rules"
        assert "Saved" in all_text(i.response.edit_message.call_args.kwargs["view"])
        assert 10 not in cog.drafts

        # pasting the message link works too
        cog.drafts.clear()
        i = make_interaction(guild=g)
        await cog.edit.callback(cog, i, "https://discord.com/channels/1/500/777")
        assert cog.drafts[10].message_id == 777
    run(go())


def test_edit_refuses_unknown_other_server_and_deleted_messages():
    async def go():
        bot = make_bot()
        cog = Message(bot)
        g = guild()
        i = make_interaction(guild=g)
        await cog.edit.callback(cog, i, "12345")
        assert "only edit messages made with" in all_text(sent_view(i.response.send_message))

        await seeded(bot, "888", guild_id=999)
        i = make_interaction(guild=g)
        await cog.edit.callback(cog, i, "888")
        assert "only edit messages made with" in all_text(sent_view(i.response.send_message))

        await seeded(bot, "777")
        GUILD_CHANNELS[0].fetch_message = AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404, reason="x"), "gone"))
        i = make_interaction(guild=g)
        await cog.edit.callback(cog, i, "777")
        assert "was deleted" in all_text(sent_view(i.response.send_message))
        assert "777" not in bot.database.composed.docs, "forgotten once it's gone"
    run(go())


def test_edit_autocomplete_lists_newest_first():
    async def go():
        bot = make_bot()
        cog = Message(bot)
        g = guild()
        await seeded(bot, "1", [card_block("## First")])
        await seeded(bot, "2", [card_block("## Second")])
        bot.database.composed.docs["2"]["created_at"] = 5
        i = make_interaction(guild=g)
        choices = await cog.edit_autocomplete(i, "")
        assert [c.value for c in choices] == ["2", "1"]
        assert choices[0].name == "#rules · Second"
        assert [c.value for c in await cog.edit_autocomplete(i, "first")] == ["1"]
    run(go())


def test_command_group_is_hidden_from_regular_members():
    async def go():
        from discord.ext import commands
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        await bot.add_cog(Message(bot))
        group = bot.tree.get_command("message")
        assert group.default_permissions.manage_guild and group.guild_only
        assert sorted(c.name for c in group.commands) == ["create", "edit"]
        await bot.close()
    run(go())
