begin;

alter table if exists app.user_bug_reports
  alter column user_id drop not null;

commit;
