#!/usr/bin/env python3
"""Observational, isolated cross-border pilot for MPHI. Does not change any forecast."""
import csv
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from hydrologic_v2 import (
    SOURCE_URL as ANA_LEGACY_URL,
    aggregate_daily,
    parse_telemetry_xml,
    session_with_retries,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "crossborder_pilot.json"
PERU_CSV = ROOT / "data" / "crossborder" / "peru_observations.csv"
TZ = timezone(timedelta(hours=-4))
SCHEMA = "mphi-crossborder-observations-v1"
TABATINGA = "10100000"
SOURCES = {
    TABATINGA: {"name": "Tabatinga", "river": "Solimoes", "country": "BR", "agency": "ANA"},
    "pe:tamshiyacu": {"name": "Tamshiyacu", "river": "Amazonas", "country": "PE", "agency": "SENAMHI"},
    "pe:requena": {"name": "Requena", "river": "Ucayali", "country": "PE", "agency": "SENAMHI"},
    "pe:san-regis": {"name": "San Regis", "river": "Maranon", "country": "PE", "agency": "SENAMHI"},
}
PERU = set(SOURCES) - {TABATINGA}
COLUMNS = {"station", "date", "metric", "value", "unit", "datum", "source_url", "source_reference"}
ALLOWED_UNITS = {"stage": {"m", "cm", "m_asl"}, "discharge": {"m3/s"}}


def official_peru_url(value):
    uri = urlsplit(value.strip())
    domain = (uri.hostname or "").lower()
    allowed = ("senamhi.gob.pe", "gob.pe", "dhn.mil.pe")
    return (uri.scheme == "https" and
            any(domain == host or domain.endswith("." + host) for host in allowed) and
            uri.username is None and uri.password is None)


def track_id(observation):
    return "|".join(str(observation[k]) for k in ("station", "metric", "unit", "datum"))


def normalize_peru_row(row, today):
    station = row["station"].strip().lower()
    if station not in PERU:
        raise ValueError("Estacao peruana desconhecida: " + station)
    day = date.fromisoformat(row["date"].strip())
    if day > today:
        raise ValueError("Observacao futura: " + str(day))
    metric, unit = row["metric"].strip(), row["unit"].strip()
    if unit not in ALLOWED_UNITS.get(metric, set()):
        raise ValueError("Unidade incompativel com metrica: " + metric + "/" + unit)
    datum = row["datum"].strip()
    if metric == "stage" and not datum:
        raise ValueError("Cota sem referencial/datum")
    if metric == "discharge" and datum:
        raise ValueError("Vazao nao deve ter datum")
    value = float(row["value"].strip().replace(",", "."))
    if not (-100 <= value <= 2000 if metric == "stage" else 0 <= value <= 2000000):
        raise ValueError("Valor fora do dominio de validacao")
    url = row["source_url"].strip()
    reference = row["source_reference"].strip()
    if not official_peru_url(url) or not reference:
        raise ValueError("Fonte oficial e identificador documental obrigatorios")
    return {
        "station": station, "date": day.isoformat(), "metric": metric,
        "value": value, "unit": unit, "datum": datum, "source_url": url,
        "source_reference": reference, "source": "SENAMHI/Peru (registro documentado)",
        "verification": "documental_manual",
    }


def read_peru(path, today):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not COLUMNS.issubset(reader.fieldnames):
            raise ValueError("CSV peruano sem colunas obrigatorias")
        observations = []
        for lineno, row in enumerate(reader, start=2):
            try:
                if row["station"] and row["station"].strip().startswith("#"):
                    continue
                observations.append(normalize_peru_row(row, today))
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Linha {lineno} invalida: {exc}") from exc
        return observations


def fetch_tabatinga(today):
    """Fetch the existing ANA legacy endpoint ONLY as a provisional observation."""
    start = today - timedelta(days=96)
    session = session_with_retries()
    try:
        response = session.get(
            ANA_LEGACY_URL,
            params={"codEstacao": TABATINGA, "dataInicio": start.strftime("%d/%m/%Y"),
                    "dataFim": today.strftime("%d/%m/%Y")},
            headers={"User-Agent": "MPHI-Uiara/crossborder-observation-pilot"},
            timeout=(10, 45),
        )
        response.raise_for_status()
        observations = [item for item in parse_telemetry_xml(response.text, TABATINGA)
                        if item["timestamp"].date() <= today]
        if not observations:
            raise RuntimeError("ANA retornou observacoes sem datas validas")
        daily = aggregate_daily(observations)
        return [{
            "station": TABATINGA, "date": row["date"], "metric": "stage",
            "value": row["level_m"], "unit": "m", "datum": "ana_10100000_local_gauge",
            "samples": row["samples"], "source": "ANA telemetria (legado, provisoria)",
            "source_url": ANA_LEGACY_URL, "source_reference": "ANA 10100000",
            "verification": "automatica_provisoria",
        } for row in daily]
    finally:
        session.close()


def merge_tracks(existing, observations):
    """Never silently rewrite previously recorded observations."""
    tracks = {key: {**track, "observations": list(track["observations"])}
              for key, track in existing.items()}
    conflicts = []
    for row in observations:
        key = track_id(row)
        if key not in tracks:
            tracks[key] = {
                "station": row["station"], "metric": row["metric"], "unit": row["unit"],
                "datum": row["datum"], "observations": [],
            }
        by_day = {item["date"]: item for item in tracks[key]["observations"]}
        before = by_day.get(row["date"])
        if before is None:
            tracks[key]["observations"].append(row)
        elif abs(float(before["value"]) - float(row["value"])) > 1e-8:
            conflicts.append({
                "track": key, "date": row["date"], "old_value": before["value"],
                "new_value": row["value"], "resolution": "old_value_preserved",
            })
        tracks[key]["observations"].sort(key=lambda item: item["date"])
    return tracks, conflicts


def trend_for(track, today):
    series = {row["date"]: float(row["value"]) for row in track["observations"]}
    if not series:
        return {"state": "awaiting_observations"}
    latest_date = max(series)
    latest_day = date.fromisoformat(latest_date)
    age_days = (today - latest_day).days
    result = {
        "state": "recent" if 0 <= age_days <= 3 else "stale",
        "latest_date": latest_date, "age_days": age_days,
        "latest_value": series[latest_date], "unit": track["unit"],
        "datum": track["datum"],
    }
    for days in (3, 7):
        then = (latest_day - timedelta(days=days)).isoformat()
        key = f"change_{days}d_per_day"
        result[key] = round((series[latest_date] - series[then]) / days, 5) if then in series else None
    result["trend_unit"] = track["unit"] + "/day"
    result["notes"] = "Descriptive only; no causal lag or forecast inferred."
    return result


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".crossborder-", suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(data, tmp, indent=2, ensure_ascii=False, allow_nan=False)
        tmp.write("\n")
    os.replace(tmp_path, path)


def build(existing, ana_rows, peru_rows, today, checked_at, ana_error=None):
    if existing and existing.get("schema") != SCHEMA:
        raise ValueError("Esquema existente incompativel; nao sobrescrever")
    tracks, conflicts = merge_tracks(existing.get("tracks", {}) if existing else {},
                                     ana_rows + peru_rows)
    states = {key: trend_for(track, today) for key, track in tracks.items()}
    peru_tracks = [key for key in tracks if key.startswith("pe:")]
    return {
        "schema": SCHEMA, "mode": "observation_only", "affects_public_forecast": False,
        "checked_at": checked_at, "timezone": "America/Manaus",
        "source_status": {
            "ana_tabatinga": {
                "state": ("unavailable" if ana_error else "received") if ana_rows or ana_error
                         else "no_observations",
                "error": ana_error, "legacy_api": True,
                "migration_required": True,
            },
            "senamhi_peru": {
                "state": "documented_data_loaded" if peru_rows else "awaiting_documented_data",
                "records_ingested_this_run": len(peru_rows),
                "api_integration": "not_verified",
            },
        },
        "stations_catalog": SOURCES,
        "tracks": tracks, "signals": states, "peru_tracks_total": len(peru_tracks),
        "conflicts": (existing.get("conflicts", []) if existing else []) + conflicts,
        "warning": "Nunca comparar cotas absolutas entre diferentes datums; apenas series homogêneas.",
    }


def main():
    now = datetime.now(TZ)
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    peru_rows = read_peru(PERU_CSV, now.date())
    ana_rows, ana_error = [], None
    try:
        ana_rows = fetch_tabatinga(now.date())
    except (requests.RequestException, RuntimeError, ValueError, OSError) as exc:
        ana_error = type(exc).__name__
    result = build(existing, ana_rows, peru_rows, now.date(),
                   now.isoformat(timespec="seconds"), ana_error)
    write_json_atomic(OUT, result)
    print(json.dumps({"state": result["source_status"], "tracks": len(result["tracks"]),
                      "conflicts": len(result["conflicts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
