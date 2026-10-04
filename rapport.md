# Mini-rapport — Serveur de fichiers sécurisé (aiohttp)

## 1. Choix techniques

- **Framework** : aiohttp (asynchrone, WebSocket natif, cohérent avec
  le reste du module).
- **Authentification** : jeton JWT signé (`PyJWT`), valable 8 heures.
- **Mots de passe** : jamais stockés en clair — hachés avec `bcrypt`.
- **Utilisateurs** : fichier `users.json` (suggestion de l'énoncé, pas
  de base de données).
- **Métadonnées des fichiers** (propriétaire) : fichier
  `fichiers_meta.json`, généré et mis à jour automatiquement.
- **Sécurité des noms de fichiers** : une expression régulière bloque
  tout nom contenant `/`, `\` ou des séquences `..`, pour empêcher une
  attaque par traversée de chemin (ex. `../../etc/passwd`).

## 2. Lancer le projet

```bash
pip install -r requirements.txt
python generer_utilisateurs.py   # crée users.json (une seule fois)
python server.py
```

Serveur disponible sur : http://localhost:8080
(client web de test inclus, servi automatiquement sur `/`)

Comptes de démonstration :

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| alice | alice123 | user |
| bob | bob123 | user |
| admin | admin123 | admin |

## 3. Description des routes

### `POST /login`

Vérifie les identifiants et retourne un jeton d'accès.

**Requête :**
```json
{
  "username": "alice",
  "password": "alice123"
}
```

**Réponse (200) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "username": "alice",
  "role": "user"
}
```

**Réponse (401, identifiants invalides) :**
```json
{ "erreur": "identifiants invalides" }
```

Toutes les routes suivantes nécessitent l'en-tête :
```
Authorization: Bearer <access_token>
```

---

### `GET /files`

Liste les fichiers disponibles (nom, taille, date de modification).

**Réponse (200) :**
```json
[
  {
    "nom": "rapport.pdf",
    "taille": 48213,
    "date_modification": "2026-10-03T18:21:23.760300+00:00"
  }
]
```

**Réponse (401, jeton manquant/invalide) :**
```json
{ "erreur": "jeton manquant" }
```

---

### `POST /files`

Téléverse un fichier (`multipart/form-data`, champ nommé `fichier`).

**Requête (exemple curl) :**
```bash
curl -X POST http://localhost:8080/files \
  -H "Authorization: Bearer <token>" \
  -F "fichier=@rapport.pdf"
```

**Réponse (201) :**
```json
{
  "nom": "rapport.pdf",
  "taille": 48213,
  "proprietaire": "alice"
}
```

Déclenche une notification WebSocket `"event": "uploaded"` à tous
les clients connectés.

---

### `GET /files/{nom}`

Télécharge le fichier demandé (réponse brute, en pièce jointe).

**Réponse (404, fichier absent) :**
```json
{ "erreur": "fichier introuvable" }
```

**Réponse (400, nom invalide / tentative de traversée de chemin) :**
```json
{ "erreur": "nom de fichier invalide" }
```

---

### `DELETE /files/{nom}`

Supprime un fichier. Réservé au **propriétaire** du fichier ou à un
utilisateur avec le rôle **admin**.

**Réponse (200) :**
```json
{ "message": "fichier 'rapport.pdf' supprimé" }
```

**Réponse (403, ni propriétaire ni admin) :**
```json
{ "erreur": "seul le propriétaire ou un administrateur peut supprimer ce fichier" }
```

Déclenche une notification WebSocket `"event": "deleted"` à tous les
clients connectés.

---

### `GET /ws?token=<access_token>`

Connexion WebSocket pour recevoir les notifications en temps réel.
Le jeton est transmis en paramètre d'URL car un client WebSocket ne
peut pas envoyer d'en-tête `Authorization` personnalisé.

**Message reçu à chaque ajout ou suppression :**
```json
{ "event": "uploaded", "file": "rapport.pdf", "user": "alice" }
```
```json
{ "event": "deleted", "file": "rapport.pdf", "user": "alice" }
```

## 4. Tests effectués

Toutes les routes ont été testées de bout en bout avec `curl` et un
client WebSocket Python simulé :

- connexion réussie et échouée (401) ;
- accès refusé sans jeton (401) ;
- téléversement, liste, téléchargement ;
- suppression refusée pour un non-propriétaire non-admin (403) ;
- suppression autorisée pour l'administrateur ;
- tentative de traversée de chemin bloquée (400) ;
- notification WebSocket reçue par un **autre** client connecté
  (bob), immédiatement après l'upload puis la suppression effectués
  par alice — confirmant le temps réel multi-utilisateurs.

## 5. Déploiement (lien du serveur)

Le projet est prêt pour un déploiement sur Render.com (mêmes
principes que les TP précédents du module) :

- Build command : `pip install -r requirements.txt`
- Start command : `python server.py`
- Variable d'environnement à définir : `SECRET_KEY` (une chaîne
  aléatoire longue, différente de la valeur par défaut du code).

> ⚠️ Sur le plan gratuit Render, le système de fichiers est éphémère :
> les fichiers téléversés et `users.json`/`fichiers_meta.json`
> seraient perdus à chaque redémarrage du service. Pour un usage
> réel en production, il faudrait un stockage persistant externe
> (ex. un volume Render payant, ou un stockage objet comme S3).

**Lien du serveur déployé :** _à compléter après déploiement._
