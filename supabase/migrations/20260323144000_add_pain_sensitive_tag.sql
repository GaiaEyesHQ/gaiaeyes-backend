do $$
declare
  has_section boolean;
  has_tag_type boolean;
  has_risk_level boolean;
begin
  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'section'
  ) into has_section;

  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'tag_type'
  ) into has_tag_type;

  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'risk_level'
  ) into has_risk_level;

  if has_section then
    insert into dim.user_tag_catalog (tag_key, label, description, section, is_active)
    values ('pain_sensitive', 'Pain Sensitive', 'Pain or body flares tend to surface faster for me.', 'sensitivity', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        description = excluded.description,
        section = excluded.section,
        is_active = excluded.is_active;
  elsif has_tag_type and has_risk_level then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, risk_level, description, is_active)
    values ('pain_sensitive', 'Pain Sensitive', 'sensitivity', 'medium', 'Pain or body flares tend to surface faster for me.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        tag_type = excluded.tag_type,
        risk_level = excluded.risk_level,
        description = excluded.description,
        is_active = excluded.is_active;
  elsif has_tag_type then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, description, is_active)
    values ('pain_sensitive', 'Pain Sensitive', 'sensitivity', 'Pain or body flares tend to surface faster for me.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        tag_type = excluded.tag_type,
        description = excluded.description,
        is_active = excluded.is_active;
  else
    insert into dim.user_tag_catalog (tag_key, label, description, is_active)
    values ('pain_sensitive', 'Pain Sensitive', 'Pain or body flares tend to surface faster for me.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        description = excluded.description,
        is_active = excluded.is_active;
  end if;
end $$;
