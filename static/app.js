// =========================================================================
// VARIABLES GLOBALES
// =========================================================================

let token = localStorage.getItem("token") || null;
let nomUtilisateur = localStorage.getItem("nomUtilisateur") || null;
let role = localStorage.getItem("role") || null;
let socket = null;

// =========================================================================
// AFFICHAGE : BASCULER ENTRE ÉCRAN DE CONNEXION ET ÉCRAN PRINCIPAL
// =========================================================================

function afficherEcranConnexion() {
  document.getElementById("ecran-connexion").hidden = false;
  document.getElementById("ecran-principal").hidden = true;
  document.getElementById("statut").textContent = "Non connecté";
}

function afficherEcranPrincipal() {
  document.getElementById("ecran-connexion").hidden = true;
  document.getElementById("ecran-principal").hidden = false;
  document.getElementById("statut").textContent = "Connecté : " + nomUtilisateur;
  document.getElementById("info-utilisateur").textContent =
    nomUtilisateur + " (" + role + ")";
}

// =========================================================================
// CONNEXION (POST /login)
// =========================================================================

document
  .getElementById("formulaire-connexion")
  .addEventListener("submit", async function (event) {
    event.preventDefault();

    const utilisateur = document.getElementById("champ-utilisateur").value.trim();
    const motDePasse = document.getElementById("champ-mot-de-passe").value;
    const zoneErreur = document.getElementById("erreur-connexion");
    zoneErreur.textContent = "";

    try {
      const reponse = await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: utilisateur, password: motDePasse }),
      });

      const donnees = await reponse.json();

      if (!reponse.ok) {
        zoneErreur.textContent = donnees.erreur || "Échec de connexion.";
        return;
      }

      token = donnees.access_token;
      nomUtilisateur = donnees.username;
      role = donnees.role;

      localStorage.setItem("token", token);
      localStorage.setItem("nomUtilisateur", nomUtilisateur);
      localStorage.setItem("role", role);

      demarrer();
    } catch (erreur) {
      zoneErreur.textContent = "Impossible de contacter le serveur.";
      console.error(erreur);
    }
  });

document.getElementById("btn-deconnexion").addEventListener("click", function () {
  token = null;
  nomUtilisateur = null;
  role = null;
  localStorage.clear();

  if (socket) {
    socket.close();
    socket = null;
  }

  afficherEcranConnexion();
});

// =========================================================================
// LISTE DES FICHIERS (GET /files)
// =========================================================================

function formaterTaille(octets) {
  if (octets < 1024) return octets + " o";
  if (octets < 1024 * 1024) return (octets / 1024).toFixed(1) + " Ko";
  return (octets / (1024 * 1024)).toFixed(1) + " Mo";
}

function formaterDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleString();
}

async function chargerFichiers() {
  const reponse = await fetch("/files", {
    headers: { Authorization: "Bearer " + token },
  });

  if (reponse.status === 401) {
    afficherEcranConnexion();
    return;
  }

  const fichiers = await reponse.json();
  const corps = document.getElementById("corps-table-fichiers");
  corps.innerHTML = "";

  fichiers.forEach(function (fichier) {
    const ligne = document.createElement("tr");

    const celluleNom = document.createElement("td");
    celluleNom.textContent = fichier.nom;

    const celluleTaille = document.createElement("td");
    celluleTaille.textContent = formaterTaille(fichier.taille);

    const celluleDate = document.createElement("td");
    celluleDate.textContent = formaterDate(fichier.date_modification);

    const celluleActions = document.createElement("td");

    const boutonTelecharger = document.createElement("button");
    boutonTelecharger.textContent = "⬇️";
    boutonTelecharger.title = "Télécharger";
    boutonTelecharger.addEventListener("click", function () {
      telechargerFichier(fichier.nom);
    });

    const boutonSupprimer = document.createElement("button");
    boutonSupprimer.textContent = "🗑️";
    boutonSupprimer.title = "Supprimer";
    boutonSupprimer.addEventListener("click", function () {
      supprimerFichier(fichier.nom);
    });

    celluleActions.appendChild(boutonTelecharger);
    celluleActions.appendChild(boutonSupprimer);

    ligne.appendChild(celluleNom);
    ligne.appendChild(celluleTaille);
    ligne.appendChild(celluleDate);
    ligne.appendChild(celluleActions);

    corps.appendChild(ligne);
  });
}

// =========================================================================
// TÉLÉVERSEMENT (POST /files, multipart/form-data)
// =========================================================================

document
  .getElementById("formulaire-upload")
  .addEventListener("submit", async function (event) {
    event.preventDefault();

    const champFichier = document.getElementById("champ-fichier");
    if (!champFichier.files.length) return;

    const formulaire = new FormData();
    formulaire.append("fichier", champFichier.files[0]);

    const reponse = await fetch("/files", {
      method: "POST",
      headers: { Authorization: "Bearer " + token },
      body: formulaire,
    });

    if (!reponse.ok) {
      const erreur = await reponse.json();
      alert(erreur.erreur || "Échec du téléversement.");
      return;
    }

    champFichier.value = "";
    // La liste se mettra à jour automatiquement via la notification WebSocket.
  });

// =========================================================================
// TÉLÉCHARGEMENT (GET /files/{nom})
// =========================================================================

async function telechargerFichier(nom) {
  const reponse = await fetch("/files/" + encodeURIComponent(nom), {
    headers: { Authorization: "Bearer " + token },
  });

  if (!reponse.ok) {
    alert("Impossible de télécharger ce fichier.");
    return;
  }

  const blob = await reponse.blob();
  const url = URL.createObjectURL(blob);

  const lien = document.createElement("a");
  lien.href = url;
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  document.body.removeChild(lien);
  URL.revokeObjectURL(url);
}

// =========================================================================
// SUPPRESSION (DELETE /files/{nom})
// =========================================================================

async function supprimerFichier(nom) {
  if (!confirm("Supprimer '" + nom + "' ?")) return;

  const reponse = await fetch("/files/" + encodeURIComponent(nom), {
    method: "DELETE",
    headers: { Authorization: "Bearer " + token },
  });

  if (!reponse.ok) {
    const erreur = await reponse.json();
    alert(erreur.erreur || "Échec de la suppression.");
    return;
  }

  // La liste se mettra à jour automatiquement via la notification WebSocket.
}

// =========================================================================
// WEBSOCKET : NOTIFICATIONS TEMPS RÉEL
// =========================================================================

function afficherNotification(message) {
  const zone = document.getElementById("notifications");
  const element = document.createElement("div");
  element.classList.add("notification");

  if (message.event === "uploaded") {
    element.textContent = `📤 ${message.user} a ajouté "${message.file}"`;
  } else if (message.event === "deleted") {
    element.textContent = `🗑️ ${message.user} a supprimé "${message.file}"`;
  }

  zone.prepend(element);

  setTimeout(function () {
    element.remove();
  }, 6000);
}

function connecterWebSocket() {
  const protocole = window.location.protocol === "https:" ? "wss://" : "ws://";
  socket = new WebSocket(
    protocole + window.location.host + "/ws?token=" + encodeURIComponent(token)
  );

  socket.onmessage = function (event) {
    const message = JSON.parse(event.data);

    if (message.event === "uploaded" || message.event === "deleted") {
      afficherNotification(message);
      chargerFichiers(); // on recharge la liste à jour
    }
  };

  socket.onclose = function () {
    console.log("WebSocket fermé.");
  };
}

// =========================================================================
// DÉMARRAGE
// =========================================================================

function demarrer() {
  afficherEcranPrincipal();
  chargerFichiers();
  connecterWebSocket();
}

if (token) {
  demarrer();
} else {
  afficherEcranConnexion();
}
