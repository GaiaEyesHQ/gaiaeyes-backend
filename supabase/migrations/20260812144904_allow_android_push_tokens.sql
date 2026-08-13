-- Allow the existing push-token registry to serve both Apple and Android.
-- Delivery remains platform-aware in the sender; this migration only broadens
-- the accepted platform values without changing existing iOS rows.
alter table app.user_push_tokens
    drop constraint if exists user_push_tokens_platform_check;

alter table app.user_push_tokens
    add constraint user_push_tokens_platform_check
    check (platform in ('ios', 'android'));
