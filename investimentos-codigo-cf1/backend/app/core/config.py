from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_IMPORT_HMAC_SECRET = "dev-only-change-in-production-import-hmac-secret"
_LOCAL_ENVIRONMENTS = {"development", "test"}


class Settings(BaseSettings):
    """Configuração central da aplicação.

    Nesta fase (Fundação do projeto) só existem valores básicos de
    identificação. Configuração de banco de dados, autenticação e
    integrações externas entra nas fases correspondentes, não aqui.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Sistema de Controle de Investimentos"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investimentos_dev"
    # D-A1 (Fase 6): sem autenticação real ainda. O "usuário atual" é
    # resolvido a partir deste e-mail configurado, nunca aceito do
    # cliente. Trocar para autenticação real no futuro significa mudar
    # só `get_current_user_id` (app/api/deps.py), não os services/routers.
    single_user_email: str = "owner@local"
    # Fase 10a: chave usada para assinar (HMAC-SHA256) o payload de
    # preview de importação, garantindo que o commit só processe
    # exatamente o que foi mostrado ao usuário. Nunca retornada em
    # nenhuma resposta da API. Valor abaixo é só para desenvolvimento —
    # em produção, definir via variável de ambiente `IMPORT_HMAC_SECRET`.
    import_hmac_secret: str = _DEV_IMPORT_HMAC_SECRET
    # Tamanho máximo de um arquivo de importação (bytes). O upload é
    # lido inteiro em memória para ser parseado; sem teto, um único
    # request derruba o processo por falta de memória.
    import_max_upload_bytes: int = 10 * 1024 * 1024
    # A API não tem autenticação (single-user, decisão da Fase 6), então
    # a fronteira de segurança é a REDE: quem alcança a porta enxerga e
    # altera tudo. Estes dois parâmetros fecham os dois caminhos pelos
    # quais um SITE QUALQUER aberto no navegador do dono alcançaria a
    # API local:
    # - `allowed_hosts`: cabeçalho Host aceito. Bloqueia DNS rebinding
    #   (um domínio do atacante apontado para 127.0.0.1 chega com o
    #   Host DELE, não `localhost`).
    # - `cors_allowed_origins`: únicas origens cujo JavaScript pode LER
    #   respostas da API — o frontend local, e nada mais.
    # Listas via variável de ambiente usam JSON: ALLOWED_HOSTS='["a","b"]'.
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Análises-2: pasta de troca com o Claude. O backend grava ali o
    # retrato da carteira (`carteira.json`) e lê os relatórios que a
    # tarefa agendada do Claude deixa em `relatorios/`. Padrão: ao lado
    # da pasta do projeto ("Dashboard Financeiro/claude-analises").
    insights_dir: Path = Path(__file__).resolve().parents[4] / "claude-analises"
    # Pasta Entrada: extratos e faturas soltos aqui são carregados pelo
    # botão "Carregar a pasta Entrada" (ou pelo iniciador). Padrão: ao
    # lado da pasta do projeto ("Dashboard Financeiro/Entrada").
    inbox_dir: Path = Path(__file__).resolve().parents[4] / "Entrada"

    @model_validator(mode="after")
    def _segredo_de_desenvolvimento_so_em_ambiente_local(self) -> Settings:
        """O segredo HMAC padrão está no código-fonte: quem o conhece
        forja a assinatura de qualquer lote de importação. Fora de
        desenvolvimento/teste a aplicação se recusa a subir com ele.
        """
        if (
            self.environment not in _LOCAL_ENVIRONMENTS
            and self.import_hmac_secret == _DEV_IMPORT_HMAC_SECRET
        ):
            raise ValueError(
                "IMPORT_HMAC_SECRET precisa ser definido fora de development/test — "
                "o valor padrão é público (está no código-fonte)"
            )
        return self


settings = Settings()
