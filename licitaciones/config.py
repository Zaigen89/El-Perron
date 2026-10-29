"""Rutas del proyecto y carga de configuración (perfil, empresa, ticket)."""
import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDA = RAIZ / "salida"
OFERTAS = RAIZ / "ofertas"
CONFIG = RAIZ / "config"
PLANTILLAS = RAIZ / "plantillas"


def cargar_yaml(nombre):
    with open(CONFIG / nombre, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cargar_perfil():
    return cargar_yaml("perfil.yaml")


def _leer_env():
    ruta = RAIZ / ".env"
    if not ruta.exists():
        return {}
    valores = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def ticket():
    valor = os.environ.get("MP_TICKET") or _leer_env().get("MP_TICKET")
    if not valor:
        raise SystemExit(
            "Falta el ticket de Mercado Público. Pídelo gratis en https://api.mercadopublico.cl "
            "(botón para solicitar ticket, entra con ClaveÚnica) y pégalo en el archivo .env como MP_TICKET=..."
        )
    return valor
