CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.job_notes (
  note_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id TEXT NOT NULL REFERENCES public.jobs(job_id) ON DELETE CASCADE,
  application_id UUID REFERENCES public.applications(application_id) ON DELETE SET NULL,
  author TEXT DEFAULT 'user',
  note_text TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

