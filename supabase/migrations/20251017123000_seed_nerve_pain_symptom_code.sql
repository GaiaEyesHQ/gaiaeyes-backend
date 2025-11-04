-- Ensure the nerve_pain symptom code exists for mobile logging.
DO $$
DECLARE
    schema_name text;
    has_label boolean;
    has_category boolean;
    has_description boolean;
BEGIN
    FOR schema_name IN
        SELECT table_schema
        FROM information_schema.tables
        WHERE table_name = 'symptom_codes'
    LOOP
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = schema_name
              AND table_name = 'symptom_codes'
              AND column_name = 'label'
        ) INTO has_label;

        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = schema_name
              AND table_name = 'symptom_codes'
              AND column_name = 'category'
        ) INTO has_category;

        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = schema_name
              AND table_name = 'symptom_codes'
              AND column_name = 'description'
        ) INTO has_description;

        IF has_label AND has_category AND has_description THEN
            EXECUTE format(
                'INSERT INTO %I.symptom_codes (code, label, category, description)
                 VALUES ($1, $2, $3, $4)
                 ON CONFLICT (code) DO UPDATE
                 SET label = EXCLUDED.label,
                     category = EXCLUDED.category,
                     description = EXCLUDED.description',
                schema_name
            ) USING
                'nerve_pain',
                'Nerve pain',
                'pain',
                'Neuropathy, tingling, or nerve flare symptoms logged via the mobile app.';

        ELSIF has_label AND has_category THEN
            EXECUTE format(
                'INSERT INTO %I.symptom_codes (code, label, category)
                 VALUES ($1, $2, $3)
                 ON CONFLICT (code) DO UPDATE
                 SET label = EXCLUDED.label,
                     category = EXCLUDED.category',
                schema_name
            ) USING
                'nerve_pain',
                'Nerve pain',
                'pain';

        ELSIF has_label THEN
            EXECUTE format(
                'INSERT INTO %I.symptom_codes (code, label)
                 VALUES ($1, $2)
                 ON CONFLICT (code) DO UPDATE
                 SET label = EXCLUDED.label',
                schema_name
            ) USING
                'nerve_pain',
                'Nerve pain';

        ELSE
            EXECUTE format(
                'INSERT INTO %I.symptom_codes (code)
                 VALUES ($1)
                 ON CONFLICT (code) DO NOTHING',
                schema_name
            ) USING
                'nerve_pain';
        END IF;
    END LOOP;
END
$$;
