CREATE TABLE IF NOT EXISTS public.search_results (
  search_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  proposals_tier TEXT,
  is_applied BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (search_id, job_id),
  CONSTRAINT fk_search_id FOREIGN KEY (search_id) REFERENCES public.scrape_requests(search_id) ON DELETE CASCADE,
  CONSTRAINT fk_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE CASCADE
);

