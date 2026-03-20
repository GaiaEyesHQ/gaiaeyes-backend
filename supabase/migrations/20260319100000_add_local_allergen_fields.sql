begin;

alter table if exists marts.local_forecast_daily
    add column if not exists pollen_tree_level text,
    add column if not exists pollen_grass_level text,
    add column if not exists pollen_weed_level text,
    add column if not exists pollen_mold_level text,
    add column if not exists pollen_overall_level text,
    add column if not exists pollen_primary_type text,
    add column if not exists pollen_source text,
    add column if not exists pollen_updated_at timestamptz,
    add column if not exists pollen_tree_index numeric,
    add column if not exists pollen_grass_index numeric,
    add column if not exists pollen_weed_index numeric,
    add column if not exists pollen_mold_index numeric,
    add column if not exists pollen_overall_index numeric;

comment on column marts.local_forecast_daily.pollen_overall_level is
  'Normalized Gaia Eyes allergen severity bucket for the forecast day: low, moderate, high, very_high.';

comment on column marts.local_forecast_daily.pollen_primary_type is
  'Forecast allergen type with the highest projected daily burden when available.';

alter table if exists marts.user_daily_features
    add column if not exists pollen_overall_index numeric,
    add column if not exists pollen_tree_index numeric,
    add column if not exists pollen_grass_index numeric,
    add column if not exists pollen_weed_index numeric,
    add column if not exists pollen_mold_index numeric,
    add column if not exists pollen_overall_level text,
    add column if not exists pollen_tree_level text,
    add column if not exists pollen_grass_level text,
    add column if not exists pollen_weed_level text,
    add column if not exists pollen_mold_level text,
    add column if not exists pollen_primary_type text,
    add column if not exists pollen_overall_exposed boolean,
    add column if not exists pollen_tree_exposed boolean,
    add column if not exists pollen_grass_exposed boolean,
    add column if not exists pollen_weed_exposed boolean,
    add column if not exists pollen_mold_exposed boolean;

comment on column marts.user_daily_features.pollen_overall_exposed is
  'True when the daily overall allergen burden reached at least moderate for the user location context.';

commit;
