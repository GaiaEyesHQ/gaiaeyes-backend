do $$
declare
  has_section boolean;
  has_tag_type boolean;
  has_risk_level boolean;
  has_is_active boolean;
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

  select exists (
    select 1
    from information_schema.columns
    where table_schema = 'dim'
      and table_name = 'user_tag_catalog'
      and column_name = 'is_active'
  ) into has_is_active;

  if has_section then
    insert into dim.user_tag_catalog (tag_key, label, description, section, is_active)
    values
      ('air_quality_sensitive', 'Air Quality Sensitive', 'Air and irritation triggers affect me.', 'sensitivity', true),
      ('anxiety_sensitive', 'Anxiety Sensitive', 'Stress-reactive or overstimulated periods can hit me harder.', 'sensitivity', true),
      ('geomagnetic_sensitive', 'Geomagnetic Sensitive', 'I notice changes during geomagnetic activity.', 'sensitivity', true),
      ('pressure_sensitive', 'Pressure Sensitive', 'Barometric swings can hit me harder.', 'sensitivity', true),
      ('sleep_sensitive', 'Sleep Sensitive', 'My sleep is easily disrupted by stressors.', 'sensitivity', true),
      ('temperature_sensitive', 'Temperature Sensitive', 'Rapid temperature shifts can affect me.', 'sensitivity', true),
      ('migraine_history', 'Migraine History', 'I''m prone to migraines or head-pressure flares.', 'health_context', true),
      ('chronic_pain', 'Chronic Pain', 'Pain flares affect me.', 'health_context', true),
      ('arthritis', 'Arthritis', 'Joint pain or stiffness flares affect me.', 'health_context', true),
      ('fibromyalgia', 'Fibromyalgia', 'Pain and fatigue flares affect me.', 'health_context', true),
      ('hypermobility_eds', 'Hypermobility / EDS', 'Joint and nervous-system flares can affect me.', 'health_context', true),
      ('pots_dysautonomia', 'POTS / Dysautonomia', 'I notice circulation / autonomic changes.', 'health_context', true),
      ('mcas_histamine', 'MCAS / Histamine', 'Histamine or irritation triggers affect me.', 'health_context', true),
      ('allergies_sinus', 'Allergies / Sinus', 'Air and seasonal triggers affect me.', 'health_context', true),
      ('asthma_breathing_sensitive', 'Asthma / Breathing Sensitive', 'Air and breathing irritation affect me.', 'health_context', true),
      ('heart_rhythm_sensitive', 'Heart Rhythm Sensitive', 'I notice heart-rhythm or palpitations more easily.', 'health_context', true),
      ('autoimmune_condition', 'Autoimmune Condition', 'Pain, fatigue, or flare cycles affect me.', 'health_context', true),
      ('nervous_system_dysregulation', 'Nervous System Dysregulation', 'I notice nervous-system overload or regulation changes.', 'health_context', true),
      ('insomnia_sleep_disruption', 'Insomnia / Sleep Disruption', 'Sleep disruption affects me more easily.', 'health_context', true)
    on conflict (tag_key) do update
    set
      label = excluded.label,
      description = excluded.description,
      section = excluded.section,
      is_active = excluded.is_active;

  elsif has_tag_type and has_risk_level then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, risk_level, description, is_active)
    values
      ('air_quality_sensitive', 'Air Quality Sensitive', 'sensitivity', 'low', 'Air and irritation triggers affect me.', true),
      ('anxiety_sensitive', 'Anxiety Sensitive', 'sensitivity', 'low', 'Stress-reactive or overstimulated periods can hit me harder.', true),
      ('geomagnetic_sensitive', 'Geomagnetic Sensitive', 'sensitivity', 'low', 'I notice changes during geomagnetic activity.', true),
      ('pressure_sensitive', 'Pressure Sensitive', 'sensitivity', 'low', 'Barometric swings can hit me harder.', true),
      ('sleep_sensitive', 'Sleep Sensitive', 'sensitivity', 'low', 'My sleep is easily disrupted by stressors.', true),
      ('temperature_sensitive', 'Temperature Sensitive', 'sensitivity', 'low', 'Rapid temperature shifts can affect me.', true),
      ('migraine_history', 'Migraine History', 'health_context', 'medium', 'I''m prone to migraines or head-pressure flares.', true),
      ('chronic_pain', 'Chronic Pain', 'health_context', 'medium', 'Pain flares affect me.', true),
      ('arthritis', 'Arthritis', 'health_context', 'medium', 'Joint pain or stiffness flares affect me.', true),
      ('fibromyalgia', 'Fibromyalgia', 'health_context', 'medium', 'Pain and fatigue flares affect me.', true),
      ('hypermobility_eds', 'Hypermobility / EDS', 'health_context', 'medium', 'Joint and nervous-system flares can affect me.', true),
      ('pots_dysautonomia', 'POTS / Dysautonomia', 'health_context', 'medium', 'I notice circulation / autonomic changes.', true),
      ('mcas_histamine', 'MCAS / Histamine', 'health_context', 'medium', 'Histamine or irritation triggers affect me.', true),
      ('allergies_sinus', 'Allergies / Sinus', 'health_context', 'medium', 'Air and seasonal triggers affect me.', true),
      ('asthma_breathing_sensitive', 'Asthma / Breathing Sensitive', 'health_context', 'medium', 'Air and breathing irritation affect me.', true),
      ('heart_rhythm_sensitive', 'Heart Rhythm Sensitive', 'health_context', 'medium', 'I notice heart-rhythm or palpitations more easily.', true),
      ('autoimmune_condition', 'Autoimmune Condition', 'health_context', 'medium', 'Pain, fatigue, or flare cycles affect me.', true),
      ('nervous_system_dysregulation', 'Nervous System Dysregulation', 'health_context', 'medium', 'I notice nervous-system overload or regulation changes.', true),
      ('insomnia_sleep_disruption', 'Insomnia / Sleep Disruption', 'health_context', 'medium', 'Sleep disruption affects me more easily.', true)
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
      ('air_quality_sensitive', 'Air Quality Sensitive', 'sensitivity', 'Air and irritation triggers affect me.', true),
      ('anxiety_sensitive', 'Anxiety Sensitive', 'sensitivity', 'Stress-reactive or overstimulated periods can hit me harder.', true),
      ('geomagnetic_sensitive', 'Geomagnetic Sensitive', 'sensitivity', 'I notice changes during geomagnetic activity.', true),
      ('pressure_sensitive', 'Pressure Sensitive', 'sensitivity', 'Barometric swings can hit me harder.', true),
      ('sleep_sensitive', 'Sleep Sensitive', 'sensitivity', 'My sleep is easily disrupted by stressors.', true),
      ('temperature_sensitive', 'Temperature Sensitive', 'sensitivity', 'Rapid temperature shifts can affect me.', true),
      ('migraine_history', 'Migraine History', 'health_context', 'I''m prone to migraines or head-pressure flares.', true),
      ('chronic_pain', 'Chronic Pain', 'health_context', 'Pain flares affect me.', true),
      ('arthritis', 'Arthritis', 'health_context', 'Joint pain or stiffness flares affect me.', true),
      ('fibromyalgia', 'Fibromyalgia', 'health_context', 'Pain and fatigue flares affect me.', true),
      ('hypermobility_eds', 'Hypermobility / EDS', 'health_context', 'Joint and nervous-system flares can affect me.', true),
      ('pots_dysautonomia', 'POTS / Dysautonomia', 'health_context', 'I notice circulation / autonomic changes.', true),
      ('mcas_histamine', 'MCAS / Histamine', 'health_context', 'Histamine or irritation triggers affect me.', true),
      ('allergies_sinus', 'Allergies / Sinus', 'health_context', 'Air and seasonal triggers affect me.', true),
      ('asthma_breathing_sensitive', 'Asthma / Breathing Sensitive', 'health_context', 'Air and breathing irritation affect me.', true),
      ('heart_rhythm_sensitive', 'Heart Rhythm Sensitive', 'health_context', 'I notice heart-rhythm or palpitations more easily.', true),
      ('autoimmune_condition', 'Autoimmune Condition', 'health_context', 'Pain, fatigue, or flare cycles affect me.', true),
      ('nervous_system_dysregulation', 'Nervous System Dysregulation', 'health_context', 'I notice nervous-system overload or regulation changes.', true),
      ('insomnia_sleep_disruption', 'Insomnia / Sleep Disruption', 'health_context', 'Sleep disruption affects me more easily.', true)
    on conflict (tag_key) do update
    set
      is_active = excluded.is_active,
      label = excluded.label,
      tag_type = excluded.tag_type,
      description = excluded.description;

  else
    insert into dim.user_tag_catalog (tag_key, label, description, is_active)
    values
      ('air_quality_sensitive', 'Air Quality Sensitive', 'Air and irritation triggers affect me.', true),
      ('anxiety_sensitive', 'Anxiety Sensitive', 'Stress-reactive or overstimulated periods can hit me harder.', true),
      ('geomagnetic_sensitive', 'Geomagnetic Sensitive', 'I notice changes during geomagnetic activity.', true),
      ('pressure_sensitive', 'Pressure Sensitive', 'Barometric swings can hit me harder.', true),
      ('sleep_sensitive', 'Sleep Sensitive', 'My sleep is easily disrupted by stressors.', true),
      ('temperature_sensitive', 'Temperature Sensitive', 'Rapid temperature shifts can affect me.', true),
      ('migraine_history', 'Migraine History', 'I''m prone to migraines or head-pressure flares.', true),
      ('chronic_pain', 'Chronic Pain', 'Pain flares affect me.', true),
      ('arthritis', 'Arthritis', 'Joint pain or stiffness flares affect me.', true),
      ('fibromyalgia', 'Fibromyalgia', 'Pain and fatigue flares affect me.', true),
      ('hypermobility_eds', 'Hypermobility / EDS', 'Joint and nervous-system flares can affect me.', true),
      ('pots_dysautonomia', 'POTS / Dysautonomia', 'I notice circulation / autonomic changes.', true),
      ('mcas_histamine', 'MCAS / Histamine', 'Histamine or irritation triggers affect me.', true),
      ('allergies_sinus', 'Allergies / Sinus', 'Air and seasonal triggers affect me.', true),
      ('asthma_breathing_sensitive', 'Asthma / Breathing Sensitive', 'Air and breathing irritation affect me.', true),
      ('heart_rhythm_sensitive', 'Heart Rhythm Sensitive', 'I notice heart-rhythm or palpitations more easily.', true),
      ('autoimmune_condition', 'Autoimmune Condition', 'Pain, fatigue, or flare cycles affect me.', true),
      ('nervous_system_dysregulation', 'Nervous System Dysregulation', 'I notice nervous-system overload or regulation changes.', true),
      ('insomnia_sleep_disruption', 'Insomnia / Sleep Disruption', 'Sleep disruption affects me more easily.', true)
    on conflict (tag_key) do update
    set
      is_active = excluded.is_active,
      label = excluded.label,
      description = excluded.description;
  end if;

  if has_is_active then
    update dim.user_tag_catalog
       set is_active = false
     where tag_key in ('aqi_sensitive', 'temp_sensitive');
  end if;
end $$;

insert into dim.symptom_codes as sc (symptom_code, label, description)
values
  ('brain_fog', 'Brain fog', 'Foggy, scattered, or slower-than-usual thinking'),
  ('chest_tightness', 'Chest tightness', 'Chest tightness or heavier breathing feel'),
  ('fatigue', 'Fatigue', 'Fatigue or heavier-than-usual body load'),
  ('joint_pain', 'Joint pain', 'Joint pain or arthritic flare feeling'),
  ('light_sensitivity', 'Light sensitivity', 'Light feels harsher or easier to notice'),
  ('pain', 'Pain flare', 'Broader pain flare or body discomfort'),
  ('palpitations', 'Palpitations', 'Heart-rhythm awareness or palpitations'),
  ('resp_irritation', 'Breathing irritation', 'Breathing irritation or airway sensitivity'),
  ('restless_sleep', 'Restless sleep', 'Restless or unrefreshing sleep'),
  ('sinus_pressure', 'Sinus pressure', 'Sinus or head-pressure feeling'),
  ('stiffness', 'Stiffness', 'Body stiffness or tightness'),
  ('wired', 'Wired', 'Wired, buzzy, or restless feeling')
on conflict (symptom_code) do update
set label = excluded.label,
    description = excluded.description,
    is_active = true;
