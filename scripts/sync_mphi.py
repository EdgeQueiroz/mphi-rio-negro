#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
import re
import sys

import requests
from bs4 import BeautifulSoup

import update_mphi as core

TZ = timezone(timedelta(hours=-4))
MONTHS = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3,
    'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7,
    'agosto': 8, 'setembro': 9, 'outubro': 10,
    'novembro': 11, 'dezembro': 12,
}
MONTH_RE = re.compile(
    r'(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+(20\d{2})',
    re.I,
)


def table_period(table):
    for text in table.find_all_previous(string=True, limit=120):
        normalized = ' '.join(str(text).split())
        match = MONTH_RE.search(normalized)
        if match:
            return int(match.group(2)), MONTHS[match.group(1).lower()]
    return None


def parse_table_rows(table, year, month):
    rows = {}
    for tr in table.find_all('tr'):
        cells = [c.get_text(' ', strip=True).replace(',', '.') for c in tr.find_all(['td', 'th'])]
        if len(cells) < 2:
            continue
        try:
            day_match = re.search(r'\d{1,2}', cells[0])
            level_match = re.search(r'\d+(?:\.\d+)?', cells[1])
            if not day_match or not level_match:
                continue
            day = int(day_match.group())
            level = float(level_match.group())
            delta_match = re.search(r'-?\d+(?:\.\d+)?', cells[2]) if len(cells) > 2 else None
            delta = float(delta_match.group()) if delta_match else None
            date = datetime(year, month, day).date().isoformat()
            if 5 <= level <= 35:
                rows[date] = {
                    'date': date,
                    'level': level,
                    'delta_cm': delta,
                    'source': 'Porto de Manaus',
                }
        except (ValueError, TypeError):
            continue
    return [rows[k] for k in sorted(rows)]


def extract_current_month(html, now):
    soup = BeautifulSoup(html, 'html.parser')
    candidates = []
    for table in soup.find_all('table'):
        text = ' '.join(table.stripped_strings)
        if 'Cota' not in text or 'Dia' not in text:
            continue
        if table_period(table) != (now.year, now.month):
            continue
        rows = parse_table_rows(table, now.year, now.month)
        if rows:
            candidates.append(rows)

    if not candidates:
        raise RuntimeError(f'Tabela do mês corrente não encontrada: {now.year:04d}-{now.month:02d}')

    return max(candidates, key=len)


def sync_month(d, source_rows, now):
    by_date = {row['date']: row for row in d.get('series', [])}
    changed = False

    for row in source_rows:
        existing = by_date.get(row['date'])
        if existing is None:
            by_date[row['date']] = row
            changed = True
        else:
            before = (existing.get('level'), existing.get('delta_cm'), existing.get('source'))
            existing.update(row)
            after = (existing.get('level'), existing.get('delta_cm'), existing.get('source'))
            changed = changed or before != after

    series = sorted(by_date.values(), key=lambda x: x['date'])

    month_prefix = f'{now.year:04d}-{now.month:02d}-'
    observed = [x for x in series if x.get('level') is not None]
    for prev, cur in zip(observed, observed[1:]):
        if not cur['date'].startswith(month_prefix):
            continue
        prev_date = datetime.fromisoformat(prev['date']).date()
        cur_date = datetime.fromisoformat(cur['date']).date()
        if (cur_date - prev_date).days == 1 and abs(cur['level'] - prev['level']) > 1.0:
            raise RuntimeError(
                f'Salto anômalo no Porto: {prev["date"]} {prev["level"]} -> '
                f'{cur["date"]} {cur["level"]} m'
            )

    d['series'] = series
    return changed


def main():
    now = datetime.now(TZ)
    d = core.read_json(core.DATA, {})
    ledger = core.read_json(core.LEDGER, {
        'schema': 'mphi-forecast-ledger-v1',
        'policy': 'append-only: campos de previsão são congelados na emissão e não devem ser reescritos',
        'entries': [],
    })

    try:
        response = requests.get(core.URL, timeout=30, headers={'User-Agent': 'MPHI-Uiara/1.1-sync'})
        response.raise_for_status()
        source_rows = extract_current_month(response.text, now)
        latest_source_date = source_rows[-1]['date']
        changed = sync_month(d, source_rows, now)

        # Sem dado novo, correção ou lacuna recuperada: encerra sem tocar nos arquivos.
        if not changed and d.get('current', {}).get('date') == latest_source_date:
            print(f'Sem alteração: Porto e MPHI já estão em {latest_source_date}.')
            return

        core.recalc(d)
        if d['current']['date'] != latest_source_date:
            raise RuntimeError(
                f'Inconsistência após sincronização: fonte={latest_source_date}, MPHI={d["current"]["date"]}'
            )

        d['meta']['source_note'] = (
            'Atualização automática concluída a partir do Porto de Manaus, '
            'com sincronização e recuperação do mês corrente.'
        )

        # Só a previsão realmente emitida na data mais recente é congelada; não há previsão retroativa.
        core.freeze_forecast(d, ledger)
        validation = core.build_validation(d, ledger)

        core.write_json(core.DATA, d)
        core.write_json(core.LEDGER, ledger)
        core.write_json(core.VALIDATION, validation)
        print(
            f'Sincronização concluída: {len(source_rows)} dias do mês; '
            f'última medição {latest_source_date} = {d["current"]["level"]:.2f} m.'
        )
    except Exception as exc:
        # Falha de fonte/parsing não altera a última publicação válida.
        print(f'Falha de sincronização; último estado válido preservado: {exc}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
