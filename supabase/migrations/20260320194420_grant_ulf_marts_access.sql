begin;

grant usage on schema marts to authenticated;

grant select
  on table marts.ulf_activity_5m
  to authenticated;

grant select
  on table marts.ulf_context_5m
  to authenticated;

commit;
