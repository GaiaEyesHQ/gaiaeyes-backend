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
      'illness_other'
    )
  );

comment on column raw.user_exposure_events.exposure_key is
  'Temporary context flags from daily check-ins/manual logs. Used for current gauge context and to suppress confounded personal pattern learning days.';

commit;
