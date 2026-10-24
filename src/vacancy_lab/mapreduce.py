"""Own map, shuffle/combiner and reduce over a bounded S3 byte stream."""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import os
import re
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool

from .storage import client, read_config

PROGRAMMER = re.compile(r'программист|разработчик|developer|programmer', re.I)
ONE_C = re.compile(r'1[сc]', re.I)
BITRIX = re.compile(r'битрикс|bitrix', re.I)
JAVA_DEVELOPER = re.compile(r'java[\s-]+developer', re.I)


def belongs_to_variant(row: dict) -> bool:
    """The Python predicate; DuckDB implements its own predicate in SQL."""
    name = row.get('name', '')
    return bool(
        row.get('role') == 'Программист, разработчик'
        and ONE_C.search(name)
        and PROGRAMMER.search(name)
        and not BITRIX.search(name)
        and not JAVA_DEVELOPER.search(name)
    )


class ChunkStream(io.RawIOBase):
    """Bound every body.read; TextIOWrapper handles split UTF-8 and quoted CSV."""
    def __init__(self, body, chunk_bytes):
        super().__init__()
        self.body, self.chunk_bytes = body, chunk_bytes
        self.bytes_read = self.read_calls = self.max_read = 0
        self.digest = hashlib.sha256()
        self.cache = b''
        self.offset = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.offset == len(self.cache):
            self.cache = self.body.read(self.chunk_bytes)
            self.offset = 0
            if not self.cache:
                return 0
            self.bytes_read += len(self.cache)
            self.read_calls += 1
            self.max_read = max(self.max_read, len(self.cache))
            self.digest.update(self.cache)
        length = min(len(buffer), len(self.cache) - self.offset)
        buffer[:length] = memoryview(self.cache)[self.offset:self.offset + length]
        self.offset += length
        return length


def map_batch(rows, mode, crash=False):
    if crash:
        os._exit(73)  # A real mapper process exit, only in the explicit fault test.
    counts = Counter() if mode == 'optimized' else []
    histogram = Counter()
    selected = []
    emitted = Counter()
    for row in rows:
        if not belongs_to_variant(row):
            continue
        selected.append(row['source'] + ':' + row['vacancy_id'])
        skills = sorted({s.strip().lower() for s in row.get('key_skills', '').split(';') if s.strip()})
        histogram[len(skills)] += 1
        for size in (1, 2, 3):
            combinations = [(size, *combo) for combo in itertools.combinations(skills, size)]
            emitted[size] += len(combinations)
            if mode == 'optimized':
                counts.update(combinations)
            else:
                counts.extend(combinations)
    return counts, histogram, selected, emitted


def run(mode='optimized', inject_failure=False):
    cfg = read_config()
    if not cfg['variant_condition']:
        raise RuntimeError('Не указан индивидуальный вариант.')
    start = time.perf_counter()
    response = client().get_object(Bucket=cfg['bucket'], Key=cfg['input_key'])
    body = response['Body']
    raw = ChunkStream(body, cfg['chunk_bytes'])
    csv.field_size_limit(16 * 1024 * 1024)
    text = io.TextIOWrapper(io.BufferedReader(raw, buffer_size=cfg['chunk_bytes']), encoding='utf-8-sig', newline='')
    reader = csv.DictReader(text)
    pool = ProcessPoolExecutor(max_workers=cfg['workers'])
    pending = {}
    combined = Counter()
    materialized = []
    histogram = Counter()
    emitted = Counter()
    identities = []
    committed = set()
    batch_id = rows_read = 0
    failures = []

    def submit(identifier, batch, attempt=0):
        future = pool.submit(map_batch, batch, mode, inject_failure and identifier == 1 and attempt == 0)
        pending[future] = (identifier, batch, attempt)

    def finish_some():
        nonlocal pool
        done, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            identifier, batch, attempt = pending[future]
            try:
                counts, hist, ids, emitted_counts = future.result()
            except BrokenProcessPool:
                if not inject_failure or failures:
                    raise
                retry_batches = list(pending.values())
                failures.append({'type': 'mapper_process_exit', 'exit_code': 73,
                                 'uncommitted_batches_replayed': len(retry_batches)})
                pending.clear()
                pool.shutdown(wait=True, cancel_futures=True)
                pool = ProcessPoolExecutor(max_workers=cfg['workers'])
                for old_identifier, old_batch, old_attempt in retry_batches:
                    submit(old_identifier, old_batch, old_attempt + 1)
                return
            pending.pop(future)
            if identifier in committed:
                raise RuntimeError('Попытка повторно учесть уже зафиксированный батч.')
            committed.add(identifier)
            if mode == 'optimized':
                combined.update(counts)
            else:
                materialized.extend(counts)
            histogram.update(hist)
            emitted.update(emitted_counts)
            identities.extend(ids)

    try:
        while True:
            batch = list(itertools.islice(reader, cfg['batch_rows']))
            if not batch:
                break
            rows_read += len(batch)
            if mode == 'optimized':
                fields = ('source', 'vacancy_id', 'name', 'role', 'key_skills')
                batch = [{key: row[key] for key in fields} for row in batch]
            submit(batch_id, batch)
            batch_id += 1
            # Resolve the deliberately failing task before adding new tasks to a
            # potentially broken pool. Normal benchmark scheduling is unaffected.
            while inject_failure and not failures and pending:
                finish_some()
            while len(pending) >= 2 * cfg['workers']:
                finish_some()
        while pending:
            finish_some()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        text.close()
        body.close()
    if mode == 'baseline':
        combined.update(materialized)
    if len(identities) != len(set(identities)):
        raise RuntimeError('Обнаружены повторные вакансии: нужно явно определить правило дедупликации.')
    identity_hash = hashlib.sha256('\n'.join(sorted(identities)).encode()).hexdigest()
    return combined, {
        'method': 'mapreduce_' + mode,
        'compute_seconds': time.perf_counter() - start,
        'input_uri': f"s3://{cfg['bucket']}/{cfg['input_key']}",
        'input_etag': response['ETag'],
        'input_bytes': raw.bytes_read,
        'input_sha256': raw.digest.hexdigest(),
        'body_read_calls': raw.read_calls,
        'largest_body_read_bytes': raw.max_read,
        'rows_read': rows_read,
        'selected_vacancies': len(identities),
        'selected_ids_sha256': identity_hash,
        'skills_histogram': dict(sorted(histogram.items())),
        'emitted_by_stack_size': dict(sorted(emitted.items())),
        'batches': batch_id,
        'committed_batches': len(committed),
        'workers': cfg['workers'],
        'failures': failures,
    }

