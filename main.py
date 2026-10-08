"""
Bot Discord de validation par présentation.
Aucune base de données : tout l'état persistant est encodé dans les custom_id.
Compatible avec les hébergeurs à faible RAM et redémarrages fréquents.
"""

# ─────────────────────────── Imports ────────────────────────────────────────
import os
import re
import logging
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import aiohttp
import discord
import yt_dlp
from discord.ext import commands, tasks
from dotenv import load_dotenv

from tiktok_message import formater_message
from tiktok_storage import lire_dernier_tiktok_id, sauvegarder_dernier_tiktok_id

# ─────────────────────────── Logging ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────── Variables d'environnement ──────────────────────
load_dotenv()

def _env(name: str) -> str:
    """Récupère une variable d'environnement ou lève une erreur claire."""
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(
            f"❌  Variable d'environnement manquante : {name}\n"
            "   Vérifiez votre fichier .env ou les variables de votre hébergeur."
        )
    return val

def _env_optional(name: str) -> int:
    """Récupère un ID optionnel ; retourne 0 si absent ou invalide (= création auto)."""
    val = os.getenv(name, "0").strip()
    try:
        return int(val)
    except ValueError:
        return 0

TOKEN              = _env("TOKEN")
ID_PRESENTATION    = int(_env("ID_PRESENTATION"))
ID_VALIDATION      = _env_optional("ID_VALIDATION")       # 0 = sera créé au démarrage
ID_ROLE_NONVERIFIE = _env_optional("ID_ROLE_NONVERIFIE")  # 0 = sera créé au démarrage
ID_ROLE_MODO       = int(_env("ID_ROLE_MODO"))
ID_SALON_TIKTOK    = _env_optional("ID_SALON_TIKTOK")     # salon de notif TikTok

# URL du compte TikTok à surveiller directement via yt-dlp (sans service RSS payant)
TIKTOK_USER_URL = os.getenv(
    "TIKTOK_USER_URL",
    "https://www.tiktok.com/@olobywater"
)

# ─────────────────────────── État en mémoire ────────────────────────────────
# Set des user_id dont la présentation est en attente de validation.
# Perdu au redémarrage, sans conséquence grave (les boutons fonctionnent sans).
en_attente: set[int] = set()

# Dernière vidéo TikTok connue (guid RSS). None = non initialisé.
# Au 1er passage de la tâche : on mémorise sans notifier (évite le spam au restart).
dernier_video_id: str | None = None

# ─────────────────────────── Intents & Bot ──────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class MonBot(commands.Bot):
    """Bot principal avec setup_hook pour enregistrer les DynamicItems."""

    async def setup_hook(self) -> None:
        # Enregistrement des boutons persistants (survie aux redémarrages)
        self.add_dynamic_items(BoutonAccepter, BoutonRefuser, MenuSanction)
        # Lancement unique de la tâche de débannissement temporaire
        if not verif_tempbans.is_running():
            verif_tempbans.start()
        # Lancement de la surveillance TikTok (si salon configuré)
        if ID_SALON_TIKTOK and not verif_tiktok.is_running():
            verif_tiktok.start()
        log.info("setup_hook terminé – DynamicItems et tâches de fond enregistrées.")

bot = MonBot(command_prefix="!", intents=intents)

# ═══════════════════════════════════════════════════════════════════════════
#  DYNAMIC ITEMS – Bouton Accepter
# ═══════════════════════════════════════════════════════════════════════════
class BoutonAccepter(discord.ui.DynamicItem[discord.ui.Button],
                     template=r"accepter:(?P<user_id>\d+)"):
    """Bouton vert « Accepter » encodant l'user_id dans son custom_id."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(
            discord.ui.Button(
                label="✅  Accepter",
                style=discord.ButtonStyle.success,
                custom_id=f"accepter:{user_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        # Vérification du rôle Modérateur
        role_modo = interaction.guild.get_role(ID_ROLE_MODO)
        if role_modo not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Vous devez être Modérateur pour effectuer cette action.",
                ephemeral=True,
            )
            return

        # Anti-double traitement : vérifie si les boutons sont déjà désactivés
        if interaction.message.components:
            first_button = interaction.message.components[0].children[0]
            if first_button.disabled:
                await interaction.response.send_message(
                    "⚠️ Cette présentation a déjà été traitée.", ephemeral=True
                )
                return

        await interaction.response.defer()

        # Retrait du rôle Non-vérifié
        role_nv = interaction.guild.get_role(ID_ROLE_NONVERIFIE)
        member = interaction.guild.get_member(self.user_id)
        if member:
            try:
                await member.remove_roles(role_nv, reason="Présentation acceptée")
                log.info("Rôle Non-vérifié retiré de %s", member)
            except discord.Forbidden:
                log.warning("Permission manquante pour retirer le rôle à %s", member)
        else:
            log.info("Membre %d introuvable (a peut-être quitté le serveur).", self.user_id)

        # MP de bienvenue
        if member:
            try:
                await member.send(
                    "🎉 **Bienvenue !** Ta présentation a été acceptée par les modérateurs. "
                    "Tu as maintenant accès à l'ensemble du serveur. Bonne discussion !"
                )
            except discord.Forbidden:
                log.info("MP impossible pour %s (messages privés fermés).", member)

        # Mise à jour de l'embed et désactivation des boutons
        await _finaliser_embed(
            interaction.message,
            couleur=discord.Color.green(),
            footer=f"Accepté par {interaction.user} ✅",
        )
        en_attente.discard(self.user_id)
        log.info("Présentation de %d acceptée par %s.", self.user_id, interaction.user)


# ═══════════════════════════════════════════════════════════════════════════
#  DYNAMIC ITEMS – Bouton Refuser
# ═══════════════════════════════════════════════════════════════════════════
class BoutonRefuser(discord.ui.DynamicItem[discord.ui.Button],
                    template=r"refuser:(?P<user_id>\d+):(?P<msg_id>\d+)"):
    """Bouton rouge « Refuser » encodant user_id et msg_id dans son custom_id."""

    def __init__(self, user_id: int, msg_id: int):
        self.user_id = user_id
        self.msg_id  = msg_id
        super().__init__(
            discord.ui.Button(
                label="❌  Refuser",
                style=discord.ButtonStyle.danger,
                custom_id=f"refuser:{user_id}:{msg_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["user_id"]), int(match["msg_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        # Vérification du rôle Modérateur
        role_modo = interaction.guild.get_role(ID_ROLE_MODO)
        if role_modo not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Vous devez être Modérateur pour effectuer cette action.",
                ephemeral=True,
            )
            return

        # Anti-double traitement
        if interaction.message.components:
            first_button = interaction.message.components[0].children[0]
            if first_button.disabled:
                await interaction.response.send_message(
                    "⚠️ Cette présentation a déjà été traitée.", ephemeral=True
                )
                return

        # Affichage du menu de sanction (éphémère, transmis via custom_id)
        view = discord.ui.View(timeout=None)
        view.add_item(MenuSanction(self.user_id, self.msg_id))
        await interaction.response.send_message(
            "⚖️ **Choisissez la sanction à appliquer :**",
            view=view,
            ephemeral=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
#  DYNAMIC ITEMS – Menu déroulant de sanction
# ═══════════════════════════════════════════════════════════════════════════
SANCTIONS = {
    "kick":    "Expulsion (kick)",
    "ban_1":   "Ban 1 jour",
    "ban_7":   "Ban 7 jours",
    "ban_30":  "Ban 30 jours",
    "ban_def": "Ban définitif",
}

class MenuSanction(discord.ui.DynamicItem[discord.ui.Select],
                   template=r"sanction:(?P<user_id>\d+):(?P<msg_id>\d+)"):
    """Menu déroulant de sanction ; user_id et msg_id encodés dans le custom_id."""

    def __init__(self, user_id: int, msg_id: int):
        self.user_id = user_id
        self.msg_id  = msg_id
        super().__init__(
            discord.ui.Select(
                placeholder="Sélectionnez une sanction…",
                custom_id=f"sanction:{user_id}:{msg_id}",
                options=[
                    discord.SelectOption(label=label, value=value)
                    for value, label in SANCTIONS.items()
                ],
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["user_id"]), int(match["msg_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        # Répondre immédiatement pour respecter la limite de 3 secondes Discord
        await interaction.response.defer(ephemeral=True)

        choix      = self.values[0]
        modo       = interaction.user
        guild      = interaction.guild
        label_sanc = SANCTIONS.get(choix, choix)

        # Vérification des permissions via guild_permissions (fiable sur éphémère)
        gperms = interaction.user.guild_permissions
        if choix == "kick" and not gperms.kick_members:
            await interaction.followup.send(
                "❌ Vous n'avez pas la permission d'expulser des membres.", ephemeral=True
            )
            return
        if choix.startswith("ban") and not gperms.ban_members:
            await interaction.followup.send(
                "❌ Vous n'avez pas la permission de bannir des membres.", ephemeral=True
            )
            return


        member = guild.get_member(self.user_id)
        motif  = f"Présentation refusée par {modo}"

        # 1. MP AVANT l'action (car après ban, plus de serveur commun)
        if member:
            try:
                await member.send(
                    f"❌ Ta présentation a été **refusée** par les modérateurs.\n"
                    f"Sanction appliquée : **{label_sanc}**."
                )
            except discord.Forbidden:
                pass

        # 2. Application de la sanction
        if choix == "kick":
            if member:
                try:
                    await member.kick(reason=motif)
                    log.info("Kick appliqué à %d par %s.", self.user_id, modo)
                except discord.Forbidden:
                    log.warning("Permission manquante pour kick %d.", self.user_id)
        else:
            # Calcul de la durée pour les bans temporaires
            durees = {"ban_1": 1, "ban_7": 7, "ban_30": 30}
            if choix in durees:
                fin = datetime.now(timezone.utc) + timedelta(days=durees[choix])
                motif_ban = f"TEMPBAN|{fin.isoformat()}|{motif}"
            else:
                motif_ban = motif
            try:
                await guild.ban(
                    discord.Object(id=self.user_id),
                    reason=motif_ban,
                    delete_message_days=0,
                )
                log.info("Ban (%s) appliqué à %d par %s.", choix, self.user_id, modo)
            except discord.Forbidden:
                log.warning("Permission manquante pour ban %d.", self.user_id)
            except discord.NotFound:
                log.info("Membre %d introuvable pour ban.", self.user_id)

        # 3. Mise à jour de l'embed dans #validation-modos
        try:
            chan_val = guild.get_channel(ID_VALIDATION)
            msg_val  = await chan_val.fetch_message(self.msg_id)
            await _finaliser_embed(
                msg_val,
                couleur=discord.Color.red(),
                footer=f"Refusé par {modo} ❌ — {label_sanc}",
            )
        except (discord.NotFound, discord.HTTPException) as e:
            log.warning("Impossible de mettre à jour le message de validation : %s", e)

        # 4. Nettoyage du set en mémoire
        en_attente.discard(self.user_id)
        await interaction.followup.send(
            f"✅ Sanction **{label_sanc}** appliquée.", ephemeral=True
        )
        log.info("Sanction '%s' appliquée à %d par %s.", choix, self.user_id, modo)


# ─────────────────────────── Helpers ────────────────────────────────────────
async def _finaliser_embed(message: discord.Message,
                           couleur: discord.Color,
                           footer: str) -> None:
    """Modifie l'embed du message de validation et désactive tous les boutons."""
    if not message.embeds:
        return
    embed = message.embeds[0]
    embed.colour = couleur
    embed.set_footer(text=footer)

    # Désactivation de tous les boutons de la vue
    new_view = discord.ui.View.from_message(message, timeout=None)
    for child in new_view.children:
        child.disabled = True

    try:
        await message.edit(embed=embed, view=new_view)
    except (discord.NotFound, discord.HTTPException) as e:
        log.warning("Impossible d'éditer le message de validation : %s", e)


def _build_validation_view(user_id: int, msg_id: int) -> discord.ui.View:
    """Construit la vue avec Accepter + Refuser pour le salon de validation."""
    view = discord.ui.View(timeout=None)
    view.add_item(BoutonAccepter(user_id))
    view.add_item(BoutonRefuser(user_id, msg_id))
    return view


async def _configurer_permissions_role(guild: discord.Guild,
                                       role_nv: discord.Role) -> None:
    """
    Configure les permissions du rôle Non-vérifié sur tout le serveur :
    - Bloque 'Voir les salons' sur toutes les catégories et salons sans catégorie
    - Autorise uniquement #présentation (voir + écrire)
    """
    deny_all  = discord.PermissionOverwrite(view_channel=False, connect=False)
    allow_pres = discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        connect=False,   # pas de vocal
    )

    # Bloquer sur toutes les catégories (couvre leurs salons texte et vocaux)
    for category in guild.categories:
        try:
            await category.set_permissions(role_nv, overwrite=deny_all,
                                           reason="Config auto Non-vérifié")
            log.info("🔒 Catégorie '%s' bloquée pour Non-vérifié.", category.name)
        except discord.Forbidden:
            log.warning("Permission manquante pour modifier la catégorie '%s'.", category.name)

    # Bloquer également les salons sans catégorie
    for channel in guild.channels:
        if channel.category is None and not isinstance(channel, discord.CategoryChannel):
            try:
                await channel.set_permissions(role_nv, overwrite=deny_all,
                                              reason="Config auto Non-vérifié")
                log.info("🔒 Salon '%s' (sans catégorie) bloqué.", channel.name)
            except discord.Forbidden:
                log.warning("Permission manquante pour le salon '%s'.", channel.name)

    # Autoriser uniquement #présentation
    chan_pres = guild.get_channel(ID_PRESENTATION)
    if chan_pres:
        try:
            await chan_pres.set_permissions(role_nv, overwrite=allow_pres,
                                            reason="Config auto Non-vérifié")
            log.info("✅ #%s ouvert pour Non-vérifié.", chan_pres.name)
        except discord.Forbidden:
            log.warning("Permission manquante pour configurer #présentation.")
    else:
        log.warning("Salon #présentation (ID %d) introuvable pour config des perms.", ID_PRESENTATION)


# ═══════════════════════════════════════════════════════════════════════════
#  ÉVÉNEMENTS
# ═══════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready() -> None:
    log.info("Bot connecté en tant que %s (ID %d).", bot.user, bot.user.id)

    global ID_VALIDATION, ID_ROLE_NONVERIFIE

    for guild in bot.guilds:
        # ── Création automatique du rôle "Non-vérifié" si ID = 0 ──────────────
        if ID_ROLE_NONVERIFIE == 0:
            role_nv = discord.utils.get(guild.roles, name="Non-vérifié")
            if not role_nv:
                try:
                    role_nv = await guild.create_role(
                        name="Non-vérifié",
                        colour=discord.Colour.greyple(),
                        reason="Création automatique par le bot",
                    )
                    log.info(
                        "✅ Rôle 'Non-vérifié' créé (ID : %d). "
                        "Ajoutez  ID_ROLE_NONVERIFIE=%d  dans votre .env !",
                        role_nv.id, role_nv.id,
                    )
                except discord.Forbidden:
                    log.error("❌ Permission manquante pour créer le rôle 'Non-vérifié'.")
                    role_nv = None
            else:
                log.info("Rôle 'Non-vérifié' trouvé (ID : %d). "
                         "Ajoutez  ID_ROLE_NONVERIFIE=%d  dans votre .env !",
                         role_nv.id, role_nv.id)
            if role_nv:
                ID_ROLE_NONVERIFIE = role_nv.id
                # Configuration automatique des permissions sur tout le serveur
                await _configurer_permissions_role(guild, role_nv)

        # ── Création automatique du salon #validation-modos si ID = 0 ─────────
        if ID_VALIDATION == 0:
            chan_val = discord.utils.get(guild.text_channels, name="validation-modos")
            if not chan_val:
                try:
                    # Récupère l'overwrite de @everyone (refuser Voir les salons)
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    }
                    role_modo = guild.get_role(ID_ROLE_MODO)
                    if role_modo:
                        overwrites[role_modo] = discord.PermissionOverwrite(view_channel=True)
                    overwrites[guild.me] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, embed_links=True
                    )
                    chan_val = await guild.create_text_channel(
                        "validation-modos",
                        overwrites=overwrites,
                        reason="Création automatique par le bot",
                    )
                    log.info(
                        "✅ Salon #validation-modos créé (ID : %d). "
                        "Ajoutez  ID_VALIDATION=%d  dans votre .env !",
                        chan_val.id, chan_val.id,
                    )
                except discord.Forbidden:
                    log.error("❌ Permission manquante pour créer le salon #validation-modos.")
                    chan_val = None
            else:
                log.info("Salon #validation-modos trouvé (ID : %d). "
                         "Ajoutez  ID_VALIDATION=%d  dans votre .env !",
                         chan_val.id, chan_val.id)
            if chan_val:
                ID_VALIDATION = chan_val.id

        # ── Rattrapage des membres arrivés pendant l'absence du bot (≤ 5 min) ──
        role_nv   = guild.get_role(ID_ROLE_NONVERIFIE)
        role_modo = guild.get_role(ID_ROLE_MODO)
        if not role_nv:
            log.warning("[%s] Rôle Non-vérifié introuvable.", guild.name)
            continue

        chan_pres = guild.get_channel(ID_PRESENTATION)
        limite    = datetime.now(timezone.utc) - timedelta(minutes=5)

        for member in guild.members:
            if member.bot:
                continue
            if member.joined_at and member.joined_at > limite:
                if role_nv not in member.roles and role_modo not in member.roles:
                    try:
                        await member.add_roles(role_nv, reason="Rattrapage au démarrage")
                        log.info("Rôle Non-vérifié ajouté (rattrapage) à %s.", member)
                    except discord.Forbidden:
                        log.warning("Permission manquante pour ajouter le rôle à %s.", member)
                        continue

                    # Message de bienvenue dans #présentation (comme on_member_join)
                    if chan_pres:
                        try:
                            await chan_pres.send(
                                f"👋 Bienvenue {member.mention} !\n\n"
                                "Pour accéder au serveur, **présente-toi en un seul message** :\n"
                                "• Ton âge\n• Tes centres d'intérêt\n• Pourquoi tu rejoins ce serveur\n\n"
                                "⚠️ Minimum **50 caractères**. Ta présentation sera examinée par les modérateurs."
                            )
                        except discord.HTTPException as e:
                            log.warning("Impossible d'envoyer le message de rattrapage pour %s : %s", member, e)


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Attribution du rôle Non-vérifié et message de bienvenue."""
    if member.bot:
        return

    role_nv = member.guild.get_role(ID_ROLE_NONVERIFIE)
    if role_nv:
        try:
            await member.add_roles(role_nv, reason="Nouveau membre")
        except discord.Forbidden:
            log.warning("Permission manquante pour ajouter le rôle à %s.", member)

    chan = member.guild.get_channel(ID_PRESENTATION)
    if chan:
        await chan.send(
            f"👋 Bienvenue {member.mention} !\n\n"
            "Pour accéder au serveur, **présente-toi en un seul message** :\n"
            "• Ton Pseudo (Twitch / TikTok)\n• Ton âge\n• Tes centres d'intérêt\n• Pourquoi tu rejoins ce serveur\n\n"
            "⚠️ Minimum **50 caractères**. Ta présentation sera examinée par les modérateurs."
        )
    log.info("Nouveau membre : %s. Rôle Non-vérifié attribué.", member)


@bot.event
async def on_message(message: discord.Message) -> None:
    """Traitement des présentations dans #présentation."""
    if message.author.bot:
        return
    if not message.guild:
        return
    if message.channel.id != ID_PRESENTATION:
        await bot.process_commands(message)
        return

    role_nv = message.guild.get_role(ID_ROLE_NONVERIFIE)
    # On n'interagit qu'avec les membres Non-vérifiés
    if not role_nv or role_nv not in message.author.roles:
        return

    # Présentation trop courte
    if len(message.content) < 50:
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await message.channel.send(
            f"{message.author.mention} ❌ Ton message est trop court "
            f"({len(message.content)} caractères). Minimum **50 caractères** requis.",
            delete_after=8,
        )
        return

    # Présentation déjà en attente
    if message.author.id in en_attente:
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await message.channel.send(
            f"{message.author.mention} ⏳ Ta présentation est déjà en cours d'examen. "
            "Merci de patienter !",
            delete_after=8,
        )
        return

    # ✅ Présentation valide : ajout au set et transmission aux modos
    en_attente.add(message.author.id)
    try:
        await message.add_reaction("✅")
    except discord.HTTPException:
        pass

    chan_val = message.guild.get_channel(ID_VALIDATION)
    if not chan_val:
        log.error("Salon de validation (ID %d) introuvable.", ID_VALIDATION)
        return

    embed = discord.Embed(
        title="📋 Nouvelle présentation",
        description=message.content,
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(
        name=str(message.author),
        icon_url=message.author.display_avatar.url,
    )
    embed.add_field(
        name="📅 Compte créé le",
        value=discord.utils.format_dt(message.author.created_at, "D"),
        inline=True,
    )
    embed.add_field(
        name="📥 Arrivé le",
        value=discord.utils.format_dt(message.author.joined_at, "D"),
        inline=True,
    )
    embed.set_thumbnail(url=message.author.display_avatar.url)

    # Envoi de l'embed – récupération du msg_id pour les boutons
    val_msg = await chan_val.send(embed=embed)
    view    = _build_validation_view(message.author.id, val_msg.id)
    await val_msg.edit(view=view)

    log.info("Présentation de %s transmise aux modérateurs (msg %d).",
             message.author, val_msg.id)

    # Suppression du message de bienvenue du bot dans #présentation
    try:
        async for msg in message.channel.history(limit=50):
            if msg.author == bot.user and message.author.mention in msg.content:
                await msg.delete()
                break
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

    await bot.process_commands(message)


# ═══════════════════════════════════════════════════════════════════════════
#  TÂCHE DE FOND – Levée des bans temporaires
# ═══════════════════════════════════════════════════════════════════════════
@tasks.loop(minutes=10)
async def verif_tempbans() -> None:
    """Parcourt les bans et lève ceux dont le TEMPBAN est échu."""
    maintenant = datetime.now(timezone.utc)
    for guild in bot.guilds:
        try:
            async for ban_entry in guild.bans():
                reason = ban_entry.reason or ""
                if not reason.startswith("TEMPBAN|"):
                    continue
                try:
                    parties  = reason.split("|", 2)
                    fin_ban  = datetime.fromisoformat(parties[1])
                    if maintenant >= fin_ban:
                        await guild.unban(
                            ban_entry.user,
                            reason="Fin de ban temporaire",
                        )
                        log.info(
                            "Ban temporaire levé pour %s (échéance : %s).",
                            ban_entry.user, parties[1],
                        )
                except (ValueError, IndexError):
                    log.warning("Motif TEMPBAN mal formé : %r", reason)
                except discord.NotFound:
                    log.info("Ban déjà levé pour %s.", ban_entry.user)
                except discord.HTTPException as e:
                    log.warning("Erreur HTTP lors du déban : %s", e)
        except discord.Forbidden:
            log.warning("[%s] Permission manquante pour lire les bans.", guild.name)
        except discord.HTTPException as e:
            log.warning("[%s] Erreur HTTP sur guild.bans() : %s", guild.name, e)

@verif_tempbans.before_loop
async def before_verif_tempbans() -> None:
    await bot.wait_until_ready()


# ═══════════════════════════════════════════════════════════════════════════
#  TÂCHE DE FOND – Surveillance TikTok (via yt-dlp, sans service RSS payant)
# ═══════════════════════════════════════════════════════════════════════════

def _ytdlp_fetch_sync() -> list[tuple[str, str, str]]:
    """
    Récupère les 30 plus récentes vidéos TikTok via yt-dlp.
    Retourne une liste de tuples (video_id, titre, lien), du plus récent au plus ancien.
    """
    ydl_opts = {
        "extract_flat": True,
        "playlistend": 30,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(TIKTOK_USER_URL, download=False)
            entries = info.get("entries", [])
            resultats = []
            for item in entries:
                video_id = str(item.get("id") or "").strip()
                title = str(item.get("title") or "Nouvelle vidéo TikTok").strip()
                url = str(item.get("url") or f"https://www.tiktok.com/@olobywater/video/{video_id}").strip()
                if video_id:
                    resultats.append((video_id, title, url))
            return resultats
    except Exception as e:
        log.warning("TikTok yt-dlp extraction error : %s", e)
    return []


@tasks.loop(minutes=10)
async def verif_tiktok() -> None:
    """Vérifie toutes les 10 min si de nouvelles vidéos ont été postées et rattrape les manquées."""
    global dernier_video_id

    # 1. Charger depuis le fichier local au démarrage si la mémoire est vide
    if dernier_video_id is None:
        dernier_video_id = lire_dernier_tiktok_id()

    # 2. Récupérer les vidéos récentes (du plus récent au plus ancien)
    recentes = await asyncio.to_thread(_ytdlp_fetch_sync)
    if not recentes:
        return

    # Si c'est le tout premier lancement (fichier vide & mémoire vide)
    if dernier_video_id is None:
        plus_recente_id = recentes[0][0]
        dernier_video_id = plus_recente_id
        sauvegarder_dernier_tiktok_id(plus_recente_id)
        log.info("TikTok initialisé – vidéo la plus récente mémorisée : %s", plus_recente_id)
        return

    # Si la vidéo la plus récente est déjà la dernière envoyée
    if recentes[0][0] == dernier_video_id:
        return

    # 3. Détecter les vidéos manquées
    manquees = []
    found = False
    for video in recentes:
        if video[0] == dernier_video_id:
            found = True
            break
        manquees.append(video)

    if not found:
        # Si l'ID mémorisé est trop ancien (plus dans les 10 dernières), on prend toutes les 10
        manquees = recentes

    # Inverser pour poster du plus ancien au plus récent (ordre chronologique)
    manquees.reverse()

    # 4. Envoyer chaque vidéo manquante et mettre à jour le fichier
    for video_id, titre, lien in manquees:
        log.info("TikTok : envoi vidéo (%s) → %s", video_id, lien)
        contenu = formater_message(titre, lien)

        for guild in bot.guilds:
            chan = guild.get_channel(ID_SALON_TIKTOK)
            if not chan:
                continue
            try:
                await chan.send(contenu)
                log.info("TikTok : notification envoyée dans #%s (%s).", chan.name, guild.name)
            except discord.Forbidden:
                log.warning("TikTok : permission manquante dans #%s.", chan.name)
            except discord.HTTPException as e:
                log.warning("TikTok : erreur HTTP lors de l'envoi – %s", e)

        dernier_video_id = video_id
        sauvegarder_dernier_tiktok_id(video_id)
        await asyncio.sleep(2)  # Pause de 2s entre chaque envoi si plusieurs vidéos


@verif_tiktok.before_loop
async def before_verif_tiktok() -> None:
    await bot.wait_until_ready()


# ─────────────────────────── Lancement ──────────────────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN, log_handler=None)  # log_handler=None = on gère nous-mêmes le logging
