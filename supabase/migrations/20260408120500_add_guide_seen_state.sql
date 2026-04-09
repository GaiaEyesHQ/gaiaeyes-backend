alter table if exists app.user_experience_profiles
  add column if not exists guide_last_viewed_signature text,
  add column if not exists guide_last_viewed_at timestamptz;
