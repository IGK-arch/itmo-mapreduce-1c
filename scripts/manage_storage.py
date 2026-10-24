"""Prepare the environment without selecting an unconfirmed individual variant."""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python-packages'))
sys.path.insert(0, str(ROOT / 'src'))
sys.stdout.reconfigure(encoding='utf-8')


def save(name: str, payload: dict) -> None:
    result = {'time_utc': datetime.now(timezone.utc).isoformat(), **payload}
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    (evidence / name).write_text(text, encoding='utf-8')
    print(text, end='', flush=True)


def check() -> dict:
    versions = {}
    for name in ['boto3', 'duckdb', 'psutil']:
        module = importlib.import_module(name)
        versions[name] = module.__version__
    prior_csv = ROOT.parent / 'lab' / 'data' / 'it_vacancy_data.csv'
    columns = []
    if prior_csv.is_file():
        with prior_csv.open(encoding='utf-8-sig', newline='') as stream:
            columns = next(csv.reader(stream))
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    import psutil
    cpu_name = platform.processor()
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu_name = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    return {
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'cpu_name': cpu_name,
        'physical_cpu_cores': psutil.cpu_count(logical=False),
        'logical_cpu_count': psutil.cpu_count(),
        'total_ram_bytes': psutil.virtual_memory().total,
        'versions': versions,
        'previous_csv_columns': columns,
        'previous_csv_has_salary': any('salary' in col.lower() for col in columns),
        'variant_configured': bool(config['variant_condition']),
        'bucket': config['bucket'],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'init-storage', 'list-storage'])
    args = parser.parse_args()
    if args.action == 'check':
        save('environment.json', check())
    else:
        from vacancy_lab.storage import initialize_bucket, list_objects
        if args.action == 'init-storage':
            save('storage-init.json', initialize_bucket())
        else:
            save('storage-list.json', list_objects())


if __name__ == '__main__':
    main()
