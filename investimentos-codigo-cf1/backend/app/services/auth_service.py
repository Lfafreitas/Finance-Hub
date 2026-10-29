"""Trava do acesso remoto: Face ID (passkey) no celular.

Fluxo:

1. No COMPUTADOR, o usuário gera um código de pareamento (8 caracteres,
   10 minutos, 5 tentativas). Só o computador gera código: quem está na
   rede não consegue cadastrar aparelho sozinho.
2. No CELULAR, ele digita o código e o iPhone cria uma passkey (Face ID).
   O servidor guarda só a chave pública.
3. A cada abertura, o celular prova que tem a passkey (Face ID) e recebe
   uma sessão: cookie HttpOnly, Secure, SameSite=Strict. A sessão expira
   após 15 min sem uso ou 12 h no total — como app de banco.

Os desafios WebAuthn vivem na memória por 5 minutos e valem uma vez só.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.remote import host_name
from app.db.base import utcnow
from app.models.passkey import AuthSession, PairingCode, Passkey

RP_NAME = "Dashboard Financeiro"
SESSION_COOKIE = "dash_session"
SESSION_IDLE = timedelta(minutes=15)
SESSION_MAX = timedelta(hours=12)
PAIRING_TTL = timedelta(minutes=10)
PAIRING_MAX_ATTEMPTS = 5
CHALLENGE_TTL = timedelta(minutes=5)
MAX_PENDING_CHALLENGES = 50
# Sem 0/O, 1/I/L: fácil de ler na tela e digitar no celular.
PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class AuthError(Exception):
    """Falha de autenticação com mensagem para a tela (nunca detalhe interno)."""


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


# --- Origem ----------------------------------------------------------------------


@dataclass(frozen=True)
class Origin:
    rp_id: str  # "meupc.tail1234.ts.net"
    origin: str  # "https://meupc.tail1234.ts.net"


def origin_for(client_host: str | None) -> Origin:
    """A passkey fica presa ao endereço HTTPS que o celular usa. Sem
    endereço, ou com endereço local, não há o que cadastrar.
    """
    if not client_host:
        raise AuthError("Abra o dashboard pelo endereço do Tailscale (https://…ts.net).")
    name = host_name(client_host)
    if not name or name in {"localhost", "127.0.0.1", "::1"}:
        raise AuthError("A trava com Face ID vale para o acesso pelo celular.")
    port = client_host.strip().lower().rsplit(":", 1)[1] if client_host.count(":") == 1 else ""
    suffix = f":{port}" if port and port != "443" else ""
    return Origin(rp_id=name, origin=f"https://{name}{suffix}")


# --- Desafios (memória, uso único) -------------------------------------------------


@dataclass
class _Challenge:
    purpose: str  # "register" | "login"
    challenge: bytes
    origin: Origin
    expires_at: datetime


_challenges: dict[str, _Challenge] = {}
_lock = threading.Lock()


def _remember(purpose: str, challenge: bytes, origin: Origin) -> str:
    now = utcnow()
    with _lock:
        for key in [k for k, c in _challenges.items() if c.expires_at < now]:
            del _challenges[key]
        if len(_challenges) >= MAX_PENDING_CHALLENGES:
            _challenges.pop(next(iter(_challenges)))
        challenge_id = secrets.token_urlsafe(24)
        _challenges[challenge_id] = _Challenge(purpose, challenge, origin, now + CHALLENGE_TTL)
    return challenge_id


def _take(challenge_id: str, purpose: str) -> _Challenge:
    with _lock:
        found = _challenges.pop(challenge_id, None)
    if found is None or found.purpose != purpose or found.expires_at < utcnow():
        raise AuthError("O pedido expirou. Tente de novo.")
    return found


def reset_challenges() -> None:
    with _lock:
        _challenges.clear()


# --- Pareamento --------------------------------------------------------------------


def start_pairing(db: Session, user_id: uuid.UUID) -> tuple[str, datetime]:
    code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
    expires_at = utcnow() + PAIRING_TTL
    db.execute(delete(PairingCode).where(PairingCode.user_id == user_id))
    db.add(PairingCode(user_id=user_id, code_hash=_hash(code), expires_at=expires_at, attempts=0))
    db.flush()
    return f"{code[:4]}-{code[4:]}", expires_at


def _check_pairing(db: Session, user_id: uuid.UUID, code: str) -> PairingCode:
    pairing = db.get(PairingCode, user_id)
    if pairing is None or pairing.expires_at < utcnow():
        raise AuthError("Nenhum código válido. Gere um novo no computador (Segurança).")
    if pairing.attempts >= PAIRING_MAX_ATTEMPTS:
        raise AuthError("Código bloqueado por tentativas erradas. Gere um novo no computador.")
    if not hmac.compare_digest(pairing.code_hash, _hash(normalize_code(code))):
        pairing.attempts += 1
        db.flush()
        left = PAIRING_MAX_ATTEMPTS - pairing.attempts
        raise AuthError(
            f"Código errado. Restam {left} tentativa(s)."
            if left
            else "Código bloqueado. Gere um novo."
        )
    return pairing


# --- Cadastro da passkey -------------------------------------------------------------


def registration_options(
    db: Session, user_id: uuid.UUID, code: str, client_host: str | None
) -> tuple[str, str]:
    origin = origin_for(client_host)
    _check_pairing(db, user_id, code)
    existing = db.scalars(select(Passkey).where(Passkey.user_id == user_id)).all()
    options = generate_registration_options(
        rp_id=origin.rp_id,
        rp_name=RP_NAME,
        user_id=user_id.bytes,
        user_name="dashboard",
        user_display_name="Dashboard Financeiro",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=p.credential_id) for p in existing],
    )
    return _remember("register", options.challenge, origin), options_to_json(options)


def finish_registration(
    db: Session,
    user_id: uuid.UUID,
    challenge_id: str,
    code: str,
    credential: dict,
    name: str,
) -> tuple[Passkey, str]:
    state = _take(challenge_id, "register")
    pairing = _check_pairing(db, user_id, code)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=state.challenge,
            expected_rp_id=state.origin.rp_id,
            expected_origin=state.origin.origin,
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
        raise AuthError("O aparelho não confirmou o Face ID. Tente de novo.") from exc
    passkey = Passkey(
        user_id=user_id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        rp_id=state.origin.rp_id,
        name=(name.strip() or "iPhone")[:60],
    )
    db.add(passkey)
    db.delete(pairing)  # o código vale para UM aparelho
    db.flush()
    return passkey, create_session(db, passkey)


# --- Desbloqueio ---------------------------------------------------------------------


def login_options(db: Session, user_id: uuid.UUID, client_host: str | None) -> tuple[str, str]:
    origin = origin_for(client_host)
    keys = db.scalars(
        select(Passkey).where(Passkey.user_id == user_id, Passkey.rp_id == origin.rp_id)
    ).all()
    if not keys:
        raise AuthError("Este endereço ainda não tem aparelho cadastrado.")
    options = generate_authentication_options(
        rp_id=origin.rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=k.credential_id) for k in keys],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return _remember("login", options.challenge, origin), options_to_json(options)


def finish_login(
    db: Session, user_id: uuid.UUID, challenge_id: str, credential: dict
) -> tuple[Passkey, str]:
    state = _take(challenge_id, "login")
    try:
        raw_id = base64url_to_bytes(str(credential.get("rawId") or credential.get("id") or ""))
    except (ValueError, TypeError) as exc:
        raise AuthError("Resposta do aparelho inválida.") from exc
    passkey = db.scalars(
        select(Passkey).where(
            Passkey.user_id == user_id,
            Passkey.credential_id == raw_id,
            Passkey.rp_id == state.origin.rp_id,
        )
    ).one_or_none()
    if passkey is None:
        raise AuthError("Este aparelho não está cadastrado (ou foi removido no computador).")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=state.challenge,
            expected_rp_id=state.origin.rp_id,
            expected_origin=state.origin.origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as exc:
        raise AuthError("O Face ID não foi confirmado. Tente de novo.") from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    db.flush()
    return passkey, create_session(db, passkey)


# --- Sessões -----------------------------------------------------------------------------


def create_session(db: Session, passkey: Passkey) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        AuthSession(
            user_id=passkey.user_id,
            passkey_id=passkey.id,
            token_hash=_hash(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_MAX,
        )
    )
    db.flush()
    return token


def valid_session(db: Session, user_id: uuid.UUID, token: str | None) -> AuthSession | None:
    """Sessão viva e do usuário certo; renova o "visto por último"."""
    if not token:
        return None
    session = db.scalars(
        select(AuthSession).where(AuthSession.token_hash == _hash(token))
    ).one_or_none()
    now = utcnow()
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at + SESSION_IDLE <= now
    ):
        return None
    session.last_seen_at = now
    db.flush()
    return session


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == _hash(token), AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )


def revoke_all(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    return result.rowcount or 0


def list_passkeys(db: Session, user_id: uuid.UUID) -> list[Passkey]:
    return list(
        db.scalars(
            select(Passkey).where(Passkey.user_id == user_id).order_by(Passkey.created_at)
        ).all()
    )


def delete_passkey(db: Session, user_id: uuid.UUID, passkey_id: uuid.UUID) -> bool:
    passkey = db.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user_id:
        return False
    db.execute(delete(AuthSession).where(AuthSession.passkey_id == passkey_id))
    db.delete(passkey)
    db.flush()
    return True


def has_passkeys(db: Session, user_id: uuid.UUID) -> bool:
    return (
        db.scalars(select(Passkey.id).where(Passkey.user_id == user_id).limit(1)).first()
        is not None
    )
