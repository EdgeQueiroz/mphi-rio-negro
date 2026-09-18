#!/usr/bin/env python3
"""Mantém uma execução do GitHub acordada até o Porto publicar o dia."""

import argparse
from datetime import datetime, timedelta, timezone
import time

import sync_mphi as sync


TZ = timezone(timedelta(hours=-4))


def probe(now=None):
    now = now or datetime.now(TZ)
    rows = sync.extract_recent_months(sync.fetch_source(), now)
    latest = rows[-1]['date']
    return latest == now.date().isoformat(), latest


def before_cutoff(now, hour, minute):
    cutoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now < cutoff


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=300)
    parser.add_argument('--cutoff', default='12:15')
    args = parser.parse_args()
    cutoff_hour, cutoff_minute = (int(part) for part in args.cutoff.split(':', 1))
    attempt = 0

    while True:
        attempt += 1
        now = datetime.now(TZ)
        try:
            ready, latest = probe(now)
            print(
                f'Tentativa {attempt}: Porto em {latest}; '
                f'hoje é {now.date().isoformat()}.',
                flush=True,
            )
            if ready:
                print('Medição do dia encontrada; liberando sincronização.', flush=True)
                return
        except Exception as exc:
            print(f'Tentativa {attempt}: fonte indisponível ({type(exc).__name__}).', flush=True)

        if not before_cutoff(now, cutoff_hour, cutoff_minute):
            print('Janela de vigília encerrada; o fluxo fará uma última sincronização.', flush=True)
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()

