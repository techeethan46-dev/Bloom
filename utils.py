"""Small helpers for building Bloom's pink cards (Discord "Components V2" messages)."""
from __future__ import annotations

import discord
from discord import ui

from config import PINK, ROLE_LABELS, ROSE, SOFT_PINK


def text(*lines: str | None) -> ui.TextDisplay:
    """A block of text. Empty (None) lines are skipped."""
    return ui.TextDisplay("\n".join(line for line in lines if line is not None))


def divider() -> ui.Separator:
    return ui.Separator()


def card(*children: ui.Item, color: int = PINK) -> ui.Container:
    """A card: a box with a colored bar on the left."""
    return ui.Container(*children, accent_colour=color)


def card_view(*cards: ui.Item, timeout: float | None = 180) -> ui.LayoutView:
    """A message made of one or more cards."""
    view = ui.LayoutView(timeout=timeout)
    for item in cards:
        view.add_item(item)
    return view


_NOTICE_STYLES = {
    "ok": ("🌷", PINK),
    "warn": ("🌼", SOFT_PINK),
    "bad": ("🥀", ROSE),
}


def notice(kind: str, message: str, title: str | None = None) -> ui.LayoutView:
    """A short pink message: kind is 'ok', 'warn' or 'bad'."""
    icon, color = _NOTICE_STYLES[kind]
    head = f"### {icon} {title}" if title else None
    return card_view(card(text(head, message), color=color))


def has_any_bloom_role(member: discord.Member, settings: dict, keys: tuple[str, ...]) -> bool:
    role_map = settings.get("roles", {})
    allowed_ids = {int(role_map[key]) for key in keys if role_map.get(key)}
    return any(role.id in allowed_ids for role in member.roles)


def role_mentions(settings: dict) -> str:
    role_map = settings.get("roles", {})
    lines = []
    for key, label in ROLE_LABELS.items():
        role_id = role_map.get(key)
        lines.append(f"**{label}** · <@&{role_id}>" if role_id else f"**{label}** · *not set*")
    return "\n".join(lines)
