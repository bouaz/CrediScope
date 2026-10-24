import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(
    page_title="CrediScope",
    page_icon="📊",
    layout="wide"
)

st.title("CrediScope")
st.subheader("Tableau de bord intelligent — Analyse du risque de crédit")
st.caption("Hackathon EGI 2026")

fichier = st.file_uploader(
    "Importer votre dataset initial (CSV ou Excel)",
    type=["csv", "xlsx"]
)

def preparer_donnees(df):
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.drop_duplicates()

    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].map(
            lambda x: x.strip() if isinstance(x, str) else x
        )
        df[col] = df[col].replace("", np.nan)

    colonnes_num = [
        "taux_interet", "montant_pret", "revenu_annuel",
        "mensualite", "ratio_endettement",
        "taux_utilisation_cartes", "demandes_credit_6mois"
    ]
    for col in colonnes_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df

if fichier is not None:
    try:
        if fichier.name.lower().endswith(".csv"):
            try:
                brut = pd.read_csv(fichier, sep=None, engine="python")
            except UnicodeDecodeError:
                fichier.seek(0)
                brut = pd.read_csv(
                    fichier, sep=None, engine="python", encoding="latin-1"
                )
        else:
            brut = pd.read_excel(fichier)

        data = preparer_donnees(brut)

        st.success("Dataset importé et prétraitement initial terminé.")

        c1, c2, c3 = st.columns(3)
        c1.metric("Lignes initiales", len(brut))
        c2.metric("Lignes préparées", len(data))
        c3.metric("Colonnes", len(data.columns))

        st.subheader("Aperçu des données préparées")
        st.dataframe(data.head(100), use_container_width=True)

        st.info(
            "Vérifiez les colonnes et les statuts de prêt. "
            "Ce prétraitement générique doit être complété par les "
            "règles spécifiques de votre notebook si nécessaire."
        )

        requis = [
            "statut_pret", "taux_interet", "classe_credit",
            "montant_pret", "revenu_annuel", "mensualite"
        ]

        if all(c in data.columns for c in requis):
            statut = data["statut_pret"].astype("string").str.strip().str.casefold()

            paye = statut.isin(["fully paid", "paid"])
            perte = statut.isin(["charged off", "charge off"])
            defaut = statut.isin(["default"])

            nb_payes = int(paye.sum())
            nb_pertes = int(perte.sum())
            nb_defauts = int(defaut.sum())
            nb_termines = nb_payes + nb_pertes + nb_defauts

            taux = (
                (nb_pertes + nb_defauts) / nb_termines * 100
                if nb_termines else np.nan
            )

            st.subheader("Indicateurs principaux")
            a, b, c, d = st.columns(4)
            a.metric("Prêts analysés", len(data))
            b.metric("Prêts remboursés", nb_payes)
            c.metric("Prêts Charged Off", nb_pertes)
            d.metric(
                "Taux de défaut",
                f"{taux:.2f} %" if pd.notna(taux) else "N/D"
            )

            repartition = (
                data["statut_pret"].fillna("Non renseigné")
                .value_counts().rename_axis("Statut")
                .reset_index(name="Nombre de prêts")
            )
            st.plotly_chart(
                px.bar(
                    repartition, x="Statut", y="Nombre de prêts",
                    title="Répartition des prêts par statut"
                ),
                use_container_width=True
            )

            interets = data["taux_interet"].dropna()
            if not interets.empty:
                interets_pct = (
                    interets * 100 if interets.max() <= 1.5 else interets
                )
                st.plotly_chart(
                    px.histogram(
                        x=interets_pct, nbins=30,
                        title="Distribution des taux d'intérêt",
                        labels={
                            "x": "Taux d'intérêt (%)",
                            "y": "Nombre de prêts"
                        }
                    ),
                    use_container_width=True
                )

            data["_defaut"] = np.nan
            data.loc[paye, "_defaut"] = 0
            data.loc[perte | defaut, "_defaut"] = 1

            par_classe = data[
                data["classe_credit"].notna() & data["_defaut"].notna()
            ].copy()
            par_classe["classe_credit"] = (
                par_classe["classe_credit"].astype(str).str.upper()
            )

            if not par_classe.empty:
                stats = (
                    par_classe.groupby("classe_credit", observed=True)
                    ["_defaut"].mean().mul(100)
                    .rename("Taux de défaut (%)").reset_index()
                )
                st.plotly_chart(
                    px.bar(
                        stats, x="classe_credit",
                        y="Taux de défaut (%)",
                        title="Taux de défaut par classe de crédit"
                    ),
                    use_container_width=True
                )

            revenu = data["revenu_annuel"].where(data["revenu_annuel"] > 0)
            data["loan_income_ratio"] = data["montant_pret"] / revenu
            data["payment_burden"] = data["mensualite"] * 12 / revenu

            indicateurs = pd.DataFrame([
                {
                    "Indicateur": "Taux de défaut historique",
                    "Valeur": f"{taux:.2f} %" if pd.notna(taux) else "N/D"
                },
                {
                    "Indicateur": "Ratio prêt / revenu médian",
                    "Valeur": f"{data['loan_income_ratio'].replace([np.inf, -np.inf], np.nan).median() * 100:.2f} %"
                },
                {
                    "Indicateur": "Charge annuelle / revenu médian",
                    "Valeur": f"{data['payment_burden'].replace([np.inf, -np.inf], np.nan).median() * 100:.2f} %"
                },
                {
                    "Indicateur": "Score moyen de stress financier",
                    "Valeur": "N/D si les variables nécessaires ne sont pas disponibles"
                }
            ])

            st.subheader("Indicateurs financiers")
            st.dataframe(indicateurs, hide_index=True, use_container_width=True)

        else:
            st.warning(
                "Les colonnes attendues par le tableau de bord ne sont "
                "pas toutes présentes. Vérifiez les noms de colonnes."
            )

        st.download_button(
            "Télécharger les données préparées (CSV)",
            data=data.to_csv(index=False).encode("utf-8-sig"),
            file_name="CrediScope_donnees_preparees.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Erreur lors du traitement du fichier : {e}")

else:
    st.info("Importez un fichier pour commencer l'analyse.")
