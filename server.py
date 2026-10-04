"""
Serveur de fichiers HTTP sécurisé avec notifications temps réel (aiohttp).

Fonctionnalités :
    - Authentification par jeton JWT (POST /login)
    - Liste des fichiers (GET /files)
    - Téléversement de fichiers (POST /files, multipart/form-data)
    - Téléchargement de fichiers (GET /files/{nom})
    - Suppression de fichiers, réservée au propriétaire ou à l'administrateur
      (DELETE /files/{nom})
    - Notifications temps réel par WebSocket (/ws) à chaque ajout/suppression

Les utilisateurs sont stockés dans un simple fichier JSON (users.json),
comme suggéré par le sujet, avec des mots de passe hachés (bcrypt) —
jamais en clair.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from aiohttp import web

# =====================================================================
# CONFIGURATION
# =====================================================================

DOSSIER_UPLOADS = "uploads"
FICHIER_UTILISATEURS = "users.json"
FICHIER_METADONNEES = "fichiers_meta.json"

# À changer impérativement en production (variable d'environnement).
SECRET_KEY = os.environ.get("SECRET_KEY", "change-moi-en-production")
ALGORITHME_JWT = "HS256"
DUREE_TOKEN_HEURES = 8

# Clients WebSocket actuellement connectés (pour diffuser les notifications).
clients_ws = set()


# =====================================================================
# UTILISATEURS (fichier JSON — suggestion de l'énoncé)
# =====================================================================

def charger_utilisateurs():
    with open(FICHIER_UTILISATEURS, "r", encoding="utf-8") as f:
        return json.load(f)


def trouver_utilisateur(nom_utilisateur):
    for utilisateur in charger_utilisateurs():
        if utilisateur["username"] == nom_utilisateur:
            return utilisateur
    return None


def verifier_mot_de_passe(mot_de_passe_clair, hash_stocke):
    return bcrypt.checkpw(
        mot_de_passe_clair.encode("utf-8"), hash_stocke.encode("utf-8")
    )


# =====================================================================
# MÉTADONNÉES DES FICHIERS (propriétaire de chaque fichier)
# =====================================================================

def charger_metadonnees():
    if not os.path.exists(FICHIER_METADONNEES):
        return {}
    with open(FICHIER_METADONNEES, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_metadonnees(metadonnees):
    with open(FICHIER_METADONNEES, "w", encoding="utf-8") as f:
        json.dump(metadonnees, f, indent=2, ensure_ascii=False)


# =====================================================================
# JETON JWT
# =====================================================================

def generer_token(nom_utilisateur, role):
    expiration = datetime.now(timezone.utc) + timedelta(hours=DUREE_TOKEN_HEURES)
    charge_utile = {
        "sub": nom_utilisateur,
        "role": role,
        "exp": expiration,
    }
    return jwt.encode(charge_utile, SECRET_KEY, algorithm=ALGORITHME_JWT)


def decoder_token(token):
    """Retourne la charge utile du jeton, ou None si invalide/expiré."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHME_JWT])
    except jwt.PyJWTError:
        return None


def extraire_token_requete(request):
    """Récupère le jeton depuis l'en-tête 'Authorization: Bearer ...'."""
    entete = request.headers.get("Authorization", "")
    if not entete.startswith("Bearer "):
        return None
    return entete[len("Bearer "):]


async def utilisateur_courant(request):
    """
    Vérifie le jeton de la requête et retourne sa charge utile (sub, role).
    Lève une erreur HTTP 401 si le jeton est absent, invalide ou expiré.
    """
    token = extraire_token_requete(request)
    if not token:
        raise web.HTTPUnauthorized(
            text=json.dumps({"erreur": "jeton manquant"}),
            content_type="application/json",
        )

    charge_utile = decoder_token(token)
    if charge_utile is None:
        raise web.HTTPUnauthorized(
            text=json.dumps({"erreur": "jeton invalide ou expiré"}),
            content_type="application/json",
        )

    return charge_utile


# =====================================================================
# SÉCURITÉ : VALIDATION DU NOM DE FICHIER
# =====================================================================

# Lettres, chiffres, espace, point, tiret, underscore uniquement.
NOM_FICHIER_AUTORISE = re.compile(r"^[A-Za-z0-9_\-. ]+$")


def nom_fichier_valide(nom):
    """
    Empêche les attaques par traversée de chemin (ex: ../../etc/passwd)
    et les noms de fichiers dangereux.
    """
    if not nom or nom in (".", ".."):
        return False
    if "/" in nom or "\\" in nom:
        return False
    if not NOM_FICHIER_AUTORISE.match(nom):
        return False
    return True


# =====================================================================
# DIFFUSION DES NOTIFICATIONS WEBSOCKET
# =====================================================================

async def diffuser_notification(evenement, nom_fichier, utilisateur):
    message = {
        "event": evenement,
        "file": nom_fichier,
        "user": utilisateur,
    }
    for ws in list(clients_ws):
        try:
            await ws.send_json(message)
        except ConnectionResetError:
            clients_ws.discard(ws)


# =====================================================================
# ROUTE : AUTHENTIFICATION
# =====================================================================

async def route_login(request):
    try:
        corps = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"erreur": "corps JSON invalide"}, status=400)

    nom_utilisateur = corps.get("username", "")
    mot_de_passe = corps.get("password", "")

    utilisateur = trouver_utilisateur(nom_utilisateur)

    if utilisateur is None or not verifier_mot_de_passe(
        mot_de_passe, utilisateur["password_hash"]
    ):
        return web.json_response({"erreur": "identifiants invalides"}, status=401)

    token = generer_token(utilisateur["username"], utilisateur["role"])

    return web.json_response({
        "access_token": token,
        "token_type": "bearer",
        "username": utilisateur["username"],
        "role": utilisateur["role"],
    })


# =====================================================================
# ROUTES : FICHIERS
# =====================================================================

async def route_lister_fichiers(request):
    await utilisateur_courant(request)  # vérifie juste la validité du jeton

    resultats = []
    for nom in sorted(os.listdir(DOSSIER_UPLOADS)):
        chemin = os.path.join(DOSSIER_UPLOADS, nom)
        if not os.path.isfile(chemin):
            continue
        stat = os.stat(chemin)
        resultats.append({
            "nom": nom,
            "taille": stat.st_size,
            "date_modification": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })

    return web.json_response(resultats)


async def route_televerser_fichier(request):
    utilisateur = await utilisateur_courant(request)

    lecteur = await request.multipart()
    champ = await lecteur.next()

    if champ is None or champ.name != "fichier":
        return web.json_response(
            {"erreur": "champ 'fichier' manquant (multipart/form-data)"},
            status=400,
        )

    nom_original = champ.filename
    if not nom_fichier_valide(nom_original):
        return web.json_response(
            {"erreur": "nom de fichier invalide"}, status=400
        )

    chemin_destination = os.path.join(DOSSIER_UPLOADS, nom_original)

    taille = 0
    with open(chemin_destination, "wb") as f:
        while True:
            morceau = await champ.read_chunk()
            if not morceau:
                break
            taille += len(morceau)
            f.write(morceau)

    # Enregistrement du propriétaire du fichier.
    metadonnees = charger_metadonnees()
    metadonnees[nom_original] = {"proprietaire": utilisateur["sub"]}
    sauvegarder_metadonnees(metadonnees)

    await diffuser_notification("uploaded", nom_original, utilisateur["sub"])

    return web.json_response({
        "nom": nom_original,
        "taille": taille,
        "proprietaire": utilisateur["sub"],
    }, status=201)


async def route_telecharger_fichier(request):
    await utilisateur_courant(request)

    nom = request.match_info["nom"]
    if not nom_fichier_valide(nom):
        return web.json_response({"erreur": "nom de fichier invalide"}, status=400)

    chemin = os.path.join(DOSSIER_UPLOADS, nom)
    if not os.path.isfile(chemin):
        return web.json_response({"erreur": "fichier introuvable"}, status=404)

    return web.FileResponse(chemin)


async def route_supprimer_fichier(request):
    utilisateur = await utilisateur_courant(request)

    nom = request.match_info["nom"]
    if not nom_fichier_valide(nom):
        return web.json_response({"erreur": "nom de fichier invalide"}, status=400)

    chemin = os.path.join(DOSSIER_UPLOADS, nom)
    if not os.path.isfile(chemin):
        return web.json_response({"erreur": "fichier introuvable"}, status=404)

    metadonnees = charger_metadonnees()
    info_fichier = metadonnees.get(nom, {})
    proprietaire = info_fichier.get("proprietaire")

    est_proprietaire = proprietaire == utilisateur["sub"]
    est_admin = utilisateur["role"] == "admin"

    if not (est_proprietaire or est_admin):
        return web.json_response(
            {"erreur": "seul le propriétaire ou un administrateur peut supprimer ce fichier"},
            status=403,
        )

    os.remove(chemin)
    metadonnees.pop(nom, None)
    sauvegarder_metadonnees(metadonnees)

    await diffuser_notification("deleted", nom, utilisateur["sub"])

    return web.json_response({"message": f"fichier '{nom}' supprimé"})


# =====================================================================
# ROUTE : WEBSOCKET (NOTIFICATIONS TEMPS RÉEL)
# =====================================================================

async def route_websocket(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Le jeton est transmis en paramètre d'URL : un client WebSocket ne
    # peut pas envoyer d'en-tête Authorization personnalisé comme une
    # requête HTTP classique.
    token = request.query.get("token")
    charge_utile = decoder_token(token) if token else None

    if charge_utile is None:
        await ws.send_json({"erreur": "jeton invalide ou manquant"})
        await ws.close()
        return ws

    clients_ws.add(ws)
    print(f"[WS] {charge_utile['sub']} connecté ({len(clients_ws)} client(s))")

    try:
        async for _ in ws:
            pass  # ce canal ne sert qu'à recevoir des notifications
    finally:
        clients_ws.discard(ws)
        print(f"[WS] {charge_utile['sub']} déconnecté ({len(clients_ws)} client(s))")

    return ws


# =====================================================================
# PAGE D'ACCUEIL (CLIENT WEB DE TEST)
# =====================================================================

async def route_index(request):
    return web.FileResponse("./static/index.html")


# =====================================================================
# APPLICATION
# =====================================================================

def initialiser_dossiers():
    os.makedirs(DOSSIER_UPLOADS, exist_ok=True)
    if not os.path.exists(FICHIER_METADONNEES):
        sauvegarder_metadonnees({})


app = web.Application()

app.router.add_get("/", route_index)
app.router.add_post("/login", route_login)
app.router.add_get("/files", route_lister_fichiers)
app.router.add_post("/files", route_televerser_fichier)
app.router.add_get("/files/{nom}", route_telecharger_fichier)
app.router.add_delete("/files/{nom}", route_supprimer_fichier)
app.router.add_get("/ws", route_websocket)
app.router.add_static("/static/", path="static", name="static")


if __name__ == "__main__":
    initialiser_dossiers()
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
