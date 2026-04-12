begin;

do $$
begin
  if to_regclass('app.user_locations') is not null then
    alter table app.user_locations
      add column if not exists use_gps boolean not null default false;

    alter table app.user_locations
      add column if not exists local_insights_enabled boolean not null default true;

    alter table app.user_locations
      add column if not exists updated_at timestamptz not null default now();

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'app'
        and table_name = 'user_locations'
        and column_name = 'gps_enabled'
    ) then
      update app.user_locations set use_gps = true where gps_enabled = true;
    end if;

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'app'
        and table_name = 'user_locations'
        and column_name = 'gps_allowed'
    ) then
      update app.user_locations set use_gps = true where gps_allowed = true;
    end if;

    if exists (
      select 1 from information_schema.columns
      where table_schema = 'app'
        and table_name = 'user_locations'
        and column_name = 'local_enabled'
    ) then
      update app.user_locations set local_insights_enabled = false where local_enabled = false;
    end if;
  end if;
end $$;

commit;
