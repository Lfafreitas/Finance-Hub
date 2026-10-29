"""Troca de arquivos com o Claude (Análises-2).

O backend roda no computador do dono e não fica exposto: a tarefa
agendada do Claude não chama a API. A troca é por uma pasta:

- `carteira.json` — retrato da carteira, escrito pelo backend;
- `relatorios/AAAA-MM-DD.json` — análise do dia, escrita pelo Claude;
- `alertas/AAAA-MM-DD.json` — notícias sérias do dia, escritas pela
  checagem de hora em hora (só quando há alguma);
- `alertas/lidos.json` — quais alertas você já viu, escrito pelo backend.

O retrato leva só o necessário para a análise (ativo, classe, moeda,
quantidade, custo, valor, pesos, cenários e ritmo de aporte). Nenhum
nome de pessoa, documento ou número de conta.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.files import atomic_write_text
from app.db.base import utcnow
from app.models.asset import Asset
from app.schemas.insights import (
    AlertFile,
    AlertIndex,
    AlertRead,
    InsightHistoryItem,
    InsightIndex,
    InsightReport,
    InsightReportRead,
    InvalidReportFile,
    SnapshotResult,
)
from app.services.agenda_service import get_agenda
from app.services.allocation_service import get_allocation
from app.services.analytics_service import get_portfolio_analytics
from app.services.benchmark_service import get_benchmarks
from app.services.dashboard_service import get_dashboard_summary
from app.services.financial_health_service import get_financial_health
from app.services.notes_service import list_notes, list_sources
from app.services.performance_service import get_kpis

SNAPSHOT_FILE = "carteira.json"
REPORTS_DIR = "relatorios"
ALERTS_DIR = "alertas"
READ_FILE = "lidos.json"
MAX_READ_IDS = 2000
ALERT_DAYS_MAX = 60
_REPORT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
MAX_REPORT_BYTES = 512 * 1024


class InsightReportNotFoundError(Exception):
    pass


def _folder() -> Path:
    return Path(settings.insights_dir)


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def build_snapshot(db: Session, user_id: UUID) -> dict:
    summary = get_dashboard_summary(db, user_id)
    analytics = get_portfolio_analytics(db, user_id)
    assets = {
        a.id: a
        for a in db.execute(
            select(Asset).where(Asset.id.in_([p.asset_id for p in summary.positions]))
        ).scalars()
    }
    positions = [
        {
            "ticker": p.asset_ticker,
            "name": p.asset_name,
            "asset_class": assets[p.asset_id].asset_class_code,
            "country": assets[p.asset_id].country,
            "currency": p.currency_code,
            "quantity": _decimal(p.quantity),
            "average_cost": _decimal(p.average_cost),
            "total_cost": _decimal(p.total_cost_basis),
            "market_price": _decimal(p.market_price),
            "market_price_date": p.market_price_date.isoformat() if p.market_price_date else None,
            "market_value": _decimal(p.market_value),
        }
        for p in summary.positions
        if p.quantity > 0 and p.currency_code is not None
    ]
    blocks = []
    for block in analytics.blocks:
        blocks.append(
            {
                "currency": block.currency_code,
                "market_value": _decimal(block.market_value),
                "concentration": (
                    {
                        "basis": block.concentration.basis,
                        "by_asset": [
                            {"ticker": w.label, "weight": _decimal(w.weight)}
                            for w in block.concentration.by_asset
                        ],
                        "by_class": [
                            {"class": w.label, "weight": _decimal(w.weight)}
                            for w in block.concentration.by_class
                        ],
                        "flags": block.concentration.flags,
                    }
                    if block.concentration
                    else None
                ),
                "scenarios": (
                    {
                        "until": block.scenarios.until.isoformat(),
                        "pessimistic_return": _decimal(block.scenarios.pessimistic_return),
                        "realistic_return": _decimal(block.scenarios.realistic_return),
                        "optimistic_return": _decimal(block.scenarios.optimistic_return),
                        "probability_below_today": _decimal(
                            block.scenarios.probability_below_today
                        ),
                    }
                    if block.scenarios
                    else None
                ),
                "contributions": (
                    {
                        "year": block.contributions.year,
                        "total_year": _decimal(block.contributions.total_year),
                        "projections": [
                            {"pace": p.pace, "monthly": _decimal(p.monthly)}
                            for p in block.contributions.projections
                        ],
                    }
                    if block.contributions
                    else None
                ),
                "alerts": block.alerts,
            }
        )
    kpis = get_kpis(db, user_id, today=analytics.reference_date)
    return {
        "schema_version": 1,
        "generated_at": utcnow().isoformat(),
        "reference_date": analytics.reference_date.isoformat(),
        "positions": positions,
        "currencies": blocks,
        # KPIs-1: indicadores calculados pelo app (pesos, concentração,
        # resultado e desempenho de preço de 12 meses) — a avaliação da
        # carteira parte destes números.
        "kpis": json.loads(kpis.model_dump_json()),
        # Agenda: vencimentos de renda fixa (data, taxa, estimativa).
        "agenda": json.loads(
            get_agenda(db, user_id, today=analytics.reference_date).model_dump_json()
        ),
        # Alocação por classe: peso atual × alvo que o próprio usuário definiu.
        "allocation": json.loads(
            get_allocation(db, user_id, today=analytics.reference_date).model_dump_json()
        ),
        # Comparação com a referência (SPY em dólar, CDI em reais), sem a série diária.
        "benchmarks": [
            json.loads(c.model_dump_json(exclude={"points"}))
            for c in get_benchmarks(db, user_id, today=analytics.reference_date).comparisons
        ],
        # Saúde financeira: reserva em meses de gasto e taxa de poupança
        # (só totais por moeda; nenhuma descrição de lançamento).
        "financial_health": json.loads(
            get_financial_health(db, user_id, today=analytics.reference_date).model_dump_json()
        ),
        # Fontes de leitura que o usuário cadastrou: a análise resume o que saiu
        # de novo em cada uma (campo `papers` do relatório).
        "reading_sources": [
            {"name": src.name, "url": src.url, "focus": src.focus}
            for src in list_sources(db, user_id, active_only=True)
        ],
        # Só as anotações que ele marcou para o Claude.
        "notes_for_claude": [
            {
                "title": n.title,
                "body": n.body[:1500],
                "quote": n.quote,
                "tickers": n.tickers,
                "updated_at": n.updated_at.isoformat(),
            }
            for n in list_notes(db, user_id, shared_only=True)[:20]
        ],
        "note": (
            "Valores em moedas diferentes nunca são somados. Retornos e pesos são frações "
            "(0.25 = 25%)."
        ),
    }


def write_snapshot(db: Session, user_id: UUID) -> SnapshotResult:
    """Grava o retrato da carteira de forma atômica (arquivo temporário
    + troca), para o Claude nunca ler um arquivo pela metade.
    """
    snapshot = build_snapshot(db, user_id)
    atomic_write_text(_folder() / SNAPSHOT_FILE, json.dumps(snapshot, ensure_ascii=False, indent=2))
    return SnapshotResult(written_at=utcnow(), positions=len(snapshot["positions"]))


def _snapshot_written_at() -> datetime | None:
    target = _folder() / SNAPSHOT_FILE
    if not target.exists():
        return None
    return datetime.fromtimestamp(target.stat().st_mtime, UTC)


def _read_report(path: Path) -> InsightReport:
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError(f"arquivo maior que {MAX_REPORT_BYTES // 1024} KB")
    return InsightReport.model_validate_json(path.read_bytes())


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return f"{where}: {first['msg']}" if where else first["msg"]
    return str(exc)


def list_reports() -> InsightIndex:
    folder = _folder() / REPORTS_DIR
    valid: list[tuple[date, InsightReport]] = []
    invalid: list[InvalidReportFile] = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            match = _REPORT_NAME.match(path.name)
            if not match or not path.is_file():
                continue
            try:
                report_date = date.fromisoformat(match.group(1))
                valid.append((report_date, _read_report(path)))
            except (ValueError, ValidationError, OSError) as exc:
                invalid.append(InvalidReportFile(file_name=path.name, error=_describe(exc)))
    valid.sort(key=lambda item: item[0], reverse=True)
    latest = InsightReportRead(report_date=valid[0][0], report=valid[0][1]) if valid else None
    return InsightIndex(
        latest=latest,
        history=[InsightHistoryItem(report_date=d, headline=r.headline) for d, r in valid],
        invalid_files=invalid,
        snapshot_written_at=_snapshot_written_at(),
    )


def get_report(report_date: date) -> InsightReportRead:
    path = _folder() / REPORTS_DIR / f"{report_date.isoformat()}.json"
    if not path.is_file():
        raise InsightReportNotFoundError(f"não há análise de {report_date.strftime('%d/%m/%Y')}")
    try:
        return InsightReportRead(report_date=report_date, report=_read_report(path))
    except (ValueError, ValidationError) as exc:
        raise InsightReportNotFoundError(
            f"a análise de {report_date.strftime('%d/%m/%Y')} está com formato inválido: "
            f"{_describe(exc)}"
        ) from exc


# --- Alertas -------------------------------------------------------------------------


def _alerts_folder() -> Path:
    return _folder() / ALERTS_DIR


def _read_ids() -> set[str]:
    try:
        data = json.loads((_alerts_folder() / READ_FILE).read_text(encoding="utf-8"))
        return {str(item) for item in data.get("read", [])}
    except (OSError, ValueError, AttributeError):
        return set()


def _write_read_ids(ids: list[str]) -> None:
    atomic_write_text(
        _alerts_folder() / READ_FILE, json.dumps({"read": ids[-MAX_READ_IDS:]}, indent=2)
    )


def list_alerts(*, days: int = 7, today: date | None = None) -> AlertIndex:
    """Alertas dos últimos `days` dias (pelo nome do arquivo), mais novo
    primeiro. O mesmo id em dois arquivos aparece uma vez (o mais novo).
    """
    today = today or date.today()
    days = max(1, min(days, ALERT_DAYS_MAX))
    first = date.fromordinal(today.toordinal() - days + 1)
    read = _read_ids()
    found: dict[str, AlertRead] = {}
    invalid: list[InvalidReportFile] = []
    folder = _alerts_folder()
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            match = _REPORT_NAME.match(path.name)
            if not match or not path.is_file():
                continue
            try:
                day = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if not first <= day <= today:
                continue
            try:
                if path.stat().st_size > MAX_REPORT_BYTES:
                    raise ValueError(f"arquivo maior que {MAX_REPORT_BYTES // 1024} KB")
                parsed = AlertFile.model_validate_json(path.read_bytes())
            except (ValueError, ValidationError, OSError) as exc:
                invalid.append(InvalidReportFile(file_name=path.name, error=_describe(exc)))
                continue
            for alert in parsed.alerts:
                found[alert.id] = AlertRead(day=day, read=alert.id in read, alert=alert)
    alerts = sorted(found.values(), key=lambda a: a.alert.detected_at, reverse=True)
    return AlertIndex(
        alerts=alerts,
        unread_count=sum(1 for a in alerts if not a.read),
        invalid_files=invalid,
    )


def mark_alerts_read(alert_ids: list[str]) -> AlertIndex:
    current = list(_read_ids())
    for alert_id in alert_ids:
        if alert_id not in current:
            current.append(alert_id)
    _write_read_ids(sorted(current))
    return list_alerts()


def mark_all_alerts_read(*, days: int = ALERT_DAYS_MAX) -> AlertIndex:
    return mark_alerts_read([a.alert.id for a in list_alerts(days=days).alerts])
