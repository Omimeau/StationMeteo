let PERIODES = [];
let ROTATION_MS = 1;
// Intervalles récupérés depuis Python
let intervalleCapteurs = 1;
let intervalleMeteo = 1;

// Date prévue pour le prochain appel capteurs
let prochaineActualisationCapteurs = null;

// Résultat de la dernière lecture des capteurs (null = pas encore lue)
let capteursOk = null;

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

// Mode nuit : luminosité en % (LUMINOSITE_NUIT de config_local.py)
let luminositeNuit = 35;

// AFFICHAGE_INTERACTIF de config_local.py : true = cases simplifiées
// qui s'ouvrent en grand et fournisseur modifiable ; false = affichage
// classique (tous les détails) d'une seule source
let interactif = true;

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

// Émojis affichés en images (static/emojis, Fluent Emoji de Microsoft,
// licence MIT) : même dessin sur le PC et sur le Raspberry, dont la
// police d'émojis (Noto) est différente de celle de Windows.
// Clé = caractère sans le sélecteur de variante U+FE0F.
const EMOJIS = {
    "🌡": "thermometre",
    "☀": "soleil",
    "🌤": "soleil_nuage",
    "☁": "nuage",
    "🌫": "brouillard",
    "🌧": "pluie",
    "❄": "neige",
    "🌦": "averses",
    "🌨": "averses_neige",
    "⛈": "orage",
    "💨": "vent",
    "🧭": "boussole",
    "💧": "goutte",
    "🔆": "luminosite",
    "🌙": "lune",
    "⚠": "attention",
    "✅": "valide",
    "⏳": "sablier",
    "🔋": "batterie"
};

const MOTIF_EMOJIS = new RegExp(
    "(" + Object.keys(EMOJIS).join("|") + ")️?", "gu"
);

// Remplace les émojis connus d'un texte HTML par leur image
function avecEmojis(html) {
    return html.replace(MOTIF_EMOJIS, (caractere, base) =>
        `<img class="emoji" src="/static/emojis/${EMOJIS[base]}.svg"`
        + ` alt="${caractere}" draggable="false">`
    );
}

// Icône d'état (✅ ⚠️ ⏳) : l'élément n'est réécrit que si elle change,
// pour ne pas recréer l'image à chaque seconde
function afficherEtat(element, caractere) {
    if (element.dataset.emoji === caractere) return;
    element.dataset.emoji = caractere;
    element.innerHTML = avecEmojis(caractere);
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

// Toutes les valeurs d'une période d'un jour (case et vue agrandie)
function calculerPeriode(numero, periode) {
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

    const codes = valeurs("weather_code").filter(x => x != null);
    const frequences = new Map();

    codes.forEach(c => {
        frequences.set(c, (frequences.get(c) || 0) + 1);
    });

    const codeDominant = [...frequences.entries()]
        .sort((a, b) => b[1] - a[1])[0]?.[0];

    const [icone, description] = symbole(codeDominant);

    // Ensoleillement en heures ; « — » s'il n'est pas fourni
    const secondesSoleil = somme(valeurs("sunshine_duration"));

    return {
        date,
        titre: numero === 0 ? "Aujourd'hui" : dateLocale(date),
        indices,
        icone,
        description,
        tMin: minimum(temperatures),
        tMax: maximum(temperatures),
        pluie: somme(valeurs("precipitation")),
        risque: maximum(valeurs("precipitation_probability")),
        vent: moyenne(valeurs("wind_speed_10m")),
        direction: moyenneDirection(valeurs("wind_direction_10m")),
        humidite: moyenne(valeurs("relative_humidity_2m")),
        pression: moyenne(valeurs("pressure_msl")),
        soleil: secondesSoleil == null ? null : secondesSoleil / 3600,
        rayonnement: maximum(valeurs("shortwave_radiation"))
    };
}

// Haut de case sur deux colonnes : icône + texte | min puis max
function construireHaut(p) {
    return `
        <div class="haut-prevision">
            <div class="ciel">
                <span class="icone">${p.icone}</span>
                <span class="description">${p.description}</span>
            </div>
            <div class="temperature">
                <span class="t-min">${nombre(p.tMin)}°</span>
                <span class="t-max">${nombre(p.tMax)}°</span>
            </div>
        </div>
    `;
}

function construireJour(numero, periode, indexPeriode) {
    const p = calculerPeriode(numero, periode);

    return `
        <section
            class="case jour ${numero === 0 ? "aujourdhui" : ""}"
            data-jour="${numero}"
            data-periode="${indexPeriode}"
            role="button"
            title="Afficher le détail"
        >
            <div class="date">
                <span>${p.titre}</span>
                <span class="periode-case">${periode.nom}</span>
            </div>

            ${construireHaut(p)}

            <div class="resume">
                <div>🌧️ Pluie : ${nombre(p.pluie, 1)} mm
                    · ${nombre(p.risque)} %</div>
                <div>💨 Vent : ${nombre(p.vent)} km/h
                    · ${directionVent(p.direction)}</div>
            </div>
        </section>
    `;
}

// Affichage non interactif : case classique avec tous les détails
function construireJourClassique(numero, periode) {
    const p = calculerPeriode(numero, periode);

    return `
        <section class="case classique ${numero === 0 ? "aujourdhui" : ""}">
            <div class="date">
                <span>${p.titre}</span>
                <span class="periode-case">${periode.nom}</span>
            </div>

            <div class="description">
                <span class="icone">${p.icone}</span>
                ${p.description}
            </div>

            <div class="temperature">
                ${nombre(p.tMin)}° /
                ${nombre(p.tMax)}°
            </div>

            <div class="details">
                <div>🌧️ Pluie : ${nombre(p.pluie, 1)} mm</div>
                <div>🌧️ Risque : ${nombre(p.risque)} %</div>
                <div>💨 Vent : ${nombre(p.vent)} km/h</div>
                <div>🧭 Direction : ${directionVent(p.direction)}</div>
                <div>💧 Humidité : ${nombre(p.humidite)} %</div>
                <div>🌡️ ${nombre(p.pression)} hPa</div>
                <div>☀️ Soleil : ${nombre(p.soleil, 1)} h</div>
                <div>🔆 ${nombre(p.rayonnement)} W/m²</div>
            </div>
        </section>
    `;
}

// ==========================================
// VUE AGRANDIE D'UNE CASE
// ==========================================

// Case ouverte en grand : { numero, indexPeriode } ou null
let detailOuvert = null;
let minuterieDetail = null;

// Fermeture automatique (kiosque)
const DUREE_DETAIL_MS = 60 * 1000;

function ouvrirDetail(numero, indexPeriode) {
    detailOuvert = { numero, indexPeriode };
    afficherDetail();

    clearTimeout(minuterieDetail);
    minuterieDetail = setTimeout(fermerDetail, DUREE_DETAIL_MS);
}

function fermerDetail() {
    detailOuvert = null;
    clearTimeout(minuterieDetail);

    const vue = document.getElementById("detail-prevision");
    vue.hidden = true;
    vue.replaceChildren();
}

function afficherDetail() {
    if (!detailOuvert || !donnees) return;

    const periode = PERIODES[detailOuvert.indexPeriode];
    if (!periode) return fermerDetail();

    const h = donnees.hourly;
    const p = calculerPeriode(detailOuvert.numero, periode);

    // Tableau heure par heure : les 24 heures du jour, quelle que soit la
    // période, sur deux colonnes (0 h - 11 h | 12 h - 23 h). Les heures de
    // la période affichée sont en gras.
    const heuresJour = [];
    for (let i = 0; i < h.time.length; i++) {
        if (h.time[i].slice(0, 10) === p.date) heuresJour.push(i);
    }

    const ligne = i => {
        const [icone, description] = symbole(valeur(h, "weather_code", i));
        const classe = p.indices.includes(i) ? ' class="dans-periode"' : "";

        return `
            <tr${classe}>
                <td>${h.time[i].slice(11, 13)} h</td>
                <td title="${description}">${icone}</td>
                <td>${nombre(valeur(h, "temperature_2m", i))}°</td>
                <td>${nombre(valeur(h, "precipitation", i), 1)} mm</td>
                <td>${nombre(valeur(h, "precipitation_probability", i))} %</td>
                <td>${nombre(valeur(h, "wind_speed_10m", i))} km/h
                    (${directionVent(valeur(h, "wind_direction_10m", i))})</td>
            </tr>
        `;
    };

    const tableau = indices => indices.length ? `
        <table class="heures">
            <thead>
                <tr>
                    <th>Heure</th><th></th><th>Temp.</th>
                    <th>Pluie</th><th>Risque</th><th>Vent</th>
                </tr>
            </thead>
            <tbody>${indices.map(ligne).join("")}</tbody>
        </table>
    ` : "";

    const heure = i => Number(h.time[i].slice(11, 13));
    const matin = heuresJour.filter(i => heure(i) < 12);
    const soir = heuresJour.filter(i => heure(i) >= 12);

    const vue = document.getElementById("detail-prevision");

    vue.innerHTML = avecEmojis(`
        <section class="fenetre-detail">
            <div class="date">
                <span>${p.titre}</span>
                <span class="periode-case">${periode.nom}</span>
            </div>

            <div
                class="fournisseur-detail"
                role="button"
                title="Changer de fournisseur de prévisions"
            >
                ${changementEnCours
                    ? "chargement…"
                    : donnees.fournisseur?.nom ?? ""}
            </div>

            ${construireHaut(p)}

            <div class="details">
                <div>🌧️ Pluie : ${nombre(p.pluie, 1)} mm</div>
                <div>🌧️ Risque : ${nombre(p.risque)} %</div>
                <div>💨 Vent : ${nombre(p.vent)} km/h</div>
                <div>🧭 Direction : ${directionVent(p.direction)}</div>
                <div>💧 Humidité : ${nombre(p.humidite)} %</div>
                <div>🌡️ ${nombre(p.pression)} hPa</div>
                <div>☀️ Soleil : ${nombre(p.soleil, 1)} h</div>
                <div>🔆 ${nombre(p.rayonnement)} W/m²</div>
            </div>

            ${heuresJour.length ? `
                <div class="heures-jour">
                    ${tableau(matin)}
                    ${tableau(soir)}
                </div>
            ` : "<p>Aucune prévision horaire pour ce jour.</p>"}

            <p class="fermer-detail">Toucher pour fermer</p>
        </section>
    `);

    vue.hidden = false;
}

// Case d'information (en bas à droite), dans les deux affichages.
// Non interactif : fournisseur affiché sans pouvoir le changer et pas
// de bouton du mode nuit (programmé par NUIT_DEBUT / NUIT_FIN).
function construireInformation() {
    const nomFournisseur = changementEnCours
        ? "chargement…"
        : fournisseurActif?.nom ?? "—";

    const ligneFournisseur = interactif
        ? `
            <div
                class="ligne-fournisseur modifiable"
                id="choixFournisseur"
                role="button"
                title="Changer de fournisseur de prévisions"
            >
                <span>Prévisions :</span>
                <span class="choix-fournisseur">${nomFournisseur}</span>
            </div>
        `
        : `
            <div class="ligne-fournisseur">
                <span>Prévisions :</span>
                <span class="nom-fournisseur">${nomFournisseur}</span>
            </div>
        `;

    const boutonNuit = interactif
        ? `
            <button
                type="button"
                class="bouton-nuit"
                id="boutonNuit"
                title="Mode nuit (toucher l'écran pour revenir au mode jour)"
                aria-label="Mode nuit"
            >🌙</button>
        `
        : "";

    return `
        <section class="case information">

            <div class="date-heure">
                <div id="dateJour">—</div>
                <div class="horloge" id="horloge">--:--:--</div>
            </div>

            <div class="liste-infos">
                <div>
                    Ville :
                    <strong id="ville"></strong>
                </div>

                <div>
                    Météo :
                    <span class="etat-compteur" id="etatMeteo"></span>
                    <strong id="compteRebours">--:--:--</strong>
                </div>

                <div>
                    Capteurs :
                    <span class="etat-compteur" id="etatCapteurs"></span>
                    <strong id="compteReboursCapteurs">--:--:--</strong>
                </div>

                ${ligneFournisseur}
            </div>

            ${erreur ? '<p class="erreur-info">⚠️ Actualisation impossible</p>' : ""}

            <div class="bas-information">
                ${boutonNuit}
                <span class="source-osm">Ville © OpenStreetMap</span>
            </div>

        </section>
    `;
}

function afficher() {
    const periode = PERIODES[periodeActive];

    let html = "";

    if (donnees) {
        for (let jour = 0; jour < 5; jour++) {
            html += interactif
                ? construireJour(jour, periode, periodeActive)
                : construireJourClassique(jour, periode);
        }
    } else {
        html += `<section class="case">${erreur || "Chargement..."}</section>`;
    }

    // Toujours affichée : elle permet de changer de fournisseur
    // même si le fournisseur choisi ne répond pas.
    html += construireInformation();

    document.getElementById("grille").innerHTML = avecEmojis(html);

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

    // Icône d'état affichée à côté du décompte météo
    const etatElement = document.getElementById(
        "etatMeteo"
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

    if (!etatElement || !compteurElement) return;

    if (cacheInfo.etat === "attente") {

        afficherEtat(etatElement, "⚠️");
        etatElement.title = "Anciennes données (dernière récupération en échec)";
        compteurElement.textContent = formaterDuree(attente);

    } else if (restant > 0) {

        afficherEtat(etatElement, "✅");
        etatElement.title = "Prévisions à jour";
        compteurElement.textContent = formaterDuree(restant);

    } else {

        afficherEtat(etatElement, "⏳");
        etatElement.title = "Prévisions expirées";
        compteurElement.textContent = "00:00:00";
    }
}

function afficherCompteReboursCapteurs() {

    const element = document.getElementById(
        "compteReboursCapteurs"
    );

    if (!element) return;

    // Icône d'état de la dernière lecture des capteurs
    const etatElement = document.getElementById("etatCapteurs");

    if (etatElement) {
        afficherEtat(
            etatElement,
            capteursOk === null ? "" : capteursOk ? "✅" : "⚠️"
        );
        etatElement.title = capteursOk
            ? "Capteurs à jour"
            : "Dernière lecture des capteurs en échec";
    }

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

    // Vue agrandie ouverte : reprendre les nouvelles données
    if (detailOuvert) {
        if (donnees) afficherDetail(); else fermerDetail();
    }
}

// Passe au fournisseur suivant à chaque clic sur « Prévisions : … »
// (case d'information) ou sur le fournisseur de la vue agrandie
async function changerFournisseur() {
    if (!interactif || changementEnCours || fournisseurs.length < 2) return;

    const position = fournisseurs.findIndex(
        f => f.id === fournisseurActif?.id
    );
    const suivant = fournisseurs[(position + 1) % fournisseurs.length];

    changementEnCours = true;
    afficher();
    afficherDetail();

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
        afficherDetail();
    }
}

// ==========================================
// MODE NUIT
// ==========================================

// Un voile noir couvre tout l'écran : son opacité donne la luminosité.
// Le voile reçoit le clic suivant, n'importe où sur l'écran, et revient
// au mode jour sans déclencher l'élément situé en dessous.
function activerModeNuit() {
    const voile = document.getElementById("voile-nuit");
    voile.style.opacity = String(1 - luminositeNuit / 100);
    voile.hidden = false;

    // Option ECRAN_VEILLE = "hdmi" : l'écran est en plus éteint
    if (veilleHdmi && !ecranEteint) commanderEcran(true);
}

function activerModeJour() {
    document.getElementById("voile-nuit").hidden = true;

    if (veilleHdmi && ecranEteint) commanderEcran(false);
}

// ==========================================
// VEILLE DE L'ÉCRAN (option ECRAN_VEILLE = "hdmi")
// ==========================================

// Le serveur coupe le signal HDMI ; écran éteint, la page ne reçoit plus
// les touchers : c'est le serveur qui rallume l'écran au premier appui.
// La page le voit à la date du dernier réveil (GET /api/ecran) et repasse
// alors en mode jour. Le voile reste dessous : si l'extinction échoue,
// le mode nuit reste celui du voile.
let veilleHdmi = false;
let ecranEteint = false;
let reveilConnu = null;

async function commanderEcran(veille) {
    try {
        const reponse = await fetch("/api/ecran", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ veille })
        });
        if (!reponse.ok) throw new Error("HTTP " + reponse.status);

        const etat = await reponse.json();
        ecranEteint = etat.veille;
        reveilConnu = etat.dernier_reveil;

    } catch (e) {
        console.error("Erreur veille de l'écran :", e);
        ecranEteint = false;
    }
}

// Appelée toutes les 2 s tant que l'écran est éteint
async function surveillerReveil() {
    if (!ecranEteint) return;

    try {
        const reponse = await fetch("/api/ecran", { cache: "no-store" });
        if (!reponse.ok) return;
        const etat = await reponse.json();

        if (etat.veille || !ecranEteint) return;

        if (etat.dernier_reveil !== reveilConnu) {
            // Rallumé par un toucher : retour au mode jour
            reveilConnu = etat.dernier_reveil;
            ecranEteint = false;
            activerModeJour();
        } else {
            // Serveur redémarré pendant la veille : la redemander
            ecranEteint = false;
            commanderEcran(true);
        }

    } catch (e) {
        console.error("Erreur état de l'écran :", e);
    }
}

// Mode nuit programmé (NUIT_DEBUT / NUIT_FIN de config_local.py), en
// minutes depuis minuit, heure de Paris ; null = non programmé.
let nuitDebut = null;
let nuitFin = null;

// Dernier état connu de la plage horaire (null = pas encore vérifié)
let dansPlageNuitPrecedent = null;

function minutesParis() {
    const [heures, minutes] = new Intl.DateTimeFormat("fr-FR", {
        timeZone: "Europe/Paris",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23"
    }).format(new Date()).split(":").map(Number);

    return heures * 60 + minutes;
}

function dansPlageNuit() {
    const maintenant = minutesParis();

    // Plage passant minuit (ex. 22:30 -> 07:00)
    return nuitDebut < nuitFin
        ? maintenant >= nuitDebut && maintenant < nuitFin
        : maintenant >= nuitDebut || maintenant < nuitFin;
}

// Appelée chaque seconde. Seuls les passages d'heure basculent le mode :
// à NUIT_DEBUT on passe en mode nuit (sans effet s'il est déjà actif par
// le bouton) ; à NUIT_FIN on revient au jour si la nuit est toujours là.
// Entre les deux, le bouton et le toucher restent libres. Au chargement
// de la page dans la plage (redémarrage la nuit), le mode nuit est mis.
function verifierPlageNuit() {
    if (nuitDebut === null || nuitFin === null) return;

    const dedans = dansPlageNuit();

    if (dedans !== dansPlageNuitPrecedent) {
        if (dedans) {
            activerModeNuit();
        } else if (dansPlageNuitPrecedent !== null) {
            activerModeJour();
        }
        dansPlageNuitPrecedent = dedans;
    }
}

// ==========================================
// CURSEUR DE LA SOURIS
// ==========================================

// Le curseur est masqué par défaut (kiosque tactile). Il ne réapparaît
// que si une vraie souris bouge, puis disparaît après 3 s d'inactivité.
// Les touchers de l'écran (pointerType « touch ») ne l'affichent pas.
let minuterieCurseur = null;

function gererCurseur(e) {
    if (e.pointerType !== "mouse") return;

    document.documentElement.classList.remove("curseur-masque");
    clearTimeout(minuterieCurseur);
    minuterieCurseur = setTimeout(() => {
        document.documentElement.classList.add("curseur-masque");
    }, 3000);
}

// ==========================================
// GRAPHIQUES D'UN CAPTEUR (vue agrandie)
// ==========================================

// Un toucher sur une case de capteur (affichage interactif) ouvre deux
// graphiques de température : relevés des 24 dernières heures et
// moyennes journalières des 30 derniers jours. Un toucher n'importe où
// les referme, sinon fermeture automatique après DUREE_DETAIL_MS.
let minuterieCapteur = null;

// Taille du dessin (unités SVG, mis à l'échelle de la fenêtre)
const GRAPHIQUE = {
    largeur: 840, hauteur: 210,
    gauche: 46, droite: 18, haut: 22, bas: 26
};

function echapper(texte) {
    return String(texte).replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

async function ouvrirCapteur(nom) {
    const vue = document.getElementById("detail-capteur");

    clearTimeout(minuterieCapteur);
    minuterieCapteur = setTimeout(fermerCapteur, DUREE_DETAIL_MS);

    vue.innerHTML = fenetreCapteur(nom, '<p class="vide">Chargement…</p>');
    vue.hidden = false;

    let contenu;
    try {
        const reponse = await fetch(
            "/api/capteurs/historique?capteur=" + encodeURIComponent(nom),
            { cache: "no-store" }
        );
        const historique = await reponse.json().catch(() => ({}));

        if (!reponse.ok) {
            throw new Error(historique.erreur || "Erreur HTTP " + reponse.status);
        }
        contenu = graphiques24h(historique.heures || [])
            + graphiques30j(historique.jours || []);

    } catch (e) {
        console.error("Erreur historique capteur :", e);
        contenu = `<p class="vide">${avecEmojis("⚠️")} ${echapper(e.message)}</p>`;
    }

    // Vue refermée pendant le chargement : ne pas la rouvrir
    if (!vue.hidden) vue.innerHTML = fenetreCapteur(nom, contenu);
}

function fermerCapteur() {
    clearTimeout(minuterieCapteur);
    const vue = document.getElementById("detail-capteur");
    vue.hidden = true;
    vue.replaceChildren();
}

function fenetreCapteur(nom, contenu) {
    return `
        <section class="fenetre-detail fenetre-capteur">
            <div class="date">
                <span>${echapper(nom)}</span>
                <span class="periode-case">Température</span>
            </div>
            ${contenu}
            <p class="fermer-detail">Toucher pour fermer</p>
        </section>
    `;
}

// Pas « rond » de l'échelle des températures : 4 à 6 graduations
function echelleTemperatures(valeurs) {
    let min = Math.min(...valeurs);
    let max = Math.max(...valeurs);
    if (max - min < 2) { min -= 1; max += 1; }

    const pas = [0.5, 1, 2, 5, 10, 20].find(p => (max - min) / p <= 5) || 50;
    min = Math.floor(min / pas) * pas;
    max = Math.ceil(max / pas) * pas;

    const graduations = [];
    for (let v = min; v <= max + pas / 2; v += pas) graduations.push(v);
    return { min, max, graduations };
}

// Graphique en ligne : points [{x, y}] (x entre xMin et xMax, y en °C ;
// y null = trou), graduations [{x, texte}] sous l'axe horizontal.
// ecartMax : au-delà de cet écart entre deux points, la courbe est
// interrompue (relevés manquants). Les valeurs minimale, maximale et
// la dernière sont écrites sur la courbe.
// bande (facultatif) : [{x, min, max}] dessinée sous la courbe (minimum et
// maximum de chaque jour), interrompue comme la courbe.
function dessinerGraphique({ points, xMin, xMax, graduationsX, ecartMax, marqueurs, bande = [] }) {
    const G = GRAPHIQUE;
    const valides = points.filter(p => p.y != null);
    const bandeValide = bande.filter(b => b.min != null && b.max != null);
    const { min, max, graduations } = echelleTemperatures([
        ...valides.map(p => p.y),
        ...bandeValide.flatMap(b => [b.min, b.max])
    ]);

    const px = x => G.gauche + (x - xMin) / (xMax - xMin) * (G.largeur - G.gauche - G.droite);
    const py = y => G.haut + (max - y) / (max - min) * (G.hauteur - G.haut - G.bas);

    let svg = "";

    // Grille horizontale et graduations des températures
    for (const v of graduations) {
        svg += `<line class="grille-axe" x1="${G.gauche}" x2="${G.largeur - G.droite}"
                    y1="${py(v)}" y2="${py(v)}"/>
                <text class="texte-axe" x="${G.gauche - 8}" y="${py(v) + 4}"
                    text-anchor="end">${nombre(v, decimalesGraduations(graduations))}°</text>`;
    }

    // Graduations horizontales (heures ou dates)
    for (const g of graduationsX) {
        svg += `<text class="texte-axe" x="${px(g.x)}" y="${G.hauteur - 6}"
                    text-anchor="middle">${g.texte}</text>`;
    }

    // Bande min - max : un polygone par suite de jours sans trou (un jour
    // isolé est élargi pour rester visible)
    const segments = [];
    for (const b of bandeValide) {
        const dernierSegment = segments[segments.length - 1];
        const precedente = dernierSegment?.[dernierSegment.length - 1];
        if (precedente && b.x - precedente.x <= ecartMax) dernierSegment.push(b);
        else segments.push([b]);
    }
    for (const s of segments) {
        const largeur = s.length === 1 ? 0.3 : 0;
        const haut = s.map((b, i) =>
            `${i ? "L" : "M"}${px(b.x - largeur).toFixed(1)},${py(b.max).toFixed(1)}`
            + (largeur ? `L${px(b.x + largeur).toFixed(1)},${py(b.max).toFixed(1)}` : "")
        ).join("");
        const bas = [...s].reverse().map(b =>
            (largeur ? `L${px(b.x + largeur).toFixed(1)},${py(b.min).toFixed(1)}` : "")
            + `L${px(b.x - largeur).toFixed(1)},${py(b.min).toFixed(1)}`
        ).join("");
        svg += `<path class="bande" d="${haut}${bas}Z"/>`;
    }

    // Courbe, interrompue aux trous
    let chemin = "";
    let precedent = null;
    for (const p of points) {
        if (p.y == null) { precedent = null; continue; }
        const nouveau = !precedent || p.x - precedent.x > ecartMax;
        chemin += `${nouveau ? "M" : "L"}${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`;
        precedent = p;
    }
    svg += `<path class="courbe" d="${chemin}"/>`;

    if (marqueurs) {
        for (const p of valides) {
            svg += `<circle class="point" cx="${px(p.x)}" cy="${py(p.y)}" r="4"/>`;
        }
    }

    // Étiquettes : minimum, maximum et dernière valeur
    const pMin = valides.reduce((a, b) => (b.y < a.y ? b : a));
    const pMax = valides.reduce((a, b) => (b.y > a.y ? b : a));
    const dernier = valides[valides.length - 1];
    // Température constante : seule la dernière valeur est écrite
    const etiquettes = pMin.y === pMax.y
        ? new Map()
        : new Map([[pMax, "haut"], [pMin, "bas"]]);
    if (!etiquettes.has(dernier)) etiquettes.set(dernier, "haut");

    for (const [p, position] of etiquettes) {
        let x = Math.min(Math.max(px(p.x), G.gauche + 20), G.largeur - G.droite - 20);
        let y = position === "haut" ? py(p.y) - 8 : py(p.y) + 18;
        let ancre = "middle";

        // Pas de place au-dessus ou au-dessous (bord du graphique, axe des
        // heures) : étiquette à côté du point
        if (y < 14 || y > G.hauteur - G.bas - 2) {
            y = py(p.y) + 5;
            const aDroite = px(p.x) < G.largeur - G.droite - 60;
            x = px(p.x) + (aDroite ? 10 : -10);
            ancre = aDroite ? "start" : "end";
        }

        svg += `<text class="etiquette" x="${x}" y="${y}"
                    text-anchor="${ancre}">${nombre(p.y, 1)}°</text>`;
    }

    return `<svg viewBox="0 0 ${G.largeur} ${G.hauteur}" role="img">${svg}</svg>`;
}

// Décimales des graduations : 1 si le pas est d'un demi-degré
function decimalesGraduations(graduations) {
    return graduations.some(v => !Number.isInteger(v)) ? 1 : 0;
}

function graphiques24h(heures) {
    const titre = "<h3>24 dernières heures</h3>";
    const points = heures.map(r => ({
        x: new Date(r.date).getTime(),
        y: r.temperature
    }));

    if (!points.some(p => p.y != null)) {
        return `<div class="graphique-capteur">${titre}
            <p class="vide">Aucun relevé sur les 24 dernières heures.</p></div>`;
    }

    const xMax = Date.now();
    const xMin = xMax - 24 * 3600 * 1000;

    // Une graduation toutes les 3 heures « rondes »
    const graduationsX = [];
    const heure = new Date(xMin);
    heure.setMinutes(0, 0, 0);
    heure.setHours(Math.ceil((heure.getHours() + 1) / 3) * 3);
    for (; heure.getTime() < xMax; heure.setHours(heure.getHours() + 3)) {
        graduationsX.push({ x: heure.getTime(), texte: heure.getHours() + " h" });
    }

    return `<div class="graphique-capteur">${titre}${dessinerGraphique({
        points, xMin, xMax, graduationsX,
        ecartMax: 20 * 60 * 1000,       // plus de 20 min sans relevé
        marqueurs: false
    })}</div>`;
}

function graphiques30j(jours) {
    const titre = "<h3>Moyenne journalière, 30 derniers jours"
        + ' <span class="legende-bande">(bande : minimum – maximum du jour)</span></h3>';

    // Les 30 jours, du plus ancien à aujourd'hui (x = 0 … 29)
    const parJour = new Map(jours.map(j => [j.jour, j]));
    const points = [];
    const bande = [];
    const graduationsX = [];
    for (let k = 29; k >= 0; k--) {
        const date = dateDuJour(-k);
        const x = 29 - k;
        const jour = parJour.get(date);
        points.push({ x, y: jour?.temperature ?? null });
        bande.push({
            x,
            min: jour?.temperature_min ?? null,
            max: jour?.temperature_max ?? null
        });
        if (k % 5 === 0) {
            graduationsX.push({ x, texte: date.slice(8, 10) + "/" + date.slice(5, 7) });
        }
    }

    if (!points.some(p => p.y != null)) {
        return `<div class="graphique-capteur">${titre}
            <p class="vide">Aucun relevé sur les 30 derniers jours.</p></div>`;
    }

    return `<div class="graphique-capteur">${titre}${dessinerGraphique({
        points, xMin: -0.5, xMax: 29.5, graduationsX,
        ecartMax: 1,                    // un jour manquant interrompt la courbe
        marqueurs: true,
        bande
    })}</div>`;
}

// ==========================================
// CAPTEURS DE LA MAISON
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
        capteursOk = true;

        // Effacer uniquement l'ancienne liste des capteurs
        conteneur.replaceChildren();

        if (capteurs.length === 0) {
            conteneur.textContent = "Aucun capteur détecté";
            return;
        }

        for (const capteur of capteurs) {

            const carte = document.createElement("section");
            carte.className = "case-capteur";

            // Affichage interactif : un toucher ouvre les graphiques
            if (interactif && capteur.nom) {
                carte.classList.add("cliquable");
                carte.dataset.capteur = capteur.nom;
                carte.setAttribute("role", "button");
                carte.title = "Afficher les graphiques";
            }

            const titre = document.createElement("h3");
            titre.textContent = capteur.nom || "Capteur inconnu";

            const temperature = document.createElement("div");
            temperature.className = "temperature-capteur";
            temperature.textContent =
                nombre(capteur.temperature, 1) + " °C";

            const humidite = document.createElement("div");
            humidite.className = "detail-capteur";
            humidite.innerHTML =
                avecEmojis("💧 ") +
                nombre(capteur.humidite) + " %";

            const batterie = document.createElement("div");
            batterie.className = "detail-capteur";
            batterie.innerHTML =
                avecEmojis("🔋 ") +
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

            const ligneMesures = document.createElement("div");
            ligneMesures.className = "ligne-mesures";
            ligneMesures.append(humidite, batterie);
            carte.append(
                titre,
                temperature,
                ligneMesures,
                extremes
            );
            conteneur.appendChild(carte);
        }

    } catch (e) {
        console.error("Erreur capteurs de la maison :", e);
        capteursOk = false;

        // En cas d'erreur, conserver les dernières cases.
        if (!conteneur.querySelector(".case-capteur")) {
            conteneur.innerHTML = avecEmojis(
                "⚠️ Capteurs momentanément indisponibles"
            );
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
        luminositeNuit = config.luminosite_nuit ?? luminositeNuit;
        interactif = config.interactif ?? interactif;
        nuitDebut = config.nuit_debut ?? null;
        nuitFin = config.nuit_fin ?? null;
        veilleHdmi = config.veille_hdmi ?? false;

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
        } else if (e.target.closest("#boutonNuit")) {
            activerModeNuit();
        } else if (interactif) {
            const caseJour = e.target.closest(".case[data-jour]");
            if (caseJour) {
                ouvrirDetail(
                    Number(caseJour.dataset.jour),
                    Number(caseJour.dataset.periode)
                );
            }
        }
    });

    // Vue agrandie : un toucher sur le fournisseur en change (la vue
    // reste ouverte, 60 s de plus) ; ailleurs, il la referme
    document.getElementById("detail-prevision").addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();

        if (e.target.closest(".fournisseur-detail")) {
            clearTimeout(minuterieDetail);
            minuterieDetail = setTimeout(fermerDetail, DUREE_DETAIL_MS);
            changerFournisseur();
        } else {
            fermerDetail();
        }
    });

    // Cases des capteurs (reconstruites à chaque lecture) : clic écouté
    // sur la liste. Graphiques : un toucher n'importe où les referme.
    document.getElementById("liste-capteurs").addEventListener("click", e => {
        const carte = e.target.closest(".case-capteur[data-capteur]");
        if (carte) ouvrirCapteur(carte.dataset.capteur);
    });

    document.getElementById("detail-capteur").addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        fermerCapteur();
    });

    // Mode nuit : le moindre clic (ou toucher) sur le voile revient au
    // jour en affichage interactif ; sinon il est sans effet (le mode
    // nuit ne suit que NUIT_DEBUT / NUIT_FIN).
    document.getElementById("voile-nuit").addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        if (interactif) activerModeJour();
    });

    if (!interactif) {
        document.getElementById("voile-nuit").title = "";
    }

    // Mode nuit programmé : état au chargement de la page
    verifierPlageNuit();

    // Écran éteint (option hdmi) : guetter le réveil au toucher
    if (veilleHdmi) setInterval(surveillerReveil, 2000);

    // Curseur masqué tant que la souris ne bouge pas
    document.addEventListener("pointermove", gererCurseur);

    // Premier chargement des prévisions
    actualiser();

    // Premier chargement des capteurs
    actualiserCapteurs();

    // Rotation des périodes : toutes les 12 secondes
    setInterval(() => {
        periodeActive =
            (periodeActive + 1) % PERIODES.length;

        afficher();

        // Vue agrandie ouverte : elle suit aussi la nouvelle période
        if (detailOuvert) {
            detailOuvert.indexPeriode = periodeActive;
            afficherDetail();
        }

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

    // Horloge, comptes à rebours et mode nuit programmé
    setInterval(() => {
        afficherHorloge();
        verifierPlageNuit();
    }, 1000);
}

// Démarrer l'application
initialiser();
