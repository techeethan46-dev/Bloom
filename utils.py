import discord
from config import PINK, DARK, ROLE_LABELS

def bloom_embed(title: str, description: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=PINK,
    )
    embed.set_footer(text="Bloom • Growing together")
    return embed

async def has_any_bloom_role(member: discord.Member, settings: dict, keys: tuple[str, ...]) -> bool:
    role_map = settings.get("roles", {})
    allowed_ids = {int(role_map[key]) for key in keys if role_map.get(key)}
    return any(role.id in allowed_ids for role in member.roles)

def role_mentions(settings: dict) -> str:
    role_map = settings.get("roles", {})
    lines = []
    for key, label in ROLE_LABELS.items():
        role_id = role_map.get(key)
        lines.append(f"**{label}:** <@&{role_id}>" if role_id else f"**{label}:** Not configured")
    return "\n".join(lines)
