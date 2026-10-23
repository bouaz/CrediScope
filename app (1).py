import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="CrediScope",
    page_icon="🏦",
    layout="wide"
)

st.title("🏦 CrediScope")
st.subheader("Tableau de bord du risque de crédit")

st.write(
    "Importez votre propre fichier CSV ou Excel "
    "pour visualiser vos indicateurs de crédit."
)

fichier = st.file_uploader(
    "Choisissez votre fichier de données",
    type=["csv", "xlsx"]
)

if fichier is None:
    st.info("👆 Importez un fichier CSV ou Excel pour commencer.")
    st.stop()

try:
    if fichier.name.lower().endswith(".xlsx"):
        df = pd.read_excel(fichier)
    else:
        df = pd.read_csv(
            fichier,
            sep=None,
            engine="python",
            encoding="utf-8-sig"
        )

    df.columns = df.columns.astype(str).str.strip()
    df = df.replace(r"^\s*(NA)?\s*$", pd.NA, regex=True)
    df = df.dropna(how="all").copy()

    st.success("Fichier importé avec succès !")

    c1, c2 = st.columns(2)
    c1.metric("Nombre de prêts", f"{len(df):,}".replace(",", " "))
    c2.metric("Nombre de colonnes", len(df.columns))

    st.subheader("Aperçu des données")
    st.dataframe(df.head(10), use_container_width=True)

    if "statut_pret" in df.columns:
        statut = df["statut_pret"].astype("string").str.strip()

        rembourses = int((statut == "Fully Paid").sum())
        charged_off = int((statut == "Charged Off").sum())
        defaults = int((statut == "Default").sum())

        termines = int(
            statut.isin(
                ["Fully Paid", "Charged Off", "Default"]
            ).sum()
        )
        defauts = charged_off + defaults
        taux = defauts / termines * 100 if termines else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Prêts remboursés", rembourses)
        c2.metric("Prêts en défaut", defauts)
        c3.metric("Taux historique de défaut", f"{taux:.2f} %")

        st.caption(
            "Taux calculé sur les prêts Fully Paid, "
            "Charged Off et Default uniquement."
        )

        repartition = (
            statut.value_counts(dropna=False)
            .rename_axis("Statut")
            .reset_index(name="Nombre de prêts")
        )
        repartition["Statut"] = repartition["Statut"].fillna(
            "Statut manquant"
        )

        st.subheader("Statuts des prêts")
        fig1 = px.bar(
            repartition,
            x="Statut",
            y="Nombre de prêts",
            color="Statut"
        )
        st.plotly_chart(fig1, use_container_width=True)

    if "taux_interet" in df.columns:
        df["taux_interet"] = pd.to_numeric(
            df["taux_interet"], errors="coerce"
        )
        valeurs = df.dropna(subset=["taux_interet"])

        st.subheader("Distribution des taux d'intérêt")
        fig2 = px.histogram(
            valeurs,
            x="taux_interet",
            nbins=20,
            labels={"taux_interet": "Taux d'intérêt"}
        )
        st.plotly_chart(fig2, use_container_width=True)

    if {"statut_pret", "classe_credit"}.issubset(df.columns):
        statut = df["statut_pret"].astype("string").str.strip()

        fini = df[
            statut.isin(["Fully Paid", "Charged Off", "Default"])
        ].copy()

        fini["defaut"] = (
            fini["statut_pret"].astype("string").str.strip()
            .isin(["Charged Off", "Default"]).astype(int)
        )

        fini = fini.dropna(subset=["classe_credit"])

        if not fini.empty:
            classes = fini.groupby("classe_credit").agg(
                nombre_prets=("defaut", "size"),
                nombre_defauts=("defaut", "sum"),
                taux_defaut=("defaut", "mean")
            ).reset_index()

            classes["taux_defaut"] *= 100

            st.subheader("Taux de défaut par classe de crédit")
            fig3 = px.bar(
                classes,
                x="classe_credit",
                y="taux_defaut",
                labels={
                    "classe_credit": "Classe de crédit",
                    "taux_defaut": "Taux de défaut (%)"
                },
                hover_data=["nombre_prets", "nombre_defauts"]
            )
            st.plotly_chart(fig3, use_container_width=True)

            with st.expander("Voir les chiffres par classe"):
                st.dataframe(classes, use_container_width=True)

    st.subheader("Autres graphiques")
    numeriques = df.select_dtypes(include="number").columns.tolist()

    if numeriques:
        colonne = st.selectbox(
            "Choisissez une autre variable numérique",
            numeriques
        )
        fig4 = px.histogram(df, x=colonne, nbins=30)
        st.plotly_chart(fig4, use_container_width=True)

except Exception as e:
    st.error(
        "Impossible de lire ce fichier. Vérifiez son format "
        "et la présence des colonnes nécessaires."
    )
    st.caption(f"Détail technique : {e}")
