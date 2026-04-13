begin;

grant usage on schema content to authenticated, service_role;

grant select
on table content.home_feed_items
to authenticated, service_role;

grant select, insert, update
on table content.user_home_feed_seen
to authenticated, service_role;

commit;
