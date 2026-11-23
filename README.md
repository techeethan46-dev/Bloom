# Bloom Discord Bot

A modular Discord bot for Bloom, built with Python, `discord.py` 2.x, MongoDB, and Render Background Workers.

## Features in this starter
- Pink/black branded embeds
- MongoDB persistence
- Slash-command setup and diagnostics
- Configurable welcome messages
- Staff application panel, modal submissions, private review channel, approve/reject actions
- Staff role mapping and permission checks
- Persistent application review buttons after restart

## Requirements
- Python 3.11+
- Discord application + bot token
- MongoDB Atlas database and connection string
- Render account

## Local setup
1. Create a Discord application at https://discord.com/developers/applications.
2. Add a Bot user and enable the **Server Members Intent** under Bot > Privileged Gateway Intents.
3. Invite the bot with `bot` and `applications.commands` scopes. Grant only the permissions it needs:
   - View Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Manage Roles (only if you want auto-role assignment)
4. Create a MongoDB Atlas database and obtain its connection string.
5. Copy `.env.example` to `.env`, then fill in the values.
6. Install dependencies:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
7. Start:
   ```bash
   python main.py
   ```

## First Discord setup
Use `/bloom_setup` in the server. The command is restricted to members with Manage Server or Administrator permission.

Then:
1. `/bloom_config` to set welcome and application-review channels.
2. `/bloom_roles` to map the server's actual role IDs to Bloom role types.
3. `/bloom_welcome_test` to test the welcome embed.
4. `/bloom_application_panel` to post the application panel.

### Role mapping keys
`founder`, `co_owner`, `vice_president`, `moderator`, `commander`, `recruit_manager`, `left_right_hand`, `deputy`, `member`, `unranked`, `jailed`

The bot does not create or rename roles automatically. Map existing roles using their IDs. The founder/co-owner IDs should be mapped carefully.

## Render deployment
Create a **Background Worker** (not a sleeping web service):
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`

Set these environment variables in Render:
- `DISCORD_TOKEN`
- `MONGODB_URI`
- `MONGODB_DATABASE` (for example `bloom_bot`)
- `GUILD_ID` (optional during development; recommended for fast command sync to one server)

Do not put secrets in source code or commit `.env`.

## Important Discord details
- The bot can only manage roles that are **below the bot's highest role** in the server role list.
- Staff application approval is intentionally limited to Founder, Co-owner, and Vice President by default. Adjust in `config.py` if Bloom wants a different review policy.
- The starter records application submissions and decisions in MongoDB. Approval does not automatically grant a role: the reviewer should assign the appropriate staff role after checking the application.
- `/bloom_roles` and `/bloom_config` are administrator-only configuration commands.
