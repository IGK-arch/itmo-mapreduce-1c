"""Independent Python recomputation of reported salary and regional summaries."""
import csv
import io
import json
import math
import statistics
from collections import Counter, defaultdict

import bootstrap
from bootstrap import ROOT
from vacancy_lab.mapreduce import ChunkStream, belongs_to_variant
from vacancy_lab.results import read_result
from vacancy_lab.storage import client, read_config


def amount(text):
    try:
        return float(text) if text else None
    except ValueError:
        return None


def pay(row):
    if row['currency'] != 'RUR' or row['gross'] != 'false':
        return None
    lo, hi = amount(row['salary_from']), amount(row['salary_to'])
    if (lo is not None and lo <= 0) or (hi is not None and hi <= 0):
        return None
    if lo is not None and hi is not None:
        return (lo+hi)/2 if lo <= hi else None
    return lo if lo is not None else hi


def main():
    cfg = read_config()
    analysis = json.loads((ROOT/'results'/'analysis.json').read_text(encoding='utf-8'))
    expected = {}
    effects = []
    for groups in analysis['salary_rankings'].values():
        for direction in ('higher','lower'):
            for row in groups[direction]:
                k = row['stack_size']
                group = tuple(row[f'skill_{i}'] for i in range(1,k+1))
                # Resolve the actual most frequent base from complete MR frequencies.
                effects.append((group,row))
                expected[group] = (row['vacancies'],row['salary_vacancies'],row['median_salary'])
    counts = read_result(ROOT/'results'/'optimized-1')
    import itertools
    bases = {}
    for group,row in effects:
        subsets=list(itertools.combinations(group,len(group)-1))
        base=min(subsets,key=lambda item:(-counts[(len(item),*item)],item))
        assert ' + '.join(base)==row['base_skills']
        bases[group]=base
        expected[base]=(row['base_vacancies'],row['base_salary_vacancies'],row['base_median_salary'])
    all_pay=[]
    group_counts=Counter()
    group_pay=defaultdict(list)
    group_employers=defaultdict(list)
    region_counts=Counter()
    region_skill_counts=Counter()
    region_pay=defaultdict(list)
    regional_expected={}
    for row in analysis['regional_combinations']:
        group=tuple(row[f'skill_{i}'] for i in range(1,row['stack_size']+1))
        regional_expected[(row['area'],group)]=row
    regional_counts=Counter()
    regional_pay=defaultdict(list)
    raw=ChunkStream(client().get_object(Bucket=cfg['bucket'],Key=cfg['input_key'])['Body'],cfg['chunk_bytes'])
    csv.field_size_limit(16*1024*1024)
    text=io.TextIOWrapper(io.BufferedReader(raw),encoding='utf-8-sig',newline='')
    selected=0
    try:
        for row in csv.DictReader(text):
            if not belongs_to_variant(row):
                continue
            selected+=1
            skills={s.strip().lower() for s in row['key_skills'].split(';') if s.strip()}
            salary=pay(row)
            if salary is not None:all_pay.append(salary)
            for group in expected:
                if set(group)<=skills:
                    group_counts[group]+=1
                    if salary is not None:
                        group_pay[group].append(salary)
                        group_employers[group].append((row['employer_id'],salary))
            area=row['area']
            if area in analysis['regions']:
                region_counts[area]+=1
                region_skill_counts[area]+=bool(skills)
                if salary is not None:region_pay[area].append(salary)
                for (region,group) in regional_expected:
                    if region==area and set(group)<=skills:
                        regional_counts[(region,group)]+=1
                        if salary is not None:regional_pay[(region,group)].append(salary)
    finally:
        text.close();raw.body.close()
    audit = json.loads((ROOT/'evidence'/'source-audit.json').read_text(encoding='utf-8'))
    assert selected==analysis['coverage']['vacancies']==audit['counts']['selected_vacancies']
    assert len(all_pay)==analysis['coverage']['salary_vacancies']==7594
    assert statistics.median(all_pay)==analysis['coverage']['median_salary']==150000
    for group,(total,paid,median) in expected.items():
        assert group_counts[group]==total,(group,'count')
        assert len(group_pay[group])==paid,(group,'salary_count')
        assert statistics.median(group_pay[group])==median,(group,'median')
    for row in analysis['regions_overview']:
        area=row['area']
        assert region_counts[area]==row['vacancies']
        assert region_skill_counts[area]==row['vacancies_with_skills']
        assert len(region_pay[area])==row['salary_vacancies']
        assert statistics.median(region_pay[area])==row['median_salary']
    for key,row in regional_expected.items():
        assert regional_counts[key]==row['vacancies']
        assert len(regional_pay[key])==row['salary_vacancies']
        assert statistics.median(regional_pay[key])==row['median_salary']
    for diagnostic in analysis['cohort_diagnostics']:
        group=tuple(diagnostic['skills']);largest=diagnostic['largest_employers'][0]
        employers=Counter(e for e,_ in group_employers[group])
        assert employers[largest['id']]==largest['vacancies']
        without=[p for e,p in group_employers[group] if e!=largest['id']]
        assert len(without)==diagnostic['without_largest_employer']['salary_vacancies']
        assert statistics.median(without)==diagnostic['without_largest_employer']['median_salary']
    summary={'all_checks_passed':True,'selected_vacancies':selected,'salary_vacancies':len(all_pay),
             'salary_groups_checked':len(expected),'regional_groups_checked':len(regional_expected),
             'source_sha256':raw.digest.hexdigest()}
    (ROOT/'evidence'/'analysis-validation.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
