"""Cliente mínimo de la API pública de Mercado Público (ChileCompra).

Documentación oficial: https://api.mercadopublico.cl  (requiere ticket gratuito).
La API rechaza peticiones simultáneas con el mismo ticket, por eso todo va en serie y con pausa.
"""
import time

import requests

BASE = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
FICHA_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"


class ErrorAPI(Exception):
    pass


class MercadoPublico:
    def __init__(self, ticket, pausa=1.0, reintentos=4, session=None):
        self.ticket = ticket
        self.pausa = pausa
        self.reintentos = reintentos
        self.session = session or requests.Session()
        self.peticiones = 0

    def _get(self, params):
        params = {**params, "ticket": self.ticket}
        espera = 2.0
        for intento in range(self.reintentos + 1):
            if self.peticiones:
                time.sleep(self.pausa)
            self.peticiones += 1
            try:
                r = self.session.get(BASE, params=params, timeout=90)
            except requests.RequestException as e:
                error = f"sin conexión: {e}"
            else:
                if r.status_code >= 500:
                    error = f"HTTP {r.status_code}"
                else:
                    try:
                        datos = r.json()
                    except ValueError:
                        raise ErrorAPI(f"respuesta no es JSON (HTTP {r.status_code}): {r.text[:200]}")
                    if "Listado" in datos:
                        return datos
                    mensaje = str(datos.get("Mensaje") or datos)
                    if "simult" not in mensaje.lower():
                        raise ErrorAPI(mensaje)
                    error = mensaje
            if intento < self.reintentos:
                time.sleep(espera)
                espera *= 2
        raise ErrorAPI(f"falló tras {self.reintentos + 1} intentos: {error}")

    def activas(self):
        """Todas las licitaciones publicadas (abiertas). Solo trae código, nombre, estado y fecha de cierre."""
        return self._get({"estado": "activas"}).get("Listado") or []

    def detalle(self, codigo):
        """Ficha completa de una licitación: comprador, descripción, ítems, fechas, montos."""
        listado = self._get({"codigo": codigo}).get("Listado") or []
        return listado[0] if listado else None
