"""Audit the teacher's complete CSV, sample JSONs, then upload original bytes."""
import argparse
import csv
import hashlib
import json
import random
import zipfile
from collections import Counter
from datetime import datetime, timezone

import bootstrap
from bootstrap import ROOT
from vacancy_lab.mapreduce import belongs_to_variant, ONE_C
from vacancy_lab.storage import client, read_config


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def audit():
    cfg = read_config()
    source = ROOT / 'data' / cfg['source_filename']
    assert source.stat().st_size == 847619384, 'CSV downloaded incompletely'
    csv.field_size_limit(16 * 1024 * 1024)
    ids = set()
    counts = Counter()
    currencies = Counter()
    skills_histogram = Counter()
    examples = []
    exclusions = []
    for row in csv.DictReader(source.open(encoding='utf-8-sig', newline='')):
        counts['input_rows'] += 1
        key = row['source'] + ':' + row['vacancy_id']
        if key in ids:
            counts['duplicate_ids'] += 1
        ids.add(key)
        if ONE_C.search(row['name']):
            counts['name_mentions_1c'] += 1
        if not belongs_to_variant(row):
            if ONE_C.search(row['name']) and len(exclusions) < 25:
                exclusions.append({k: row[k] for k in ['vacancy_id', 'name', 'role']})
            continue
        counts['selected_vacancies'] += 1
        skills = {s.strip().lower() for s in row['key_skills'].split(';') if s.strip()}
        skills_histogram[len(skills)] += 1
        counts['selected_with_skills'] += bool(skills)
        if row['salary_from'] or row['salary_to']:
            counts['selected_with_salary'] += 1
            currencies[row['currency'] + ';gross=' + row['gross']] += 1
        if len(examples) < 25:
            examples.append({k: row[k] for k in ['vacancy_id', 'name', 'role', 'area']})
    if counts['duplicate_ids']:
        raise RuntimeError(f"Found {counts['duplicate_ids']} duplicate IDs; define deduplication before counting")
    with zipfile.ZipFile(ROOT / 'data' / 'hh.zip') as z:
        members = sorted(name for name in z.namelist() if name.endswith('.json'))
        sample = sorted(random.Random(cfg['random_seed']).sample(members, cfg['json_sample_size']))
        sample_path = ROOT / 'data' / 'hh-sample-1000.jsonl'
        sample_selected = 0
        with sample_path.open('w', encoding='utf-8', newline='\n') as out:
            for name in sample:
                row = json.loads(z.read(name))
                out.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
                roles = {r['name'] for r in row.get('professional_roles', [])}
                if belongs_to_variant({'name': row['name'], 'role': 'Программист, разработчик' if 'Программист, разработчик' in roles else ''}):
                    sample_selected += 1
    result = {
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'source_url': cfg['source_url'],
        'source_bytes': source.stat().st_size,
        'source_sha256': digest(source),
        'variant': cfg['variant_name'],
        'condition': cfg['variant_condition'],
        'counts': dict(counts),
        'salary_flags': dict(currencies),
        'skills_histogram': dict(sorted(skills_histogram.items())),
        'selected_examples': examples,
        'excluded_examples': exclusions,
        'json_zip_sha256': digest(ROOT / 'data' / 'hh.zip'),
        'json_sample': {'source_files': len(members), 'sample_files': len(sample),
                        'seed': cfg['random_seed'], 'variant_vacancies': sample_selected,
                        'bytes': sample_path.stat().st_size, 'sha256': digest(sample_path),
                        'members': sample},
    }
    (ROOT / 'evidence' / 'source-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    concise = {k: v for k, v in result.items() if k not in ['selected_examples', 'excluded_examples', 'json_sample']}
    concise['json_sample'] = {k: v for k, v in result['json_sample'].items() if k != 'members'}
    print(json.dumps(concise, ensure_ascii=False, indent=2), flush=True)


def upload():
    cfg = read_config()
    s3 = client()
    files = [(cfg['source_filename'], cfg['input_key'], 'text/csv'),
             ('hh-sample-1000.jsonl', 'raw/hh-sample-1000.jsonl', 'application/x-ndjson')]
    result = []
    for filename, key, mime in files:
        path = ROOT / 'data' / filename
        checksum = digest(path)
        s3.upload_file(str(path), cfg['bucket'], key,
                       ExtraArgs={'ContentType': mime, 'Metadata': {'sha256': checksum}})
        head = s3.head_object(Bucket=cfg['bucket'], Key=key)
        assert head['ContentLength'] == path.stat().st_size
        assert head['Metadata']['sha256'] == checksum
        result.append({'bucket': cfg['bucket'], 'key': key, 'bytes': head['ContentLength'],
                       'ETag': head['ETag'], 'sha256': checksum,
                       'HTTP': head['ResponseMetadata']['HTTPStatusCode']})
        print(json.dumps(result[-1], ensure_ascii=False), flush=True)
    (ROOT / 'evidence' / 'uploads.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['audit', 'upload'])
    args = parser.parse_args()
    audit() if args.action == 'audit' else upload()
