"""Compare every combination and the exact selected-ID set hash, not just top N."""
import json
import math
from collections import Counter

import bootstrap
from bootstrap import ROOT
from vacancy_lab.results import read_result
from vacancy_lab.storage import client, read_config


def main():
    reference_path = ROOT / 'results' / 'duckdb-1'
    reference = read_result(reference_path)
    expected_meta = json.loads((reference_path / 'metadata.json').read_text(encoding='utf-8'))
    audit = json.loads((ROOT / 'evidence' / 'source-audit.json').read_text(encoding='utf-8'))
    comparisons = []
    for directory in sorted((ROOT / 'results').iterdir()):
        if not (directory / 'metadata.json').is_file():
            continue
        actual = read_result(directory)
        meta = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
        differing = sum(actual.get(key, 0) != reference.get(key, 0) for key in set(actual) | set(reference))
        assert differing == 0, (directory.name, differing)
        for field in ['selected_vacancies', 'selected_ids_sha256', 'skills_histogram', 'emitted_by_stack_size']:
            assert meta[field] == expected_meta[field], (directory.name, field)
        if meta['method'].startswith('mapreduce'):
            assert meta['input_sha256'] == audit['source_sha256']
            assert meta['input_bytes'] == audit['source_bytes']
            assert meta['rows_read'] == audit['counts']['input_rows']
            assert meta['largest_body_read_bytes'] <= read_config()['chunk_bytes']
            assert meta['committed_batches'] == meta['batches']
        comparisons.append({'run': directory.name, 'different_keys': differing,
                            'selected_ids_match': True, 'result_sha256': meta['results_sha256']})
    growth = []
    for size in (1, 2, 3):
        total = sum(n for key, n in reference.items() if key[0] == size)
        expected = sum(math.comb(int(n), size) * jobs for n, jobs in expected_meta['skills_histogram'].items() if int(n) >= size)
        assert total == expected
        growth.append({'stack_size': size, 'emitted_combinations': total,
                       'unique_combinations': sum(key[0] == size for key in reference),
                       'sum_choose_n_k': expected})
    fault_path = ROOT / 'results' / 'mapper-failure' / 'metadata.json'
    assert fault_path.is_file(), 'The mapper failure test has not been run'
    fault = json.loads(fault_path.read_text(encoding='utf-8'))
    assert fault['failures'] and fault['failures'][0]['exit_code'] == 73
    cfg = read_config()
    s3 = client()
    stored = []
    for method, source in [('mapreduce', 'optimized-1'), ('duckdb', 'duckdb-1')]:
        for size in (1, 2, 3):
            path = ROOT / 'results' / source / f'skills_{size}.csv'
            key = f'results/variant-01/{method}/{path.name}'
            content = path.read_bytes()
            s3.put_object(Bucket=cfg['bucket'], Key=key, Body=content, ContentType='text/csv; charset=utf-8')
            body = s3.get_object(Bucket=cfg['bucket'], Key=key)['Body']
            try:
                assert body.read() == content
            finally:
                body.close()
            stored.append({'key': key, 'bytes': len(content), 'readback_matches': True})
    result = {'all_equal': True, 'compared_runs': len(comparisons), 'comparisons': comparisons,
              'selected_vacancies': expected_meta['selected_vacancies'], 'growth': growth,
              'mapper_failure_recovered': True, 'results_in_s3': stored}
    (ROOT / 'evidence' / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'comparisons'}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
