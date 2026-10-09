#!/usr/bin/env python3
"""Decide and verify Pages publication without importing or changing any model."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
PAGE_URL = 'https://edgequeiroz.github.io/mphi-rio-negro/'
MANAUS = timezone(timedelta(hours=-4))
FILES = (
    'latest.json', 'forecast_ledger.json', 'validation.json', 'status.json',
    'basin_signals.json', 'hydrologic_latest.json', 'hydrologic_ledger.json',
)


def load_expected(folder):
    return {name: json.loads((Path(folder) / name).read_text()) for name in FILES}


def status_matches(expected, published, now):
    if expected == published:
        return True
    # Once today's measurement is public, a later successful check alone
    # does not warrant redeployment. Error/waiting states remain strict.
    today = now.astimezone(MANAUS).date().isoformat()
    if expected.get('state') != 'current' or expected.get('observation_date') != today:
        return False
    if {k: v for k, v in expected.items() if k != 'checked_at'} != {
        k: v for k, v in published.items() if k != 'checked_at'
    }:
        return False
    try:
        checked = datetime.fromisoformat(published['checked_at'])
        return (checked.tzinfo is not None
                and checked.astimezone(MANAUS).date().isoformat() == today
                and checked <= now + timedelta(minutes=5))
    except (KeyError, TypeError, ValueError):
        return False


def check_published(expected, page_url=PAGE_URL, session=None, now=None):
    """Check every model/ledger byte represented by JSON; relax only check time."""
    now = now or datetime.now(timezone.utc)
    session = session or requests.Session()
    for name in FILES:
        response = session.get(
            page_url.rstrip('/') + '/data/' + name,
            params={'verify': str(time.time_ns())},
            headers={'Cache-Control': 'no-cache, no-store, max-age=0'},
            timeout=(5, 15),
        )
        response.raise_for_status()
        published = response.json()
        matches = (status_matches(expected[name], published, now) if name == 'status.json'
                   else published == expected[name])
        if not matches:
            raise ValueError(f'{name}: publicação difere dos dados esperados')


def publication_needed(expected, page_url=PAGE_URL, session=None, now=None, force=False):
    if force:
        return True, 'Publicação solicitada por alteração do projeto ou recuperação explícita.'
    try:
        check_published(expected, page_url, session, now)
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        return True, f'Publicação necessária: {type(exc).__name__}.'
    return False, 'Dados já conferidos no site público; nenhuma republicação necessária.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('decide', 'verify'))
    parser.add_argument('--folder', type=Path, default=ROOT / 'docs' / 'data')
    parser.add_argument('--page-url', default=os.environ.get('PAGE_URL') or PAGE_URL)
    args = parser.parse_args()
    expected = load_expected(args.folder)
    if args.command == 'decide':
        publish, message = publication_needed(
            expected, args.page_url,
            force=os.environ.get('PUBLICATION_FORCE', '').lower() == 'true',
        )
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write(f'publish={str(publish).lower()}\n')
        print(message)
    else:
        for attempt in range(1, 9):
            try:
                check_published(expected, args.page_url)
                current = expected['latest.json']['current']
                message = (f'Publicação verificada: {current["date"]} = {current["level"]:.2f} m; '
                           'ledgers e validação conferidos.')
                print(message)
                break
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                if attempt == 8:
                    raise SystemExit(f'Falha na verificação pública: {exc}')
                print(f'Aguardando propagação do Pages ({attempt}/8): {exc}')
                time.sleep(5)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(message + '\n')


if __name__ == '__main__':
    main()
