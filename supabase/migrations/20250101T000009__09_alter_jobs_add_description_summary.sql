ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS description_summary TEXT,
  ADD COLUMN IF NOT EXISTS description_summary_model TEXT,
  ADD COLUMN IF NOT EXISTS description_summary_tokens INTEGER;