#!/usr/bin/env python3
"""Mantém uma execução do GitHub acordada até o Porto publicar o dia."""

import argparse
from datetime import datetime, timedelta, timezone
import time

import sync_mphi as sync


TZ = timezone(timedelta(hours=-4))


def sync_today(now=None):
    now = now or datetime.now(TZ)
    # A consulta só é considerada pronta quando o dado já entrou no MPHI.
    # Isso evita liberar o fluxo após uma leitura pontual que a coleta seguinte
    # poderia não reproduzir por causa de caches intermediários da fonte.
    sync.main()
    latest = sync.core.read_json(sync.core.DATA, {}).get('current', {}).get('date')
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
            ready, latest = sync_today(now)
            print(
                f'Tentativa {attempt}: MPHI em {latest}; '
                f'hoje é {now.date().isoformat()}.',
                flush=True,
            )
            if ready:
                print('Medição do dia sincronizada; liberando publicação.', flush=True)
                return
        except (Exception, SystemExit) as exc:
            print(f'Tentativa {attempt}: fonte indisponível ({type(exc).__name__}).', flush=True)

        if not before_cutoff(now, cutoff_hour, cutoff_minute):
            print('Janela de vigília encerrada; o fluxo fará uma última sincronização.', flush=True)
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
