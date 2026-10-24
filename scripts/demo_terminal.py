"""Run the real S3 calculations and print a compact terminal transcript."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

import bootstrap
from bootstrap import ROOT
from vacancy_lab.results import read_result
from vacancy_lab.storage import client, read_config


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def compute():
    cfg=read_config()
    print('VARIANT 1: Программист, разработчик на 1С',flush=True)
    print(f"Input: s3://{cfg['bucket']}/{cfg['input_key']}",flush=True)
    for method,label in [('optimized','terminal-mapreduce'),('duckdb','terminal-duckdb')]:
        print(f'\npython scripts/run_counts.py {method} --output results/{label}',flush=True)
        args=[sys.executable,str(ROOT/'scripts'/'run_counts.py'),method,
              '--output',str(ROOT/'results'/label)]
        with (ROOT/'evidence'/f'{label}.log').open('w',encoding='utf-8') as stream:
            subprocess.run(args,stdout=stream,stderr=subprocess.STDOUT,check=True)
        meta=read(f'results/{label}/metadata.json')
        assert meta['selected_vacancies']==18164
        print(f"Selected: {meta['selected_vacancies']}",flush=True)
        if method=='optimized':
            assert meta['input_sha256']==read('evidence/source-audit.json')['source_sha256']
            assert meta['largest_body_read_bytes']==1048576
            print(f"S3: {meta['rows_read']} rows; {meta['input_bytes']} bytes; {meta['body_read_calls']} reads",flush=True)
            print('Maximum S3 read size: 1 MiB',flush=True)
        print('k    total combinations    unique combinations',flush=True)
        for k in (1,2,3):
            print(f"{k}    {meta['emitted_by_stack_size'][str(k)]:>18}    {meta['unique_by_stack_size'][str(k)]:>19}",flush=True)
        print('Completed successfully.',flush=True)


def verify():
    cfg=read_config()
    print('Full MapReduce / DuckDB comparison',flush=True)
    mr=read_result(ROOT/'results'/'terminal-mapreduce')
    sql=read_result(ROOT/'results'/'terminal-duckdb')
    reference=read_result(ROOT/'results'/'optimized-1')
    assert mr==sql==reference
    a=read('results/terminal-mapreduce/metadata.json')
    b=read('results/terminal-duckdb/metadata.json')
    assert a['selected_ids_sha256']==b['selected_ids_sha256']
    print(f"Selected: {a['selected_vacancies']}; selected IDs: identical",flush=True)
    comparisons=[]
    for k in (1,2,3):
        keys={key for key in mr.keys()|sql.keys() if key[0]==k}
        different=sum(mr.get(key)!=sql.get(key) for key in keys)
        assert different==0
        print(f'k={k}: {len(keys)} keys checked; differences={different}',flush=True)
        comparisons.append({'stack_size':k,'checked_keys':len(keys),'different_keys':different})
    print('\nS3: full readback of the six stored results',flush=True)
    stored=[]
    s3=client()
    for method in ('mapreduce','duckdb'):
        for k in (1,2,3):
            key=f'results/variant-01/{method}/skills_{k}.csv'
            response=s3.get_object(Bucket=cfg['bucket'],Key=key)
            try:
                content=response['Body'].read()
            finally:
                response['Body'].close()
            expected=(ROOT/'results'/'terminal-mapreduce'/f'skills_{k}.csv').read_bytes()
            assert content==expected
            print(f'{method}/skills_{k}.csv: {len(content)} bytes; SHA-256 matches',flush=True)
            stored.append({'key':key,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'readback_matches':True})
    result={'time_utc':datetime.now(timezone.utc).isoformat(),'selected_vacancies':a['selected_vacancies'],
            'all_equal':True,'comparisons':comparisons,'results_in_s3':stored}
    (ROOT/'evidence'/'terminal-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('\nALL CHECKS PASSED',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['compute','verify'])
    action=parser.parse_args().action
    marker=ROOT/'tmp'/f'terminal-{action}-ready.json'
    marker.write_text('{"completed":false}\n',encoding='utf-8')
    compute() if action=='compute' else verify()
    marker.write_text('{"completed":true}\n',encoding='utf-8')


if __name__=='__main__':main()
