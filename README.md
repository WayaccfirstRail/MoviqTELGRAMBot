# Captain M Telegram Bot

This is an Arabic Telegram bot for the Captain M platform that provides movie and series listings, website status checking, and administrative controls.

## Features

- 🎬 **Movie Listings**: Browse available movies in Arabic
- 📺 **Series Listings**: View available TV series
- 🌐 **Website Status**: Check if Captain M website is online
- 🔐 **Invite Codes**: Manage and share invite codes
- 👮 **Admin Controls**: Ban, block, and flag users
- 🇸🇦 **Arabic Language**: Full Arabic language support

## Setup Instructions

### 1. Get a Telegram Bot Token

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot with `/newbot`
3. Choose a name and username for your bot
4. Copy the bot token

### 2. Configure Environment Variables

In Replit Secrets, add:
- `BOT_TOKEN`: Your Telegram bot token

### 3. Configure Admin IDs

Edit the `ADMIN_IDS` list in `main.py` with your Telegram user IDs:

```python
ADMIN_IDS: List[int] = [YOUR_USER_ID_HERE]
