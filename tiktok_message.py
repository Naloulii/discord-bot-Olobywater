"""
Structure du message TikTok – partagée entre main.py et post_tiktok.py.
Modifiez ce fichier pour changer le format des notifications TikTok.
"""


def formater_message(titre: str, lien: str) -> str:
    """
    Construit le message Discord pour une nouvelle vidéo TikTok.

    Paramètres
    ----------
    titre : str  – Titre de la vidéo (peut être vide si indisponible)
    lien  : str  – URL complète de la vidéo TikTok

    Format actuel :
        🎵 Nouvelle vidéo TikTok !
        **Titre de la vidéo**

        https://www.tiktok.com/...
    """
    lignes = ["🎵 **Nouvelle vidéo TikTok !**"]

    lignes.append("")          # ligne vide
    if titre:
        lignes.append(f"**{titre}**")

    lignes.append(lien)        # lien brut → Discord génère la miniature automatiquement

    return "\n".join(lignes)
