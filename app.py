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

ACQ_COLUMNS = [
    "acquisition_id", "animal_id", "date_acquisition", "heure_acquisition",
    "exploitation", "race", "parite", "jours_en_lait", "stade_lactation",
    "poids_kg", "vue_photo", "distance_estimee_m", "qualite_photo",
    "operateur_1", "bcs_operateur_1",
    "operateur_2", "bcs_operateur_2",
    "operateur_3", "bcs_operateur_3",
    "notes", "photo_filename",
    "quality_status", "rejection_reason", "reviewed_by", "reviewed_at"
]

SCORE_COLUMNS = [
    "score_id", "acquisition_id", "animal_id", "evaluateur",
    "date_scoring", "bcs", "confiance", "commentaire"
]

BCS_OPTIONS = [round(x * 0.25, 2) for x in range(4, 21)]  # 1.00 à 5.00
QUALITY_STATUSES = ["to_review", "accepted", "rejected"]
REJECTION_REASONS = [
    "Cadrage incorrect",
    "Photo floue",
    "Animal partiellement masqué",
    "Mauvaise vue",
    "Mauvaise identification de l’animal",
    "Mauvaise annotation",
    "Doublon",
    "Luminosité insuffisante",
    "Autre",
]


def ensure_csv(path, columns):
    """Crée le CSV ou migre doucement un ancien schéma vers le schéma courant."""
    if not path.exists():
        pd.DataFrame(columns=columns).to_csv(path, index=False)
        return

    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=columns)

    # Compatibilité avec la première version qui utilisait un seul champ opérateur.
    if "operateur" in df.columns and "operateur_1" not in df.columns:
        df["operateur_1"] = df["operateur"]

    for column in columns:
        if column not in df.columns:
            if column == "quality_status":
                # Les anciennes acquisitions sont conservées mais passent en revue.
                df[column] = "to_review"
            else:
                df[column] = ""

    # Normalise les statuts vides/anciens.
    if "quality_status" in df.columns:
        df["quality_status"] = df["quality_status"].fillna("").astype(str)
        df.loc[~df["quality_status"].isin(QUALITY_STATUSES), "quality_status"] = "to_review"

    df = df[columns]
    df.to_csv(path, index=False)


def append_row(path, row, columns):
    pd.DataFrame(
        [[row.get(c, "") for c in columns]],
        columns=columns
    ).to_csv(path, mode="a", header=False, index=False)


def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def update_acquisition(acquisition_id, updates):
    """Met à jour une acquisition identifiée par acquisition_id."""
    df = load_csv(ACQ_FILE)
    if df.empty or "acquisition_id" not in df.columns:
        return False

    mask = df["acquisition_id"].astype(str) == str(acquisition_id)
    if not mask.any():
        return False

    for key, value in updates.items():
        if key in df.columns:
            df.loc[mask, key] = value

    df.to_csv(ACQ_FILE, index=False)
    return True


def delete_scores_for_acquisition(acquisition_id):
    """Supprime les scores indépendants liés à une acquisition rejetée si demandé."""
    scores = load_csv(SCORE_FILE)
    if scores.empty or "acquisition_id" not in scores.columns:
        return 0
    before = len(scores)
    scores = scores[scores["acquisition_id"].astype(str) != str(acquisition_id)]
    scores.to_csv(SCORE_FILE, index=False)
    return before - len(scores)


def acquisition_label(row):
    status = str(row.get("quality_status", "to_review"))
    return (
        f"{row.get('animal_id', '')} — {row.get('date_acquisition', '')} — "
        f"{str(row.get('acquisition_id', ''))[:8]} — {status}"
    )


ensure_csv(ACQ_FILE, ACQ_COLUMNS)
ensure_csv(SCORE_FILE, SCORE_COLUMNS)

st.set_page_config(
    page_title="BCS Cattle Data Acquisition",
    page_icon="🐄",
    layout="centered"
)

st.title("🐄 BCS Cattle – Acquisition des données")
st.caption(
    "Acquisition photographique, scores terrain, contrôle qualité et scoring indépendant."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "📷 Nouvelle acquisition",
    "🧑‍⚕️ Scoring indépendant",
    "✅ Contrôle qualité",
    "📊 Données",
])


# -----------------------------------------------------------------------------
# TAB 1 — NOUVELLE ACQUISITION
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Nouvelle acquisition")
    st.info("Standardisez autant que possible la vue, la distance et le cadrage.")

    with st.form("acquisition_form", clear_on_submit=True):
        animal_id = st.text_input(
            "Numéro d’identification de la vache *",
            placeholder="Ex. BE 123456789"
        )
        st.caption(
            f"Date d’acquisition : {date.today().strftime('%d/%m/%Y')} — "
            "enregistrée automatiquement dans les métadonnées"
        )

        c1, c2 = st.columns(2)
        with c1:
            exploitation = st.text_input("Exploitation *", value="CARE-FEPEX")
            race = st.selectbox(
                "Race",
                [
                    "Holstein", "Pie rouge", "Jersey", "Montbéliarde",
                    "Blanc-Bleu Belge", "Autre", "Inconnue"
                ]
            )
            parite = st.number_input(
                "Numéro de parité *",
                min_value=0,
                max_value=15,
                value=1,
                step=1
            )
            jours_en_lait = st.number_input(
                "Jours en lait (DIM)",
                min_value=0,
                max_value=1000,
                value=0,
                step=1
            )
        with c2:
            stade_lactation = st.selectbox(
                "Stade physiologique",
                [
                    "Début de lactation (0–60 j)",
                    "Milieu de lactation (61–180 j)",
                    "Fin de lactation (>180 j)",
                    "Tarissement", "Génisse", "Inconnu"
                ]
            )
            poids_kg = st.number_input(
                "Poids (kg, optionnel)",
                min_value=0.0,
                max_value=1500.0,
                value=0.0,
                step=1.0
            )

        st.markdown("#### Opérateurs et scores BCS terrain")
        st.caption(
            "Jusqu’à trois opérateurs peuvent participer. L’opérateur 1 est obligatoire. "
            "Chaque opérateur renseigné peut encoder immédiatement son propre BCS."
        )

        o1, s1 = st.columns([2, 1])
        with o1:
            operateur_1 = st.text_input("Opérateur 1 *")
        with s1:
            bcs_operateur_1 = st.selectbox(
                "BCS opérateur 1 *",
                BCS_OPTIONS,
                index=8,
                key="bcs_op1"
            )

        o2, s2 = st.columns([2, 1])
        with o2:
            operateur_2 = st.text_input("Opérateur 2", placeholder="Optionnel")
        with s2:
            bcs_operateur_2 = st.selectbox(
                "BCS opérateur 2",
                ["Non renseigné"] + BCS_OPTIONS,
                key="bcs_op2"
            )

        o3, s3 = st.columns([2, 1])
        with o3:
            operateur_3 = st.text_input("Opérateur 3", placeholder="Optionnel")
        with s3:
            bcs_operateur_3 = st.selectbox(
                "BCS opérateur 3",
                ["Non renseigné"] + BCS_OPTIONS,
                key="bcs_op3"
            )

        st.markdown("#### Photographie")
        vue_photo = st.selectbox(
            "Vue photographique *",
            ["Dorso-caudale", "Arrière", "Latérale gauche", "Latérale droite", "Autre"]
        )
        distance = st.number_input(
            "Distance estimée appareil–animal (m)",
            min_value=0.5,
            max_value=10.0,
            value=2.5,
            step=0.1
        )
        qualite = st.selectbox("Qualité estimée de la photo", ["Bonne", "Acceptable", "Médiocre"])
        photo_camera = st.camera_input("Prendre une photo")
        photo_upload = st.file_uploader("ou importer une photo", type=["jpg", "jpeg", "png"])
        notes = st.text_area(
            "Notes / conditions particulières",
            placeholder="Posture, luminosité, animal sale, obstacle, etc."
        )
        submitted = st.form_submit_button(
            "💾 Enregistrer l'acquisition",
            use_container_width=True
        )

    if submitted:
        photo = photo_camera if photo_camera is not None else photo_upload
        missing = []
        if not animal_id.strip():
            missing.append("identifiant animal")
        if not exploitation.strip():
            missing.append("exploitation")
        if not operateur_1.strip():
            missing.append("opérateur 1")
        if photo is None:
            missing.append("photo")

        # Cohérence opérateur / BCS facultatifs.
        if operateur_2.strip() and bcs_operateur_2 == "Non renseigné":
            missing.append("BCS opérateur 2")
        if not operateur_2.strip() and bcs_operateur_2 != "Non renseigné":
            missing.append("nom opérateur 2")
        if operateur_3.strip() and bcs_operateur_3 == "Non renseigné":
            missing.append("BCS opérateur 3")
        if not operateur_3.strip() and bcs_operateur_3 != "Non renseigné":
            missing.append("nom opérateur 3")

        if missing:
            st.error("Champs requis/incohérents : " + ", ".join(missing))
        else:
            acq_id = str(uuid.uuid4())
            ext = Path(getattr(photo, "name", "photo.jpg")).suffix.lower()
            if ext not in [".jpg", ".jpeg", ".png"]:
                ext = ".jpg"

            safe_animal = "".join(
                ch for ch in animal_id if ch.isalnum() or ch in "-_"
            )
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
                "bcs_operateur_1": float(bcs_operateur_1),
                "operateur_2": operateur_2.strip(),
                "bcs_operateur_2": "" if bcs_operateur_2 == "Non renseigné" else float(bcs_operateur_2),
                "operateur_3": operateur_3.strip(),
                "bcs_operateur_3": "" if bcs_operateur_3 == "Non renseigné" else float(bcs_operateur_3),
                "notes": notes.strip(),
                "photo_filename": filename,
                "quality_status": "to_review",
                "rejection_reason": "",
                "reviewed_by": "",
                "reviewed_at": "",
            }
            append_row(ACQ_FILE, row, ACQ_COLUMNS)
            st.success(
                f"Acquisition enregistrée pour {animal_id}. Statut : à contrôler."
            )


# -----------------------------------------------------------------------------
# TAB 2 — SCORING INDÉPENDANT
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Scoring indépendant")
    st.caption(
        "Seules les acquisitions validées lors du contrôle qualité sont proposées. "
        "Les scores terrain des opérateurs restent masqués."
    )

    acquisitions = load_csv(ACQ_FILE)
    scores = load_csv(SCORE_FILE)

    if acquisitions.empty:
        st.warning("Aucune acquisition disponible.")
    else:
        # Scoring uniquement des acquisitions acceptées.
        available = acquisitions.copy()
        if "quality_status" in available.columns:
            available = available[available["quality_status"].astype(str) == "accepted"]

        if available.empty:
            st.info("Aucune acquisition validée n’est disponible pour le scoring.")
        else:
            evaluator = st.text_input("Nom / code évaluateur *", key="eval_name")

            if evaluator.strip() and not scores.empty:
                already = scores.loc[
                    scores["evaluateur"].astype(str).str.lower() == evaluator.strip().lower(),
                    "acquisition_id"
                ].astype(str).tolist()
                available = available[
                    ~available["acquisition_id"].astype(str).isin(already)
                ]

            if available.empty:
                st.info("Toutes les acquisitions validées ont déjà été scorées par cet évaluateur.")
            else:
                labels, lookup = [], {}
                for _, r in available.iterrows():
                    label = (
                        f"{r['animal_id']} — {r['date_acquisition']} — "
                        f"{str(r['acquisition_id'])[:8]}"
                    )
                    labels.append(label)
                    lookup[label] = r

                selected = st.selectbox("Acquisition à scorer", labels)
                r = lookup[selected]
                photo_path = PHOTO_DIR / str(r["photo_filename"])

                if photo_path.exists():
                    st.image(
                        str(photo_path),
                        caption=f"Animal {r['animal_id']}",
                        use_container_width=True
                    )
                else:
                    st.error("Le fichier photo associé à cette acquisition est introuvable.")

                st.caption(
                    "Les scores terrain et les scores des autres évaluateurs ne sont pas affichés."
                )

                with st.form("score_form"):
                    bcs = st.select_slider(
                        "BCS de référence *",
                        options=BCS_OPTIONS,
                        value=3.0
                    )
                    confiance = st.selectbox(
                        "Confiance de l'évaluateur",
                        ["Élevée", "Moyenne", "Faible"]
                    )
                    commentaire = st.text_area("Commentaire")
                    score_submit = st.form_submit_button(
                        "💾 Enregistrer le score",
                        use_container_width=True
                    )

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
                            "commentaire": commentaire.strip(),
                        }
                        append_row(SCORE_FILE, row, SCORE_COLUMNS)
                        st.success("Score enregistré.")
                        st.rerun()


# -----------------------------------------------------------------------------
# TAB 3 — CONTRÔLE QUALITÉ
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("Contrôle qualité")
    acquisitions = load_csv(ACQ_FILE)

    if acquisitions.empty:
        st.warning("Aucune acquisition à contrôler.")
    else:
        reviewer = st.text_input(
            "Nom / code du réviseur *",
            key="quality_reviewer"
        )

        status_filter = st.multiselect(
            "Statuts à afficher",
            QUALITY_STATUSES,
            default=["to_review"]
        )

        review_pool = acquisitions.copy()
        if status_filter:
            review_pool = review_pool[
                review_pool["quality_status"].astype(str).isin(status_filter)
            ]

        if review_pool.empty:
            st.info("Aucune acquisition ne correspond au filtre sélectionné.")
        else:
            labels, lookup = [], {}
            for _, r in review_pool.iterrows():
                label = acquisition_label(r)
                labels.append(label)
                lookup[label] = r

            selected_review = st.selectbox(
                "Acquisition à contrôler",
                labels,
                key="quality_review_select"
            )
            r_review = lookup[selected_review]
            acq_id = str(r_review["acquisition_id"])
            photo_path = PHOTO_DIR / str(r_review["photo_filename"])

            if photo_path.exists():
                st.image(
                    str(photo_path),
                    caption=(
                        f"Animal {r_review['animal_id']} — "
                        f"statut {r_review.get('quality_status', 'to_review')}"
                    ),
                    use_container_width=True
                )
            else:
                st.error("Le fichier photo associé à cette acquisition est introuvable.")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Métadonnées**")
                st.write(f"Animal : {r_review.get('animal_id', '')}")
                st.write(f"Parité : {r_review.get('parite', '')}")
                st.write(f"Race : {r_review.get('race', '')}")
                st.write(f"Vue : {r_review.get('vue_photo', '')}")
                st.write(f"Distance : {r_review.get('distance_estimee_m', '')} m")
            with c2:
                st.markdown("**Scores terrain**")
                st.write(
                    f"{r_review.get('operateur_1', '')} : "
                    f"{r_review.get('bcs_operateur_1', '')}"
                )
                if pd.notna(r_review.get("operateur_2", "")) and str(r_review.get("operateur_2", "")).strip():
                    st.write(
                        f"{r_review.get('operateur_2', '')} : "
                        f"{r_review.get('bcs_operateur_2', '')}"
                    )
                if pd.notna(r_review.get("operateur_3", "")) and str(r_review.get("operateur_3", "")).strip():
                    st.write(
                        f"{r_review.get('operateur_3', '')} : "
                        f"{r_review.get('bcs_operateur_3', '')}"
                    )

            st.markdown("#### Corriger les métadonnées")
            with st.form(f"metadata_edit_{acq_id}"):
                corrected_animal = st.text_input(
                    "Numéro d'identification",
                    value=str(r_review.get("animal_id", ""))
                )

                current_parity = pd.to_numeric(
                    pd.Series([r_review.get("parite", 0)]), errors="coerce"
                ).fillna(0).iloc[0]

                corrected_parity = st.number_input(
                    "Parité",
                    min_value=0,
                    max_value=15,
                    value=int(current_parity),
                    step=1
                )
                corrected_view = st.selectbox(
                    "Vue photographique",
                    ["Dorso-caudale", "Arrière", "Latérale gauche", "Latérale droite", "Autre"],
                    index=(
                        ["Dorso-caudale", "Arrière", "Latérale gauche", "Latérale droite", "Autre"].index(str(r_review.get("vue_photo", "Autre")))
                        if str(r_review.get("vue_photo", "")) in ["Dorso-caudale", "Arrière", "Latérale gauche", "Latérale droite", "Autre"]
                        else 4
                    )
                )
                corrected_notes = st.text_area(
                    "Notes",
                    value="" if pd.isna(r_review.get("notes", "")) else str(r_review.get("notes", ""))
                )
                save_metadata = st.form_submit_button(
                    "Enregistrer les corrections",
                    use_container_width=True
                )

            if save_metadata:
                if not reviewer.strip():
                    st.error("Veuillez renseigner le réviseur.")
                elif not corrected_animal.strip():
                    st.error("L’identifiant animal ne peut pas être vide.")
                else:
                    update_acquisition(
                        acq_id,
                        {
                            "animal_id": corrected_animal.strip(),
                            "parite": int(corrected_parity),
                            "vue_photo": corrected_view,
                            "notes": corrected_notes.strip(),
                            "reviewed_by": reviewer.strip(),
                            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )
                    st.success("Métadonnées corrigées.")
                    st.rerun()

            st.markdown("#### Décision de contrôle qualité")
            rejection_reason = st.selectbox(
                "Motif du rejet",
                REJECTION_REASONS,
                key=f"rejection_reason_{acq_id}"
            )
            rejection_other = st.text_input(
                "Précision si 'Autre'",
                key=f"rejection_other_{acq_id}"
            )

            c_accept, c_reject = st.columns(2)

            with c_accept:
                if st.button(
                    "✅ Accepter cette acquisition",
                    use_container_width=True,
                    key=f"accept_{acq_id}"
                ):
                    if not reviewer.strip():
                        st.error("Veuillez renseigner le réviseur.")
                    else:
                        update_acquisition(
                            acq_id,
                            {
                                "quality_status": "accepted",
                                "rejection_reason": "",
                                "reviewed_by": reviewer.strip(),
                                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                            }
                        )
                        st.success("Acquisition acceptée.")
                        st.rerun()

            with c_reject:
                if st.button(
                    "❌ Rejeter cette acquisition",
                    use_container_width=True,
                    key=f"reject_{acq_id}"
                ):
                    if not reviewer.strip():
                        st.error("Veuillez renseigner le réviseur.")
                    elif rejection_reason == "Autre" and not rejection_other.strip():
                        st.error("Précisez le motif de rejet.")
                    else:
                        final_reason = (
                            rejection_other.strip()
                            if rejection_reason == "Autre"
                            else rejection_reason
                        )
                        update_acquisition(
                            acq_id,
                            {
                                "quality_status": "rejected",
                                "rejection_reason": final_reason,
                                "reviewed_by": reviewer.strip(),
                                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                            }
                        )
                        st.warning("Acquisition rejetée. La photo est conservée pour la traçabilité.")
                        st.rerun()

            if str(r_review.get("quality_status", "")) == "rejected":
                st.markdown("#### Suppression définitive")
                st.warning(
                    "Cette action supprime le fichier photo et l’acquisition. "
                    "Utilisez-la uniquement si la conservation de la donnée rejetée n’est pas souhaitée."
                )
                confirm_delete = st.checkbox(
                    "Je confirme vouloir supprimer définitivement cette acquisition",
                    key=f"confirm_delete_{acq_id}"
                )
                if st.button(
                    "Supprimer définitivement",
                    disabled=not confirm_delete,
                    key=f"delete_{acq_id}"
                ):
                    df = load_csv(ACQ_FILE)
                    df = df[df["acquisition_id"].astype(str) != acq_id]
                    df.to_csv(ACQ_FILE, index=False)
                    delete_scores_for_acquisition(acq_id)
                    if photo_path.exists():
                        photo_path.unlink()
                    st.success("Acquisition et photo supprimées définitivement.")
                    st.rerun()


# -----------------------------------------------------------------------------
# TAB 4 — DONNÉES ET EXPORTS
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("Données collectées")
    acquisitions = load_csv(ACQ_FILE)
    scores = load_csv(SCORE_FILE)

    total = len(acquisitions)
    accepted_n = 0
    review_n = 0
    rejected_n = 0
    if not acquisitions.empty and "quality_status" in acquisitions.columns:
        accepted_n = int((acquisitions["quality_status"] == "accepted").sum())
        review_n = int((acquisitions["quality_status"] == "to_review").sum())
        rejected_n = int((acquisitions["quality_status"] == "rejected").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Acquisitions", total)
    m2.metric("Validées", accepted_n)
    m3.metric("À contrôler", review_n)
    m4.metric("Rejetées", rejected_n)

    if not acquisitions.empty:
        st.markdown("#### Acquisitions")
        display_status = st.multiselect(
            "Afficher",
            QUALITY_STATUSES,
            default=QUALITY_STATUSES,
            key="data_status_filter"
        )

        displayed_acq = acquisitions.copy()
        if display_status:
            displayed_acq = displayed_acq[
                displayed_acq["quality_status"].astype(str).isin(display_status)
            ]

        st.dataframe(
            displayed_acq,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "⬇️ Télécharger toutes les acquisitions",
            data=acquisitions.to_csv(index=False).encode("utf-8"),
            file_name="acquisitions.csv",
            mime="text/csv"
        )

        accepted = acquisitions[
            acquisitions["quality_status"].astype(str) == "accepted"
        ].copy()
        st.download_button(
            "⬇️ Télécharger uniquement les acquisitions validées",
            data=accepted.to_csv(index=False).encode("utf-8"),
            file_name="acquisitions_validated.csv",
            mime="text/csv",
            disabled=accepted.empty
        )

        # Table longue des scores terrain, utile pour analyses statistiques.
        terrain_rows = []
        for _, r in accepted.iterrows():
            for i in (1, 2, 3):
                op = r.get(f"operateur_{i}", "")
                bcs_val = r.get(f"bcs_operateur_{i}", "")
                if pd.notna(op) and str(op).strip() and pd.notna(bcs_val) and str(bcs_val).strip():
                    terrain_rows.append({
                        "acquisition_id": r.get("acquisition_id", ""),
                        "animal_id": r.get("animal_id", ""),
                        "operateur": str(op).strip(),
                        "bcs_terrain": bcs_val,
                        "date_acquisition": r.get("date_acquisition", ""),
                    })

        terrain_scores = pd.DataFrame(terrain_rows)
        if not terrain_scores.empty:
            terrain_scores["bcs_terrain"] = pd.to_numeric(
                terrain_scores["bcs_terrain"], errors="coerce"
            )
            st.markdown("#### Scores BCS terrain — format long")
            st.dataframe(terrain_scores, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Télécharger les scores terrain",
                data=terrain_scores.to_csv(index=False).encode("utf-8"),
                file_name="scores_bcs_terrain.csv",
                mime="text/csv"
            )

    if not scores.empty:
        st.markdown("#### Scores indépendants sur photographies")
        st.dataframe(scores, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Télécharger scores_independants.csv",
            data=scores.to_csv(index=False).encode("utf-8"),
            file_name="scores_independants.csv",
            mime="text/csv"
        )

        sc = scores.copy()
        sc["bcs"] = pd.to_numeric(sc["bcs"], errors="coerce")
        consensus = sc.groupby(
            ["acquisition_id", "animal_id"],
            as_index=False
        ).agg(
            nombre_evaluateurs=("bcs", "count"),
            bcs_median=("bcs", "median"),
            bcs_moyen=("bcs", "mean"),
            ecart_type=("bcs", "std")
        )

        st.markdown("#### Synthèse des scores indépendants")
        st.dataframe(consensus, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Télécharger la synthèse BCS",
            data=consensus.to_csv(index=False).encode("utf-8"),
            file_name="synthese_bcs.csv",
            mime="text/csv"
        )
