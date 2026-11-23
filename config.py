import os

# Bloom's colors: pink and black.
PINK = 0xE8A7C8       # the main accent on every card
DARK = 0x241B29
SOFT_PINK = 0xF6DCEB  # gentle notes and warnings
ROSE = 0xC9507D       # errors and "no"
GREEN = 0x7BC8A4      # approved

DATABASE_NAME = os.getenv("MONGODB_DATABASE", "bloom_bot")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

# Default policy: only top leadership can review applications.
APPLICATION_REVIEW_KEYS = ("founder", "co_owner", "vice_president")

ROLE_KEYS = (
    "founder",
    "co_owner",
    "vice_president",
    "moderator",
    "commander",
    "recruit_manager",
    "left_right_hand",
    "deputy",
    "member",
    "unranked",
    "jailed",
)

ROLE_LABELS = {
    "founder": "Founder",
    "co_owner": "Co-owner",
    "vice_president": "Vice President",
    "moderator": "Moderator",
    "commander": "Commander",
    "recruit_manager": "Recruit Manager",
    "left_right_hand": "Left/Right Hand",
    "deputy": "Deputy",
    "member": "Member",
    "unranked": "Unranked",
    "jailed": "Jailed",
}
