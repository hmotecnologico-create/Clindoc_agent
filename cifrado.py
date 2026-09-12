# -*- coding: utf-8 -*-
"""Cifrado AES-256-GCM para la huella de auditoría del facultativo (RGPD).

Módulo ligero (solo cryptography + hashlib) para que lo usen tanto el pipeline como la
interfaz sin arrastrar dependencias pesadas. Clave de 32 bytes (=AES-256) derivada por
SHA-256; nonce aleatorio por mensaje; cifrado autenticado (GCM).

Alcance: solo la huella de auditoría de la historia YA VALIDADA por el facultativo
(`utils/ui_helpers.py::registrar_validacion_facultativo`, `datos/historias_validadas/*.enc`)
pasa por este módulo. El estado intermedio del pipeline (`dashboard_data.json`,
`datos/auditorias/*.json`) se persiste en JSON plano y NO está cubierto por este cifrado.
"""
import os
import base64
import hashlib
import warnings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CLAVE_DEMO_PUBLICA = "clinDoc_Sovereign_2026"


class CifradoClinDoc:
    def __init__(self, clave: str = None):
        # La clave por defecto solo existe para que el sistema funcione "out of the box"
        # en una evaluación/demo (ver Anexo E de reproducibilidad); al ser un valor literal
        # en el código fuente público, no aporta confidencialidad real. Un despliegue real
        # debe fijar CLINDOC_CIFRADO_KEY a un secreto propio del entorno.
        clave = clave or os.environ.get("CLINDOC_CIFRADO_KEY")
        if not clave:
            warnings.warn(
                "CLINDOC_CIFRADO_KEY no está definida: se está usando la clave pública de "
                "demo/evaluación (ver Anexo E). Cualquier .enc cifrado con ella es legible por "
                "cualquiera que haya visto el código fuente público. Definir CLINDOC_CIFRADO_KEY "
                "con un secreto propio antes de usar este módulo con datos clínicos reales.",
                stacklevel=2,
            )
            clave = _CLAVE_DEMO_PUBLICA
        self.key = hashlib.sha256(clave.encode()).digest()  # 32 bytes = AES-256
        self.aes = AESGCM(self.key)

    def cifrar(self, data: str) -> str:
        nonce = os.urandom(12)
        ct = self.aes.encrypt(nonce, data.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def descifrar(self, token: str) -> str:
        raw = base64.b64decode(token)
        return self.aes.decrypt(raw[:12], raw[12:], None).decode("utf-8")
