CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.applications (
  application_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id TEXT NOT NULL REFERENCES public.jobs(job_id) ON DELETE CASCADE,
  draft_suggestion_title TEXT,
  draft_suggestion TEXT,
  model_provider TEXT,
  model_name TEXT,
  prompt_version TEXT,
  temperature NUMERIC,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  final_message TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  submitted_at TIMESTAMPTZ,
  connects_spent INT,
  boosted BOOLEAN,
  proposal_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

