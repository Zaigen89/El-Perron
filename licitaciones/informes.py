"""Textos compactos para leer (ella o Claude): resumen diario y ficha de una licitación.

Están pensados para gastar pocos tokens: solo los campos útiles, sin el JSON crudo.
"""
from datetime import datetime

from .api import FICHA_URL
from .filtro import fecha

FECHAS = [
    ("FechaPublicacion", "Publicación"),
    ("FechaFinal", "Cierre de preguntas"),
    ("FechaPubRespuestas", "Publicación de respuestas"),
    ("FechaVisitaTerreno", "Visita a terreno"),
    ("FechaCierre", "Cierre de ofertas"),
    ("FechaActoAperturaTecnica", "Apertura técnica"),
    ("FechaEstimadaAdjudicacion", "Adjudicación estimada"),
]


def _f(valor):
    d = fecha(valor)
    return d.strftime("%d-%m-%Y %H:%M") if d else "—"


def _monto(detalle):
    monto = detalle.get("MontoEstimado")
    if not monto:
        return "no informado"
    return f"${monto:,.0f} {detalle.get('Moneda') or ''}".replace(",", ".").strip()


def _limpio(texto, largo=None):
    texto = " ".join(str(texto or "").split())
    return texto[:largo] + "…" if largo and len(texto) > largo else texto


def resumen(filas, hoy=None):
    """filas: lista de (fila_bd, detalle) ya ordenada por puntos."""
    hoy = hoy or datetime.now()
    lineas = [f"# Licitaciones que calzan — {hoy:%d-%m-%Y %H:%M}", ""]
    if not filas:
        lineas.append("Hoy no hay licitaciones abiertas que calcen con el perfil.")
        return "\n".join(lineas) + "\n"
    lineas.append(f"{len(filas)} licitaciones, de más a menos afines. Para preparar una: `/oferta CODIGO` en Claude Code.")
    for fila, det in filas:
        comprador = det.get("Comprador") or {}
        cierre = fecha(det.get("FechaCierre"))
        dias = f" (en {(cierre - hoy).days} días)" if cierre else ""
        nueva = " 🆕" if (fila["visto_primera_vez"] or "")[:10] == hoy.strftime("%Y-%m-%d") else ""
        lineas += [
            "",
            f"## {fila['puntos']:.0f} pts · {det.get('Nombre')}{nueva}",
            f"- Código: `{fila['codigo']}` · Tipo {det.get('Tipo') or '—'} · Monto: {_monto(det)}",
            f"- Comprador: {comprador.get('NombreOrganismo') or '—'} ({comprador.get('RegionUnidad') or '—'})",
            f"- Cierre: {_f(det.get('FechaCierre'))}{dias}",
            f"- Por qué: {fila['motivos']}",
            f"- {_limpio(det.get('Descripcion'), 280)}",
            f"- Ficha: {FICHA_URL.format(codigo=fila['codigo'])}",
        ]
    return "\n".join(lineas) + "\n"


def ficha(detalle):
    """Ficha de una licitación con lo que sirve para decidir y para armar la oferta."""
    c = detalle.get("Comprador") or {}
    fechas = detalle.get("Fechas") or {}
    codigo = detalle.get("CodigoExterno")
    lineas = [
        f"# {detalle.get('Nombre')}",
        "",
        f"- Código: {codigo} · Tipo: {detalle.get('Tipo') or '—'} · Estado: {detalle.get('Estado') or '—'}",
        f"- Monto estimado: {_monto(detalle)}",
        f"- Organismo: {c.get('NombreOrganismo') or '—'} · Unidad: {c.get('NombreUnidad') or '—'}",
        f"- Región/comuna: {c.get('RegionUnidad') or '—'} / {c.get('ComunaUnidad') or '—'}",
        f"- Ficha y adjuntos (bases): {FICHA_URL.format(codigo=codigo)}",
        "",
        "## Fechas",
    ]
    for clave, etiqueta in FECHAS:
        valor = fechas.get(clave) or (detalle.get(clave) if clave == "FechaCierre" else None)
        if valor:
            lineas.append(f"- {etiqueta}: {_f(valor)}")
    extras = [
        ("Duración del contrato", detalle.get("TiempoDuracionContrato") and
         f"{detalle.get('TiempoDuracionContrato')} {detalle.get('UnidadTiempoDuracionContrato') or ''}"),
        ("Visita a terreno obligatoria", detalle.get("VisitaTerreno") and "sí"),
        ("Subcontratación permitida", detalle.get("SubContratacion") in (1, "1", True) and "sí"),
        ("Garantía de seriedad", detalle.get("MontoGarantiaSeriedad") or None),
        ("Contacto", detalle.get("NombreResponsableContrato") or detalle.get("NombreResponsablePago")),
    ]
    extras = [(k, v) for k, v in extras if v]
    if extras:
        lineas += ["", "## Condiciones"] + [f"- {k}: {_limpio(v)}" for k, v in extras]
    lineas += ["", "## Descripción", _limpio(detalle.get("Descripcion")) or "—", "", "## Ítems"]
    for i in (detalle.get("Items") or {}).get("Listado") or []:
        lineas.append(
            f"- {i.get('Cantidad') or ''} {i.get('UnidadMedida') or ''} · {i.get('NombreProducto') or ''}"
            f" [{i.get('CodigoCategoria') or ''}] — {_limpio(i.get('Descripcion'), 600)}"
        )
    return "\n".join(lineas) + "\n"
