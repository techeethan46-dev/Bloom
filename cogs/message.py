"""/message: write rich messages (rules, announcements) from a banner and cards, post them, and edit them later.

A builder (private to you) keeps the draft in memory while you work.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import discord
from discord import app_commands, ui
from discord.ext import commands

from compose import (
    MAX_BLOCKS, MAX_COMPONENTS, MAX_TEXT, SAMPLE_COLORS, component_count, label, parse_buttons, parse_color, parse_image,
    problem, readable_mentions, render_blocks, resolve_mentions, text_length,
)
from utils import card, card_view, divider, notice, text

NO_PINGS = discord.AllowedMentions.none()  # a rules message that mentions @Role shows it, but doesn't ping anyone


@dataclass
class Draft:
    mode: str                      # "post" or "edit"
    guild_id: int
    channel_id: int
    message_id: int | None = None  # the message being edited
    blocks: list[dict] = field(default_factory=list)
    selected: int | None = None


def _hex(color: int | None) -> str:
    return f"#{color:06x}" if color is not None else ""


class BuilderView(ui.LayoutView):
    """The private builder screen. Every button builds the next screen."""

    def __init__(self, cog: "Message", draft: Draft, guild: discord.Guild, user_id: int, error: str | None = None):
        super().__init__(timeout=1800)
        self.cog = cog
        self.draft = draft
        self.guild = guild
        self.user_id = user_id
        self.add_item(self._build(error))

    # ------------------------------------------------------------ what it looks like
    def _build(self, error: str | None) -> ui.Container:
        d = self.draft
        chars, parts = text_length(d.blocks), component_count(d.blocks)
        heading = (f"-# ✍️ MESSAGE BUILDER · will be posted in <#{d.channel_id}>" if d.mode == "post"
                   else "-# ✍️ EDITING A MESSAGE · saving changes the live message")
        if d.blocks:
            lines = [
                f"{'▶️' if i == d.selected else '▫️'} **{i + 1}.** {'🖼️' if b['type'] == 'banner' else '📄'} {label(b)}"
                + (f" · {len(b['text']):,} chars" if b["type"] == "card" else "")
                for i, b in enumerate(d.blocks)
            ]
        else:
            lines = ["*Nothing yet. Add a card or a banner below.*"]

        children: list[ui.Item] = [
            text(heading, "### Blocks in this message"),
            text(*lines),
            text(f"-# {chars:,} / {MAX_TEXT:,} characters · {parts} / {MAX_COMPONENTS} parts · up to {MAX_BLOCKS} blocks"),
            text(f"❌ {error}") if error else text(),
            divider(),
        ]
        children = [c for c in children if not (isinstance(c, ui.TextDisplay) and not c.content)]

        if d.blocks:
            pick = ui.Select(
                placeholder="Pick a block to change…",
                options=[discord.SelectOption(label=f"{i + 1}. {label(b)}"[:100], value=str(i),
                                              emoji="🖼️" if b["type"] == "banner" else "📄", default=i == d.selected)
                         for i, b in enumerate(d.blocks)],
            )
            pick.callback = self._picked
            children.append(ui.ActionRow(pick))
        if d.selected is not None and d.blocks:
            edit = self._button("Edit", "✏️", discord.ButtonStyle.primary, self._edit)
            up = self._button("Up", "⬆️", discord.ButtonStyle.secondary, lambda i: self._move(i, -1), disabled=d.selected == 0)
            down = self._button("Down", "⬇️", discord.ButtonStyle.secondary, lambda i: self._move(i, 1), disabled=d.selected == len(d.blocks) - 1)
            delete = self._button("Delete", "🗑️", discord.ButtonStyle.danger, self._delete)
            children.append(ui.ActionRow(edit, up, down, delete))

        full = len(d.blocks) >= MAX_BLOCKS
        children.append(ui.ActionRow(
            self._button("Add card", "📄", discord.ButtonStyle.secondary, self._add_card, disabled=full),
            self._button("Add banner", "🖼️", discord.ButtonStyle.secondary, self._add_banner, disabled=full),
            self._button("Preview", "👁️", discord.ButtonStyle.secondary, self._preview, disabled=not d.blocks),
        ))
        finish = ("Post message", "📨") if d.mode == "post" else ("Save changes", "💾")
        children.append(ui.ActionRow(
            self._button(finish[0], finish[1], discord.ButtonStyle.success, self._finish, disabled=not d.blocks),
            self._button("Cancel", None, discord.ButtonStyle.secondary, self._cancel),
        ))
        children.append(text("-# Type #channel or @Role in the text and it becomes a link · up to 3,800 characters per message, so post several for long rules"))
        return card(*children)

    @staticmethod
    def _button(label_: str, emoji: str | None, style: discord.ButtonStyle, callback, disabled: bool = False) -> ui.Button:
        b = ui.Button(label=label_, emoji=emoji, style=style, disabled=disabled)
        b.callback = callback
        return b

    # ------------------------------------------------------------ checks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(view=notice("bad", "You need **Manage Server** to use this."), ephemeral=True)
            return False
        if self.cog.drafts.get(self.user_id) is not self.draft:
            await interaction.response.send_message(view=notice(
                "warn", "That builder has expired (the bot restarted, or you started another one). Run `/message create` again."), ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction, error: str | None = None) -> None:
        await interaction.response.edit_message(view=BuilderView(self.cog, self.draft, self.guild, self.user_id, error))

    # ------------------------------------------------------------ what the buttons do
    async def _picked(self, interaction: discord.Interaction) -> None:
        self.draft.selected = int(interaction.data["values"][0])
        await self.refresh(interaction)

    async def _add_card(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CardModal(self, None, "new"))

    async def _add_banner(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(BannerModal(self, None, "new"))

    async def _edit(self, interaction: discord.Interaction) -> None:
        d = self.draft
        block = d.blocks[d.selected] if d.selected is not None and d.selected < len(d.blocks) else None
        if not block:
            return await self.refresh(interaction)
        modal = BannerModal(self, block, d.selected) if block["type"] == "banner" else CardModal(self, block, d.selected)
        await interaction.response.send_modal(modal)

    async def _move(self, interaction: discord.Interaction, step: int) -> None:
        d = self.draft
        to = d.selected + step
        if 0 <= to < len(d.blocks):
            d.blocks[d.selected], d.blocks[to] = d.blocks[to], d.blocks[d.selected]
            d.selected = to
        await self.refresh(interaction)

    async def _delete(self, interaction: discord.Interaction) -> None:
        d = self.draft
        if d.selected is not None and d.selected < len(d.blocks):
            d.blocks.pop(d.selected)
            d.selected = min(d.selected, len(d.blocks) - 1) if d.blocks else None
        await self.refresh(interaction)

    async def _preview(self, interaction: discord.Interaction) -> None:
        why = problem(self.draft.blocks)
        if why:
            return await self.refresh(interaction, why)
        await interaction.response.send_message(view=render_blocks(self.draft.blocks), ephemeral=True)

    async def _cancel(self, interaction: discord.Interaction) -> None:
        self.cog.drafts.pop(self.user_id, None)
        await interaction.response.edit_message(view=notice("ok", "Nothing was posted or changed.", "Cancelled"))

    async def _finish(self, interaction: discord.Interaction) -> None:
        d = self.draft
        why = problem(d.blocks)
        if why:
            return await self.refresh(interaction, why)
        channel = self.guild.get_channel(d.channel_id) or await self.guild.fetch_channel(d.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await self.refresh(interaction, "I can't find that channel anymore.")
        db = self.cog.bot.database

        if d.mode == "edit":
            try:
                message = await channel.fetch_message(d.message_id)
                await message.edit(view=render_blocks(d.blocks), allowed_mentions=NO_PINGS)
            except discord.NotFound:
                return await self.refresh(interaction, "That message was deleted, so it can't be edited.")
            except discord.HTTPException as err:
                return await self.refresh(interaction, f"Discord refused the change: {err.text or err}")
            await db.composed.update_one({"_id": str(d.message_id)}, {"$set": {"blocks": d.blocks, "edited_at": discord.utils.utcnow()}})
            self.cog.drafts.pop(self.user_id, None)
            return await interaction.response.edit_message(view=notice("ok", f"The message in {channel.mention} was updated.\n{message.jump_url}", "Saved"))

        try:
            sent = await channel.send(view=render_blocks(d.blocks), allowed_mentions=NO_PINGS)
        except discord.HTTPException as err:
            return await self.refresh(interaction, f"I couldn't post in {channel.mention}: {err.text or err}. "
                                                    "Give me **View Channel** and **Send Messages** there, and check that your picture links work.")
        await db.composed.insert_one({
            "_id": str(sent.id), "guild_id": d.guild_id, "channel_id": channel.id, "author_id": interaction.user.id,
            "blocks": d.blocks, "created_at": discord.utils.utcnow(),
        })
        self.cog.drafts.pop(self.user_id, None)
        await interaction.response.edit_message(view=notice(
            "ok", f"Posted in {channel.mention}.\nChange it any time with `/message edit`.\n{sent.jump_url}", "Posted!"))


# ---------------------------------------------------------------- the forms

class _BlockModal(ui.Modal):
    def __init__(self, builder: BuilderView, block: dict | None, where, title: str):
        super().__init__(title=title)
        self.builder = builder
        self.where = where  # "new" or the index being edited

    async def on_submit(self, interaction: discord.Interaction):
        b = self.builder
        if not interaction.user.guild_permissions.manage_guild or b.cog.drafts.get(b.user_id) is not b.draft:
            return await b.interaction_check(interaction)
        block, error = self.read(b.guild)
        if error:
            return await b.refresh(interaction, error)
        blocks = list(b.draft.blocks)
        if self.where == "new":
            blocks.append(block)
        else:
            blocks[self.where] = block
        why = problem(blocks)
        if why:
            return await b.refresh(interaction, why)
        b.draft.blocks = blocks
        b.draft.selected = len(blocks) - 1 if self.where == "new" else self.where
        await b.refresh(interaction)

    def read(self, guild: discord.Guild) -> tuple[dict | None, str | None]:
        raise NotImplementedError


class CardModal(_BlockModal):
    def __init__(self, builder: BuilderView, block: dict | None, where):
        super().__init__(builder, block, where, "Edit card" if block else "New card")
        guild = builder.guild
        self.body = ui.TextInput(
            label="Text (## Heading, **bold**, - lists)", style=discord.TextStyle.paragraph, max_length=MAX_TEXT,
            default=readable_mentions(block["text"], guild) if block else None, placeholder="## 📜 Rules\n• Be kind\n• Read #rules first")
        self.color = ui.TextInput(
            label=f"Color ({SAMPLE_COLORS})"[:45], required=False, max_length=20, default=_hex(block.get("color")) if block else None)
        self.thumb = ui.TextInput(
            label="Small picture on the right (link)", required=False, max_length=400, default=(block or {}).get("thumb"))
        self.image = ui.TextInput(
            label="Big picture at the bottom (link)", required=False, max_length=400, default=(block or {}).get("image"))
        self.buttons = ui.TextInput(
            label="Buttons (Label | link, one per line)", style=discord.TextStyle.paragraph, required=False, max_length=700,
            default="\n".join(f"{x['label']} | {x['url']}" for x in (block or {}).get("buttons", [])) or None)
        for item in (self.body, self.color, self.thumb, self.image, self.buttons):
            self.add_item(item)

    def read(self, guild):
        color, error = parse_color(self.color.value)
        if error:
            return None, error
        body = resolve_mentions(self.body.value.strip(), guild)  # #rules and @VIP become real links
        thumb, thumb_error = parse_image(self.thumb.value, "small picture")
        image, image_error = parse_image(self.image.value, "big picture")
        buttons, button_error = parse_buttons(self.buttons.value)
        error = ("The card needs some text." if not body else thumb_error or image_error or button_error)
        if error:
            return None, error
        return {"type": "card", "text": body, "color": color, "thumb": thumb, "image": image, "buttons": buttons}, None


class BannerModal(_BlockModal):
    def __init__(self, builder: BuilderView, block: dict | None, where):
        super().__init__(builder, block, where, "Edit banner" if block else "New banner")
        self.image = ui.TextInput(
            label="Picture link (https://…)", max_length=400, default=(block or {}).get("image"), placeholder="https://i.imgur.com/example.png")
        self.color = ui.TextInput(
            label=f"Edge color ({SAMPLE_COLORS})"[:45], required=False, max_length=20, default=_hex(block.get("color")) if block else None)
        self.add_item(self.image)
        self.add_item(self.color)

    def read(self, guild):
        color, error = parse_color(self.color.value)
        if error:
            return None, error
        image, error = parse_image(self.image.value, "banner picture")
        if error or not image:
            return None, error or "Paste a link to the banner picture."
        return {"type": "banner", "image": image, "color": color}, None


# ---------------------------------------------------------------- the command

@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Message(commands.GroupCog, name="message", description="Write rich messages like rules and announcements"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.drafts: dict[int, Draft] = {}  # user id -> the draft they're working on

    def _open(self, interaction: discord.Interaction, draft: Draft):
        self.drafts[interaction.user.id] = draft
        return interaction.response.send_message(
            view=BuilderView(self, draft, interaction.guild, interaction.user.id), ephemeral=True)

    @app_commands.command(name="create", description="Build a new message and post it")
    @app_commands.describe(channel="Where to post it (default: this channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        target = channel or interaction.channel
        await self._open(interaction, Draft(mode="post", guild_id=interaction.guild_id, channel_id=target.id))

    @app_commands.command(name="edit", description="Change a message that was made with /message")
    @app_commands.describe(message="Pick it from the list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def edit(self, interaction: discord.Interaction, message: str):
        record = await self.bot.database.composed.find_one({"_id": message.strip().rsplit("/", 1)[-1]})
        if not record or record["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(view=notice(
                "bad", "I can only edit messages made with `/message create`. Pick one from the list as you type.", "Can't find that message"), ephemeral=True)
        channel = interaction.guild.get_channel(record["channel_id"])
        try:
            if channel is None:
                raise discord.NotFound(None, "channel gone")
            await channel.fetch_message(int(record["_id"]))
        except discord.HTTPException:
            await self.bot.database.composed.delete_one({"_id": record["_id"]})
            return await interaction.response.send_message(view=notice(
                "bad", "That message was deleted, so there's nothing to edit.", "Message not found"), ephemeral=True)
        await self._open(interaction, Draft(
            mode="edit", guild_id=interaction.guild_id, channel_id=record["channel_id"], message_id=int(record["_id"]),
            blocks=[dict(b) for b in record["blocks"]], selected=0))

    @edit.autocomplete("message")
    async def edit_autocomplete(self, interaction: discord.Interaction, current: str):
        """The list of messages you can edit, newest first."""
        found = []
        async for m in self.bot.database.composed.find({"guild_id": interaction.guild_id}).sort("created_at", -1).limit(25):
            channel = interaction.guild.get_channel(m["channel_id"])
            first = next((b for b in m["blocks"] if b["type"] == "card"), m["blocks"][0])
            name = f"#{channel.name if channel else 'channel'} · {label(first)}"[:100]
            if current.lower() in name.lower() or current in m["_id"]:
                found.append(app_commands.Choice(name=name, value=m["_id"]))
        return found[:25]


async def setup(bot):
    await bot.add_cog(Message(bot))
