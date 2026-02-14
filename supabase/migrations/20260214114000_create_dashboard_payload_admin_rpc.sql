create or replace function app.get_dashboard_payload_admin(
  p_user uuid,
  p_day date default current_date
)
returns jsonb
language plpgsql
security definer
set search_path = app, public
as $$
declare
  v_role text;
  v_payload jsonb;
begin
  v_role := coalesce(
    current_setting('request.jwt.claim.role', true),
    auth.role()
  );

  if not (
    current_user in ('postgres', 'supabase_admin', 'service_role')
    or v_role = 'service_role'
  ) then
    raise exception 'Not authorized';
  end if;

  begin
    execute 'select app.get_dashboard_payload($1::uuid, $2::date)'
      into v_payload
      using p_user, p_day;
  exception when undefined_function then
    begin
      execute 'select app.get_dashboard_payload($1::date, $2::uuid)'
        into v_payload
        using p_day, p_user;
    exception when undefined_function then
      raise exception 'app.get_dashboard_payload(uuid,date) signature not found';
    end;
  end;

  return coalesce(v_payload, '{}'::jsonb);
end;
$$;

revoke all on function app.get_dashboard_payload_admin(uuid, date) from public;
grant execute on function app.get_dashboard_payload_admin(uuid, date) to service_role;
