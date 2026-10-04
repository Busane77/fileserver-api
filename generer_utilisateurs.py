"""
Génère le fichier users.json avec des mots de passe hachés (bcrypt).

À exécuter une seule fois (ou à chaque fois qu'on veut ajouter/modifier
un utilisateur). Les mots de passe ne sont JAMAIS stockés en clair.
"""

import json

import bcrypt


def hacher(mot_de_passe):
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


UTILISATEURS = [
    {
        "username": "alice",
        "password_hash": hacher("alice123"),
        "role": "user",
    },
    {
        "username": "bob",
        "password_hash": hacher("bob123"),
        "role": "user",
    },
    {
        "username": "admin",
        "password_hash": hacher("admin123"),
        "role": "admin",
    },
]


if __name__ == "__main__":
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(UTILISATEURS, f, indent=2, ensure_ascii=False)

    print("users.json généré avec succès.")
    print("Comptes de démonstration :")
    print("  - alice / alice123  (rôle : user)")
    print("  - bob   / bob123    (rôle : user)")
    print("  - admin / admin123  (rôle : admin)")
