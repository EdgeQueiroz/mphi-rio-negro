#!/usr/bin/env python3
"""Choose an available weather provider without importing or changing the MPHI model."""
import os
from pathlib import Path
from update_weather import DATA_DIR, SOURCE as CLIMATEMPO_SOURCE, read
from update_weather import update as climatempo
from update_met import update as met_norway


def collect(folder=None, env=None, now=None):
    env = os.environ if env is None else env
    kwargs = {} if folder is None else {'folder': folder}
    if now is not None:
        kwargs['now'] = now
    if env.get('CLIMATEMPO_TOKEN', '').strip():
        result = climatempo(env=env, **kwargs)
        # A partial response can be used only when both existing sections
        # already belong to Climatempo; otherwise use a complete MET snapshot.
        location = Path(folder or DATA_DIR)
        latest = read(location / 'weather_latest.json', {})
        if result['state'] == 'ok' or (result['state'] == 'partial' and latest.get('source') == CLIMATEMPO_SOURCE):
            return result
    return met_norway(**kwargs)


if __name__ == '__main__':
    try:
        print('Meteorologia:', collect()['state'])
    except Exception:
        print('Meteorologia: falha interna; último arquivo válido preservado.')
        raise SystemExit(1)
