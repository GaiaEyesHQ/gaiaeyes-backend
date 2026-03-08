begin;

-- Camera quick-check writes from iOS use PostgREST with:
--   Content-Profile: raw
-- and reads with:
--   Accept-Profile: marts
-- Ensure authenticated clients can use these schemas + objects.

grant usage on schema raw to authenticated;
grant usage on schema marts to authenticated;

grant select, insert, delete
  on table raw.camera_health_checks
  to authenticated;

grant select
  on table marts.camera_health_daily
  to authenticated;

-- Prefer invoker semantics for safety on client-facing view queries.
do $$
begin
  begin
    execute 'alter view marts.camera_health_daily set (security_invoker = true)';
  exception when others then
    -- Ignore if unsupported by postgres version/settings.
    null;
  end;
end
$$;

commit;
