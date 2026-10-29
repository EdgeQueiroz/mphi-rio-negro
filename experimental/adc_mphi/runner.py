"""MPHI -> ADC experimental read-only learning adapter.

Reads frozen forecasts and observed levels, never rewrites MPHI state. Stdlib only.
The emitted analytics report is NOT an ADC append-only ledger or a Gauntlet promotion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
from zoneinfo import ZoneInfo

HORIZONS = (7, 15, 30)
REPO_MODELS = ('MPHI v1.0', 'MPHI v1.1-shadow', 'MPHI v2.0-hydrologic-alpha')
CONTROL = 'PERSISTENCE-ADC'
VERSION = 'ADC-MPHI-READONLY-v0.1'
TZ = ZoneInfo('America/Manaus')
INPUTS = {
    'observations': 'docs/data/latest.json',
    'forecasts': 'docs/data/forecast_ledger.json',
    'hydrologic': 'docs/data/hydrologic_ledger.json',
}


def read_inputs(repo_root: Path):
    data, proofs = {}, {}
    for name, relative in INPUTS.items():
        raw = (repo_root / relative).read_bytes()
        data[name] = json.loads(raw)
        proofs[name] = {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest()}
    return data, proofs


def number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{field} deve ser número finito')
    return float(value)


def load_observations(obj, as_of):
    measured = {}
    for item in obj.get('series', []):
        date = dt.date.fromisoformat(item['date'])
        if date > as_of or item.get('level') is None:
            continue
        if item.get('source') != 'Porto de Manaus':
            continue
        value = number(item['level'], 'level')
        if date in measured and measured[date] != value:
            raise ValueError(f'Cotas contraditórias para {date}')
        measured[date] = value
    return measured


def forecast_records(data, as_of):
    """Source forecast date is a recorded assertion; not independent proof of issue time."""
    result, seen = [], set()
    ledgers = [data['forecasts'], data['hydrologic']]
    for ledger in ledgers:
        for entry in ledger.get('entries', []):
            model = entry.get('model_version')
            if model not in REPO_MODELS:
                continue
            issue = dt.date.fromisoformat(entry['forecast_date'])
            created = dt.datetime.fromisoformat(entry['created_at'])
            if created.tzinfo is None:
                raise ValueError('Previsão sem timezone verificável')
            if created.astimezone(TZ).date() != issue:
                raise ValueError(f'Data de emissão incompatível: {entry.get("forecast_id")}')
            if issue > as_of:
                continue
            issue_level = number(entry['observed_level_at_issue'], 'observed_level_at_issue')
            for horizon in HORIZONS:
                payload = entry.get('projections', {}).get(str(horizon))
                if not payload:
                    continue
                target = dt.date.fromisoformat(payload['target_date'])
                if target != issue + dt.timedelta(days=horizon):
                    raise ValueError(f'Horizonte inconsistente: {entry.get("forecast_id")}')
                key = (issue, horizon, model)
                if key in seen:
                    raise ValueError(f'Previsão duplicada: {key}')
                seen.add(key)
                row = {
                    'forecast_id': entry['forecast_id'], 'issued_on': issue,
                    'target_on': target, 'horizon': horizon,
                    'model': model, 'predicted_m': number(payload['central'], 'central'),
                    'issued_at': created.isoformat(),
                }
                result.append(row)
                if model == 'MPHI v1.0':
                    result.append({**row, 'forecast_id': f'{issue}|{CONTROL}',
                                   'model': CONTROL, 'predicted_m': issue_level,
                                   'source_note': 'Controle ingênuo de persistência calculado pela ADC'})
    return result


def evaluate(forecasts, observations, as_of):
    results, pending, missing = [], [], []
    for row in forecasts:
        target = row['target_on']
        view = {k: v.isoformat() if isinstance(v, dt.date) else v for k, v in row.items()}
        if target > as_of:
            pending.append(view)
        elif target not in observations:
            missing.append(view)
        else:
            error = observations[target] - row['predicted_m']
            results.append({**view, 'observed_m': observations[target],
                            'signed_error_m': round(error, 6),
                            'absolute_error_m': round(abs(error), 6)})
    return results, pending, missing


def metrics(rows):
    if not rows:
        return {'n': 0, 'mae_m': None, 'bias_m': None, 'rmse_m': None}
    errs = [r['signed_error_m'] for r in rows]
    return {'n': len(errs), 'mae_m': round(statistics.mean(map(abs, errs)), 4),
            'bias_m': round(statistics.mean(errs), 4),
            'rmse_m': round(math.sqrt(statistics.mean(e * e for e in errs)), 4)}


def comparison(rows, model, reference, horizon):
    a = {(r['issued_on'], r['target_on']): r for r in rows
         if r['model'] == model and r['horizon'] == horizon}
    b = {(r['issued_on'], r['target_on']): r for r in rows
         if r['model'] == reference and r['horizon'] == horizon}
    keys = sorted(set(a) & set(b))
    a_rows, b_rows = [a[k] for k in keys], [b[k] for k in keys]
    left, right = metrics(a_rows), metrics(b_rows)
    return {'model': model, 'reference': reference, 'horizon_days': horizon,
            'n_paired': len(keys), 'model_mae_m': left['mae_m'],
            'reference_mae_m': right['mae_m'],
            'mae_delta_m': (round(left['mae_m'] - right['mae_m'], 4) if keys else None),
            'model_wins': sum(a[k]['absolute_error_m'] < b[k]['absolute_error_m'] for k in keys),
            'reference_wins': sum(a[k]['absolute_error_m'] > b[k]['absolute_error_m'] for k in keys),
            'ties': sum(a[k]['absolute_error_m'] == b[k]['absolute_error_m'] for k in keys),
            'interpretation': 'amostra exploratória; nenhuma promoção ou recalibração automática'}


def build_report(data, proofs, as_of):
    observations = load_observations(data['observations'], as_of)
    forecasts = forecast_records(data, as_of)
    evaluated, pending, missing = evaluate(forecasts, observations, as_of)
    model_metrics = []
    for model in (*REPO_MODELS, CONTROL):
        for horizon in HORIZONS:
            model_metrics.append({'model': model, 'horizon_days': horizon,
                                  **metrics([r for r in evaluated if r['model'] == model and r['horizon'] == horizon])})
    pairs = []
    for model in REPO_MODELS:
        for horizon in HORIZONS:
            if model != 'MPHI v1.0':
                pairs.append(comparison(evaluated, model, 'MPHI v1.0', horizon))
            pairs.append(comparison(evaluated, model, CONTROL, horizon))
    next_due = sorted(set(p['target_on'] for p in pending))[:10]
    latest = max(observations) if observations else None
    return {
        'schema': 'adc-mphi-learning-report-v1', 'adapter_version': VERSION,
        'date_manaus': as_of.isoformat(), 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'mode': 'READ_ONLY_NO_MPHI_WRITE', 'model_selection': 'MPHI v1.0 permanece oficial',
        'baseline_modified': False, 'decision_ledger_written': False,
        'source_hashes': proofs,
        'observation_latest_date': latest.isoformat() if latest else None,
        'observation_latest_m': observations[latest] if latest else None,
        'stale_observation': latest is None or (as_of - latest).days > 0,
        'forecast_count': len(forecasts), 'evaluated_count': len(evaluated),
        'pending_count': len(pending), 'missing_observations_count': len(missing),
        'missing_target_dates': sorted(set(p['target_on'] for p in missing)),
        'next_due_dates': next_due,
        'metrics': model_metrics, 'paired_comparisons': pairs,
        'warnings': [
            'Histórico do repositório não prova emissão contemporânea ou custódia independente.',
            'Métricas são descritivas e têm forte sobreposição temporal entre previsões.',
            'Comparar MAE entre versões exige pares da mesma data de emissão, alvo e horizonte.',
            'Controle de persistência é gerado pela ADC; não é uma versão do MPHI.',
            'Este relatório não é um ledger ADC append-only nem validação pelo Gauntlet.',
            'Nenhum ajuste de parâmetros, modelo Stable ou fluxo operacional é autorizado por este relatório.',
        ],
        'learning_candidates': [
            {'model': m['model'], 'horizon_days': m['horizon_days'],
             'observation': 'Viés persistente a investigar', 'status': 'HIPOTESE_SEM_AUTORIZACAO',
             'bias_m': m['bias_m']}
            for m in model_metrics
            if m['n'] >= 15 and m['bias_m'] is not None and abs(m['bias_m']) >= 0.2
        ],
    }


def render_markdown(report):
    lines = [f'# ADC × MPHI — Aprendizagem diária ({report["date_manaus"]})', '',
             '**Status:** experimental, somente leitura; nenhuma mudança em MPHI v1.0.','',
             f'**Última cota observada:** {report["observation_latest_m"]} m em {report["observation_latest_date"]}.',
             f'**Previsões avaliadas:** {report["evaluated_count"]}; pendentes: {report["pending_count"]}; alvos sem leitura: {report["missing_observations_count"]}.',
             '', '## Erros por modelo e horizonte', '',
             '| Modelo | Dias | N | MAE (m) | Viés (m) | RMSE (m) |',
             '|---|---:|---:|---:|---:|---:|']
    def v(value):
        return '—' if value is None else f'{value:.3f}'
    for m in report['metrics']:
        lines.append(f'| {m["model"]} | {m["horizon_days"]} | {m["n"]} | {v(m["mae_m"])} | {v(m["bias_m"])} | {v(m["rmse_m"])} |')
    lines += ['', '## Comparações emparelhadas', '',
              '| Modelo | Referência | Dias | N pares | Δ MAE (m) |',
              '|---|---|---:|---:|---:|']
    for p in report['paired_comparisons']:
        lines.append(f'| {p["model"]} | {p["reference"]} | {p["horizon_days"]} | {p["n_paired"]} | {v(p["mae_delta_m"])} |')
    lines += ['', 'Δ MAE = MAE do modelo menos MAE da referência (negativo = menor erro nesta amostra).',
              '', '## Hipóteses para investigação (sem aplicação automática)', '']
    for c in report['learning_candidates']:
        lines.append(f'- {c["model"]}, {c["horizon_days"]} dias: viés observado {c["bias_m"]:+.3f} m; estudar causa e validação fora da amostra.')
    if not report['learning_candidates']:
        lines.append('- Nenhum gatilho descritivo alcançado nesta execução.')
    lines += ['', f'**Próximas datas-alvo:** {", ".join(report["next_due_dates"]) or "nenhuma"}.',
              '', '## Limitações e integridade', '']
    for warning in report['warnings']:
        lines.append(f'- {warning}')
    for key, value in report['source_hashes'].items():
        lines.append(f'- `{key}`: `{value["sha256"]}` — `{value["path"]}`')
    if report['stale_observation']:
        lines.append('- **ALERTA:** leitura do Porto ainda não está atualizada para a data do relatório.')
    return '\n'.join(lines) + '\n'


def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        temp = tmp.name
    os.replace(temp, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--output-dir', type=Path, default=Path('adc_mphi_report'))
    parser.add_argument('--as-of', type=dt.date.fromisoformat, default=dt.datetime.now(TZ).date())
    args = parser.parse_args(argv)
    data, proofs = read_inputs(args.repo_root)
    report = build_report(data, proofs, args.as_of)
    write_atomic(args.output_dir / 'report.json', json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write_atomic(args.output_dir / 'report.md', render_markdown(report))
    print(json.dumps({'mode': report['mode'], 'date': report['date_manaus'],
                      'evaluated': report['evaluated_count'], 'out': str(args.output_dir)}, ensure_ascii=False))


if __name__ == '__main__':
    main()