"""S3 access for the laboratory. Credentials are never written to evidence files."""
from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[2]


def read_config() -> dict:
    return json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))


def credentials() -> tuple[str, str]:
    access = os.environ.get('RUSTFS_ACCESS_KEY')
    secret = os.environ.get('RUSTFS_SECRET_KEY')
    if access and secret:
        return access, secret
    if access or secret:
        raise RuntimeError('Нужно задать оба ключа RUSTFS_ACCESS_KEY и RUSTFS_SECRET_KEY.')
    path = ROOT.parent / 'lab' / '.credentials.json'
    if path.is_file():
        local = json.loads(path.read_text(encoding='utf-8'))
        return local['access'], local['secret']
    raise RuntimeError('Задайте RUSTFS_ACCESS_KEY и RUSTFS_SECRET_KEY в окружении.')


def endpoint_url() -> str:
    return os.environ.get('RUSTFS_ENDPOINT_URL', read_config()['endpoint_url'])


def client():
    access, secret = credentials()
    return boto3.client(
        's3',
        endpoint_url=endpoint_url(),
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=read_config()['region'],
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            retries={'max_attempts': 0},
            connect_timeout=3,
            read_timeout=30,
            request_checksum_calculation='when_required',
            response_checksum_validation='when_required',
        ),
    )


def initialize_bucket() -> dict:
    s3 = client()
    bucket = read_config()['bucket']
    created = False
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response['ResponseMetadata']['HTTPStatusCode'] != 404:
            raise
        s3.create_bucket(Bucket=bucket)
        created = True
    response = s3.head_bucket(Bucket=bucket)
    return {
        'endpoint': endpoint_url(),
        'bucket': bucket,
        'created': created,
        'HTTP': response['ResponseMetadata']['HTTPStatusCode'],
    }


def list_objects() -> dict:
    s3 = client()
    bucket = read_config()['bucket']
    items = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket):
        items.extend({'key': row['Key'], 'bytes': row['Size']} for row in page.get('Contents', []))
    return {'bucket': bucket, 'objects': items, 'count': len(items)}

