"""Filtro y puntaje sin IA: palabras clave, exclusiones, monto, región y plazo (0 tokens)."""
import re
import unicodedata
from datetime import datetime


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _patron(palabras):
    """Cada palabra clave calza al inicio de una palabra: 'capacitaci' calza con capacitación/capacitaciones."""
    palabras = [normalizar(p) for p in palabras or [] if p]
    if not palabras:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in sorted(palabras, key=len, reverse=True)) + ")")


def _coincidencias(patron, texto):
    return sorted(set(patron.findall(texto))) if patron and texto else []


def fecha(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).split(".")[0].replace("Z", ""))
    except ValueError:
        return None


class Filtro:
    def __init__(self, perfil):
        self.perfil = perfil
        self.formato = _patron(perfil.get("formato"))
        self.temas = _patron(perfil.get("temas"))
        self.excluir = _patron(perfil.get("excluir"))
        self.categorias = [str(c) for c in perfil.get("categorias_unspsc") or []]
        self.regiones = [normalizar(r) for r in perfil.get("regiones") or []]
        self.monto_min = perfil.get("monto_minimo") or 0
        self.monto_max = perfil.get("monto_maximo") or 0
        self.dias_min = perfil.get("dias_minimos_para_preparar", 0)

    def interesa_por_nombre(self, nombre):
        """Primer cedazo con lo que trae el listado de activas (solo nombre). Decide si vale pedir el detalle."""
        n = normalizar(nombre)
        if _coincidencias(self.excluir, n):
            return False
        return bool(_coincidencias(self.formato, n) or _coincidencias(self.temas, n))

    def evaluar(self, detalle, hoy=None):
        """Devuelve (puntos, motivos, descarte). descarte es None si la licitación sigue en carrera."""
        hoy = hoy or datetime.now()
        nombre = normalizar(detalle.get("Nombre"))
        items = (detalle.get("Items") or {}).get("Listado") or []
        cuerpo = normalizar(" ".join(
            [str(detalle.get("Descripcion") or "")]
            + [f"{i.get('NombreProducto') or ''} {i.get('Descripcion') or ''} {i.get('Categoria') or ''}" for i in items]
        ))
        motivos = []

        excl = _coincidencias(self.excluir, nombre)
        if excl:
            return 0, motivos, f"excluida por: {', '.join(excl)}"

        cierre = fecha(detalle.get("FechaCierre") or (detalle.get("Fechas") or {}).get("FechaCierre"))
        if cierre:
            dias = (cierre - hoy).total_seconds() / 86400
            if dias < 0:
                return 0, motivos, "ya cerró"
            if dias < self.dias_min:
                return 0, motivos, f"cierra en {dias:.1f} días (mínimo {self.dias_min})"

        monto = detalle.get("MontoEstimado") or 0
        if monto and self.monto_min and monto < self.monto_min:
            return 0, motivos, f"monto {monto:,.0f} bajo el mínimo"
        if monto and self.monto_max and monto > self.monto_max:
            return 0, motivos, f"monto {monto:,.0f} sobre el máximo"

        if self.regiones:
            region = normalizar((detalle.get("Comprador") or {}).get("RegionUnidad"))
            if region and not any(r in region for r in self.regiones):
                return 0, motivos, f"región fuera de alcance ({region})"

        f_nombre, f_cuerpo = _coincidencias(self.formato, nombre), _coincidencias(self.formato, cuerpo)
        t_nombre, t_cuerpo = _coincidencias(self.temas, nombre), _coincidencias(self.temas, cuerpo)
        cats = sorted({str(i.get("CodigoCategoria") or "") for i in items
                       if any(str(i.get("CodigoCategoria") or "").startswith(c) for c in self.categorias)})

        if not (f_nombre or f_cuerpo or cats):
            return 0, motivos, "no es capacitación, charla ni taller"
        if not (t_nombre or t_cuerpo):
            return 0, motivos, "ningún tema afín"

        puntos = 3 * min(len(f_nombre), 2) + min(len(f_cuerpo), 3)
        puntos += 3 * min(len(t_nombre), 3) + min(len(t_cuerpo), 4)
        if cats:
            puntos += 2
            motivos.append(f"categoría {', '.join(cats)}")
        formatos = sorted(set(f_nombre) | set(f_cuerpo))
        temas = sorted(set(t_nombre) | set(t_cuerpo))
        if formatos:
            motivos.append("formato: " + ", ".join(formatos))
        motivos.append("temas: " + ", ".join(temas))
        return puntos, motivos, None
