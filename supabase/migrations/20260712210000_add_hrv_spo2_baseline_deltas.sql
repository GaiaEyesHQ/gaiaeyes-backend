alter table gaia.daily_summary
  add column if not exists hrv_baseline_delta numeric,
  add column if not exists spo2_baseline_delta numeric;

comment on column gaia.daily_summary.hrv_baseline_delta is
  'Daily HRV average minus the preceding 14-day personal average; requires at least 3 prior days.';

comment on column gaia.daily_summary.spo2_baseline_delta is
  'Daily SpO2 average minus the preceding 14-day personal average in percentage points; requires at least 3 prior days.';

create or replace function gaia.set_daily_summary_hrv_spo2_baselines()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  hrv_baseline numeric;
  hrv_days bigint;
  spo2_baseline numeric;
  spo2_days bigint;
begin
  select avg(d.hrv_avg), count(*)
    into hrv_baseline, hrv_days
  from gaia.daily_summary d
  where d.user_id = new.user_id
    and d.date >= new.date - 14
    and d.date < new.date
    and d.hrv_avg is not null;

  select avg(d.spo2_avg), count(*)
    into spo2_baseline, spo2_days
  from gaia.daily_summary d
  where d.user_id = new.user_id
    and d.date >= new.date - 14
    and d.date < new.date
    and d.spo2_avg is not null;

  new.hrv_baseline_delta := case
    when hrv_days >= 3 and new.hrv_avg is not null and hrv_baseline is not null
      then round((new.hrv_avg - hrv_baseline)::numeric, 3)
    else null
  end;

  new.spo2_baseline_delta := case
    when spo2_days >= 3 and new.spo2_avg is not null and spo2_baseline is not null
      then round((new.spo2_avg - spo2_baseline)::numeric, 3)
    else null
  end;

  return new;
end;
$$;

drop trigger if exists daily_summary_hrv_spo2_baselines on gaia.daily_summary;

create trigger daily_summary_hrv_spo2_baselines
before insert or update of user_id, date, hrv_avg, spo2_avg
on gaia.daily_summary
for each row
execute function gaia.set_daily_summary_hrv_spo2_baselines();

with baseline_values as (
  select
    d.user_id,
    d.date,
    case
      when hrv_base.n >= 3 and d.hrv_avg is not null and hrv_base.avg_val is not null
        then round((d.hrv_avg - hrv_base.avg_val)::numeric, 3)
      else null
    end as hrv_baseline_delta,
    case
      when spo2_base.n >= 3 and d.spo2_avg is not null and spo2_base.avg_val is not null
        then round((d.spo2_avg - spo2_base.avg_val)::numeric, 3)
      else null
    end as spo2_baseline_delta
  from gaia.daily_summary d
  left join lateral (
    select avg(prior.hrv_avg) as avg_val, count(*) as n
    from gaia.daily_summary prior
    where prior.user_id = d.user_id
      and prior.date >= d.date - 14
      and prior.date < d.date
      and prior.hrv_avg is not null
  ) hrv_base on true
  left join lateral (
    select avg(prior.spo2_avg) as avg_val, count(*) as n
    from gaia.daily_summary prior
    where prior.user_id = d.user_id
      and prior.date >= d.date - 14
      and prior.date < d.date
      and prior.spo2_avg is not null
  ) spo2_base on true
)
update gaia.daily_summary d
set
  hrv_baseline_delta = b.hrv_baseline_delta,
  spo2_baseline_delta = b.spo2_baseline_delta
from baseline_values b
where d.user_id = b.user_id
  and d.date = b.date
  and (
    d.hrv_baseline_delta is distinct from b.hrv_baseline_delta
    or d.spo2_baseline_delta is distinct from b.spo2_baseline_delta
  );
