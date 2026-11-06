let PERIODES = [];
let ROTATION_MS = 1;
// Intervalles récupérés depuis Python
let intervalleCapteurs = 1;
let intervalleMeteo = 1;

// Date prévue pour le prochain appel capteurs
let prochaineActualisationCapteurs = null;

let donnees = null;
let periodeActive = 0;
let derniereMaj = "—";
let erreur = "";
let cacheInfo = null;
let receptionCache = 0;
let ville = "—";

// Fournisseurs de prévisions proposés par Flask
let fournisseurs = [];
let fournisseurActif = null;
let changementEnCours = false;

// ==========================================
// OUTILS DE CALCUL ET DE FORMATAGE
// ==========================================

function nombre(valeur, decimales = 0) {
    return valeur == null
        ? "—"
        : Number(valeur).toFixed(decimales).replace(".", ",");
}

function moyenne(valeurs) {
    const v = valeurs.filter(x => x != null);
    return v.length
        ? v.reduce((a, b) => a + b, 0) / v.length
        : null;
}

function maximum(valeurs) {
    const v = valeurs.filter(x => x != null);
    return v.length ? Math.max(...v) : null;
}

function minimum(valeurs) {
    const v = valeurs.filter(x => x != null);
    return v.length ? Math.min(...v) : null;
}

function somme(valeurs) {
    const v = valeurs.filter(x => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) : null;
}

function valeur(h, cle, i) {
    return h[cle]?.[i] ?? null;
}

function directionVent(degres) {
    if (degres == null) return "—";
    const directions = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
    return directions[Math.round(degres / 45) % 8];
}

function moyenneDirection(degres) {
    const valeurs = degres.filter(x => x != null);
    if (!valeurs.length) return null;

    const x = valeurs.reduce(
        (s, a) => s + Math.sin(a * Math.PI / 180), 0
    );
    const y = valeurs.reduce(
        (s, a) => s + Math.cos(a * Math.PI / 180), 0
    );

    if (Math.hypot(x, y) < 0.000001) return null;
    return (Math.atan2(x, y) * 180 / Math.PI + 360) % 360;
}

function symbole(code) {
    if (code == null) return ["🌡️", "Indisponible"];
    if (code === 0) return ["☀️", "Ciel dégagé"];
    if (code <= 2) return ["🌤️", "Peu nuageux"];
    if (code === 3) return ["☁️", "Couvert"];
    if (code <= 48) return ["🌫️", "Brouillard"];
    if (code <= 67) return ["🌧️", "Pluie ou bruine"];
    if (code <= 77) return ["❄️", "Neige"];
    if (code <= 82) return ["🌦️", "Averses"];
    if (code <= 86) return ["🌨️", "Averses de neige"];
    return ["⛈️", "Orages"];
}

// Date à Paris au format AAAA-MM-JJ, décalée de quelques jours
function dateDuJour(decalage = 0) {
    const aujourdhui = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Europe/Paris"
    }).format(new Date());

    const date = new Date(aujourdhui + "T12:00:00Z");
    date.setUTCDate(date.getUTCDate() + decalage);

    return date.toISOString().slice(0, 10);
}

function dateLocale(iso) {
    return new Intl.DateTimeFormat("fr-FR", {
        weekday: "long",
        day: "numeric",
        month: "long",
        timeZone: "Europe/Paris"
    }).format(new Date(iso + "T12:00:00+01:00"));
}

function formaterDuree(secondes) {
    secondes = Math.max(0, Math.floor(secondes));

    const heures = Math.floor(secondes / 3600);
    const minutes = Math.floor((secondes % 3600) / 60);
    const secondesRestantes = secondes % 60;

    return [heures, minutes, secondesRestantes]
        .map(v => String(v).padStart(2, "0"))
        .join(":");
}

// ==========================================
// PRÉVISIONS MÉTÉO
// ==========================================

function construireJour(numero, periode) {
    const h = donnees.hourly;

    // Les jours sont comptés à partir de la date réelle, et non de la
    // première date des prévisions : juste après minuit, le cache peut
    // encore contenir la veille. Un jour sans prévision affiche « — ».
    const date = dateDuJour(numero);

    const indices = [];

    for (let i = 0; i < h.time.length; i++) {
        const jour = h.time[i].slice(0, 10);
        const heure = Number(h.time[i].slice(11, 13));

        if (
            jour === date &&
            heure >= periode.debut &&
            heure < periode.fin
        ) {
            indices.push(i);
        }
    }

    const valeurs = cle => indices.map(i => valeur(h, cle, i));

    const temperatures = valeurs("temperature_2m");
    const humidites = valeurs("relative_humidity_2m");
    const pluies = valeurs("precipitation");
    const risques = valeurs("precipitation_probability");
    const vents = valeurs("wind_speed_10m");
    const directions = valeurs("wind_direction_10m");
    const pressions = valeurs("pressure_msl");
    const rayonnements = valeurs("shortwave_radiation");
    const soleils = valeurs("sunshine_duration");

    const codes = valeurs("weather_code").filter(x => x != null);
    const frequences = new Map();

    codes.forEach(c => {
        frequences.set(c, (frequences.get(c) || 0) + 1);
    });

    const codeDominant = [...frequences.entries()]
        .sort((a, b) => b[1] - a[1])[0]?.[0];

    const [icone, description] = symbole(codeDominant);
    const direction = moyenneDirection(directions);

    // Ensoleillement en heures ; « — » s'il n'est pas fourni
    const secondesSoleil = somme(soleils);
    const heuresSoleil = secondesSoleil == null ? null : secondesSoleil / 3600;

    return `
        <section class="case ${numero === 0 ? "aujourdhui" : ""}">
            <div class="date">
                <span>
                    ${numero === 0 ? "Aujourd'hui" : dateLocale(date)}
                </span>
                <span class="periode-case">
                    ${periode.nom}
                </span>
            </div>

            <div class="description">
                <span class="icone">${icone}</span>
                ${description}
            </div>

            <div class="temperature">
                ${nombre(minimum(temperatures))}° /
                ${nombre(maximum(temperatures))}°
            </div>

            <div class="details">
                <div>🌧️ Pluie : ${nombre(somme(pluies), 1)} mm</div>
                <div>🌧️ Risque : ${nombre(maximum(risques))} %</div>
                <div>💨 Vent : ${nombre(moyenne(vents))} km/h</div>
                <div>🧭 Direction : ${directionVent(direction)}</div>
                <div>💧 Humidité : ${nombre(moyenne(humidites))} %</div>
                <div>🌡️ ${nombre(moyenne(pressions))} hPa</div>
                <div>☀️ Soleil : ${nombre(heuresSoleil, 1)} h</div>
                <div>🔆 ${nombre(maximum(rayonnements))} W/m²</div>
            </div>
        </section>
    `;
}

function construireInformation(periode) {
    return `
        <section class="case information">

            <div class="date-heure">
                <div id="dateJour">—</div>
                <div class="horloge" id="horloge">--:--:--</div>
            </div>

            <div class="details">
                <div>
                    Ville :
                    <strong id="ville"></strong>
                </div>

                <div>
                    <strong>${periode.nom}</strong>
                </div>

                <div>
                    Météo : <strong id="derniereRecuperation">—</strong>
                </div>

                <div>
                    Cache :
                    <strong id="etatCache">—</strong>
                </div>

                <div>
                    Météo :
                    <strong id="compteRebours">--:--:--</strong>
                </div>

                <div>
                    Capteurs :
                    <strong id="compteReboursCapteurs">--:--:--</strong>
                </div>
            </div>

            <p class="source-meteo">
                <span
                    class="choix-fournisseur"
                    id="choixFournisseur"
                    role="button"
                    title="Changer de fournisseur de prévisions"
                >Météo : ${changementEnCours
                    ? "chargement…"
                    : fournisseurActif?.nom ?? "—"}</span>
                · Ville : © OpenStreetMap
            </p>

            ${erreur ? "<p>⚠️ Actualisation impossible</p>" : ""}

        </section>
    `;
}

function afficher() {
    const periode = PERIODES[periodeActive];

    let html = "";

    if (donnees) {
        for (let jour = 0; jour < 5; jour++) {
            html += construireJour(jour, periode);
        }
    } else {
        html += `<section class="case">${erreur || "Chargement..."}</section>`;
    }

    // Toujours affichée : elle permet de changer de fournisseur
    // même si le fournisseur choisi ne répond pas.
    html += construireInformation(periode);

    document.getElementById("grille").innerHTML = html;

    // Afficher la ville une fois les éléments HTML créés
    const elementVille = document.getElementById("ville");

    if (elementVille) {
        elementVille.textContent = ville;
    }

    // Actualiser l'horloge et les informations du cache
    afficherHorloge();
}

// ==========================================
// HORLOGE, CACHE ET COMPTES À REBOURS
// ==========================================

function afficherCache() {

    if (!cacheInfo) return;

    const dateElement = document.getElementById(
        "derniereRecuperation"
    );

    const etatElement = document.getElementById(
        "etatCache"
    );

    const compteurElement = document.getElementById(
        "compteRebours"
    );

    const tempsEcoule = Math.floor(
        (Date.now() - receptionCache) / 1000
    );

    const restant = Math.max(
        0,
        cacheInfo.secondes_restantes - tempsEcoule
    );

    const attente = Math.max(
        0,
        cacheInfo.secondes_avant_tentative - tempsEcoule
    );

    // Date de dernière récupération : heure uniquement
    if (dateElement && cacheInfo.date_recuperation) {

        dateElement.textContent = new Date(
            cacheInfo.date_recuperation
        ).toLocaleTimeString("fr-FR", {
            timeZone: "Europe/Paris",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        });
    }

    if (!etatElement || !compteurElement) return;

    if (cacheInfo.etat === "attente") {

        etatElement.textContent = "⚠️ Anciennes données";
        compteurElement.textContent = formaterDuree(attente);

    } else if (restant > 0) {

        etatElement.textContent = "✅ À jour";
        compteurElement.textContent = formaterDuree(restant);

    } else {

        etatElement.textContent = "⏳ Expiré";
        compteurElement.textContent = "00:00:00";
    }
}

function afficherCompteReboursCapteurs() {

    const element = document.getElementById(
        "compteReboursCapteurs"
    );

    if (!element) return;

    if (prochaineActualisationCapteurs === null) {
        element.textContent = "--:--:--";
        return;
    }

    const secondesRestantes = Math.max(
        0,
        Math.ceil(
            (prochaineActualisationCapteurs - Date.now()) / 1000
        )
    );

    element.textContent = formaterDuree(secondesRestantes);
}

function afficherHorloge() {
    const maintenant = new Date();

    const horloge = document.getElementById("horloge");
    const dateJour = document.getElementById("dateJour");

    if (horloge) {
        horloge.textContent = maintenant.toLocaleTimeString("fr-FR", {
            timeZone: "Europe/Paris"
        });
    }

    if (dateJour) {
        dateJour.textContent = maintenant.toLocaleDateString("fr-FR", {
            timeZone: "Europe/Paris",
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric"
        });
    }
    afficherCache();
    afficherCompteReboursCapteurs();
}

async function actualiser() {
    try {
        const reponse = await fetch("/api/meteo", {
            cache: "no-store"
        });

        const nouvellesDonnees = await reponse.json().catch(() => ({}));

        // Flask indique le fournisseur actif, même en cas d'erreur
        if (nouvellesDonnees.fournisseur) {
            fournisseurActif = nouvellesDonnees.fournisseur;
        }

        if (!reponse.ok) {
            throw new Error(
                nouvellesDonnees.erreur || "Erreur HTTP " + reponse.status
            );
        }

        if (!nouvellesDonnees.hourly?.time?.length) {
            throw new Error("Prévisions absentes");
        }

        donnees = nouvellesDonnees;
        ville = nouvellesDonnees.ville || "Ville inconnue";

        cacheInfo = nouvellesDonnees.cache_info || null;

        receptionCache = Date.now();

        derniereMaj = new Date().toLocaleTimeString(
            "fr-FR"
        );

        erreur = "";

    } catch (e) {
        console.error(e);
        erreur = e.message;

        // Ne pas afficher les prévisions d'un autre fournisseur
        if (donnees && donnees.fournisseur?.id !== fournisseurActif?.id) {
            donnees = null;
            cacheInfo = null;
        }
    }

    afficher();
}

// Passe au fournisseur suivant à chaque clic sur « Météo : … »
async function changerFournisseur() {
    if (changementEnCours || fournisseurs.length < 2) return;

    const position = fournisseurs.findIndex(
        f => f.id === fournisseurActif?.id
    );
    const suivant = fournisseurs[(position + 1) % fournisseurs.length];

    changementEnCours = true;
    afficher();

    try {
        const reponse = await fetch("/api/fournisseur", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: suivant.id })
        });

        if (!reponse.ok) {
            throw new Error("Erreur HTTP " + reponse.status);
        }

        await actualiser();

    } catch (e) {
        console.error("Erreur changement de fournisseur :", e);

    } finally {
        changementEnCours = false;
        afficher();
    }
}

// ==========================================
// CAPTEURS METEOMAISON
// ==========================================

async function actualiserCapteurs() {
    prochaineActualisationCapteurs =
        Date.now() + intervalleCapteurs * 1000;
    const conteneur = document.getElementById("liste-capteurs");

    try {
        const reponse = await fetch("/api/capteurs", {
            cache: "no-store"
        });

        if (!reponse.ok) {
            throw new Error("Erreur HTTP " + reponse.status);
        }

        const donneesCapteurs = await reponse.json();

        const capteurs = donneesCapteurs.capteurs || [];

        // Effacer uniquement l'ancienne liste des capteurs
        conteneur.replaceChildren();

        if (capteurs.length === 0) {
            conteneur.textContent = "Aucun capteur détecté";
            return;
        }

        for (const capteur of capteurs) {

            const carte = document.createElement("section");
            carte.className = "case-capteur";

            const titre = document.createElement("h3");
            titre.textContent = capteur.nom || "Capteur inconnu";

            const temperature = document.createElement("div");
            temperature.className = "temperature-capteur";
            temperature.textContent =
                nombre(capteur.temperature, 1) + " °C";

            const humidite = document.createElement("div");
            humidite.className = "detail-capteur";
            humidite.textContent =
                "💧 " +
                nombre(capteur.humidite) + " %";

            const batterie = document.createElement("div");
            batterie.className = "detail-capteur";
            batterie.textContent =
                "🔋 " +
                nombre(capteur.batterie) + " %";

            // Températures extrêmes sur les dernières 24 heures
            const extremes = document.createElement("div");
            extremes.className = "extremes-capteur";

            const tMin = capteur.temperature_min == null
                ? null : Number(capteur.temperature_min);

            const tMax = capteur.temperature_max == null
                ? null : Number(capteur.temperature_max);

            if (
                tMin !== null &&
                tMax !== null &&
                Number.isFinite(tMin) &&
                Number.isFinite(tMax) &&
                tMax - tMin >= donneesCapteurs.seuil_ecart
            ) {
                const ligne = document.createElement("div");

                ligne.textContent =
                    donneesCapteurs.historique_heures + " h : " +
                    nombre(tMin, 1) + " °C - " +
                    nombre(tMax, 1) + " °C";

                extremes.appendChild(ligne);
            }

            const date = document.createElement("div");
            date.className = "date-capteur";

            if (capteur.date_releve) {
                date.textContent = "Relevé : " +
                    new Date(capteur.date_releve)
                        .toLocaleTimeString("fr-FR", {
                            timeZone: "Europe/Paris"
                        });
            }
            const ligneMesures = document.createElement("div");
            ligneMesures.className = "ligne-mesures";
            ligneMesures.append(humidite, batterie);
            carte.append(
                titre,
                temperature,
                ligneMesures,
                extremes,
                date
            );
            conteneur.appendChild(carte);
        }

    } catch (e) {
        console.error("Erreur MeteoMaison :", e);

        // En cas d'erreur, conserver les dernières cases.
        if (!conteneur.querySelector(".case-capteur")) {
            conteneur.textContent =
                "⚠️ Capteurs momentanément indisponibles";
        }
    }
}

// ==========================================
// INITIALISATION DE L'APPLICATION
// ==========================================

async function initialiser() {

    // Lire les paramètres depuis Flask
    try {
        const reponse = await fetch("/api/config", {
            cache: "no-store"
        });

        if (!reponse.ok) {
            throw new Error("Configuration indisponible");
        }

        const config = await reponse.json();

        intervalleCapteurs = config.intervalle_capteurs;
        intervalleMeteo = config.intervalle_meteo;
        PERIODES = config.periodes;
        ROTATION_MS = config.rotation_periodes * 1000;
        fournisseurs = config.fournisseurs || [];

    } catch (e) {
        console.error("Erreur configuration :", e);

        // Valeurs de secours si l'API est indisponible
        intervalleCapteurs = 300;
        intervalleMeteo = 3600;
        PERIODES = [
            { nom: "Matin", debut: 6, fin: 12 },
            { nom: "Après-midi", debut: 12, fin: 18 },
            { nom: "Soir", debut: 18, fin: 24 },
            { nom: "Nuit", debut: 0, fin: 6 }
        ];
        ROTATION_MS = 12000;
    }

    // La grille est reconstruite régulièrement : le clic est
    // donc écouté sur la grille plutôt que sur l'élément lui-même.
    document.getElementById("grille").addEventListener("click", e => {
        if (e.target.closest("#choixFournisseur")) {
            changerFournisseur();
        }
    });

    // Premier chargement des prévisions
    actualiser();

    // Premier chargement des capteurs
    actualiserCapteurs();

    // Rotation des périodes : toutes les 12 secondes
    setInterval(() => {
        periodeActive =
            (periodeActive + 1) % PERIODES.length;

        afficher();

    }, ROTATION_MS);

    // Vérification météo toutes les 60 secondes.
    // Flask gère le cache et limite les appels à Open-Meteo.
    setInterval(
        actualiser,
        60 * 1000
    );

    // Actualisation capteurs
    setInterval(
        actualiserCapteurs,
        intervalleCapteurs * 1000
    );

    // Horloge et comptes à rebours
    setInterval(
        afficherHorloge,
        1000
    );
}

// Démarrer l'application
initialiser();
