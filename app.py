
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="CrediScope",
    page_icon="📊",
    layout="wide"
)

st.title("📊 CrediScope")
st.subheader("Tableau de bord d'analyse du risque de crédit")

st.write(
    "Importez un fichier de données pour explorer les prêts, "
    "la situation financière et les indicateurs de risque."
)

# Colonnes attendues dans le jeu de données
NUMERIC_COLUMNS = [
    "montant_pret",
    "duree_pret",
    "taux_interet",
    "mensualite",
    "anciennete_emploi",
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

MISSING_MARKERS = [
    "", "NA", "N/A", "NaN", "nan", "null", "None", "-"
]


def load_file(uploaded_file):
    """Charge les fichiers CSV ou Excel."""
    filename = uploaded_file.name.lower()

    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)

    # Détection automatique du séparateur CSV
    try:
        return pd.read_csv(
            uploaded_file,
            sep=None,
            engine="python",
            encoding="utf-8-sig",
            na_values=MISSING_MARKERS
        )
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        return pd.read_csv(
            uploaded_file,
            sep=None,
            engine="python",
            encoding="latin-1",
            na_values=MISSING_MARKERS
        )


def clean_data(data):
    """Nettoie les données et supprime les lignes presque vides."""
    df = data.copy()

    # Nettoyer les noms des colonnes
    df.columns = df.columns.astype(str).str.strip()

    # Supprimer les colonnes dupliquées
    df = df.loc[:, ~df.columns.duplicated()]

    # Nettoyer les valeurs textuelles
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].map(
            lambda x: x.strip() if isinstance(x, str) else x
        )
        df[col] = df[col].replace(MISSING_MARKERS, np.nan)

    # Convertir les colonnes numériques présentes
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    rows_before = len(df)

    # Identifier les lignes vides, même si elles contiennent un identifiant
    data_columns = [
        col for col in df.columns
        if col.lower() != "id_pret"
    ]

    if data_columns:
        almost_empty_mask = df[data_columns].isna().all(axis=1)
    else:
        almost_empty_mask = df.isna().all(axis=1)

    removed_rows = int(almost_empty_mask.sum())
    df = df.loc[~almost_empty_mask].copy()

    duplicate_rows = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()

    return df, removed_rows, duplicate_rows, rows_before


def calculate_indicators(df):
    """Calcule les indicateurs lorsque les colonnes nécessaires existent."""
    df = df.copy()

    # Montant du prêt / revenu annuel
    if {"montant_pret", "revenu_annuel"}.issubset(df.columns):
        income = df["revenu_annuel"].replace(0, np.nan)
        df["loan_income_ratio"] = df["montant_pret"] / income

    # Paiements annuels / revenu annuel
    if {"mensualite", "revenu_annuel"}.issubset(df.columns):
        income = df["revenu_annuel"].replace(0, np.nan)
        df["payment_burden"] = (df["mensualite"] * 12) / income

    # Score relatif de tension financière, calculé seulement
    # lorsque les trois variables sont présentes et renseignées.
    stress_columns = [
        "ratio_endettement",
        "taux_utilisation_cartes",
        "demandes_credit_6mois"
    ]

    if all(col in df.columns for col in stress_columns):
        valid = df[stress_columns].notna().all(axis=1)
        df["financial_stress_score"] = np.nan

        if valid.any():
            ranks = df.loc[valid, stress_columns].rank(
                pct=True,
                method="average"
            )
            df.loc[valid, "financial_stress_score"] = (
                ranks.mean(axis=1) * 100
            )

    return df


def add_default_label(df):
    """Crée une étiquette de défaut si statut_pret est disponible."""
    if "statut_pret" not in df.columns:
        return df

    status = (
        df["statut_pret"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    default_values = [
        "default", "défaut", "defaut", "charged off",
        "charge off", "late", "en défaut", "en defaut"
    ]

    good_values = [
        "fully paid", "paid", "remboursé", "rembourse",
        "current", "non-default", "non default"
    ]

    df["default_label"] = np.nan
    df.loc[status.isin(default_values), "default_label"] = 1
    df.loc[status.isin(good_values), "default_label"] = 0

    # Prise en charge de statuts codés 0/1
    numeric_status = pd.to_numeric(status, errors="coerce")
    df.loc[numeric_status.isin([0, 1]), "default_label"] = numeric_status

    return df


uploaded_file = st.file_uploader(
    "Importer SmartCredit.csv ou un fichier Excel",
    type=["csv", "xlsx", "xls"]
)

if uploaded_file is not None:
    try:
        raw_df = load_file(uploaded_file)

        st.write("### Aperçu des données importées")
        st.dataframe(raw_df.head(10), use_container_width=True)

        df, removed_rows, duplicate_rows, rows_before = clean_data(raw_df)
        df = calculate_indicators(df)
        df = add_default_label(df)

        st.success("Fichier chargé et préparé avec succès.")

        # Indicateurs généraux
        c1, c2, c3 = st.columns(3)
        c1.metric("Lignes importées", f"{rows_before:,}")
        c2.metric("Lignes presque vides supprimées", f"{removed_rows:,}")
        c3.metric("Doublons supprimés", f"{duplicate_rows:,}")

        c4, c5 = st.columns(2)
        c4.metric("Lignes conservées", f"{len(df):,}")
        c5.metric("Nombre de colonnes", f"{len(df.columns):,}")

        st.divider()

        st.header("📈 Indicateurs financiers")

        available_metrics = [
            col for col in [
                "loan_income_ratio",
                "payment_burden",
                "financial_stress_score"
            ]
            if col in df.columns
        ]

        if available_metrics:
            metric_labels = {
                "loan_income_ratio": "Ratio prêt / revenu annuel",
                "payment_burden": "Charge annuelle de remboursement",
                "financial_stress_score": "Score relatif de tension financière"
            }

            metric_choice = st.selectbox(
                "Choisir un indicateur",
                available_metrics,
                format_func=lambda x: metric_labels.get(x, x)
            )

            values = df[metric_choice].dropna()

            if not values.empty:
                a, b, c = st.columns(3)
                a.metric("Moyenne", f"{values.mean():.2f}")
                b.metric("Médiane", f"{values.median():.2f}")
                c.metric("Valeurs disponibles", f"{len(values):,}")

                chart_df = df[[metric_choice]].dropna()
                fig = px.histogram(
                    chart_df,
                    x=metric_choice,
                    nbins=40,
                    title=metric_labels.get(metric_choice, metric_choice)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Aucune valeur disponible pour cet indicateur.")
        else:
            st.info(
                "Les colonnes nécessaires aux indicateurs financiers "
                "ne sont pas présentes dans ce fichier."
            )

        st.divider()
        st.header("📊 Statut des prêts")

        if "statut_pret" in df.columns:
            status_counts = (
                df["statut_pret"]
                .fillna("Non renseigné")
                .astype(str)
                .value_counts()
                .rename_axis("Statut")
                .reset_index(name="Nombre de prêts")
            )

            fig_status = px.bar(
                status_counts,
                x="Statut",
                y="Nombre de prêts",
                title="Répartition des statuts de prêts"
            )
            st.plotly_chart(fig_status, use_container_width=True)
            st.dataframe(status_counts, use_container_width=True)
        else:
            st.info("La colonne statut_pret n'est pas présente.")

        st.divider()
        st.header("🔎 Valeurs manquantes")

        missing = pd.DataFrame({
            "Colonne": df.columns,
            "Valeurs manquantes": df.isna().sum().values,
            "Pourcentage (%)": (
                df.isna().mean().values * 100
            ).round(2)
        })

        missing = missing[missing["Valeurs manquantes"] > 0]

        if missing.empty:
            st.success("Aucune valeur manquante dans les données conservées.")
        else:
            st.dataframe(missing, use_container_width=True)

        st.divider()
        st.header("📋 Données nettoyées")
        st.dataframe(df.head(100), use_container_width=True)

        csv_data = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Télécharger les données nettoyées (CSV)",
            data=csv_data,
            file_name="CrediScope_donnees_nettoyees.csv",
            mime="text/csv"
        )

        st.caption(
            "Le score de tension financière est un classement relatif "
            "dans le jeu de données. Ce n'est pas une probabilité de défaut "
            "ni une décision automatique de crédit."
        )

    except Exception as error:
        st.error(f"Impossible de traiter le fichier : {error}")
        st.info(
            "Vérifiez le format du fichier et que ses colonnes sont lisibles."
        )

else:
    st.info(
        "Pour commencer, importez votre fichier SmartCredit.csv "
        "à l'aide du bouton ci-dessus."
    )

