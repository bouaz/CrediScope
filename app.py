
import re
import io
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# CrediScope — Prétraitement SmartCredit et tableau de bord
# ============================================================

st.set_page_config(
    page_title="CrediScope | Analyse de crédit",
    page_icon="💳",
    layout="wide",
)

st.title("💳 CrediScope")
st.subheader("Analyse du risque de crédit et détection des défauts")
st.markdown(
    "Importez votre fichier brut pour nettoyer les données, "
    "calculer les indicateurs financiers et explorer le risque de défaut."
)

COL_NUM = [
    "montant_pret",
    "taux_interet",
    "mensualite",
    "revenu_annuel",
    "ratio_endettement",
    "retards_paiement_2ans",
    "demandes_credit_6mois",
    "comptes_ouverts",
    "incidents_publics",
    "taux_utilisation_credit_renouvelable",
    "nombre_total_comptes",
    "montant_total_rembourse",
    "solde_total",
    "plafond_total_credit_renouvelable",
    "comptes_ouverts_24mois",
    "solde_moyen",
    "credit_cartes_disponible",
    "taux_utilisation_cartes",
    "plafond_total_credit",
    "solde_credit_renouvelable",
    "plafond_total_cartes",
    "plafond_total_prets_echelonnes",
]

MARQUEURS_MANQUANTS = [
    "", "NA", "N/A", "NaN", "nan", "null", "None", "-"
]

STATUTS_CIBLES = {
    "charged off": 1,
    "fully paid": 0,
}


def normaliser_nom_colonne(nom):
    """Uniformise les noms de colonnes."""
    nom = str(nom).strip().lower()
    nom = re.sub(r"[\s\-\/]+", "_", nom)
    nom = re.sub(r"[^\w]", "", nom)
    return nom


def charger_fichier(fichier):
    """Charge un CSV ou un fichier Excel."""
    nom = fichier.name.lower()

    if nom.endswith((".xlsx", ".xls")):
        df = pd.read_excel(fichier)
    elif nom.endswith(".csv"):
        contenu = fichier.getvalue()

        # Détection simple du séparateur CSV.
        premiere_ligne = contenu.splitlines()[0] if contenu else b""
        sep = ";" if premiere_ligne.count(b";") > premiere_ligne.count(b",") else ","

        try:
            df = pd.read_csv(
                io.BytesIO(contenu),
                sep=sep,
                encoding="utf-8-sig",
                na_values=MARQUEURS_MANQUANTS,
                keep_default_na=True,
                low_memory=False,
            )
        except UnicodeDecodeError:
            df = pd.read_csv(
                io.BytesIO(contenu),
                sep=sep,
                encoding="latin-1",
                na_values=MARQUEURS_MANQUANTS,
                keep_default_na=True,
                low_memory=False,
            )
    else:
        raise ValueError("Format non pris en charge. Importez un fichier CSV ou Excel.")

    df.columns = [normaliser_nom_colonne(c) for c in df.columns]

    # Nettoyage des valeurs textuelles et des marqueurs de valeurs manquantes.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace(MARQUEURS_MANQUANTS, pd.NA)

    return df


def trouver_colonne(df, candidats):
    """Retourne le premier nom de colonne disponible."""
    for col in candidats:
        col_normalisee = normaliser_nom_colonne(col)
        if col_normalisee in df.columns:
            return col_normalisee
    return None


def pretraiter_donnees(df_brut):
    """Applique les principales étapes de prétraitement SmartCredit."""
    df = df_brut.copy()
    lignes_initiales = len(df)

    # Conversion des colonnes numériques disponibles.
    for col in COL_NUM:
        if col in df.columns:
            valeurs = (
                df[col]
                .astype("string")
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[col] = pd.to_numeric(valeurs, errors="coerce")

    # Durée du prêt en mois, extraite du texte si la colonne existe.
    if "duree_pret" in df.columns:
        duree = df["duree_pret"].astype("string")
        df["duree_mois"] = pd.to_numeric(
            duree.str.extract(r"(\d+(?:[.,]\d+)?)", expand=False)
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )

    # Ancienneté professionnelle en années.
    if "anciennete_emploi" in df.columns:
        anciennete = df["anciennete_emploi"].astype("string").str.strip().str.lower()

        mapping_anciennete = {
            "< 1 year": 0,
            "<1 year": 0,
            "less than 1 year": 0,
            "1 year": 1,
            "2 years": 2,
            "3 years": 3,
            "4 years": 4,
            "5 years": 5,
            "6 years": 6,
            "7 years": 7,
            "8 years": 8,
            "9 years": 9,
            "10+ years": 10,
            "10 years or more": 10,
        }

        df["anciennete_emploi_ans"] = anciennete.map(mapping_anciennete)

        # Tente également de traiter les libellés contenant un nombre.
        a_convertir = df["anciennete_emploi_ans"].isna()
        nombres = pd.to_numeric(
            anciennete.str.extract(r"(\d+)", expand=False),
            errors="coerce",
        )
        df.loc[a_convertir, "anciennete_emploi_ans"] = nombres[a_convertir]

    # Retirer les lignes entièrement vides, sauf si elles contiennent un identifiant.
    colonnes_test = [c for c in df.columns if c != "id_pret"]
    if colonnes_test:
        df = df.loc[~df[colonnes_test].isna().all(axis=1)].copy()

    lignes_apres_vides = len(df)

    # Suppression des doublons en ignorant l'identifiant du prêt.
    colonnes_doublons = [c for c in df.columns if c != "id_pret"]
    if colonnes_doublons:
        df = df.drop_duplicates(subset=colonnes_doublons).copy()

    lignes_apres_doublons = len(df)

    # Indicateur de revenu extrême : Q3 + 3 * IQR.
    if "revenu_annuel" in df.columns:
        revenus = df["revenu_annuel"]
        revenus_valides = revenus.dropna()

        if len(revenus_valides) > 0:
            q1 = revenus_valides.quantile(0.25)
            q3 = revenus_valides.quantile(0.75)
            iqr = q3 - q1
            seuil = q3 + 3 * iqr
            df["revenu_extreme"] = (
                revenus.notna() & (revenus > seuil)
            ).astype(int)
        else:
            df["revenu_extreme"] = 0

    # Ratio montant du prêt / revenu annuel.
    if {"montant_pret", "revenu_annuel"}.issubset(df.columns):
        revenu = df["revenu_annuel"].replace(0, np.nan)
        df["loan_income_ratio"] = df["montant_pret"] / revenu

    # Charge annuelle des mensualités / revenu annuel.
    if {"mensualite", "revenu_annuel"}.issubset(df.columns):
        revenu = df["revenu_annuel"].replace(0, np.nan)
        df["payment_burden"] = (df["mensualite"] * 12) / revenu

    # Score de stress financier : moyenne des rangs percentiles.
    colonnes_stress = [
        "ratio_endettement",
        "taux_utilisation_cartes",
        "demandes_credit_6mois",
    ]

    if all(c in df.columns for c in colonnes_stress):
        df["financial_stress_score"] = np.nan
        complet = df[colonnes_stress].notna().all(axis=1)

        if complet.any():
            rangs = df.loc[complet, colonnes_stress].rank(
                pct=True,
                method="average",
            )
            df.loc[complet, "financial_stress_score"] = (
                rangs.mean(axis=1) * 100
            )

    # Création de la cible de défaut à partir du statut du prêt.
    colonne_statut = trouver_colonne(
        df,
        [
            "statut_pret",
            "loan_status",
            "statut",
            "status",
            "etat_pret",
            "etat_du_pret",
        ],
    )

    if colonne_statut:
        statut_normalise = (
            df[colonne_statut]
            .astype("string")
            .str.strip()
            .str.lower()
        )
        df["default_label"] = statut_normalise.map(STATUTS_CIBLES)
    else:
        df["default_label"] = np.nan

    # Retrait de la variable de remboursement total pour éviter la fuite de cible.
    # Elle n'est pas utilisée comme variable explicative dans ce tableau de bord.
    if "montant_total_rembourse" in df.columns:
        df = df.drop(columns=["montant_total_rembourse"])

    rapport = pd.DataFrame(
        [
            {"controle": "Lignes initiales", "valeur": lignes_initiales},
            {
                "controle": "Lignes entièrement vides supprimées",
                "valeur": lignes_initiales - lignes_apres_vides,
            },
            {
                "controle": "Doublons supprimés",
                "valeur": lignes_apres_vides - lignes_apres_doublons,
            },
            {"controle": "Lignes finales", "valeur": len(df)},
            {
                "controle": "Colonnes finales",
                "valeur": len(df.columns),
            },
            {
                "controle": "Lignes avec cible connue",
                "valeur": int(df["default_label"].notna().sum()),
            },
            {
                "controle": "Valeurs manquantes au total",
                "valeur": int(df.isna().sum().sum()),
            },
        ]
    )

    return df, rapport, colonne_statut


# ============================================================
# Interface
# ============================================================

fichier = st.file_uploader(
    "Importez votre dataset brut SmartCredit",
    type=["csv", "xlsx", "xls"],
    help="Le prétraitement est appliqué automatiquement après l'import.",
)

if fichier is None:
    st.info(
        "Importez un fichier CSV ou Excel pour démarrer l'analyse. "
        "Pour tester le prétraitement, utilisez de préférence le fichier brut."
    )
    st.markdown(
        """
        **Le tableau de bord comprend :**
        - Nettoyage des noms de colonnes et conversion numérique
        - Suppression des lignes vides et des doublons
        - Création de ratios financiers et d'un score de stress
        - Analyse historique des statuts de remboursement
        - Export des données prétraitées
        """
    )
    st.stop()

try:
    donnees_brutes = charger_fichier(fichier)
    data, rapport_qualite, colonne_statut = pretraiter_donnees(donnees_brutes)
except Exception as erreur:
    st.error(f"Impossible de lire ou de prétraiter le fichier : {erreur}")
    st.stop()

if data.empty:
    st.error("Le fichier ne contient aucune ligne exploitable après le nettoyage.")
    st.stop()

st.success("Fichier chargé et prétraitement terminé.")

# ============================================================
# Indicateurs principaux
# ============================================================

st.header("📊 Vue d'ensemble")

total_prets = len(data)
cibles_connues = data["default_label"].notna()
connus = data.loc[cibles_connues, "default_label"]

taux_defaut = (
    float(connus.mean() * 100)
    if len(connus) > 0
    else np.nan
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("Nombre de prêts", f"{total_prets:,}".replace(",", " "))

c2.metric(
    "Statuts connus",
    f"{int(cibles_connues.sum()):,}".replace(",", " "),
)

c3.metric(
    "Taux historique de défaut",
    f"{taux_defaut:.2f}%" if pd.notna(taux_defaut) else "Indisponible",
)

if "loan_income_ratio" in data.columns:
    ratio_median = data["loan_income_ratio"].replace(
        [np.inf, -np.inf], np.nan
    ).median()
    ratio_affiche = f"{ratio_median:.2f}" if pd.notna(ratio_median) else "N/D"
else:
    ratio_affiche = "Colonne indisponible"

c4.metric("Ratio prêt / revenu médian", ratio_affiche)

c5, c6, c7, c8 = st.columns(4)

if "payment_burden" in data.columns:
    charge_mediane = data["payment_burden"].replace(
        [np.inf, -np.inf], np.nan
    ).median()
    c5.metric(
        "Charge annuelle médiane",
        f"{charge_mediane:.1%}" if pd.notna(charge_mediane) else "N/D",
    )
else:
    c5.metric("Charge annuelle médiane", "N/D")

if "financial_stress_score" in data.columns:
    stress_moyen = data["financial_stress_score"].mean()
    c6.metric(
        "Score de stress moyen",
        f"{stress_moyen:.1f}/100" if pd.notna(stress_moyen) else "N/D",
    )
else:
    c6.metric("Score de stress moyen", "N/D")

if "revenu_extreme" in data.columns:
    c7.metric("Revenus extrêmes détectés", int(data["revenu_extreme"].sum()))
else:
    c7.metric("Revenus extrêmes détectés", "N/D")

c8.metric("Variables disponibles", len(data.columns))

# ============================================================
# Vérification de la qualité des données
# ============================================================

st.header("🧹 Qualité des données")

avec_rapport, avec_manquants = st.tabs(
    ["Rapport de prétraitement", "Valeurs manquantes"]
)

with avec_rapport:
    st.dataframe(rapport_qualite, use_container_width=True, hide_index=True)

with avec_manquants:
    nb_manquants = data.isna().sum()
    pct_manquants = (nb_manquants / len(data) * 100).round(2)

    tableau_manquants = pd.DataFrame(
        {
            "colonne": data.columns,
            "valeurs_manquantes": [
                int(nb_manquants[c]) for c in data.columns
            ],
            "pourcentage_manquant": [
                float(pct_manquants[c]) for c in data.columns
            ],
        }
    ).sort_values("pourcentage_manquant", ascending=False)

    st.dataframe(
        tableau_manquants,
        use_container_width=True,
        hide_index=True,
    )

    colonnes_incompletes = tableau_manquants[
        tableau_manquants["valeurs_manquantes"] > 0
    ]

    if not colonnes_incompletes.empty:
        graphique_manquants = px.bar(
            colonnes_incompletes,
            x="colonne",
            y="pourcentage_manquant",
            title="Pourcentage de valeurs manquantes par colonne",
            labels={
                "colonne": "Colonne",
                "pourcentage_manquant": "Valeurs manquantes (%)",
            },
        )
        graphique_manquants.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(graphique_manquants, use_container_width=True)

# ============================================================
# Visualisations
# ============================================================

st.header("📈 Analyse exploratoire")

col_gauche, col_droite = st.columns(2)

with col_gauche:
    if colonne_statut:
        distribution = (
            data[colonne_statut]
            .fillna("Statut inconnu")
            .astype(str)
            .value_counts()
            .rename_axis("statut")
            .reset_index(name="nombre")
        )

        fig_statut = px.pie(
            distribution,
            names="statut",
            values="nombre",
            title="Répartition des statuts de prêts",
            hole=0.35,
        )
        st.plotly_chart(fig_statut, use_container_width=True)
    else:
        st.warning(
            "Aucune colonne de statut reconnue. "
            "Vérifiez que le fichier contient une colonne comme "
            "'loan_status' ou 'statut_pret'."
        )

with col_droite:
    if "taux_interet" in data.columns:
        taux = data[["taux_interet"]].dropna()

        if not taux.empty:
            fig_taux = px.histogram(
                taux,
                x="taux_interet",
                nbins=30,
                title="Distribution des taux d'intérêt",
                labels={"taux_interet": "Taux d'intérêt"},
            )
            st.plotly_chart(fig_taux, use_container_width=True)
        else:
            st.info("Aucune valeur disponible pour les taux d'intérêt.")
    else:
        st.info("Colonne 'taux_interet' absente du fichier.")

col_gauche, col_droite = st.columns(2)

with col_gauche:
    if {"classe_credit", "default_label"}.issubset(data.columns):
        taux_par_classe = (
            data.dropna(subset=["default_label", "classe_credit"])
            .groupby("classe_credit", as_index=False)
            .agg(
                taux_defaut=("default_label", "mean"),
                nombre_prets=("default_label", "size"),
            )
        )
        taux_par_classe["taux_defaut"] *= 100

        if not taux_par_classe.empty:
            fig_classe = px.bar(
                taux_par_classe,
                x="classe_credit",
                y="taux_defaut",
                hover_data=["nombre_prets"],
                title="Taux historique de défaut par classe de crédit",
                labels={
                    "classe_credit": "Classe de crédit",
                    "taux_defaut": "Défaut historique (%)",
                    "nombre_prets": "Nombre de prêts",
                },
            )
            st.plotly_chart(fig_classe, use_container_width=True)
    else:
        st.info(
            "Le graphique par classe nécessite les colonnes "
            "'classe_credit' et 'default_label'."
        )

with col_droite:
    if {"loan_income_ratio", "default_label"}.issubset(data.columns):
        comparaison = data.dropna(
            subset=["loan_income_ratio", "default_label"]
        ).copy()

        if not comparaison.empty:
            comparaison["résultat"] = comparaison["default_label"].map(
                {0: "Fully Paid — remboursé", 1: "Charged Off — défaut"}
            )

            fig_ratio = px.box(
                comparaison,
                x="résultat",
                y="loan_income_ratio",
                color="résultat",
                title="Ratio prêt / revenu selon le résultat du prêt",
                labels={
                    "résultat": "Résultat",
                    "loan_income_ratio": "Montant du prêt / revenu annuel",
                },
            )
            st.plotly_chart(fig_ratio, use_container_width=True)
    else:
        st.info(
            "Le graphique du ratio prêt/revenu nécessite une colonne "
            "'montant_pret', 'revenu_annuel' et des statuts connus."
        )

# ============================================================
# Analyse du stress financier
# ============================================================

st.header("⚠️ Stress financier")

if "financial_stress_score" in data.columns:
    scores = data["financial_stress_score"].dropna()

    if not scores.empty:
        fig_stress = px.histogram(
            scores,
            x="financial_stress_score",
            nbins=20,
            title="Distribution du score de stress financier",
            labels={"financial_stress_score": "Score de stress (0–100)"},
        )
        st.plotly_chart(fig_stress, use_container_width=True)

        st.caption(
            "Le score est la moyenne des rangs percentiles du ratio "
            "d'endettement, de l'utilisation des cartes et des demandes "
            "de crédit récentes. Il s'agit d'un indicateur exploratoire, "
            "pas d'une probabilité calibrée de défaut."
        )
    else:
        st.info(
            "Impossible de calculer le score : vérifiez que les colonnes "
            "ratio_endettement, taux_utilisation_cartes et "
            "demandes_credit_6mois contiennent des valeurs numériques."
        )
else:
    st.info(
        "Le score de stress n'a pas été créé, car certaines colonnes "
        "nécessaires sont absentes."
    )

# ============================================================
# Aperçu et téléchargements
# ============================================================

st.header("📋 Données prétraitées")

st.dataframe(data.head(100), use_container_width=True)

csv_nettoye = data.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="⬇️ Télécharger toutes les données prétraitées",
    data=csv_nettoye,
    file_name="SmartCredit_nettoye.csv",
    mime="text/csv",
)

donnees_terminees = data.loc[data["default_label"].notna()].copy()
csv_termine = donnees_terminees.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="⬇️ Télécharger les prêts avec statut connu",
    data=csv_termine,
    file_name="SmartCredit_termines.csv",
    mime="text/csv",
)

csv_rapport = rapport_qualite.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="⬇️ Télécharger le rapport de contrôle qualité",
    data=csv_rapport,
    file_name="rapport_controle_qualite.csv",
    mime="text/csv",
)

st.caption(
    "CrediScope — Analyse descriptive du risque de crédit. "
    "Les indicateurs historiques ne constituent pas, à eux seuls, "
    "une prédiction de défaut pour un nouveau demandeur."
)
