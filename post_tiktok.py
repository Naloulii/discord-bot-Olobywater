"""
Script standalone – poste une vidéo TikTok dans le salon de notifications.
Usage depuis la console Railway :
    python post_tiktok.py https://www.tiktok.com/@olobywater/video/XXXXXXXXX
"""
import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv

from tiktok_message import formater_message

load_dotenv()

TOKEN      = os.getenv("TOKEN", "")
CHANNEL_ID = os.getenv("ID_SALON_TIKTOK", "")


async def post_tiktok(lien: str) -> None:
    if not TOKEN:
        print("❌  Variable TOKEN manquante.")
        return
    if not CHANNEL_ID:
        print("❌  Variable ID_SALON_TIKTOK manquante.")
        return
    if "tiktok.com" not in lien:
        print("❌  Le lien doit être une URL TikTok.")
        return

    # Récupération du titre via l'API oEmbed publique de TikTok
    titre = ""
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={lien}"
        async with aiohttp.ClientSession() as session:
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    titre = data.get("title", "")
    except Exception:
        pass  # Titre indisponible, on continue sans

    # Construction du message (même format que la notification automatique)
    contenu = formater_message(titre, lien)

    api_url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json={"content": contenu}) as resp:
            if resp.status in (200, 201):
                print(f"✅  Vidéo postée dans le salon ({CHANNEL_ID}).")
            else:
                texte = await resp.text()
                print(f"❌  Erreur {resp.status} : {texte}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python post_tiktok.py <lien_tiktok>")
        sys.exit(1)
    asyncio.run(post_tiktok(sys.argv[1]))
