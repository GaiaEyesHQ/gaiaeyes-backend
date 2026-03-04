-- Grant ingestion role access to ext.schumann for GitHub Actions REST inserts.
grant usage on schema ext to service_role;

grant select, insert, update on table ext.schumann to service_role;
grant select on table ext.schumann_station to service_role;

-- Keep future tables in ext writable by service_role without manual grants.
alter default privileges in schema ext
  grant select, insert, update on tables to service_role;
