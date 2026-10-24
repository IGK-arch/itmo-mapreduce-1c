"""At least three isolated runs per method; sample total target process-tree RSS."""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

import bootstrap
from bootstrap import ROOT
import psutil


def measure(method, trial, fail_mapper=False):
    label = f'{method}-{trial}' if not fail_mapper else 'mapper-failure'
    out = ROOT / 'results' / label
    logpath = ROOT / 'evidence' / (label + '.log')
    args = [sys.executable, str(ROOT / 'scripts' / 'run_counts.py'), method, '--output', str(out)]
    if fail_mapper:
        args.append('--fail-mapper')
    env = dict(os.environ, PYTHONUTF8='1')
    start = time.perf_counter()
    peak_rss = peak_children = samples = 0
    with logpath.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        target = psutil.Process(process.pid)
        while process.poll() is None:
            rss = 0
            try:
                children = target.children(recursive=True)
                peak_children = max(peak_children, len(children))
                for item in [target, *children]:
                    try:
                        rss += item.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except psutil.NoSuchProcess:
                pass
            peak_rss = max(peak_rss, rss)
            samples += 1
            time.sleep(0.005)
    result = {'method': method, 'trial': trial, 'label': label,
              'time_utc': datetime.now(timezone.utc).isoformat(),
              'wall_seconds': time.perf_counter() - start,
              'peak_process_tree_rss_bytes': peak_rss,
              'sampling_interval_seconds': 0.005, 'memory_samples': samples,
              'maximum_children': peak_children, 'exit_code': process.returncode}
    (ROOT / 'evidence' / (label + '-profile.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    if process.returncode != 0:
        raise RuntimeError(f'{label} failed; inspect {logpath.name}')
    metadata = json.loads((out / 'metadata.json').read_text(encoding='utf-8'))
    result['compute_seconds'] = metadata['compute_seconds']
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--fault-only', action='store_true')
    args = parser.parse_args()
    if args.fault_only:
        measure('optimized', 1, fail_mapper=True)
        return
    if args.repeats < 3:
        raise ValueError('Для итогового профилирования нужно не менее трёх запусков.')
    results = []
    # Rotate the order to avoid always giving one engine the warmest cache.
    methods = ['baseline', 'optimized', 'duckdb']
    for trial in range(1, args.repeats + 1):
        offset = (trial - 1) % len(methods)
        for method in methods[offset:] + methods[:offset]:
            results.append(measure(method, trial))
        (ROOT / 'evidence' / 'benchmark-runs.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    summary = {}
    for method in methods:
        rows = [r for r in results if r['method'] == method]
        summary[method] = {
            'runs': len(rows),
            'median_wall_seconds': statistics.median(r['wall_seconds'] for r in rows),
            'min_wall_seconds': min(r['wall_seconds'] for r in rows),
            'max_wall_seconds': max(r['wall_seconds'] for r in rows),
            'median_peak_rss_mib': statistics.median(r['peak_process_tree_rss_bytes'] / 1048576 for r in rows),
            'maximum_peak_rss_mib': max(r['peak_process_tree_rss_bytes'] / 1048576 for r in rows),
        }
    (ROOT / 'evidence' / 'benchmark-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()

