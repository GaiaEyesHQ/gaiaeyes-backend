-- Seed starter user sensitivity tags across schema variants.
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
    values
      ('pressure_sensitive', 'Pressure Sensitive', 'More reactive during barometric swings.', 'environmental', true),
      ('temp_sensitive', 'Temperature Sensitive', 'More reactive during rapid temperature changes.', 'environmental', true),
      ('aqi_sensitive', 'Air Quality Sensitive', 'More reactive during poor air quality periods.', 'environmental', true),
      ('geomagnetic_sensitive', 'Geomagnetic Sensitive', 'More reactive during geomagnetic activity.', 'environmental', true),
      ('sleep_sensitive', 'Sleep Sensitive', 'Strongly affected by sleep disruption.', 'environmental', true),
      ('migraine_history', 'Migraine History', 'History of migraine-like episodes.', 'health', true),
      ('chronic_pain', 'Chronic Pain', 'Ongoing pain condition context.', 'health', true),
      ('fibromyalgia', 'Fibromyalgia', 'Fibromyalgia context (self-reported).', 'health', true),
      ('anxiety_sensitive', 'Anxiety Sensitive', 'Heightened sensitivity during stress/anxiety.', 'health', true)
    on conflict (tag_key) do update
    set
      label = excluded.label,
      description = excluded.description,
      section = excluded.section,
      is_active = excluded.is_active;

  elsif has_tag_type and has_risk_level then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, risk_level, description, is_active)
    values
      ('pressure_sensitive', 'Pressure sensitive', 'sensitivity', 'low', 'Weather pressure changes affect me', true),
      ('temp_sensitive', 'Temperature sensitive', 'sensitivity', 'low', 'Temperature swings affect me', true),
      ('aqi_sensitive', 'Air quality sensitive', 'sensitivity', 'low', 'Air quality changes affect me', true),
      ('geomagnetic_sensitive', 'Geomagnetic sensitive', 'sensitivity', 'low', 'I notice changes during geomagnetic activity', true),
      ('sleep_sensitive', 'Sleep sensitive', 'sensitivity', 'low', 'My sleep is easily disrupted', true),
      ('migraine_history', 'Migraine history', 'health_context', 'medium', 'Self-reported: migraine-prone', true),
      ('chronic_pain', 'Chronic pain', 'health_context', 'medium', 'Self-reported: chronic pain', true),
      ('fibromyalgia', 'Fibromyalgia', 'health_context', 'medium', 'Self-reported: fibromyalgia', true),
      ('anxiety_sensitive', 'Anxiety sensitive', 'health_context', 'medium', 'Self-reported: anxiety sensitivity', true)
    on conflict (tag_key) do update
    set
      is_active = excluded.is_active,
      label = excluded.label,
      tag_type = excluded.tag_type,
      risk_level = excluded.risk_level,
      description = excluded.description;

  elsif has_tag_type then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, description, is_active)
    values
      ('pressure_sensitive', 'Pressure sensitive', 'sensitivity', 'Weather pressure changes affect me', true),
      ('temp_sensitive', 'Temperature sensitive', 'sensitivity', 'Temperature swings affect me', true),
      ('aqi_sensitive', 'Air quality sensitive', 'sensitivity', 'Air quality changes affect me', true),
      ('geomagnetic_sensitive', 'Geomagnetic sensitive', 'sensitivity', 'I notice changes during geomagnetic activity', true),
      ('sleep_sensitive', 'Sleep sensitive', 'sensitivity', 'My sleep is easily disrupted', true),
      ('migraine_history', 'Migraine history', 'health_context', 'Self-reported: migraine-prone', true),
      ('chronic_pain', 'Chronic pain', 'health_context', 'Self-reported: chronic pain', true),
      ('fibromyalgia', 'Fibromyalgia', 'health_context', 'Self-reported: fibromyalgia', true),
      ('anxiety_sensitive', 'Anxiety sensitive', 'health_context', 'Self-reported: anxiety sensitivity', true)
    on conflict (tag_key) do update
    set
      is_active = excluded.is_active,
      label = excluded.label,
      tag_type = excluded.tag_type,
      description = excluded.description;

  else
    insert into dim.user_tag_catalog (tag_key, label, description, is_active)
    values
      ('pressure_sensitive', 'Pressure sensitive', 'Weather pressure changes affect me', true),
      ('temp_sensitive', 'Temperature sensitive', 'Temperature swings affect me', true),
      ('aqi_sensitive', 'Air quality sensitive', 'Air quality changes affect me', true),
      ('geomagnetic_sensitive', 'Geomagnetic sensitive', 'I notice changes during geomagnetic activity', true),
      ('sleep_sensitive', 'Sleep sensitive', 'My sleep is easily disrupted', true),
      ('migraine_history', 'Migraine history', 'Self-reported: migraine-prone', true),
      ('chronic_pain', 'Chronic pain', 'Self-reported: chronic pain', true),
      ('fibromyalgia', 'Fibromyalgia', 'Self-reported: fibromyalgia', true),
      ('anxiety_sensitive', 'Anxiety sensitive', 'Self-reported: anxiety sensitivity', true)
    on conflict (tag_key) do update
    set
      is_active = excluded.is_active,
      label = excluded.label,
      description = excluded.description;
  end if;
end $$;
