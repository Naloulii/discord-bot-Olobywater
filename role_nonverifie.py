"""
Script standalone – ajoute ou retire le rôle Non-vérifié à un membre.
Usage depuis la console Railway :
    python role_nonverifie.py ajouter <user_id>
    python role_nonverifie.py retirer <user_id>
"""
import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv

load_dotenv()

TOKEN              = os.getenv("TOKEN", "").strip()
ID_ROLE_NONVERIFIE = os.getenv("ID_ROLE_NONVERIFIE", "").strip()


async def get_guild_id(session: aiohttp.ClientSession) -> str | None:
    """Récupère automatiquement l'ID du premier serveur où est le bot."""
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with session.get("https://discord.com/api/v10/users/@me/guilds", headers=headers) as resp:
        if resp.status == 200:
            guilds = await resp.json()
            if guilds:
                return guilds[0]["id"]
    return None


async def modifier_role(action: str, user_id: str) -> None:
    if not TOKEN:
        print("❌  Variable TOKEN manquante.")
        return
    if not ID_ROLE_NONVERIFIE or ID_ROLE_NONVERIFIE == "0":
        print("❌  Variable ID_ROLE_NONVERIFIE manquante ou = 0.")
        return

    headers = {"Authorization": f"Bot {TOKEN}"}

    async with aiohttp.ClientSession() as session:
        guild_id = await get_guild_id(session)
        if not guild_id:
            print("❌  Impossible de trouver le serveur Discord du bot.")
            return

        method = "PUT" if action == "ajouter" else "DELETE"
        url    = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{ID_ROLE_NONVERIFIE}"

        async with session.request(method, url, headers=headers) as resp:
            if resp.status == 204:
                verbe = "ajouté à" if action == "ajouter" else "retiré de"
                print(f"✅  Rôle Non-vérifié {verbe} l'utilisateur {user_id}.")
            elif resp.status == 404:
                print(f"❌  Utilisateur {user_id} introuvable sur le serveur.")
            elif resp.status == 403:
                print("❌  Permission manquante pour modifier ce membre.")
            else:
                texte = await resp.text()
                print(f"❌  Erreur {resp.status} : {texte}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("ajouter", "retirer"):
        print("Usage :")
        print("  python role_nonverifie.py ajouter <user_id>")
        print("  python role_nonverifie.py retirer <user_id>")
        sys.exit(1)

    asyncio.run(modifier_role(sys.argv[1], sys.argv[2]))
