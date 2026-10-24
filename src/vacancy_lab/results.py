"""Stable, lossless serialization of complete frequency tables."""
import csv
import hashlib
import json
from pathlib import Path


def write_result(directory, counts, metadata):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for size in (1, 2, 3):
        with (out / f'skills_{size}.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow([f'skill_{i}' for i in range(1, size + 1)] + ['count'])
            writer.writerows([*key[1:], counts[key]] for key in sorted(counts) if key[0] == size)
    metadata['unique_by_stack_size'] = {str(k): sum(key[0] == k for key in counts) for k in (1, 2, 3)}
    metadata['results_sha256'] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('skills_*.csv'))
    }
    (out / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_result(directory):
    counts = {}
    for size in (1, 2, 3):
        with (Path(directory) / f'skills_{size}.csv').open(encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                key = (size, *(row[f'skill_{i}'] for i in range(1, size + 1)))
                if key in counts:
                    raise RuntimeError(f'Повторный ключ {key}')
                counts[key] = int(row['count'])
    return counts

