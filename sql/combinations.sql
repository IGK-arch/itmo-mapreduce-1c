CREATE OR REPLACE TEMP TABLE skill_positions AS
SELECT vacancy_key, unnest(skills) AS skill, generate_subscripts(skills, 1) AS position
FROM selected;

CREATE OR REPLACE TEMP TABLE combinations AS
SELECT a.vacancy_key, 1 AS stack_size, a.skill AS skill_1, '' AS skill_2, '' AS skill_3
FROM skill_positions a
UNION ALL
SELECT a.vacancy_key, 2, a.skill, b.skill, ''
FROM skill_positions a JOIN skill_positions b
  ON a.vacancy_key=b.vacancy_key AND a.position<b.position
UNION ALL
SELECT a.vacancy_key, 3, a.skill, b.skill, c.skill
FROM skill_positions a
JOIN skill_positions b ON a.vacancy_key=b.vacancy_key AND a.position<b.position
JOIN skill_positions c ON a.vacancy_key=c.vacancy_key AND b.position<c.position;

