with payload(symptom_code, label, description) as (
  values
    ('nausea', 'Nausea', 'Nausea, queasy, or unsettled stomach'),
    ('bloating', 'Bloating', 'Bloating or swollen stomach feeling'),
    ('stomach_pain', 'Stomach pain', 'Stomach pain or cramping'),
    ('reflux', 'Reflux', 'Reflux, heartburn, or acid irritation'),
    ('digestive_upset', 'Digestive upset', 'Digestive upset or off digestion'),
    ('bowel_urgency', 'Bowel urgency', 'Urgency, IBS flare, or sudden bowel changes')
)
insert into dim.symptom_codes as sc (symptom_code, label, description)
select p.symptom_code, p.label, p.description
from payload p
on conflict (symptom_code) do update
set label = excluded.label,
    description = excluded.description,
    is_active = true;
