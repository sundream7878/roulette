-- Run once on Supabase SQL editor (or via CLI) before deploying app that uses id / event_at / event_id.
-- Order: child tables first if your project has FKs from participants/commenters to posts.

ALTER TABLE IF EXISTS participants RENAME COLUMN url TO event_id;
ALTER TABLE IF EXISTS commenters RENAME COLUMN url TO event_id;
ALTER TABLE IF EXISTS posts RENAME COLUMN url TO id;

ALTER TABLE posts ADD COLUMN IF NOT EXISTS event_at TIMESTAMPTZ;

-- Unique constraints / upsert targets may need recreation in your project; typical names:
-- participants: UNIQUE (event_id, author)
-- commenters: UNIQUE (event_id, author)
