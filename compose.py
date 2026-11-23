"""Rich messages made with /message: a message is a list of blocks, each shown as a card.

    banner: {"type": "banner", "image": url, "color": int | None}
    card:   {"type": "card", "text": str, "color": int | None, "thumb": url | None, "image": url | None,
             "buttons": [{"label": str, "url": str}]}
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import discord
from discord import ui

from config import PINK

# Discord allows 4000 characters of text and 40 components in one message. We stay a little under both.
MAX_TEXT = 3800
MAX_COMPONENTS = 38
MAX_BLOCKS = 8
SAMPLE_COLORS = "#E8A7C8, pink, rose, gold"

# ---------------------------------------------------------------- reading what people type

NAMED = {
    "pink": 0xE8A7C8, "blush": 0xF6DCEB, "rose": 0xC9507D, "black": 0x241B29, "white": 0xF2F3F5,
    "red": 0xF2555A, "green": 0x3FCF8E, "gold": 0xF7C948, "yellow": 0xF5D547, "orange": 0xF5A524,
    "purple": 0xA66BFF, "blue": 0x5865F2, "cyan": 0x56B6F7, "grey": 0x8E9297, "gray": 0x8E9297,
}


def parse_color(raw: str | None) -> tuple[int | None, str | None]:
    """'#ff8800', 'ff8800', 'f80' or a color name -> (value, None). Empty -> (None, None). Anything else -> (None, error)."""
    s = (raw or "").strip().lower().lstrip("#")
    if not s:
        return None, None
    if s in NAMED:
        return NAMED[s], None
    if re.fullmatch(r"[0-9a-f]{6}", s):
        return int(s, 16), None
    if re.fullmatch(r"[0-9a-f]{3}", s):
        return int("".join(c * 2 for c in s), 16), None
    return None, f'"{raw.strip()}" isn\'t a color. Use a hex code like #E8A7C8, or a name like pink, rose, gold or black.'


def parse_image(raw: str | None, label: str = "image") -> tuple[str | None, str | None]:
    """Image links must be https."""
    s = (raw or "").strip()
    if not s:
        return None, None
    parsed = urlparse(s)
    if parsed.scheme != "https" or not parsed.netloc:
        return None, f"The {label} must be a link starting with https:// (a direct link to the picture)."
    return s, None


def parse_buttons(raw: str | None) -> tuple[list[dict], str | None]:
    """One 'Label | https://link' per line, up to 5."""
    lines = [line.strip() for line in (raw or "").split("\n") if line.strip()]
    if len(lines) > 5:
        return [], "A card can have up to 5 buttons."
    buttons = []
    for line in lines:
        label, sep, url_part = line.partition("|")
        url, error = parse_image(url_part, "button link")
        if not label.strip() or not sep or error or not url:
            return [], f'Button "{line[:40]}" must look like: Join the group | https://www.roblox.com/groups/123'
        buttons.append({"label": label.strip()[:80], "url": url})
    return buttons, None


# ---------------------------------------------------------------- showing it

def render_blocks(blocks: list[dict]) -> ui.LayoutView:
    """The Discord message for a list of blocks."""
    view = ui.LayoutView(timeout=None)
    for b in blocks:
        color = b.get("color") if b.get("color") is not None else PINK
        if b["type"] == "banner":
            view.add_item(ui.Container(ui.MediaGallery(discord.MediaGalleryItem(b["image"])), accent_colour=color))
            continue
        children: list[ui.Item] = []
        if b.get("thumb"):
            children.append(ui.Section(b["text"], accessory=ui.Thumbnail(b["thumb"])))
        else:
            children.append(ui.TextDisplay(b["text"]))
        if b.get("image"):
            children.append(ui.MediaGallery(discord.MediaGalleryItem(b["image"])))
        if b.get("buttons"):
            children.append(ui.ActionRow(*(
                ui.Button(label=x["label"], style=discord.ButtonStyle.link, url=x["url"]) for x in b["buttons"]
            )))
        view.add_item(ui.Container(*children, accent_colour=color))
    return view


# ---------------------------------------------------------------- limits

def text_length(blocks: list[dict]) -> int:
    return sum(len(b.get("text", "")) for b in blocks)


def component_count(blocks: list[dict]) -> int:
    """How many of Discord's 40 components the message uses (rounded up a bit to be safe)."""
    total = 0
    for b in blocks:
        if b["type"] == "banner":
            total += 1 + 2  # container + gallery
            continue
        total += 1 + (3 if b.get("thumb") else 1) + (2 if b.get("image") else 0)
        if b.get("buttons"):
            total += 1 + len(b["buttons"])
    return total


def problem(blocks: list[dict]) -> str | None:
    """A problem that would stop this message from being sent, or None."""
    if not blocks:
        return "Add at least one card or banner first."
    if len(blocks) > MAX_BLOCKS:
        return f"A message can have up to {MAX_BLOCKS} blocks."
    chars = text_length(blocks)
    if chars > MAX_TEXT:
        return (f"Too long: one message holds {MAX_TEXT:,} characters of text and you're at {chars:,}. "
                "Put the rest in a second message.")
    if component_count(blocks) > MAX_COMPONENTS:
        return "This message has too many parts (pictures, buttons). Remove a few or split it into two messages."
    return None


def label(block: dict) -> str:
    """A short title for a block, for lists: the first line of its text without the markdown."""
    if block["type"] == "banner":
        return "Banner image"
    first = next((line for line in block["text"].split("\n") if line.strip()), "Card")
    first = re.sub(r"^[#>\-\s*_`]+", "", first)
    first = re.sub(r"[*_`]", "", first).strip()[:45]
    return first or "Card"


# ---------------------------------------------------------------- #channel and @Role while typing

def _simple(s: str | None) -> str:
    """Names are compared ignoring case, spaces and symbols, so '#rules' finds a channel called '┃📜・rules'."""
    return re.sub(r"[\W_]+", "", (s or "").lower())


_WORD = r"[^\W_][\w-]*"


def _token(sign: str) -> re.Pattern:
    return re.compile(rf"(^|[\s(\[]){re.escape(sign)}({_WORD})")


def _only(items, name: str):
    found = [x for x in items if _simple(x.name) and _simple(x.name) == _simple(name)]
    return found[0] if len(found) == 1 else None  # two with the same name: better to leave it than link the wrong one


def resolve_mentions(raw: str, guild: discord.Guild) -> str:
    """Turns typed #rules into a real channel link and @VIP into a role link, when exactly one has that name."""
    channels = list(guild.channels)
    roles = [r for r in guild.roles if r.id != guild.id]

    def channel(m):
        c = _only(channels, m.group(2))
        return f"{m.group(1)}<#{c.id}>" if c else m.group(0)

    def role(m):
        if re.fullmatch(r"(everyone|here)", m.group(2), re.I):
            return m.group(0)
        r = _only(roles, m.group(2))
        return f"{m.group(1)}<@&{r.id}>" if r else m.group(0)

    return _token("@").sub(role, _token("#").sub(channel, raw or ""))


def readable_mentions(raw: str, guild: discord.Guild) -> str:
    """The reverse, for editing: <#123> becomes #rules again (only when typing that back would find the same one)."""
    channels = list(guild.channels)
    roles = [r for r in guild.roles if r.id != guild.id]

    def back(sign: str, item_id: int, items) -> str | None:
        item = next((x for x in items if x.id == item_id), None)
        word = re.sub(r"[^\w-]+", "", item.name) if item else ""
        if word and re.match(r"[^\W_]", word) and (_only(items, word) is not None) and _only(items, word).id == item_id:
            return f"{sign}{word}"
        return None

    text = re.sub(r"<#(\d+)>", lambda m: back("#", int(m.group(1)), channels) or m.group(0), raw or "")
    return re.sub(r"<@&(\d+)>", lambda m: back("@", int(m.group(1)), roles) or m.group(0), text)
