-- Improve lookup performance for daily feature snapshots per user.
create index if not exists idx_daily_features_user_day
    on marts.daily_features (user_id, day);
