"""Export readable tables after checking the saved calculation evidence."""
import csv
import hashlib
import json
import statistics

import bootstrap
from bootstrap import ROOT


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    audit = read('evidence/source-audit.json')
    verified = read('evidence/verification.json')
    checked = read('evidence/analysis-validation.json')
    profiles = read('evidence/benchmark-runs.json')
    summary = read('evidence/benchmark-summary.json')
    assert verified['all_equal'] and checked['all_checks_passed']
    assert verified['compared_runs'] == 10
    assert audit['counts']['selected_vacancies'] == verified['selected_vacancies'] == checked['selected_vacancies']
    assert all(r['different_keys']==0 and r['selected_ids_match'] for r in verified['comparisons'])
    assert len(verified['results_in_s3'])==6 and all(r['readback_matches'] for r in verified['results_in_s3'])
    assert len(profiles)==9 and all(r['exit_code']==0 for r in profiles)
    assert checked['source_sha256']==audit['source_sha256']
    table=[]
    for method in ('baseline','optimized','duckdb'):
        rows=sorted((r for r in profiles if r['method']==method),key=lambda r:r['trial'])
        assert [r['trial'] for r in rows]==[1,2,3]
        assert statistics.median(r['wall_seconds'] for r in rows)==summary[method]['median_wall_seconds']
        assert statistics.median(r['peak_process_tree_rss_bytes']/1048576 for r in rows)==summary[method]['median_peak_rss_mib']
        table.extend({'Method':method,'Attempt':r['trial'],'Wall_s':f"{r['wall_seconds']:.3f}",
                      'Peak_RSS_MiB':f"{r['peak_process_tree_rss_bytes']/1048576:.1f}",
                      'Exit_code':r['exit_code']} for r in rows)
    with (ROOT/'evidence'/'benchmark-table.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(table)
    lines=['input: s3://hh-lake/raw/it_vacancies_2024.csv',
           'variant: 1 / Программист, разработчик на 1С',
           f"selected_vacancies: {verified['selected_vacancies']}",
           'MapReduce / DuckDB: full key and frequency comparison']
    for r in verified['growth']:
        assert r['emitted_combinations']==r['sum_choose_n_k']
        lines.append(f"k={r['stack_size']}: total={r['emitted_combinations']}, unique={r['unique_combinations']}, differences=0")
    fault=read('results/mapper-failure/metadata.json')
    assert verified['mapper_failure_recovered'] and fault['failures'][0]['exit_code']==73
    assert fault['committed_batches']==fault['batches']==230
    lines += ['selected IDs: identical', 'verified runs: 9 regular + 1 mapper failure',
              'mapper exit code: 73; recovered; committed batches: 230/230',
              'S3 results: 6 objects; full readback: identical',
              f"salary groups independently checked: {checked['salary_groups_checked']}",
              f"regional groups independently checked: {checked['regional_groups_checked']}",
              'all_checks_passed: true']
    output='\n'.join(lines)+'\n'
    (ROOT/'evidence'/'data-checks.txt').write_text(output,encoding='utf-8',newline='\n')
    analysis=read('results/analysis.json')
    concise={k:v for k,v in analysis.items() if k!='regional_combinations'}
    (ROOT/'evidence'/'analysis-output.txt').write_text(json.dumps(concise,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    source_files=['src/vacancy_lab/mapreduce.py','src/vacancy_lab/duckdb_engine.py',
                  'scripts/benchmark.py','scripts/analyze.py','scripts/check_analysis.py',
                  'scripts/verify_results.py','scripts/demo_terminal.py','scripts/live_console.py',
                  'Show-Run.ps1','sql/selected.sql','sql/combinations.sql','config.json']
    # Git stores text with LF; normalize CRLF for the same hashes after cloning.
    hashes={name:hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in source_files}
    (ROOT/'evidence'/'calculation-source-sha256.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(output,end='')


if __name__=='__main__':main()
