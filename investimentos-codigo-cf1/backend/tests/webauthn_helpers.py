"""Autenticador de mentira (em software) para testar a trava de verdade:
gera respostas WebAuthn assinadas com ECDSA P-256, como um iPhone faria,
e o backend as verifica com a mesma biblioteca usada em produção.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url


def b64(data: bytes) -> str:
    return bytes_to_base64url(data)


class SoftAuthenticator:
    def __init__(self, user_verified: bool = True):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.count = 0
        self.user_verified = user_verified

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,  # kty EC2
                3: -7,  # alg ES256
                -1: 1,  # crv P-256
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _flags(self, attested: bool) -> int:
        flags = 0x01  # UP: usuário presente
        if self.user_verified:
            flags |= 0x04  # UV: Face ID confirmado
        if attested:
            flags |= 0x40  # AT: dados da credencial
        return flags

    @staticmethod
    def _client_data(kind: str, challenge: str, origin: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}
        ).encode()

    def register(self, options: dict, origin: str) -> dict:
        rp_id = options["rp"]["id"]
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([self._flags(True)])
            + struct.pack(">I", self.count)
            + bytes(16)  # AAGUID
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {"clientDataJSON": b64(client_data), "attestationObject": b64(attestation)},
            "clientExtensionResults": {},
        }

    def login(self, options: dict, origin: str, rp_id: str | None = None) -> dict:
        self.count += 1
        rp_id = rp_id or options["rpId"]
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([self._flags(False)])
            + struct.pack(">I", self.count)
        )
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(self.credential_id),
            "rawId": b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }
