"""
Forward (copy) a full Telegram channel's message history into your own
private channel, using Telethon.

SETUP
-----
1. pip install telethon
2. Get api_id / api_hash from https://my.telegram.org (log in -> API development tools)
3. Fill in API_ID and API_HASH below, then run: python forward_channel.py --list-chats
   This logs you in (first time only) and prints every chat/channel you're
   in with its numeric ID, type, and @username (if any) - use this to find
   the right values for SOURCE_CHANNEL and DEST_CHANNEL.
4. Create your private channel in the Telegram app first (or let this
   script create one for you - see CREATE_DEST_CHANNEL below), then find
   it in the --list-chats output.
5. Fill in SOURCE_CHANNEL and DEST_CHANNEL and run: python forward_channel.py
6. On first run it will ask you to log in (phone number + code) and will
   save a session file (telegram_session.session) so you won't have to
   log in again on future runs.

NOTES
-----
- You must already be a member of the source channel.
- If the source channel has "restrict saving content" enabled, Telegram
  blocks forwarding/downloading server-side and this script cannot get
  around that.
- Progress is saved to progress.json so if the script crashes or you
  stop it, re-running will resume from the last successfully copied
  message instead of starting over.
- Telegram rate-limits forwarding. The script sleeps between messages
  and automatically backs off if Telegram asks it to (FloodWaitError).
"""

import argparse
import asyncio
import json
import os

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import CreateChannelRequest

# ---------------------- CONFIG ----------------------
API_ID =  ""           # <-- your api_id (int)
API_HASH = ""      # <-- your api_hash (str)

SOURCE_CHANNEL = ""   # e.g. "somechannel" or "https://t.me/somechannel"
DEST_CHANNEL = ""  # e.g. "@my_backup_channel" or a numeric id

CREATE_DEST_CHANNEL = False   # set True to have the script create the private channel for you
NEW_CHANNEL_TITLE = "My Backup Channel"
NEW_CHANNEL_ABOUT = "Personal backup copy"

DELAY_BETWEEN_MESSAGES = 1.5   # seconds; raise this if you keep hitting flood waits
PROGRESS_FILE = "progress.json"
SESSION_NAME = "telegram_session"
# ------------------------------------------------------


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"last_id": 0}


def save_progress(last_id):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"last_id": last_id}, f)


async def list_chats():
    """Print every chat/channel/group you're in, with its ID and type,
    so you can copy the right value into SOURCE_CHANNEL / DEST_CHANNEL."""
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print(f"{'ID':<15} {'Type':<10} {'Username':<25} Title")
    print("-" * 80)
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        entity_type = type(entity).__name__  # e.g. Channel, Chat, User
        username = getattr(entity, "username", None)
        username_display = f"@{username}" if username else "-"
        print(f"{dialog.id:<15} {entity_type:<10} {username_display:<25} {dialog.name}")

    await client.disconnect()


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    source = await client.get_entity(SOURCE_CHANNEL)

    if CREATE_DEST_CHANNEL:
        result = await client(CreateChannelRequest(
            title=NEW_CHANNEL_TITLE,
            about=NEW_CHANNEL_ABOUT,
            megagroup=False,
        ))
        dest = result.chats[0]
        print(f"Created new private channel: {dest.title} (id={dest.id})")
        print("Update DEST_CHANNEL in the script with this id for future runs.")
    else:
        dest = await client.get_entity(DEST_CHANNEL)

    progress = load_progress()
    last_id = progress["last_id"]

    print(f"Resuming from message id {last_id}" if last_id else "Starting from the beginning")

    count = 0
    async for message in client.iter_messages(source, reverse=True, min_id=last_id):
        if getattr(message, "action", None) is not None:
            save_progress(message.id)
            continue

        while True:
            try:
                await client.forward_messages(dest, message)
                break
            except FloodWaitError as e:
                print(f"Flood wait: sleeping {e.seconds}s as Telegram requested")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"Failed to forward message {message.id}: {e}")
                break  # skip this message and move on

        save_progress(message.id)
        count += 1
        if count % 50 == 0:
            print(f"Copied {count} messages so far (last id: {message.id})")

        await asyncio.sleep(DELAY_BETWEEN_MESSAGES)

    print(f"Done. Copied {count} messages this run.")
    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy a Telegram channel's history to another channel.")
    parser.add_argument(
        "--list-chats",
        action="store_true",
        help="List all your chats/channels/groups with their IDs and exit (use this to find SOURCE_CHANNEL / DEST_CHANNEL).",
    )
    args = parser.parse_args()

    if args.list_chats:
        asyncio.run(list_chats())
    else:
        asyncio.run(main())
