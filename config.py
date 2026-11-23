import os

PINK = 0xE8A7C8
DARK = 0x241B29
SOFT_PINK = 0xF6DCEB

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
