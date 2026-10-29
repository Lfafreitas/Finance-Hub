"""Trava do acesso remoto (Face ID): o celular só vê dado com sessão aberta
por passkey; cadastrar aparelho exige código gerado no computador.

As respostas WebAuthn são assinadas de verdade (tests/webauthn_helpers.py)
e verificadas pela mesma biblioteca de produção.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.base import utcnow
from app.models.passkey import AuthSession, Passkey
from app.services import auth_service
from tests.webauthn_helpers import SoftAuthenticator

HOST = "meupc.tail1234.ts.net"
ORIGIN = f"https://{HOST}"
PHONE = {
    "X-Dashboard-Client-Host": HOST,
    "X-Forwarded-For": "100.101.102.103",
    "Tailscale-User-Login": "dono@example.com",
}
DESKTOP = {"X-Dashboard-Client-Host": "localhost:5173"}
PROTECTED = [
    "/overview",
    "/dashboard/summary",
    "/insights",
    "/insights/chat-context",
    "/cashflow/entries",
    "/performance/kpis",
    "/accounts",
]


@pytest.fixture(autouse=True)
def _clean_challenges():
    auth_service.reset_challenges()
    yield
    auth_service.reset_challenges()


def cookie_of(response) -> str:
    raw = response.headers["set-cookie"]
    assert raw.startswith(f"{auth_service.SESSION_COOKIE}=")
    return raw.split(";", 1)[0].split("=", 1)[1]


def phone(token: str | None = None) -> dict:
    headers = dict(PHONE)
    if token:
        headers["Cookie"] = f"{auth_service.SESSION_COOKIE}={token}"
    return headers


def pair(client) -> str:
    response = client.post("/auth/pairing", headers=DESKTOP)
    assert response.status_code == 200, response.text
    return response.json()["code"]


def register(client, device: SoftAuthenticator, code: str, origin: str = ORIGIN):
    options = client.post("/auth/register/options", json={"code": code}, headers=phone())
    assert options.status_code == 200, options.text
    body = options.json()
    credential = device.register(body["options"], origin)
    return client.post(
        "/auth/register/verify",
        json={
            "challenge_id": body["challenge_id"],
            "code": code,
            "credential": credential,
            "name": "iPhone 16e",
        },
        headers=phone(),
    )


def login(client, device: SoftAuthenticator, origin: str = ORIGIN):
    options = client.post("/auth/login/options", headers=phone())
    assert options.status_code == 200, options.text
    body = options.json()
    credential = device.login(body["options"], origin)
    return client.post(
        "/auth/login/verify",
        json={"challenge_id": body["challenge_id"], "credential": credential},
        headers=phone(),
    )


class TestTrava:
    @pytest.mark.parametrize("path", PROTECTED)
    def test_celular_sem_face_id_nao_ve_nada(self, api_client, path):
        client, _user = api_client
        response = client.get(path, headers=phone())
        assert response.status_code == 401
        assert "Face ID" in response.json()["detail"]

    @pytest.mark.parametrize("path", PROTECTED)
    def test_computador_abre_direto(self, api_client, path):
        client, _user = api_client
        assert client.get(path).status_code == 200  # widget/iniciador
        assert client.get(path, headers=DESKTOP).status_code == 200  # navegador local

    def test_sessao_inventada_nao_passa(self, api_client):
        client, _user = api_client
        assert client.get("/overview", headers=phone("inventado")).status_code == 401

    def test_status_e_saude_ficam_abertos(self, api_client):
        client, _user = api_client
        assert client.get("/health", headers=phone()).status_code == 200
        status = client.get("/auth/status", headers=phone()).json()
        assert status == {
            "remote": True,
            "unlocked": False,
            "has_passkeys": False,
            "idle_minutes": 15,
        }
        assert client.get("/auth/status", headers=DESKTOP).json()["unlocked"] is True

    def test_documentacao_da_api_so_no_computador(self, api_client):
        client, _user = api_client
        assert client.get("/docs", headers=phone()).status_code == 404
        assert client.get("/openapi.json", headers=phone()).status_code == 404
        assert client.get("/openapi.json").status_code == 200

    def test_respostas_nao_ficam_em_cache(self, api_client):
        client, _user = api_client
        response = client.get("/overview")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


class TestCadastroDoIphone:
    def test_codigo_so_pelo_computador(self, api_client):
        client, _user = api_client
        # Sem Face ID nem chega lá (401); com Face ID, recusado (403, outro teste).
        assert client.post("/auth/pairing", headers=phone()).status_code == 401
        code = pair(client)
        assert len(code) == 9 and code[4] == "-"
        assert not set(code.replace("-", "")) & set("01OIL")

    def test_cadastro_completo_abre_sessao_segura(self, api_client, db_session):
        client, _user = api_client
        response = register(client, SoftAuthenticator(), pair(client))

        assert response.status_code == 200, response.text
        assert response.json()["unlocked"] is True and response.json()["has_passkeys"] is True
        raw = response.headers["set-cookie"].lower()
        assert "httponly" in raw and "secure" in raw and "samesite=strict" in raw
        token = cookie_of(response)
        assert client.get("/overview", headers=phone(token)).status_code == 200
        # Só o hash da sessão fica no banco; da passkey, só a chave pública.
        session = db_session.scalars(select(AuthSession)).one()
        assert session.token_hash != token and len(session.token_hash) == 64
        passkey = db_session.scalars(select(Passkey)).one()
        assert (passkey.name, passkey.rp_id) == ("iPhone 16e", HOST)

    def test_codigo_vale_para_um_aparelho_so(self, api_client):
        client, _user = api_client
        code = pair(client)
        assert register(client, SoftAuthenticator(), code).status_code == 200
        again = client.post("/auth/register/options", json={"code": code}, headers=phone())
        assert again.status_code == 400

    def test_sem_codigo_gerado_ninguem_cadastra(self, api_client):
        client, _user = api_client
        response = client.post(
            "/auth/register/options", json={"code": "ABCD-EFGH"}, headers=phone()
        )
        assert response.status_code == 400
        assert "Gere um novo no computador" in response.json()["detail"]

    def test_cinco_erros_bloqueiam_o_codigo(self, api_client):
        client, _user = api_client
        code = pair(client)
        details = [
            client.post(
                "/auth/register/options", json={"code": "ZZZZ-ZZZZ"}, headers=phone()
            ).json()["detail"]
            for _ in range(5)
        ]
        assert details[0] == "Código errado. Restam 4 tentativa(s)."
        assert details[-1] == "Código bloqueado. Gere um novo."
        right = client.post("/auth/register/options", json={"code": code}, headers=phone())
        assert right.status_code == 400 and "bloqueado" in right.json()["detail"]

    def test_codigo_aceita_minusculas_e_sem_traco(self, api_client):
        client, _user = api_client
        code = pair(client).replace("-", "").lower()
        assert register(client, SoftAuthenticator(), code).status_code == 200

    def test_codigo_vencido(self, api_client, db_session):
        client, user = api_client
        code = pair(client)
        from app.models.passkey import PairingCode

        db_session.get(PairingCode, user.id).expires_at = utcnow() - timedelta(seconds=1)
        db_session.flush()
        assert (
            client.post("/auth/register/options", json={"code": code}, headers=phone()).status_code
            == 400
        )

    def test_resposta_de_outro_site_e_recusada(self, api_client, db_session):
        client, _user = api_client
        response = register(
            client, SoftAuthenticator(), pair(client), origin="https://evil.example.com"
        )
        assert response.status_code == 400
        assert db_session.scalars(select(Passkey)).all() == []

    def test_sem_face_id_confirmado_e_recusado(self, api_client, db_session):
        client, _user = api_client
        response = register(client, SoftAuthenticator(user_verified=False), pair(client))
        assert response.status_code == 400
        assert db_session.scalars(select(Passkey)).all() == []

    def test_pelo_computador_nao_cadastra(self, api_client):
        client, _user = api_client
        code = pair(client)
        response = client.post("/auth/register/options", json={"code": code}, headers=DESKTOP)
        assert response.status_code == 400 and "celular" in response.json()["detail"]


class TestDesbloqueio:
    @pytest.fixture()
    def device(self, api_client):
        client, _user = api_client
        device = SoftAuthenticator()
        assert register(client, device, pair(client)).status_code == 200
        return device

    def test_face_id_abre_e_bloquear_fecha(self, api_client, device):
        client, _user = api_client
        response = login(client, device)
        assert response.status_code == 200, response.text
        token = cookie_of(response)
        assert client.get("/overview", headers=phone(token)).status_code == 200

        assert client.post("/auth/logout", headers=phone(token)).status_code == 204
        assert client.get("/overview", headers=phone(token)).status_code == 401

    def test_desafio_vale_uma_vez(self, api_client, device):
        client, _user = api_client
        body = client.post("/auth/login/options", headers=phone()).json()
        credential = device.login(body["options"], ORIGIN)
        payload = {"challenge_id": body["challenge_id"], "credential": credential}
        assert client.post("/auth/login/verify", json=payload, headers=phone()).status_code == 200
        # Mesmo desafio, assinatura nova e válida: recusado (o desafio já foi usado).
        fresh = {
            "challenge_id": body["challenge_id"],
            "credential": device.login(body["options"], ORIGIN),
        }
        replay = client.post("/auth/login/verify", json=fresh, headers=phone())
        assert replay.status_code == 400 and "expirou" in replay.json()["detail"]

    def test_passkey_de_um_endereco_nao_abre_outro(self, api_client, device):
        client, _user = api_client
        other_host = "outro.tail1234.ts.net"
        other = dict(PHONE, **{"X-Dashboard-Client-Host": other_host})
        code = pair(client)
        body = client.post("/auth/register/options", json={"code": code}, headers=other).json()
        credential = SoftAuthenticator().register(body["options"], f"https://{other_host}")
        payload = {"challenge_id": body["challenge_id"], "code": code, "credential": credential}
        assert client.post("/auth/register/verify", json=payload, headers=other).status_code == 200

        body = client.post("/auth/login/options", headers=other).json()
        # A passkey cadastrada no primeiro endereço tenta abrir o segundo.
        forged = device.login(body["options"], f"https://{other_host}")
        response = client.post(
            "/auth/login/verify",
            json={"challenge_id": body["challenge_id"], "credential": forged},
            headers=other,
        )
        assert response.status_code == 400

    def test_outro_aparelho_nao_abre(self, api_client, device):
        client, _user = api_client
        assert login(client, SoftAuthenticator()).status_code == 400

    def test_assinatura_para_outro_site_nao_abre(self, api_client, device):
        client, _user = api_client
        assert login(client, device, origin="https://evil.example.com").status_code == 400

    def test_endereco_sem_aparelho_cadastrado(self, api_client, device):
        client, _user = api_client
        other = dict(PHONE, **{"X-Dashboard-Client-Host": "outro.tail1234.ts.net"})
        response = client.post("/auth/login/options", headers=other)
        assert response.status_code == 400

    def test_15_min_parado_pede_face_id_de_novo(self, api_client, db_session, device):
        client, _user = api_client
        token = cookie_of(login(client, device))
        for session in db_session.scalars(select(AuthSession)).all():
            session.last_seen_at = utcnow() - timedelta(minutes=15, seconds=1)
        db_session.flush()
        assert client.get("/overview", headers=phone(token)).status_code == 401

    def test_uso_renova_o_prazo_mas_12h_e_o_maximo(self, api_client, db_session, device):
        client, _user = api_client
        token = cookie_of(login(client, device))
        sessions = db_session.scalars(select(AuthSession)).all()
        for session in sessions:
            session.last_seen_at = utcnow() - timedelta(minutes=14)
        db_session.flush()
        assert client.get("/overview", headers=phone(token)).status_code == 200
        used = next(x for x in sessions if x.token_hash == auth_service._hash(token))
        db_session.refresh(used)
        assert used.last_seen_at > utcnow() - timedelta(minutes=1)  # renovou
        for session in sessions:
            session.expires_at = utcnow() - timedelta(seconds=1)
        db_session.flush()
        assert client.get("/overview", headers=phone(token)).status_code == 401

    def test_gerenciar_aparelhos_so_pelo_computador(self, api_client, device):
        client, _user = api_client
        token = cookie_of(login(client, device))
        assert client.get("/auth/passkeys", headers=phone(token)).status_code == 403
        assert client.post("/auth/sessions/revoke-all", headers=phone(token)).status_code == 403
        assert client.post("/auth/pairing", headers=phone(token)).status_code == 403
        (item,) = client.get("/auth/passkeys", headers=DESKTOP).json()
        assert item["name"] == "iPhone 16e" and item["last_used_at"] is not None
        assert (
            client.delete(f"/auth/passkeys/{item['id']}", headers=phone(token)).status_code == 403
        )

    def test_remover_o_aparelho_derruba_a_sessao(self, api_client, device):
        client, _user = api_client
        token = cookie_of(login(client, device))
        (item,) = client.get("/auth/passkeys").json()
        assert client.delete(f"/auth/passkeys/{item['id']}").status_code == 204
        assert client.get("/overview", headers=phone(token)).status_code == 401
        assert client.get("/auth/status", headers=phone()).json()["has_passkeys"] is False

    def test_bloquear_todos_os_aparelhos(self, api_client, device):
        client, _user = api_client
        token = cookie_of(login(client, device))
        assert client.post("/auth/sessions/revoke-all").json()["revoked"] >= 1
        assert client.get("/overview", headers=phone(token)).status_code == 401
