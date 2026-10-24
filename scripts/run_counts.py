"""One fresh worker process for a complete MapReduce or DuckDB run."""
import argparse
import json
from pathlib import Path

import bootstrap
from vacancy_lab.results import write_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('method', choices=['baseline', 'optimized', 'duckdb'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--fail-mapper', action='store_true')
    args = parser.parse_args()
    if args.method == 'duckdb':
        from vacancy_lab.duckdb_engine import run
        counts, metadata = run()
    else:
        from vacancy_lab.mapreduce import run
        counts, metadata = run(args.method, args.fail_mapper)
    write_result(Path(args.output), counts, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
