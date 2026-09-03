import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date
import uuid

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
PHOTO_DIR = APP_DIR / "photos"
DATA_DIR.mkdir(exist_ok=True)
PHOTO_DIR.mkdir(exist_ok=True)

ACQ_FILE = DATA_DIR / "acquisitions.csv"
SCORE_FILE = DATA_DIR / "scores.csv"

ACQ_COLUMNS = ["acquisition_id","animal_id","date_acquisition","heure_acquisition","exploitation","race","parite","jours_en_lait","stade_lactation","poids_kg","vue_photo","distance_estimee_m","qualite_photo","operateur_1","operateur_2","operateur_3","notes","photo_filename"]
SCORE_COLUMNS = ["score_id","acquisition_id","animal_id","evaluateur","date_scoring","bcs","confiance","commentaire"]

def ensure_csv(path, columns):
    if not path.exists():
        pd.DataFrame(columns=columns).to_csv(path, index=False)
        return

    # Migration douce des anciens fichiers CSV vers le schéma courant.
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=columns)

    # Ancienne version : un seul champ "operateur".
    if "operateur" in df.columns and "operateur_1" not in df.columns:
        df["operateur_1"] = df["operateur"]

    for column in columns:
        if column not in df.columns:
            df[column] = ""

    df = df[columns]
    df.to_csv(path, index=False)

def append_row(path, row, columns):
    pd.DataFrame([[row.get(c, "") for c in columns]], columns=columns).to_csv(path, mode="a", header=False, index=False)

def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

ensure_csv(ACQ_FILE, ACQ_COLUMNS)
ensure_csv(SCORE_FILE, SCORE_COLUMNS)

st.set_page_config(page_title="BCS Cattle Data Acquisition", page_icon="🐄", layout="centered")
st.title("🐄 BCS Cattle – Acquisition des données")
st.caption("Prototype pour constituer un jeu de données photographiques de score corporel bovin.")

tab1, tab2, tab3 = st.tabs(["📷 Nouvelle acquisition","🧑‍⚕️ Scoring indépendant","📊 Données"])

with tab1:
    st.subheader("Nouvelle acquisition")
    st.info("Standardisez autant que possible la vue, la distance et le cadrage.")

    with st.form("acquisition_form", clear_on_submit=True):
        animal_id = st.text_input("Numéro d’identification de la vache *", placeholder="Ex. BE 123456789")
        st.caption(f"Date d’acquisition : {date.today().strftime('%d/%m/%Y')} — enregistrée automatiquement dans les métadonnées")

        c1, c2 = st.columns(2)
        with c1:
            exploitation = st.text_input("Exploitation *", value="CARE-FEPEX")
            race = st.selectbox("Race", ["Holstein","Pie rouge","Jersey","Montbéliarde","Blanc-Bleu Belge","Autre","Inconnue"])
            parite = st.number_input("Numéro de parité *", min_value=0, max_value=15, value=1, step=1)
            jours_en_lait = st.number_input("Jours en lait (DIM)", min_value=0, max_value=1000, value=0, step=1)
        with c2:
            stade_lactation = st.selectbox("Stade physiologique", ["Début de lactation (0–60 j)","Milieu de lactation (61–180 j)","Fin de lactation (>180 j)","Tarissement","Génisse","Inconnu"])
            poids_kg = st.number_input("Poids (kg, optionnel)", min_value=0.0, max_value=1500.0, value=0.0, step=1.0)

        st.markdown("#### Opérateurs")
        st.caption("Jusqu’à trois opérateurs peuvent être associés à une acquisition. Le premier est obligatoire.")
        o1, o2, o3 = st.columns(3)
        with o1:
            operateur_1 = st.text_input("Opérateur 1 *")
        with o2:
            operateur_2 = st.text_input("Opérateur 2", placeholder="Optionnel")
        with o3:
            operateur_3 = st.text_input("Opérateur 3", placeholder="Optionnel")

        st.markdown("#### Photographie")
        vue_photo = st.selectbox("Vue photographique *", ["Dorso-caudale","Arrière","Latérale gauche","Latérale droite","Autre"])
        distance = st.number_input("Distance estimée appareil–animal (m)", min_value=0.5, max_value=10.0, value=2.5, step=0.1)
        qualite = st.selectbox("Qualité de la photo", ["Bonne","Acceptable","Médiocre"])
        photo_camera = st.camera_input("Prendre une photo")
        photo_upload = st.file_uploader("ou importer une photo", type=["jpg","jpeg","png"])
        notes = st.text_area("Notes / conditions particulières", placeholder="Posture, luminosité, animal sale, obstacle, etc.")
        submitted = st.form_submit_button("💾 Enregistrer l'acquisition", use_container_width=True)

    if submitted:
        photo = photo_camera if photo_camera is not None else photo_upload
        missing = []
        if not animal_id.strip(): missing.append("identifiant animal")
        if not exploitation.strip(): missing.append("exploitation")
        if not operateur_1.strip(): missing.append("opérateur 1")
        if photo is None: missing.append("photo")

        if missing:
            st.error("Champs requis manquants : " + ", ".join(missing))
        else:
            acq_id = str(uuid.uuid4())
            ext = Path(getattr(photo, "name", "photo.jpg")).suffix.lower()
            if ext not in [".jpg",".jpeg",".png"]:
                ext = ".jpg"
            safe_animal = "".join(ch for ch in animal_id if ch.isalnum() or ch in "-_")
            now = datetime.now()
            filename = f"{now.date().isoformat()}_{safe_animal}_{acq_id[:8]}{ext}"
            (PHOTO_DIR / filename).write_bytes(photo.getvalue())
            row = {
                "acquisition_id": acq_id,
                "animal_id": animal_id.strip(),
                "date_acquisition": now.date().isoformat(),
                "heure_acquisition": now.strftime("%H:%M:%S"),
                "exploitation": exploitation.strip(),
                "race": race,
                "parite": int(parite),
                "jours_en_lait": int(jours_en_lait),
                "stade_lactation": stade_lactation,
                "poids_kg": "" if poids_kg == 0 else float(poids_kg),
                "vue_photo": vue_photo,
                "distance_estimee_m": float(distance),
                "qualite_photo": qualite,
                "operateur_1": operateur_1.strip(),
                "operateur_2": operateur_2.strip(),
                "operateur_3": operateur_3.strip(),
                "notes": notes.strip(),
                "photo_filename": filename
            }
            append_row(ACQ_FILE, row, ACQ_COLUMNS)
            st.success(f"Acquisition enregistrée pour {animal_id}.")

with tab2:
    st.subheader("Scoring indépendant")
    acquisitions = load_csv(ACQ_FILE)
    scores = load_csv(SCORE_FILE)

    if acquisitions.empty:
        st.warning("Aucune acquisition disponible.")
    else:
        evaluator = st.text_input("Nom / code évaluateur *", key="eval_name")
        available = acquisitions.copy()

        if evaluator.strip() and not scores.empty:
            already = scores.loc[scores["evaluateur"].astype(str).str.lower() == evaluator.strip().lower(), "acquisition_id"].astype(str).tolist()
            available = available[~available["acquisition_id"].astype(str).isin(already)]

        if available.empty:
            st.info("Toutes les acquisitions ont déjà été scorées par cet évaluateur.")
        else:
            labels, lookup = [], {}
            for _, r in available.iterrows():
                label = f"{r['animal_id']} — {r['date_acquisition']} — {str(r['acquisition_id'])[:8]}"
                labels.append(label)
                lookup[label] = r
            selected = st.selectbox("Acquisition à scorer", labels)
            r = lookup[selected]
            photo_path = PHOTO_DIR / str(r["photo_filename"])
            if photo_path.exists():
                st.image(str(photo_path), caption=f"Animal {r['animal_id']}", use_container_width=True)

            st.caption("Les scores des autres évaluateurs ne sont pas affichés.")
            with st.form("score_form"):
                bcs = st.select_slider("BCS de référence *", options=[round(x*0.25,2) for x in range(4,21)], value=3.0)
                confiance = st.selectbox("Confiance de l'évaluateur", ["Élevée","Moyenne","Faible"])
                commentaire = st.text_area("Commentaire")
                score_submit = st.form_submit_button("💾 Enregistrer le score", use_container_width=True)

            if score_submit:
                if not evaluator.strip():
                    st.error("Veuillez renseigner l'évaluateur.")
                else:
                    row = {
                        "score_id": str(uuid.uuid4()),
                        "acquisition_id": r["acquisition_id"],
                        "animal_id": r["animal_id"],
                        "evaluateur": evaluator.strip(),
                        "date_scoring": datetime.now().isoformat(timespec="seconds"),
                        "bcs": float(bcs),
                        "confiance": confiance,
                        "commentaire": commentaire.strip()
                    }
                    append_row(SCORE_FILE, row, SCORE_COLUMNS)
                    st.success("Score enregistré.")

with tab3:
    st.subheader("Données collectées")
    acquisitions = load_csv(ACQ_FILE)
    scores = load_csv(SCORE_FILE)

    c1, c2, c3 = st.columns(3)
    c1.metric("Acquisitions", len(acquisitions))
    c2.metric("Scores", len(scores))
    c3.metric("Animaux distincts", acquisitions["animal_id"].nunique() if not acquisitions.empty else 0)

    if not acquisitions.empty:
        st.markdown("#### Acquisitions")
        st.dataframe(acquisitions, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Télécharger acquisitions.csv", data=ACQ_FILE.read_bytes(), file_name="acquisitions.csv", mime="text/csv")

    if not scores.empty:
        st.markdown("#### Scores")
        st.dataframe(scores, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Télécharger scores.csv", data=SCORE_FILE.read_bytes(), file_name="scores.csv", mime="text/csv")

        sc = scores.copy()
        sc["bcs"] = pd.to_numeric(sc["bcs"], errors="coerce")
        consensus = sc.groupby(["acquisition_id","animal_id"], as_index=False).agg(
            nombre_evaluateurs=("bcs","count"),
            bcs_median=("bcs","median"),
            bcs_moyen=("bcs","mean"),
            ecart_type=("bcs","std")
        )
        st.markdown("#### Synthèse des scores")
        st.dataframe(consensus, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Télécharger la synthèse BCS", data=consensus.to_csv(index=False).encode("utf-8"), file_name="synthese_bcs.csv", mime="text/csv")
