"""Salary associations and three-region comparisons within variant 1 only."""
import csv
import itertools
import json
from pathlib import Path

import bootstrap
from bootstrap import ROOT
from vacancy_lab.duckdb_engine import connect, load_selected
from vacancy_lab.storage import read_config


def rows_as_dicts(cursor):
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f'Empty analysis: {path}')
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    cfg = read_config()
    con = connect()
    load_selected(con)
    con.execute("""
        CREATE TEMP TABLE paid AS
        WITH amounts AS (
            SELECT *, try_cast(nullif(salary_from,'') AS DOUBLE) AS lo,
                      try_cast(nullif(salary_to,'') AS DOUBLE) AS hi
            FROM selected
        )
        SELECT vacancy_key, area,
          CASE WHEN currency='RUR' AND gross='false'
                 AND (lo IS NULL OR lo>0) AND (hi IS NULL OR hi>0)
                 AND (lo IS NULL OR hi IS NULL OR lo<=hi)
          THEN CASE WHEN lo IS NOT NULL AND hi IS NOT NULL THEN (lo+hi)/2
                    ELSE coalesce(lo,hi) END END AS salary
        FROM amounts;
    """)
    coverage = rows_as_dicts(con.execute("""
        SELECT count(*) AS vacancies, count(salary) AS salary_vacancies,
               median(salary) AS median_salary, min(salary) AS minimum_salary,
               max(salary) AS maximum_salary FROM paid
    """))[0]
    stats = rows_as_dicts(con.execute("""
        SELECT stack_size,skill_1,skill_2,skill_3,count(*) AS vacancies,
               count(salary) AS salary_vacancies,median(salary) AS median_salary
        FROM combinations JOIN paid USING (vacancy_key)
        GROUP BY stack_size,skill_1,skill_2,skill_3
        ORDER BY stack_size,skill_1,skill_2,skill_3
    """))
    write_csv(ROOT / 'results' / 'salary-combinations.csv', stats)
    lookup = {(r['stack_size'], *[r['skill_1'], r['skill_2'], r['skill_3']][:r['stack_size']]): r for r in stats}
    effects = []
    for row in stats:
        k = row['stack_size']
        if k < 2 or row['salary_vacancies'] < cfg['min_salary_support']:
            continue
        skills = [row['skill_1'], row['skill_2'], row['skill_3']][:k]
        subsets = [(k-1, *combo) for combo in itertools.combinations(skills, k-1)]
        base_key = min(subsets, key=lambda key: (-lookup[key]['vacancies'], key))
        baseline = lookup[base_key]
        assert baseline['vacancies'] >= row['vacancies']
        assert baseline['salary_vacancies'] >= row['salary_vacancies']
        added = next(iter(set(skills) - set(base_key[1:])))
        difference = row['median_salary'] - baseline['median_salary']
        effects.append({
            'stack_size': k, 'skills': ' + '.join(skills),
            'skill_1': skills[0], 'skill_2': skills[1], 'skill_3': skills[2] if k == 3 else '',
            'base_skills': ' + '.join(base_key[1:]), 'added_skill': added,
            'vacancies': row['vacancies'], 'salary_vacancies': row['salary_vacancies'],
            'median_salary': row['median_salary'], 'base_vacancies': baseline['vacancies'],
            'base_salary_vacancies': baseline['salary_vacancies'],
            'base_median_salary': baseline['median_salary'],
            'difference_rub': difference,
            'difference_percent': 100 * difference / baseline['median_salary'],
        })
    effects.sort(key=lambda r: (r['stack_size'], -r['difference_rub'], -r['salary_vacancies'], r['skills']))
    write_csv(ROOT / 'results' / 'salary-effects.csv', effects)
    rankings = {}
    for k in (2, 3):
        eligible = [r for r in effects if r['stack_size'] == k]
        positive = sorted([r for r in eligible if r['difference_rub'] > 0],
                          key=lambda r: (-r['difference_rub'], -r['salary_vacancies'], r['skills']))[:5]
        negative = sorted([r for r in eligible if r['difference_rub'] < 0],
                          key=lambda r: (r['difference_rub'], -r['salary_vacancies'], r['skills']))[:5]
        assert positive and negative
        rankings[str(k)] = {'higher': positive, 'lower': negative,
                            'eligible_combinations': len(eligible)}
    regions = [r[0] for r in con.execute('SELECT area FROM selected GROUP BY area ORDER BY count(*) DESC,area LIMIT 3').fetchall()]
    if cfg['analysis_regions']:
        regions = cfg['analysis_regions']
    assert len(regions) == 3
    con.execute('CREATE TEMP TABLE chosen_regions AS SELECT unnest($regions) AS area', {'regions': regions})
    region_overview = rows_as_dicts(con.execute("""
        SELECT s.area,count(*) AS vacancies,count_if(len(s.skills)>0) AS vacancies_with_skills,
               count(p.salary) AS salary_vacancies,median(p.salary) AS median_salary
        FROM selected s JOIN paid p USING(vacancy_key) JOIN chosen_regions r ON s.area=r.area
        GROUP BY s.area ORDER BY vacancies DESC,s.area
    """))
    region_combinations = rows_as_dicts(con.execute("""
        WITH grouped AS (
            SELECT p.area,c.stack_size,c.skill_1,c.skill_2,c.skill_3,
                   count(*) AS vacancies,count(p.salary) AS salary_vacancies,
                   median(p.salary) AS median_salary
            FROM combinations c JOIN paid p USING(vacancy_key)
            JOIN chosen_regions r ON p.area=r.area
            GROUP BY p.area,c.stack_size,c.skill_1,c.skill_2,c.skill_3
        ), ranked AS (
            SELECT *, row_number() OVER(PARTITION BY area,stack_size
                ORDER BY vacancies DESC,skill_1,skill_2,skill_3) AS place
            FROM grouped
        ) SELECT * FROM ranked WHERE place<=5 ORDER BY area,stack_size,place
    """))
    region_totals = {r['area']: r['vacancies'] for r in region_overview}
    for row in region_combinations:
        row['share_percent'] = 100 * row['vacancies'] / region_totals[row['area']]
    write_csv(ROOT / 'results' / 'regions-overview.csv', region_overview)
    write_csv(ROOT / 'results' / 'regions-top-combinations.csv', region_combinations)
    top_skills = sorted([r for r in stats if r['stack_size'] == 1], key=lambda r: (-r['vacancies'], r['skill_1']))[:10]
    con.execute("""
        CREATE TEMP TABLE job_details AS
        SELECT source || ':' || vacancy_id AS vacancy_key,employer_id,employer_name,experience,name
        FROM read_csv($input_uri,header=true,all_varchar=true,max_line_size=16777216)
        WHERE source || ':' || vacancy_id IN (SELECT vacancy_key FROM selected)
    """, {'input_uri': f"s3://{cfg['bucket']}/{cfg['input_key']}"})
    diagnostics = []
    for k in ('2', '3'):
        for direction in ('higher', 'lower'):
            effect = rankings[k][direction][0]
            skills = [effect[f'skill_{i}'] for i in range(1, int(k)+1)]
            cohort = rows_as_dicts(con.execute("""
                SELECT d.employer_id,d.employer_name,d.experience,d.name,p.salary,p.area
                FROM selected s JOIN paid p USING(vacancy_key)
                JOIN job_details d USING(vacancy_key)
                WHERE p.salary IS NOT NULL AND list_has_all(s.skills,$skills)
            """, {'skills': skills}))
            from collections import Counter
            employers = Counter((r['employer_id'],r['employer_name']) for r in cohort)
            experiences = Counter(r['experience'] for r in cohort)
            regions_count = Counter(r['area'] for r in cohort)
            base_subsets = [(int(k)-1,*items) for items in itertools.combinations(skills,int(k)-1)]
            base_key = min(base_subsets,key=lambda key:(-lookup[key]['vacancies'],key))
            base_skills = list(base_key[1:])
            dominant_id = employers.most_common(1)[0][0][0]
            sensitivity = rows_as_dicts(con.execute("""
                SELECT count(*) AS salary_vacancies,median(p.salary) AS median_salary
                FROM selected s JOIN paid p USING(vacancy_key)
                JOIN job_details d USING(vacancy_key)
                WHERE p.salary IS NOT NULL AND d.employer_id<>$excluded
                  AND list_has_all(s.skills,$skills)
            """, {'excluded':dominant_id,'skills':skills}))[0]
            base_without = rows_as_dicts(con.execute("""
                SELECT count(*) AS salary_vacancies,median(p.salary) AS median_salary
                FROM selected s JOIN paid p USING(vacancy_key)
                JOIN job_details d USING(vacancy_key)
                WHERE p.salary IS NOT NULL AND d.employer_id<>$excluded
                  AND list_has_all(s.skills,$skills)
            """, {'excluded':dominant_id,'skills':base_skills}))[0]
            diagnostics.append({'stack_size': int(k), 'direction': direction, 'skills': skills,
                                'salary_vacancies': len(cohort), 'employers': len(employers),
                                'largest_employers': [{'id': key[0], 'name': key[1], 'vacancies': n} for key,n in employers.most_common(3)],
                                'experience_counts': dict(experiences), 'region_counts': dict(regions_count),
                                'title_examples': list(dict.fromkeys(r['name'] for r in cohort))[:8],
                                'without_largest_employer': sensitivity,
                                'base_without_largest_employer': base_without})
            assert len(cohort) == effect['salary_vacancies']
    low_salaries = con.execute('SELECT count(*) FROM paid WHERE salary<10000').fetchone()[0]
    result = {'variant': cfg['variant_name'], 'salary_basis': 'RUR, gross=false; midpoint if both bounds, otherwise given bound',
              'min_salary_support': cfg['min_salary_support'], 'coverage': coverage,
              'top_skills': top_skills, 'salary_rankings': rankings,
              'regions': regions, 'regions_overview': region_overview,
              'regional_combinations': region_combinations, 'cohort_diagnostics': diagnostics,
              'salary_values_below_10000': low_salaries}
    (ROOT / 'results' / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    concise = {k: v for k, v in result.items() if k not in ['regional_combinations']}
    print(json.dumps(concise, ensure_ascii=False, indent=2), flush=True)
    con.close()


if __name__ == '__main__':
    main()
