import io
import os
import uuid
from datetime import datetime, date, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
BUCKET_NAME = "bcs-photos"
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
BCS_OPTIONS = [round(x * 0.25, 2) for x in range(4, 21)]  # 1.00 à 5.00
VIEW_OPTIONS = ["Dorso-caudale", "Arrière", "Latérale gauche", "Latérale droite", "Autre"]
RACE_OPTIONS = [
    "Holstein", "Pie rouge", "Jersey", "Montbéliarde",
    "Blanc-Bleu Belge", "Autre", "Inconnue"
]
PHYSIO_OPTIONS = [
    "Début de lactation (0–60 j)",
    "Milieu de lactation (61–180 j)",
    "Fin de lactation (>180 j)",
    "Tarissement", "Génisse", "Inconnu"
]

st.set_page_config(
    page_title="BCS Cattle Data Acquisition",
    page_icon="🐄",
    layout="centered",
)


# -----------------------------------------------------------------------------
# SUPABASE
# -----------------------------------------------------------------------------
def _secret(name: str) -> str:
    value = st.secrets.get(name, "")
    if not value:
        raise RuntimeError(f"Secret Streamlit manquant : {name}")
    return value


@st.cache_resource
def get_supabase():
    return create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))


def test_backend():
    sb = get_supabase()
    # Requête minimale : permet de distinguer un secret absent d'une table absente.
    sb.table("acquisitions").select("acquisition_id").limit(1).execute()
    return sb


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_now():
    # Streamlit Cloud peut utiliser UTC ; on conserve date et heure saisies au moment de l'acquisition.
    # Le champ created_at côté PostgreSQL fournit en plus un horodatage UTC serveur.
    return datetime.now()


def safe_filename_part(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in "-_")
    return cleaned or "animal"


def photo_extension(uploaded) -> str:
    ext = Path(getattr(uploaded, "name", "photo.jpg")).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        ext = ".jpg"
    return ext


def content_type_for_extension(ext: str) -> str:
    if ext == ".png":
        return "image/png"
    return "image/jpeg"


def storage_path_for_photo(animal_id: str, acquisition_id: str, ext: str, when: datetime) -> str:
    safe_animal = safe_filename_part(animal_id)
    return (
        f"{when:%Y}/{when:%m}/{when:%d}/"
        f"{when:%Y%m%d_%H%M%S}_{safe_animal}_{acquisition_id[:8]}{ext}"
    )


def upload_photo(photo, remote_path: str, ext: str):
    sb = get_supabase()
    payload = photo.getvalue()
    sb.storage.from_(BUCKET_NAME).upload(
        path=remote_path,
        file=payload,
        file_options={
            "content-type": content_type_for_extension(ext),
            "upsert": "false",
        },
    )


def download_photo(remote_path: str):
    if not remote_path:
        return None
    try:
        return get_supabase().storage.from_(BUCKET_NAME).download(remote_path)
    except Exception:
        return None


def delete_photo(remote_path: str):
    if remote_path:
        get_supabase().storage.from_(BUCKET_NAME).remove([remote_path])


def fetch_acquisitions() -> pd.DataFrame:
    response = (
        get_supabase()
        .table("acquisitions")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def fetch_scores() -> pd.DataFrame:
    response = (
        get_supabase()
        .table("scores")
        .select("*")
        .order("date_scoring", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def insert_acquisition(row: dict):
    return get_supabase().table("acquisitions").insert(row).execute()


def insert_score(row: dict):
    return get_supabase().table("scores").insert(row).execute()


def update_acquisition(acquisition_id: str, updates: dict):
    return (
        get_supabase()
        .table("acquisitions")
        .update(updates)
        .eq("acquisition_id", acquisition_id)
        .execute()
    )


def delete_acquisition(acquisition_id: str, photo_path: str):
    sb = get_supabase()
    # Les scores sont supprimés par ON DELETE CASCADE dans PostgreSQL.
    sb.table("acquisitions").delete().eq("acquisition_id", acquisition_id).execute()
    if photo_path:
        try:
            delete_photo(photo_path)
        except Exception:
            # La suppression BDD est prioritaire ; le fichier orphelin pourra être nettoyé ensuite.
            pass


def acquisition_label(row) -> str:
    status = str(row.get("quality_status", "to_review"))
    return (
        f"{row.get('animal_id', '')} — {row.get('date_acquisition', '')} — "
        f"{str(row.get('acquisition_id', ''))[:8]} — {status}"
    )


def as_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def show_photo(remote_path: str, caption: str):
    data = download_photo(remote_path)
    if data:
        st.image(data, caption=caption, use_container_width=True)
    else:
        st.error("La photo associée est introuvable dans Supabase Storage.")


# -----------------------------------------------------------------------------
# BACKEND CHECK
# -----------------------------------------------------------------------------
st.title("🐄 BCS Cattle – Acquisition des données")
st.caption(
    "Acquisition photographique, scores terrain, contrôle qualité et scoring indépendant. "
    "Stockage permanent : Supabase PostgreSQL + Storage."
)

try:
    test_backend()
except Exception as exc:
    st.error("Connexion au stockage permanent impossible.")
    st.code(str(exc))
    st.info(
        "Vérifiez SUPABASE_URL et SUPABASE_KEY dans Streamlit > Settings > Secrets, "
        "puis exécutez setup_supabase.sql dans Supabase SQL Editor et créez le bucket privé 'bcs-photos'."
    )
    st.stop()


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
            placeholder="Ex. BE 123456789",
        )
        st.caption(
            f"Date d’acquisition : {date.today().strftime('%d/%m/%Y')} — "
            "enregistrée automatiquement dans les métadonnées"
        )

        c1, c2 = st.columns(2)
        with c1:
            exploitation = st.text_input("Exploitation *", value="CARE-FEPEX")
            race = st.selectbox("Race", RACE_OPTIONS)
            parite = st.number_input(
                "Numéro de parité *", min_value=0, max_value=15, value=1, step=1
            )
            jours_en_lait = st.number_input(
                "Jours en lait (DIM)", min_value=0, max_value=1000, value=0, step=1
            )
        with c2:
            stade_lactation = st.selectbox("Stade physiologique", PHYSIO_OPTIONS)
            poids_kg = st.number_input(
                "Poids (kg, optionnel)",
                min_value=0.0,
                max_value=1500.0,
                value=0.0,
                step=1.0,
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
                "BCS opérateur 1 *", BCS_OPTIONS, index=8, key="bcs_op1"
            )

        o2, s2 = st.columns([2, 1])
        with o2:
            operateur_2 = st.text_input("Opérateur 2", placeholder="Optionnel")
        with s2:
            bcs_operateur_2 = st.selectbox(
                "BCS opérateur 2", ["Non renseigné"] + BCS_OPTIONS, key="bcs_op2"
            )

        o3, s3 = st.columns([2, 1])
        with o3:
            operateur_3 = st.text_input("Opérateur 3", placeholder="Optionnel")
        with s3:
            bcs_operateur_3 = st.selectbox(
                "BCS opérateur 3", ["Non renseigné"] + BCS_OPTIONS, key="bcs_op3"
            )

        st.markdown("#### Photographie")
        vue_photo = st.selectbox("Vue photographique *", VIEW_OPTIONS)
        distance = st.number_input(
            "Distance estimée appareil–animal (m)",
            min_value=0.5,
            max_value=10.0,
            value=2.5,
            step=0.1,
        )
        qualite = st.selectbox(
            "Qualité estimée de la photo", ["Bonne", "Acceptable", "Médiocre"]
        )
        photo_camera = st.camera_input("Prendre une photo")
        photo_upload = st.file_uploader(
            "ou importer une photo", type=["jpg", "jpeg", "png"]
        )
        notes = st.text_area(
            "Notes / conditions particulières",
            placeholder="Posture, luminosité, animal sale, obstacle, etc.",
        )
        submitted = st.form_submit_button(
            "💾 Enregistrer l'acquisition", use_container_width=True
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
            now = local_now()
            ext = photo_extension(photo)
            remote_path = storage_path_for_photo(animal_id, acq_id, ext, now)

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
                "poids_kg": None if poids_kg == 0 else float(poids_kg),
                "vue_photo": vue_photo,
                "distance_estimee_m": float(distance),
                "qualite_photo": qualite,
                "operateur_1": operateur_1.strip(),
                "bcs_operateur_1": float(bcs_operateur_1),
                "operateur_2": operateur_2.strip() or None,
                "bcs_operateur_2": None if bcs_operateur_2 == "Non renseigné" else float(bcs_operateur_2),
                "operateur_3": operateur_3.strip() or None,
                "bcs_operateur_3": None if bcs_operateur_3 == "Non renseigné" else float(bcs_operateur_3),
                "notes": notes.strip() or None,
                "photo_path": remote_path,
                "quality_status": "to_review",
                "rejection_reason": None,
                "reviewed_by": None,
                "reviewed_at": None,
            }

            try:
                # Upload d'abord, puis métadonnées. En cas d'échec BDD, on nettoie la photo.
                upload_photo(photo, remote_path, ext)
                try:
                    insert_acquisition(row)
                except Exception:
                    delete_photo(remote_path)
                    raise
                st.success(
                    f"Acquisition enregistrée durablement pour {animal_id}. Statut : à contrôler."
                )
            except Exception as exc:
                st.error("L'acquisition n'a pas pu être enregistrée dans Supabase.")
                st.code(str(exc))


# -----------------------------------------------------------------------------
# TAB 2 — SCORING INDÉPENDANT
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Scoring indépendant")
    st.caption(
        "Seules les acquisitions validées lors du contrôle qualité sont proposées. "
        "Les scores terrain des opérateurs restent masqués."
    )

    acquisitions = fetch_acquisitions()
    scores = fetch_scores()

    if acquisitions.empty:
        st.warning("Aucune acquisition disponible.")
    else:
        available = acquisitions[
            acquisitions["quality_status"].astype(str) == "accepted"
        ].copy()

        if available.empty:
            st.info("Aucune acquisition validée n’est disponible pour le scoring.")
        else:
            evaluator = st.text_input("Nom / code évaluateur *", key="eval_name")

            if evaluator.strip() and not scores.empty:
                already = scores.loc[
                    scores["evaluateur"].astype(str).str.lower()
                    == evaluator.strip().lower(),
                    "acquisition_id",
                ].astype(str).tolist()
                available = available[
                    ~available["acquisition_id"].astype(str).isin(already)
                ]

            if available.empty:
                st.info(
                    "Toutes les acquisitions validées ont déjà été scorées par cet évaluateur."
                )
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
                show_photo(
                    str(r.get("photo_path", "")),
                    caption=f"Animal {r['animal_id']}",
                )
                st.caption(
                    "Les scores terrain et les scores des autres évaluateurs ne sont pas affichés."
                )

                with st.form("score_form"):
                    bcs = st.select_slider(
                        "BCS de référence *", options=BCS_OPTIONS, value=3.0
                    )
                    confiance = st.selectbox(
                        "Confiance de l'évaluateur", ["Élevée", "Moyenne", "Faible"]
                    )
                    commentaire = st.text_area("Commentaire")
                    score_submit = st.form_submit_button(
                        "💾 Enregistrer le score", use_container_width=True
                    )

                if score_submit:
                    if not evaluator.strip():
                        st.error("Veuillez renseigner l'évaluateur.")
                    else:
                        row = {
                            "score_id": str(uuid.uuid4()),
                            "acquisition_id": str(r["acquisition_id"]),
                            "animal_id": str(r["animal_id"]),
                            "evaluateur": evaluator.strip(),
                            "date_scoring": utc_now_iso(),
                            "bcs": float(bcs),
                            "confiance": confiance,
                            "commentaire": commentaire.strip() or None,
                        }
                        try:
                            insert_score(row)
                            st.success("Score enregistré durablement.")
                            st.rerun()
                        except Exception as exc:
                            st.error("Impossible d'enregistrer le score.")
                            st.code(str(exc))


# -----------------------------------------------------------------------------
# TAB 3 — CONTRÔLE QUALITÉ
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("Contrôle qualité")
    acquisitions = fetch_acquisitions()

    if acquisitions.empty:
        st.warning("Aucune acquisition à contrôler.")
    else:
        reviewer = st.text_input("Nom / code du réviseur *", key="quality_reviewer")
        status_filter = st.multiselect(
            "Statuts à afficher", QUALITY_STATUSES, default=["to_review"]
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
                "Acquisition à contrôler", labels, key="quality_review_select"
            )
            r_review = lookup[selected_review]
            acq_id = str(r_review["acquisition_id"])
            remote_path = str(r_review.get("photo_path", "") or "")

            show_photo(
                remote_path,
                caption=(
                    f"Animal {r_review['animal_id']} — "
                    f"statut {r_review.get('quality_status', 'to_review')}"
                ),
            )

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
                if str(r_review.get("operateur_2", "") or "").strip():
                    st.write(
                        f"{r_review.get('operateur_2', '')} : "
                        f"{r_review.get('bcs_operateur_2', '')}"
                    )
                if str(r_review.get("operateur_3", "") or "").strip():
                    st.write(
                        f"{r_review.get('operateur_3', '')} : "
                        f"{r_review.get('bcs_operateur_3', '')}"
                    )

            st.markdown("#### Corriger les métadonnées")
            with st.form(f"metadata_edit_{acq_id}"):
                corrected_animal = st.text_input(
                    "Numéro d'identification", value=str(r_review.get("animal_id", ""))
                )
                corrected_parity = st.number_input(
                    "Parité",
                    min_value=0,
                    max_value=15,
                    value=as_int(r_review.get("parite", 0)),
                    step=1,
                )
                current_view = str(r_review.get("vue_photo", "Autre"))
                corrected_view = st.selectbox(
                    "Vue photographique",
                    VIEW_OPTIONS,
                    index=VIEW_OPTIONS.index(current_view) if current_view in VIEW_OPTIONS else 4,
                )
                corrected_notes = st.text_area(
                    "Notes", value=str(r_review.get("notes", "") or "")
                )
                save_metadata = st.form_submit_button(
                    "Enregistrer les corrections", use_container_width=True
                )

            if save_metadata:
                if not reviewer.strip():
                    st.error("Veuillez renseigner le réviseur.")
                elif not corrected_animal.strip():
                    st.error("L’identifiant animal ne peut pas être vide.")
                else:
                    try:
                        update_acquisition(
                            acq_id,
                            {
                                "animal_id": corrected_animal.strip(),
                                "parite": int(corrected_parity),
                                "vue_photo": corrected_view,
                                "notes": corrected_notes.strip() or None,
                                "reviewed_by": reviewer.strip(),
                                "reviewed_at": utc_now_iso(),
                            },
                        )
                        st.success("Métadonnées corrigées.")
                        st.rerun()
                    except Exception as exc:
                        st.error("Impossible de corriger les métadonnées.")
                        st.code(str(exc))

            st.markdown("#### Décision de contrôle qualité")
            rejection_reason = st.selectbox(
                "Motif du rejet", REJECTION_REASONS, key=f"rejection_reason_{acq_id}"
            )
            rejection_other = st.text_input(
                "Précision si 'Autre'", key=f"rejection_other_{acq_id}"
            )

            c_accept, c_reject = st.columns(2)
            with c_accept:
                if st.button(
                    "✅ Accepter cette acquisition",
                    use_container_width=True,
                    key=f"accept_{acq_id}",
                ):
                    if not reviewer.strip():
                        st.error("Veuillez renseigner le réviseur.")
                    else:
                        try:
                            update_acquisition(
                                acq_id,
                                {
                                    "quality_status": "accepted",
                                    "rejection_reason": None,
                                    "reviewed_by": reviewer.strip(),
                                    "reviewed_at": utc_now_iso(),
                                },
                            )
                            st.success("Acquisition acceptée.")
                            st.rerun()
                        except Exception as exc:
                            st.error("Impossible d'accepter l'acquisition.")
                            st.code(str(exc))

            with c_reject:
                if st.button(
                    "❌ Rejeter cette acquisition",
                    use_container_width=True,
                    key=f"reject_{acq_id}",
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
                        try:
                            update_acquisition(
                                acq_id,
                                {
                                    "quality_status": "rejected",
                                    "rejection_reason": final_reason,
                                    "reviewed_by": reviewer.strip(),
                                    "reviewed_at": utc_now_iso(),
                                },
                            )
                            st.warning(
                                "Acquisition rejetée. La photo reste conservée dans Supabase pour la traçabilité."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error("Impossible de rejeter l'acquisition.")
                            st.code(str(exc))

            if str(r_review.get("quality_status", "")) == "rejected":
                st.markdown("#### Suppression définitive")
                st.warning(
                    "Cette action supprime l’acquisition de PostgreSQL et la photo de Supabase Storage. "
                    "Les scores liés sont supprimés automatiquement."
                )
                confirm_delete = st.checkbox(
                    "Je confirme vouloir supprimer définitivement cette acquisition",
                    key=f"confirm_delete_{acq_id}",
                )
                if st.button(
                    "Supprimer définitivement",
                    disabled=not confirm_delete,
                    key=f"delete_{acq_id}",
                ):
                    try:
                        delete_acquisition(acq_id, remote_path)
                        st.success("Acquisition et photo supprimées définitivement.")
                        st.rerun()
                    except Exception as exc:
                        st.error("La suppression n'a pas pu être terminée.")
                        st.code(str(exc))


# -----------------------------------------------------------------------------
# TAB 4 — DONNÉES ET EXPORTS
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("Données collectées")
    acquisitions = fetch_acquisitions()
    scores = fetch_scores()

    total = len(acquisitions)
    accepted_n = review_n = rejected_n = 0
    if not acquisitions.empty:
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
            "Afficher", QUALITY_STATUSES, default=QUALITY_STATUSES, key="data_status_filter"
        )
        displayed_acq = acquisitions.copy()
        if display_status:
            displayed_acq = displayed_acq[
                displayed_acq["quality_status"].astype(str).isin(display_status)
            ]
        st.dataframe(displayed_acq, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Télécharger toutes les acquisitions",
            data=acquisitions.to_csv(index=False).encode("utf-8"),
            file_name="acquisitions.csv",
            mime="text/csv",
        )

        accepted = acquisitions[
            acquisitions["quality_status"].astype(str) == "accepted"
        ].copy()
        st.download_button(
            "⬇️ Télécharger uniquement les acquisitions validées",
            data=accepted.to_csv(index=False).encode("utf-8"),
            file_name="acquisitions_validated.csv",
            mime="text/csv",
            disabled=accepted.empty,
        )

        terrain_rows = []
        for _, r in accepted.iterrows():
            for i in (1, 2, 3):
                op = r.get(f"operateur_{i}", "")
                bcs_val = r.get(f"bcs_operateur_{i}", None)
                if str(op or "").strip() and bcs_val is not None and not pd.isna(bcs_val):
                    terrain_rows.append(
                        {
                            "acquisition_id": r.get("acquisition_id", ""),
                            "animal_id": r.get("animal_id", ""),
                            "operateur": str(op).strip(),
                            "bcs_terrain": bcs_val,
                            "date_acquisition": r.get("date_acquisition", ""),
                        }
                    )
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
                mime="text/csv",
            )

    if not scores.empty:
        st.markdown("#### Scores indépendants sur photographies")
        st.dataframe(scores, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Télécharger scores_independants.csv",
            data=scores.to_csv(index=False).encode("utf-8"),
            file_name="scores_independants.csv",
            mime="text/csv",
        )

        sc = scores.copy()
        sc["bcs"] = pd.to_numeric(sc["bcs"], errors="coerce")
        consensus = sc.groupby(
            ["acquisition_id", "animal_id"], as_index=False
        ).agg(
            nombre_evaluateurs=("bcs", "count"),
            bcs_median=("bcs", "median"),
            bcs_moyen=("bcs", "mean"),
            ecart_type=("bcs", "std"),
        )
        st.markdown("#### Synthèse des scores indépendants")
        st.dataframe(consensus, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Télécharger la synthèse BCS",
            data=consensus.to_csv(index=False).encode("utf-8"),
            file_name="synthese_bcs.csv",
            mime="text/csv",
        )
