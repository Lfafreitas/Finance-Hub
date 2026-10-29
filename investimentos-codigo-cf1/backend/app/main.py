from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import require_unlocked
from app.api.routers.accounts import router as accounts_router
from app.api.routers.analytics import router as analytics_router
from app.api.routers.auth import router as auth_router
from app.api.routers.cashflow import router as cashflow_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.dividends import router as dividends_router
from app.api.routers.imports import router as imports_router
from app.api.routers.insights import router as insights_router
from app.api.routers.notes import router as notes_router
from app.api.routers.overview import router as overview_router
from app.api.routers.performance import router as performance_router
from app.api.routers.prices import router as prices_router
from app.api.routers.reconciliation import router as reconciliation_router
from app.api.routers.registry import router as registry_router
from app.api.routers.transactions import router as transactions_router
from app.core.config import settings
from app.core.remote import is_remote

# `require_unlocked` vale para toda rota: chamada remota (celular) só passa
# com a sessão do Face ID. Ver app/core/remote.py e auth_service.
app = FastAPI(title=settings.app_name, dependencies=[Depends(require_unlocked)])

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_SECURITY_HEADERS = {
    # Dado financeiro não fica guardado em cache do navegador/celular.
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # A documentação da API é só para o computador.
    if request.url.path.startswith(_DOCS_PATHS) and is_remote(request.headers):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# Ver `Settings.allowed_hosts`/`cors_allowed_origins`: sem autenticação,
# estas duas camadas são o que impede um site aberto no navegador de
# ler os dados financeiros pela API local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
# Adicionado por último = camada mais externa: um Host não permitido é
# recusado antes de qualquer outra coisa.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.include_router(auth_router)
app.include_router(transactions_router)
app.include_router(accounts_router)
app.include_router(dashboard_router)
app.include_router(dividends_router)
app.include_router(imports_router)
app.include_router(reconciliation_router)
app.include_router(registry_router)
app.include_router(prices_router)
app.include_router(cashflow_router)
app.include_router(analytics_router)
app.include_router(insights_router)
app.include_router(notes_router)
app.include_router(overview_router)
app.include_router(performance_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Verificação simples de saúde da aplicação.

    Usado para confirmar que a fundação do projeto (servidor sobe,
    configuração carrega) está funcionando. Não depende de banco de
    dados nem de nenhuma integração externa — isso vem em fases
    posteriores.
    """
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}
