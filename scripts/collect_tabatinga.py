#!/usr/bin/env python3
"""Collect Tabatinga observations independently from all MPHI forecasts."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
from statistics import median
import tempfile
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "data" / "tabatinga.json"
SOURCE_URL = "https://telemetriaws1.ana.gov.br/serviceana.asmx/DadosHidrometeorologicos"
PAGE_URL = "https://edgequeiroz.github.io/mphi-rio-negro/data/tabatinga.json"
SCHEMA = "mphi-tabatinga-observation-v1"
STATION_CODE = "10100000"
TZ = timezone(timedelta(hours=-4))
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_OBSERVATION_AGE_DAYS = 3


def empty_snapshot():
    return {
        "schema": SCHEMA,
        "station": {"code": STATION_CODE, "name": "Tabatinga", "river": "Rio Solimões"},
        "source": {"name": "ANA/SGB - telemetria", "url": SOURCE_URL, "service": "legado"},
        "source_status": "awaiting_first_reading",
        "checked_at": None,
        "latest": None,
        "changes_cm": {"3d": None, "7d": None},
        "daily": [],
        "error": None,
    }


def read_snapshot(path):
    if not path.exists():
        return empty_snapshot()
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema") != SCHEMA or
            data.get("station", {}).get("code") != STATION_CODE):
        raise ValueError("Arquivo anterior incompatível; nenhuma substituição realizada")
    return data


def parse_observations(raw, today):
    """Parse readings in cm, retaining legitimate negative levels and dates."""
    root = ET.fromstring(raw)
    observations = {}
    for row in root.iter():
        if row.tag.rsplit("}", 1)[-1] != "DadosHidrometereologicos":
            continue
        values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in row}
        if values.get("CodEstacao") != STATION_CODE or not values.get("Nivel"):
            continue
        try:
            when = datetime.fromisoformat(values["DataHora"].replace("Z", "+00:00"))
            level_m = float(values["Nivel"].replace(",", ".")) / 100
        except (KeyError, TypeError, ValueError):
            continue
        if when.date() > today or not math.isfinite(level_m) or not -10 <= level_m <= 40:
            continue
        key = when.isoformat()
        if key in observations and observations[key]["level_m"] != level_m:
            raise ValueError("Valores conflitantes para o mesmo horário de observação")
        observations[key] = {"date": when.date().isoformat(), "level_m": level_m}
    if not observations:
        raise ValueError("Nenhuma cota válida da estação no período consultado")
    return list(observations.values())


def aggregate(observations):
    grouped = {}
    for row in observations:
        grouped.setdefault(row["date"], []).append(row["level_m"])
    daily = [{"date": day, "level_m": round(median(levels), 3), "samples": len(levels)}
             for day, levels in sorted(grouped.items())]
    for previous, current in zip(daily, daily[1:]):
        gap = (date.fromisoformat(current["date"]) - date.fromisoformat(previous["date"])).days
        if gap == 1 and abs(current["level_m"] - previous["level_m"]) > 5:
            raise ValueError("Variação diária fora do controle de qualidade")
    return daily


def build_success(previous, observations, now):
    daily = aggregate(observations)
    latest = daily[-1]
    previous_latest = previous.get("latest") or {}
    if previous_latest.get("date", "") > latest["date"]:
        raise ValueError("A fonte retornou dados anteriores à última observação preservada")
    by_date = {row["date"]: row["level_m"] for row in daily}
    latest_date = date.fromisoformat(latest["date"])
    changes = {}
    for days in (3, 7):
        reference = (latest_date - timedelta(days=days)).isoformat()
        changes[f"{days}d"] = (round((latest["level_m"] - by_date[reference]) * 100, 1)
                                if reference in by_date else None)
    result = empty_snapshot()
    result.update({
        "source_status": ("received" if (now.date() - latest_date).days <= MAX_OBSERVATION_AGE_DAYS
                          else "stale"),
        "checked_at": now.isoformat(timespec="seconds"),
        "latest": latest,
        "changes_cm": changes,
        "daily": daily,
    })
    return result


def build_failure(previous, now, error):
    result = dict(previous)
    if isinstance(error, HTTPError):
        reason = f"HTTPError:{error.code}"
    elif isinstance(error, URLError):
        reason = f"URLError:{type(error.reason).__name__}"
    else:
        reason = type(error).__name__
    result.update({"source_status": "unavailable", "checked_at": now.isoformat(timespec="seconds"),
                   "error": reason})
    return result


def fetch_observations(today):
    start = today - timedelta(days=14)
    query = urlencode({"codEstacao": STATION_CODE, "dataInicio": start.strftime("%d/%m/%Y"),
                       "dataFim": today.strftime("%d/%m/%Y")})
    request = Request(SOURCE_URL + "?" + query, headers={"User-Agent": "MPHI-Uiara/Tabatinga-observacao"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            break
        except (OSError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Resposta da fonte excede o limite de segurança")
    return parse_observations(raw, today)


def write_snapshot(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".tabatinga-", suffix=".json", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def verify_published(path, page_url=PAGE_URL):
    expected = read_snapshot(path)
    for attempt in range(1, 9):
        try:
            request = Request(page_url + "?verify=" + str(time.time_ns()),
                              headers={"Cache-Control": "no-cache, no-store, max-age=0",
                                       "User-Agent": "MPHI-Uiara/Tabatinga-publicacao"})
            with urlopen(request, timeout=15) as response:
                published = json.loads(response.read(MAX_RESPONSE_BYTES + 1))
            if published != expected:
                raise ValueError("Publicação difere do arquivo de Tabatinga")
            print("Tabatinga: dados públicos conferidos com o repositório.")
            return
        except (OSError, ValueError) as error:
            if attempt == 8:
                raise RuntimeError("Falha ao confirmar dados públicos de Tabatinga") from error
            print(f"Aguardando publicação de Tabatinga ({attempt}/8): {type(error).__name__}")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--probe", action="store_true", help="Exige leitura recente para teste da fonte")
    parser.add_argument("--verify-publication", action="store_true")
    args = parser.parse_args()
    if args.probe and args.output.resolve() == OUTPUT.resolve():
        parser.error("--probe exige --output temporário para não modificar dados publicados")
    if args.verify_publication:
        verify_published(args.output)
        return 0
    previous = read_snapshot(args.output)
    now = datetime.now(TZ)
    try:
        result = build_success(previous, fetch_observations(now.date()), now)
    except (OSError, ValueError, ET.ParseError) as error:
        result = build_failure(previous, now, error)
    write_snapshot(args.output, result)
    latest = result.get("latest") or {}
    print(json.dumps({"state": result["source_status"], "checked_at": result["checked_at"],
                      "latest": latest, "error": result.get("error")}, ensure_ascii=False))
    return 2 if args.probe and result["source_status"] != "received" else 0


if __name__ == "__main__":
    raise SystemExit(main())
