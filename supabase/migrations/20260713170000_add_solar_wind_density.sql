alter table ext.space_weather
  add column if not exists sw_density_cm3 numeric;

comment on column ext.space_weather.sw_density_cm3 is
  'Active NOAA RTSW proton density in particles per cubic centimeter.';
