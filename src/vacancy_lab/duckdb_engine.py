"""Direct S3 CSV reads and independently written SQL for the same variant."""
from __future__ import annotations

import hashlib
import time
from collections import Counter
from urllib.parse import urlparse

import duckdb

from .storage import ROOT, credentials, endpoint_url, read_config


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def connect(install=False):
    cfg = read_config()
    con = duckdb.connect()
    con.execute(f"SET threads={int(cfg['workers'])}")
    con.execute("SET memory_limit='2GB'")
    if install:
        con.execute('INSTALL httpfs')
    con.execute('LOAD httpfs')
    access, secret = credentials()
    url = urlparse(endpoint_url())
    con.execute('CREATE OR REPLACE SECRET lab_s3 (TYPE s3, '
                f"KEY_ID {quote(access)}, SECRET {quote(secret)}, REGION {quote(cfg['region'])}, "
                f"ENDPOINT {quote(url.netloc)}, URL_STYLE 'path', USE_SSL {str(url.scheme=='https').lower()}, "
                f"SCOPE {quote('s3://' + cfg['bucket'])})")
    return con


def load_selected(con):
    cfg = read_config()
    uri = f"s3://{cfg['bucket']}/{cfg['input_key']}"
    sql = (ROOT / 'sql' / 'selected.sql').read_text(encoding='utf-8')
    con.execute(sql, {'input_uri': uri})
    con.execute((ROOT / 'sql' / 'combinations.sql').read_text(encoding='utf-8'))
    return uri


def run():
    start = time.perf_counter()
    con = connect()
    uri = load_selected(con)
    rows = con.execute('SELECT stack_size,skill_1,skill_2,skill_3,count(*) '
                       'FROM combinations GROUP BY ALL').fetchall()
    counts = Counter({(k, *[a, b, c][:k]): n for k, a, b, c, n in rows})
    ids = sorted(x[0] for x in con.execute('SELECT vacancy_key FROM selected').fetchall())
    if len(ids) != len(set(ids)):
        raise RuntimeError('В SQL-выборке есть дубли vacancy_key.')
    histogram = dict(con.execute('SELECT len(skills),count(*) FROM selected GROUP BY 1 ORDER BY 1').fetchall())
    emitted = dict(con.execute('SELECT stack_size,count(*) FROM combinations GROUP BY 1 ORDER BY 1').fetchall())
    metadata = {
        'method': 'duckdb',
        'compute_seconds': time.perf_counter() - start,
        'input_uri': uri,
        'selected_vacancies': len(ids),
        'selected_ids_sha256': hashlib.sha256('\n'.join(ids).encode()).hexdigest(),
        'skills_histogram': histogram,
        'emitted_by_stack_size': emitted,
        'duckdb_version': duckdb.__version__,
        'threads': read_config()['workers'],
    }
    con.close()
    return counts, metadata

