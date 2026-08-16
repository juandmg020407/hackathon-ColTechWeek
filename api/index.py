"""Punto de entrada ASGI para Vercel.

Vercel busca las funciones en api/, pero el paquete vive en backend/. Este
modulo solo agrega backend/ al path y reexporta la app que ya existe.
"""

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
