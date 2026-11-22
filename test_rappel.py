"""
Script standalone – teste l'envoi du MP de rappel Wispbyte au propriétaire du bot.
Usage :
    python test_rappel.py
"""
import asyncio
import os
from datetime import datetime, timezone

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN", "").strip()
ID_OWNER = os.getenv("ID_OWNER", "0").strip()

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"Connecté en tant que {client.user}...")
    cible = None

    if ID_OWNER and ID_OWNER != "0":
        try:
            cible = await client.fetch_user(int(ID_OWNER))
        except Exception as e:
            print(f"Erreur avec ID_OWNER : {e}")

    if not cible:
        app_info = await client.application_info()
        cible = app_info.team.owner if app_info.team else app_info.owner

    if not cible:
        print("❌ Impossible de trouver le propriétaire du bot.")
        await client.close()
        return

    print(f"Destinataire trouvé : {cible} (ID: {cible.id})")

    embed = discord.Embed(
        title="⏰ Rappel : Garde ton bot en ligne sur Wispbyte !",
        description=(
            "Salut !\n\n"
            "Ceci est ton rappel hebdomadaire pour **garder ton bot en ligne**.\n\n"
            "⚠️ **Wispbyte exige une connexion au moins une fois toutes les 2 semaines** sur leur panel.\n"
            "Pour éviter que le serveur gratuit ne s'arrête :\n\n"
            "👉 **[Clique ici pour te connecter au panel Wispbyte](https://panel.wispbyte.com)**\n\n"
            "*Une simple visite sur le panel suffit à réinitialiser le délai !*"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Rappel automatique Wispbyte • Test manuel")

    try:
        await cible.send(embed=embed)
        print(f"✅ MP de test envoyé avec succès à {cible} !")
    except discord.Forbidden:
        print(f"❌ Impossible d'envoyer le MP : les messages privés sont désactivés pour {cible}.")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")

    await client.close()


if __name__ == "__main__":
    if not TOKEN:
        print("❌ Variable TOKEN manquante dans le fichier .env")
        exit(1)
    client.run(TOKEN)
