-- Independent SQL predicate for variant 1: programmers / developers on 1C.
CREATE OR REPLACE TEMP TABLE selected AS
SELECT
    source || ':' || vacancy_id AS vacancy_key,
    name,
    role,
    area,
    salary_from,
    salary_to,
    currency,
    gross,
    list_sort(list_distinct(list_filter(
        list_transform(string_split(coalesce(key_skills, ''), ';'), lambda s: lower(trim(s))),
        lambda s: s <> ''
    ))) AS skills
FROM read_csv($input_uri, header=true, all_varchar=true, max_line_size=16777216)
WHERE role = 'Программист, разработчик'
  AND regexp_matches(lower(name), '1[сc]')
  AND regexp_matches(lower(name), 'программист|разработчик|developer|programmer')
  AND NOT regexp_matches(lower(name), 'битрикс|bitrix');

