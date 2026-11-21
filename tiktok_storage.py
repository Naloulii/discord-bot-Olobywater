"""
Gestion du stockage du dernier ID TikTok posté dans un fichier local et sur GitHub.
Permet au bot de se souvenir du dernier TikTok envoyé après un redémarrage,
et de mettre à jour directement le dépôt GitHub via l'API GitHub.
"""
import base64
import logging
import os
import aiohttp

FILE_PATH = os.path.join(os.path.dirname(__file__), "dernier_tiktok.txt")
log = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "Naloulii/discord-bot-Olobywater").strip()


def lire_dernier_tiktok_id() -> str | None:
    """Lit l'ID du dernier TikTok posté depuis le fichier local."""
    if not os.path.exists(FILE_PATH):
        return None
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            video_id = f.read().strip()
            return video_id if video_id else None
    except Exception as e:
        log.warning("Impossible de lire %s : %s", FILE_PATH, e)
        return None


def sauvegarder_dernier_tiktok_id(video_id: str) -> None:
    """Sauvegarde l'ID du dernier TikTok posté dans le fichier local."""
    try:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(video_id.strip())
        log.info("ID TikTok sauvegardé dans dernier_tiktok.txt : %s", video_id)
    except Exception as e:
        log.warning("Impossible d'écrire dans %s : %s", FILE_PATH, e)


async def push_dernier_tiktok_github(video_id: str) -> bool:
    """
    Met à jour et committe dernier_tiktok.txt directement sur GitHub via l'API REST.
    Nécessite la variable d'environnement GITHUB_TOKEN.
    """
    if not GITHUB_TOKEN:
        log.debug("GITHUB_TOKEN non configuré, le push GitHub est ignoré.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/dernier_tiktok.txt"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "discord-bot-Olobywater",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Obtenir le SHA actuel du fichier sur GitHub
            sha = None
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sha = data.get("sha")
                elif resp.status != 404:
                    text = await resp.text()
                    log.warning("GitHub API: Erreur lors de la lecture du fichier (%d) : %s", resp.status, text)
                    return False

            # 2. Préparer le contenu en base64
            contenu_b64 = base64.b64encode(f"{video_id.strip()}\n".encode("utf-8")).decode("utf-8")
            body = {
                "message": f"Update dernier_tiktok.txt to {video_id.strip()}",
                "content": contenu_b64,
            }
            if sha:
                body["sha"] = sha

            # 3. Envoyer la mise à jour (PUT)
            async with session.put(url, headers=headers, json=body) as resp:
                if resp.status in (200, 201):
                    log.info("✅ dernier_tiktok.txt mis à jour et pushé sur GitHub (%s)", video_id.strip())
                    return True
                else:
                    text = await resp.text()
                    log.warning("❌ Échec de la mise à jour sur GitHub (%d) : %s", resp.status, text)
                    return False

    except Exception as e:
        log.warning("Erreur réseau lors de la mise à jour GitHub : %s", e)
        return False
