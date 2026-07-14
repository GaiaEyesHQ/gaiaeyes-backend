begin;

alter table raw.user_exposure_events
  drop constraint if exists user_exposure_events_exposure_key_check;

alter table raw.user_exposure_events
  add constraint user_exposure_events_exposure_key_check
  check (
    exposure_key in (
      'overexertion',
      'allergen_exposure',
      'temporary_illness',
      'illness_respiratory',
      'illness_gastrointestinal',
      'illness_fever',
      'illness_other',
      'fragrance_scented_products',
      'cleaning_products',
      'plastics_heated_food',
      'ultra_processed_meal',
      'alcohol',
      'high_histamine_foods',
      'pesticide_heavy_produce',
      'mold_damp_space',
      'workplace_exposure',
      'heavy_traffic',
      'poor_air_quality',
      'rapid_temperature_change',
      'new_supplement_medication'
    )
  );

comment on column raw.user_exposure_events.exposure_key is
  'User-logged exposure diary context. Used for current body-context guidance and future evidence-scaled personal trigger patterns; not a diagnosis, dose estimate, or confirmed causal claim.';

commit;
