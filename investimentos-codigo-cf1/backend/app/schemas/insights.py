"""Relatórios do Claude no dashboard (Análises-2).

O relatório é escrito pela tarefa agendada do Claude, que pesquisa
notícias e relatórios públicos na internet. Por isso tudo o que chega
aqui é tratado como DADO de fora: texto puro (a tela nunca interpreta
HTML), tamanhos limitados, links só http/https e um formato fechado —
campo desconhecido recusa o arquivo.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from datetime import date as Day
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHORT = 200
_TEXT = 2000


def _check_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith(("https://", "http://")):
        raise ValueError("link precisa começar com http:// ou https://")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError("link com espaço")
    return cleaned


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceLink(_Strict):
    title: str = Field(min_length=1, max_length=_SHORT)
    url: str = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)


class Metric(_Strict):
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=80)
    context: str | None = Field(default=None, max_length=_SHORT)


MetricCode = Literal[
    # Frações (0.12 = 12%)
    "RETURN_1M",
    "RETURN_YTD",
    "RETURN_1Y",
    "RETURN_3Y_ANNUALIZED",
    "DIVIDEND_YIELD",
    "EXPENSE_RATIO",
    "OCCUPANCY",
    "EARNINGS_GROWTH",
    "YIELD_TO_MATURITY",
    # Múltiplos (vezes)
    "PE_TTM",
    "PE_FORWARD",
    "P_FFO",
    "PRICE_TO_BOOK",
    "BETA",
    "DEBT_TO_EBITDA",
]
FRACTION_CODES = frozenset(
    {
        "RETURN_1M",
        "RETURN_YTD",
        "RETURN_1Y",
        "RETURN_3Y_ANNUALIZED",
        "DIVIDEND_YIELD",
        "EXPENSE_RATIO",
        "OCCUPANCY",
        "EARNINGS_GROWTH",
        "YIELD_TO_MATURITY",
    }
)


class KeyMetric(_Strict):
    """Indicador de mercado com número, data e fonte (relatório v2). Os
    códigos são fechados para a tela montar colunas fixas; frações vão
    como fração (0.035 = 3,5%), múltiplos como "vezes".
    """

    code: MetricCode
    value: float
    as_of: Day
    source: str = Field(min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value)

    @field_validator("value")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("número inválido")
        if abs(value) > 10000:
            raise ValueError("número fora de escala")
        return value

    @model_validator(mode="after")
    def _scale(self) -> KeyMetric:
        # Fração escrita como percentual (12 em vez de 0.12) seria 1200%.
        if self.code in FRACTION_CODES and abs(self.value) > 5:
            raise ValueError(f"{self.code} é fração (0.12 = 12%), não percentual")
        return self


class HoldingReading(_Strict):
    """Leitura de um ativo da carteira: fatos medidos e o que eles
    costumam indicar. `signal` resume a leitura — nunca é ordem de
    compra ou venda.
    """

    ticker: str = Field(min_length=1, max_length=20)
    signal: Literal["POSITIVO", "NEUTRO", "ATENCAO"]
    reading: str = Field(min_length=1, max_length=_TEXT)
    metrics: list[Metric] = Field(default_factory=list, max_length=12)
    key_metrics: list[KeyMetric] = Field(default_factory=list, max_length=20)
    sources: list[SourceLink] = Field(default_factory=list, max_length=10)


class NewsItem(_Strict):
    ticker: str | None = Field(default=None, max_length=20)
    topic: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)
    published_at: date | None = None
    summary: str = Field(min_length=1, max_length=_TEXT)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)


class ResearchItem(_Strict):
    """Resumo de um relatório público de uma casa de análise. Só o
    resumo e o link: o texto original fica na fonte.
    """

    house: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(max_length=500)
    published_at: date | None = None
    summary: str = Field(min_length=1, max_length=_TEXT)
    relevance: str | None = Field(default=None, max_length=_TEXT)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)


class WatchItem(_Strict):
    topic: str = Field(min_length=1, max_length=_SHORT)
    why: str = Field(min_length=1, max_length=_TEXT)
    date: Day | None = None


class ReviewPoint(_Strict):
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=1000)
    tickers: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tickers")
    @classmethod
    def _tickers(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value]
        if any(not t or len(t) > 20 for t in cleaned):
            raise ValueError("código de ativo com 1 a 20 caracteres")
        return cleaned


class PortfolioReview(_Strict):
    """Avaliação da carteira pelo Claude (relatório v2): o que está bem,
    o que pede atenção, os riscos e o que poderia melhorar. Leitura dos
    números — nunca ordem de compra ou venda.
    """

    overall: str = Field(min_length=1, max_length=1500)
    good: list[ReviewPoint] = Field(default_factory=list, max_length=8)
    attention: list[ReviewPoint] = Field(default_factory=list, max_length=8)
    risks: list[ReviewPoint] = Field(default_factory=list, max_length=8)
    improve: list[ReviewPoint] = Field(default_factory=list, max_length=8)


def _clean_tickers(value: list[str]) -> list[str]:
    cleaned = [t.strip() for t in value]
    if any(not t or len(t) > 20 for t in cleaned):
        raise ValueError("código de ativo com 1 a 20 caracteres")
    return cleaned


class Opportunity(_Strict):
    """Ideia para ESTUDAR (relatório v3): uma tese de mercado do momento,
    com o porquê agora, os riscos e o que acompanhar para saber se ela se
    confirma. Pode citar ativos fora da carteira. Nunca é ordem de compra:
    a tela sempre mostra isso junto.
    """

    title: str = Field(min_length=1, max_length=120)
    thesis: str = Field(min_length=1, max_length=1500)
    tickers: list[str] = Field(default_factory=list, max_length=10)
    relation: str | None = Field(default=None, max_length=500)  # como se liga à carteira
    why_now: str = Field(min_length=1, max_length=1000)
    risks: list[str] = Field(min_length=1, max_length=5)
    how_to_follow: str = Field(min_length=1, max_length=600)
    sources: list[SourceLink] = Field(min_length=1, max_length=5)

    @field_validator("tickers")
    @classmethod
    def _tickers(cls, value: list[str]) -> list[str]:
        return _clean_tickers(value)

    @field_validator("risks")
    @classmethod
    def _risks(cls, value: list[str]) -> list[str]:
        cleaned = [r.strip() for r in value]
        if any(not r or len(r) > 300 for r in cleaned):
            raise ValueError("cada risco precisa ter de 1 a 300 caracteres")
        return cleaned


class EtfHolding(_Strict):
    name: str = Field(min_length=1, max_length=80)
    ticker: str | None = Field(default=None, max_length=20)
    weight: float  # fração do ETF (0.08 = 8%)

    @field_validator("weight")
    @classmethod
    def _weight(cls, value: float) -> float:
        if not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError("peso é fração do ETF (0.08 = 8%), entre 0 e 1")
        return value


class EtfComposition(_Strict):
    """Maiores posições de um ETF da carteira, publicadas pela gestora
    (relatório v3). Base da exposição às empresas "por trás" dos ETFs.
    """

    etf: str = Field(min_length=1, max_length=20)
    as_of: Day
    source: str = Field(min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    top: list[EtfHolding] = Field(min_length=1, max_length=15)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value)

    @model_validator(mode="after")
    def _total(self) -> EtfComposition:
        if sum(h.weight for h in self.top) > 1.0001:
            raise ValueError(f"as posições de {self.etf} somam mais de 100%")
        keys = [(h.ticker or h.name).upper() for h in self.top]
        if len(set(keys)) != len(keys):
            raise ValueError(f"empresa repetida em {self.etf}")
        return self


class MarketPulse(_Strict):
    """Um número do mercado para a faixa do topo do jornal (relatório v3):
    "S&P 500 · 6.712 · -0,4% no dia". Texto já formatado pelo Claude.
    """

    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=40)
    change: str | None = Field(default=None, max_length=40)
    direction: Literal["UP", "DOWN", "FLAT"] | None = None
    as_of: Day
    source: str = Field(min_length=1, max_length=100)


class PaperItem(_Strict):
    """Uma leitura de uma fonte que o usuário cadastrou (relatório v4): o que
    saiu de novo ali, resumido com palavras do Claude, e o link.
    """

    source: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(max_length=500)
    published_at: Day | None = None
    summary: str = Field(min_length=1, max_length=_TEXT)
    takeaways: list[str] = Field(default_factory=list, max_length=5)
    relation: str | None = Field(default=None, max_length=1000)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)

    @field_validator("takeaways")
    @classmethod
    def _takeaways(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value]
        if any(not t or len(t) > 300 for t in cleaned):
            raise ValueError("cada ponto precisa ter de 1 a 300 caracteres")
        return cleaned


class InsightReport(_Strict):
    # v2 acrescenta `portfolio_review` e `key_metrics`; v3, `market`,
    # `opportunities` e `etf_holdings`; v4, `papers` (todos opcionais).
    schema_version: Literal[1, 2, 3, 4]
    generated_at: datetime
    headline: str = Field(min_length=1, max_length=300)
    summary: list[str] = Field(min_length=1, max_length=8)
    holdings: list[HoldingReading] = Field(default_factory=list, max_length=40)
    news: list[NewsItem] = Field(default_factory=list, max_length=40)
    research: list[ResearchItem] = Field(default_factory=list, max_length=20)
    watch: list[WatchItem] = Field(default_factory=list, max_length=15)
    portfolio_review: PortfolioReview | None = None
    market: list[MarketPulse] = Field(default_factory=list, max_length=10)
    opportunities: list[Opportunity] = Field(default_factory=list, max_length=6)
    etf_holdings: list[EtfComposition] = Field(default_factory=list, max_length=20)
    papers: list[PaperItem] = Field(default_factory=list, max_length=20)
    disclaimer: str = Field(min_length=1, max_length=500)

    @field_validator("summary")
    @classmethod
    def _paragraphs(cls, value: list[str]) -> list[str]:
        cleaned = [p.strip() for p in value]
        if any(not p or len(p) > _TEXT for p in cleaned):
            raise ValueError("cada parágrafo do resumo precisa ter de 1 a 2000 caracteres")
        return cleaned

    @model_validator(mode="after")
    def _one_composition_per_etf(self) -> InsightReport:
        etfs = [c.etf.upper() for c in self.etf_holdings]
        if len(set(etfs)) != len(etfs):
            raise ValueError("composição repetida para o mesmo ETF")
        return self


class InsightReportRead(BaseModel):
    report_date: date
    report: InsightReport


class InsightHistoryItem(BaseModel):
    report_date: date
    headline: str


class InvalidReportFile(BaseModel):
    file_name: str
    error: str


class InsightIndex(BaseModel):
    """`latest` é o relatório válido mais recente. Arquivos que não
    passam na validação aparecem em `invalid_files` e são ignorados.
    """

    latest: InsightReportRead | None
    history: list[InsightHistoryItem]
    invalid_files: list[InvalidReportFile]
    snapshot_written_at: datetime | None


class SnapshotResult(BaseModel):
    written_at: datetime
    positions: int


# --- Alertas de hora em hora ---------------------------------------------------------

_ALERT_ID = r"^[A-Za-z0-9._:-]{1,80}$"


class Alert(_Strict):
    """Notícia séria e de impacto encontrada pela checagem de hora em
    hora. Só existe quando há algo grave: a ausência de alerta é o normal.
    """

    id: str = Field(pattern=_ALERT_ID)
    detected_at: datetime
    severity: Literal["ALTA", "CRITICA"]
    tickers: list[str] = Field(default_factory=list, max_length=10)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=_TEXT)
    why_it_matters: str = Field(min_length=1, max_length=_TEXT)
    sources: list[SourceLink] = Field(min_length=1, max_length=5)

    @field_validator("tickers")
    @classmethod
    def _tickers(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value]
        if any(not t or len(t) > 20 for t in cleaned):
            raise ValueError("código de ativo com 1 a 20 caracteres")
        return cleaned


class AlertFile(_Strict):
    schema_version: Literal[1]
    alerts: list[Alert] = Field(default_factory=list, max_length=50)


class AlertRead(BaseModel):
    day: date
    read: bool
    alert: Alert


class AlertIndex(BaseModel):
    """Alertas dos últimos dias, mais novo primeiro. Arquivo que não passa
    na validação vai para `invalid_files` e é ignorado.
    """

    alerts: list[AlertRead]
    unread_count: int
    invalid_files: list[InvalidReportFile]


class ChatContext(BaseModel):
    """Resumo da carteira em texto, para levar ao Claude junto com a pergunta."""

    text: str


# --- Empresas por trás dos ETFs -------------------------------------------------------


class ViaRead(BaseModel):
    ticker: str
    weight: Decimal


class CompanyExposureRead(BaseModel):
    name: str
    ticker: str | None
    weight: Decimal
    via: list[ViaRead]


class FundCoverageRead(BaseModel):
    ticker: str
    weight: Decimal
    coverage: Decimal
    as_of: date
    source: str


class CurrencyLookThrough(BaseModel):
    """Pesos em 0..1 sobre os investimentos da moeda. `explained`: quanto
    da carteira as empresas listadas somam (piso: a composição cobre só as
    maiores posições de cada fundo). `missing`: fundos sem composição.
    """

    currency_code: str
    companies: list[CompanyExposureRead]
    funds: list[FundCoverageRead]
    missing: list[str]
    explained: Decimal


class LookThroughRead(BaseModel):
    """`report_date`: análise de onde vieram as composições (None: nenhuma
    análise v3 ainda).
    """

    report_date: date | None
    currencies: list[CurrencyLookThrough]
