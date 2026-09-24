-- BCS Cattle Acquisition v4
-- Exécuter ce script dans Supabase > SQL Editor > New query > Run.

create extension if not exists pgcrypto;

create table if not exists public.acquisitions (
    acquisition_id uuid primary key,
    animal_id text not null,
    date_acquisition date not null,
    heure_acquisition time not null,
    exploitation text not null,
    race text,
    parite integer not null check (parite between 0 and 15),
    jours_en_lait integer,
    stade_lactation text,
    poids_kg numeric,
    vue_photo text,
    distance_estimee_m numeric,
    qualite_photo text,
    operateur_1 text not null,
    bcs_operateur_1 numeric not null,
    operateur_2 text,
    bcs_operateur_2 numeric,
    operateur_3 text,
    bcs_operateur_3 numeric,
    notes text,
    photo_path text not null unique,
    quality_status text not null default 'to_review'
        check (quality_status in ('to_review', 'accepted', 'rejected')),
    rejection_reason text,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.scores (
    score_id uuid primary key,
    acquisition_id uuid not null references public.acquisitions(acquisition_id) on delete cascade,
    animal_id text not null,
    evaluateur text not null,
    date_scoring timestamptz not null default now(),
    bcs numeric not null check (bcs >= 1 and bcs <= 5),
    confiance text,
    commentaire text,
    created_at timestamptz not null default now(),
    unique (acquisition_id, evaluateur)
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_acquisitions_updated_at on public.acquisitions;
create trigger trg_acquisitions_updated_at
before update on public.acquisitions
for each row execute function public.set_updated_at();

create index if not exists idx_acquisitions_quality_status
    on public.acquisitions(quality_status);
create index if not exists idx_acquisitions_animal_id
    on public.acquisitions(animal_id);
create index if not exists idx_scores_acquisition_id
    on public.scores(acquisition_id);
create index if not exists idx_scores_evaluateur
    on public.scores(evaluateur);

-- L'application est une application serveur Streamlit utilisant une clé secrète Supabase.
-- Avec une clé secrète/service_role, les politiques RLS ne sont pas utilisées par cette app.
-- On active néanmoins RLS pour éviter un accès public direct via la Data API avec une clé publique.
alter table public.acquisitions enable row level security;
alter table public.scores enable row level security;

-- Ne pas créer de politique publique si l'application utilise SUPABASE_KEY = sb_secret_... ou service_role.
