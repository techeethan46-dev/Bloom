# Bloom Discord Bot

A modular Discord bot for Bloom, built with Python, `discord.py` 2.x, MongoDB, and Render (with UptimeRobot keeping it awake).

## What it does
- Pink and black cards, in the same friendly style as the Hard bot
- **One `/setup` screen** for everything: pick the channels and map your staff roles, step by step
- Welcome card for every new member
- Staff applications: a panel with an **Apply** button, a form, a private review channel with **Approve** and
  **Reject** buttons, and permanent buttons that keep working after a restart
- A small web page (`/health`) so Render stays happy and UptimeRobot can keep the bot awake

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
   - Read Message History
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
Run **`/setup`** in your server (you need **Manage Server**). Only you see the screen. Each time you pick a channel or role
it saves and moves to the next step:

1. **Welcome channel**: where new members are welcomed.
2. **Application review channel**: where applications arrive (make it private).
3. **Roles**: pick your server's Founder, Co-owner, Vice President, Moderator and so on. Founder, Co-owner and Vice
   President can review applications.

On the last page you can **Preview welcome** and **Post application panel** (it posts in the channel where you ran `/setup`).
Run `/setup` again any time to change something.

## Render deployment (with UptimeRobot)
1. Render: **New** > **Web Service**, connect this GitHub repo.
   - Runtime: Python 3 · Build command: `pip install -r requirements.txt` · Start command: `python main.py`
   - Plan: Free · **Health Check Path:** `/health`
2. **Environment** tab, add: `DISCORD_TOKEN`, `MONGODB_URI`, and optionally `MONGODB_DATABASE` (`bloom_bot`) and
   `GUILD_ID`. Never put these in the code.
3. In Discord's Developer Portal turn on **Server Members Intent** (Bot tab).
4. When the deploy says **Your service is live**, copy the service address (like `https://bloom-bot.onrender.com`).
5. UptimeRobot: **Add New Monitor** > type **HTTP(s)** > URL `https://<your-service>.onrender.com/health` > every **5 minutes**.
   This keeps the free service awake.

## Tests
```bash
pip install pytest
python -m pytest tests
```

## Important Discord details
- Bloom doesn't give out roles, so the role mapping can include any role, even ones above the bot.
- Staff application approval is intentionally limited to Founder, Co-owner, and Vice President by default. Adjust in `config.py` if Bloom wants a different review policy.
- The starter records application submissions and decisions in MongoDB. Approval does not automatically grant a role: the reviewer should assign the appropriate staff role after checking the application.
- `/setup` needs the **Manage Server** permission.
