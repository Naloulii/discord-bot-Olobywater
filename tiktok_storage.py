"""
Gestion du stockage du dernier ID TikTok posté dans un fichier local.
Permet au bot de se souvenir du dernier TikTok envoyé après un redémarrage,
et d'envoyer les vidéos manquées pendant l'extinction.
"""
import os
import logging

FILE_PATH = os.path.join(os.path.dirname(__file__), "dernier_tiktok.txt")
log = logging.getLogger(__name__)


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
