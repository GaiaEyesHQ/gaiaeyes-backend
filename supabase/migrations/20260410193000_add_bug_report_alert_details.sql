begin;

alter table if exists app.user_bug_reports
  add column if not exists alert_email_to text null,
  add column if not exists alert_response jsonb null;

commit;
