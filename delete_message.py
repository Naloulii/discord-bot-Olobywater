"""
Script standalone – supprime un message Discord par son ID.
Usage depuis la console Railway :
    python delete_message.py <message_id>
    python delete_message.py <message_id> <channel_id>   ← si salon différent du TikTok
"""
import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv

load_dotenv()

TOKEN              = os.getenv("TOKEN", "")
CHANNEL_ID_DEFAULT = os.getenv("ID_SALON_TIKTOK", "")


async def delete_message(message_id: str, channel_id: str) -> None:
    if not TOKEN:
        print("❌  Variable TOKEN manquante.")
        return
    if not channel_id:
        print("❌  Aucun salon spécifié et ID_SALON_TIKTOK absent.")
        return

    api_url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
    headers = {"Authorization": f"Bot {TOKEN}"}

    async with aiohttp.ClientSession() as session:
        async with session.delete(api_url, headers=headers) as resp:
            if resp.status == 204:
                print(f"✅  Message {message_id} supprimé du salon {channel_id}.")
            elif resp.status == 404:
                print(f"❌  Message introuvable (ID : {message_id}).")
            elif resp.status == 403:
                print("❌  Permission manquante pour supprimer ce message.")
            else:
                texte = await resp.text()
                print(f"❌  Erreur {resp.status} : {texte}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python delete_message.py <message_id> [channel_id]")
        sys.exit(1)

    msg_id  = sys.argv[1]
    chan_id  = sys.argv[2] if len(sys.argv) >= 3 else CHANNEL_ID_DEFAULT

    asyncio.run(delete_message(msg_id, chan_id))
