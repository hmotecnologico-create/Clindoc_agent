# -*- coding: utf-8 -*-
"""Cifrado AES-256-GCM para datos clínicos sensibles en la persistencia local (RGPD).

Módulo ligero (solo cryptography + hashlib) para que lo usen tanto el pipeline como la
interfaz sin arrastrar dependencias pesadas. Clave de 32 bytes (=AES-256) derivada por
SHA-256; nonce aleatorio por mensaje; cifrado autenticado (GCM).
"""
import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CifradoClinDoc:
    def __init__(self, clave: str = "clinDoc_Sovereign_2026"):
        self.key = hashlib.sha256(clave.encode()).digest()  # 32 bytes = AES-256
        self.aes = AESGCM(self.key)

    def cifrar(self, data: str) -> str:
        nonce = os.urandom(12)
        ct = self.aes.encrypt(nonce, data.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def descifrar(self, token: str) -> str:
        raw = base64.b64decode(token)
        return self.aes.decrypt(raw[:12], raw[12:], None).decode("utf-8")
