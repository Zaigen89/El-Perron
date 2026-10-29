"""Uso: python -m licitaciones <comando>. Ver README.md."""
import argparse
import subprocess
import sys
from datetime import datetime

from . import bases, config, exportar, informes
from .api import ErrorAPI, MercadoPublico
from .db import BD, ahora
from .filtro import Filtro


def bd():
    return BD(config.DATOS / "licitaciones.db")


def escribir_resumen(base, filtro, marca, max_en_resumen):
    filas = []
    for fila in base.vistas_en(marca):
        det = base.detalle(fila["codigo"])
        if not det or fila["decision"] == "descartada":
            continue
        puntos, motivos, descarte = filtro.evaluar(det)
        base.guardar_evaluacion(fila["codigo"], puntos, motivos, descarte)
        if descarte is None:
            filas.append(fila["codigo"])
    base.commit()
    filas = sorted((base.obtener(c) for c in filas), key=lambda f: -f["puntos"])[:max_en_resumen]
    texto = informes.resumen([(f, base.detalle(f["codigo"])) for f in filas])
    config.SALIDA.mkdir(exist_ok=True)
    (config.SALIDA / "resumen.md").write_text(texto, encoding="utf-8")
    hoy = datetime.now().strftime("%Y-%m-%d")
    nuevas = sum(1 for f in filas if (f["visto_primera_vez"] or "").startswith(hoy))
    return len(filas), nuevas


def notificar(mensaje):
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{mensaje}" with title "Licitaciones 100 Modos"'],
                       check=False)


def cmd_actualizar(args):
    perfil = config.cargar_perfil()
    filtro = Filtro(perfil)
    api = MercadoPublico(config.ticket())
    base = bd()
    marca = ahora()
    try:
        activas = api.activas()
    except ErrorAPI as e:
        raise SystemExit(f"Mercado Público respondió con error: {e}")
    nuevas = base.registrar_activas(activas)
    candidatas = [l["CodigoExterno"] for l in activas
                  if l.get("CodigoExterno") and filtro.interesa_por_nombre(l.get("Nombre"))]
    sin_detalle = [c for c in candidatas if base.detalle(c) is None]
    tope = perfil.get("max_detalles_por_corrida", 300)
    print(f"{len(activas)} activas ({nuevas} nuevas) · {len(candidatas)} pasan el filtro por nombre · "
          f"{len(sin_detalle)} sin detalle (se piden hasta {tope})")
    errores = 0
    for n, codigo in enumerate(sin_detalle[:tope], 1):
        try:
            det = api.detalle(codigo)
        except ErrorAPI as e:
            errores += 1
            print(f"  {codigo}: {e}")
            if errores >= 5:
                print("  Demasiados errores seguidos; se sigue con lo que hay.")
                break
            continue
        if det:
            base.guardar_detalle(codigo, det)
        if n % 25 == 0:
            print(f"  {n}/{min(len(sin_detalle), tope)} detalles…")
    total, nuevas_resumen = escribir_resumen(base, filtro, marca, perfil.get("max_en_resumen", 25))
    print(f"Listo: {total} calzan ({nuevas_resumen} nuevas hoy). Ver salida/resumen.md · {api.peticiones} peticiones a la API")
    if args.notificar:
        notificar(f"{total} licitaciones calzan, {nuevas_resumen} nuevas hoy")


def cmd_resumen(args):
    """Recalcula el resumen con la BD local (sin API): útil tras editar config/perfil.yaml."""
    perfil = config.cargar_perfil()
    base = bd()
    marca = base.con.execute("SELECT MAX(visto_ultima_vez) FROM licitaciones").fetchone()[0]
    if not marca:
        raise SystemExit("La base está vacía: corre primero `python -m licitaciones actualizar`.")
    total, nuevas = escribir_resumen(base, Filtro(perfil), marca, perfil.get("max_en_resumen", 25))
    print(f"{total} calzan ({nuevas} nuevas hoy). Ver salida/resumen.md")


def carpeta(codigo):
    return config.OFERTAS / codigo.strip()


def cmd_preparar(args):
    base = bd()
    codigo = args.codigo.strip()
    det = base.detalle(codigo)
    if det is None or args.refrescar:
        det = MercadoPublico(config.ticket()).detalle(codigo)
        if not det:
            raise SystemExit(f"No existe la licitación {codigo} en Mercado Público.")
        base.guardar_detalle(codigo, det)
    destino = carpeta(codigo)
    (destino / "bases").mkdir(parents=True, exist_ok=True)
    (destino / "borradores").mkdir(exist_ok=True)
    (destino / "ficha.md").write_text(informes.ficha(det), encoding="utf-8")
    leeme = destino / "bases" / "LEEME.txt"
    if not leeme.exists():
        leeme.write_text("Descarga aquí las bases y anexos desde la ficha de Mercado Público (PDF o Word).\n"
                         "Luego: python -m licitaciones bases " + codigo + "\n", encoding="utf-8")
    base.marcar(codigo, "preparando")
    print(f"Carpeta lista: {destino}")
    print(f"- ficha.md · enlace a bases: {informes.FICHA_URL.format(codigo=codigo)}")
    estado = bases.procesar(destino)
    if estado:
        print(f"- bases procesadas: {estado['archivos']} archivos, {estado['caracteres_total']:,} → "
              f"{estado['caracteres_resumen']:,} caracteres en bases_resumen.md")
    else:
        print(f"- FALTAN LAS BASES: descárgalas en {destino / 'bases'} y corre `python -m licitaciones bases {codigo}`")


def cmd_bases(args):
    estado = bases.procesar(carpeta(args.codigo))
    if not estado:
        raise SystemExit(f"No hay PDF/Word en {carpeta(args.codigo) / 'bases'}")
    ahorro = 100 * (1 - estado["caracteres_resumen"] / max(estado["caracteres_total"], 1))
    print(f"{estado['archivos']} archivos: {estado['caracteres_total']:,} → {estado['caracteres_resumen']:,} caracteres "
          f"(-{ahorro:.0f}%). Ver bases_resumen.md")


def cmd_exportar(args):
    hechos = exportar.exportar_carpeta(carpeta(args.codigo))
    if not hechos:
        raise SystemExit("No hay borradores .md en la carpeta borradores/")
    for h in hechos:
        print(f"- {h}")


def cmd_marcar(args):
    bd().marcar(args.codigo.strip(), args.decision)
    print(f"{args.codigo}: {args.decision}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="licitaciones", description="Licitaciones de Mercado Público para 100 Modos")
    sub = p.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("actualizar", help="descarga activas, filtra y escribe salida/resumen.md")
    s.add_argument("--notificar", action="store_true", help="aviso de macOS al terminar")
    s.set_defaults(fn=cmd_actualizar)
    sub.add_parser("resumen", help="recalcula el resumen sin llamar a la API").set_defaults(fn=cmd_resumen)
    s = sub.add_parser("preparar", help="crea ofertas/CODIGO con la ficha y carpeta para las bases")
    s.add_argument("codigo")
    s.add_argument("--refrescar", action="store_true", help="vuelve a pedir el detalle a la API")
    s.set_defaults(fn=cmd_preparar)
    s = sub.add_parser("bases", help="extrae y recorta el texto de las bases descargadas")
    s.add_argument("codigo")
    s.set_defaults(fn=cmd_bases)
    s = sub.add_parser("exportar", help="convierte borradores/*.md a Word en para_subir/")
    s.add_argument("codigo")
    s.set_defaults(fn=cmd_exportar)
    s = sub.add_parser("marcar", help="registra la decisión sobre una licitación")
    s.add_argument("codigo")
    s.add_argument("decision", choices=["descartada", "preparando", "postulada", "ganada", "perdida"])
    s.set_defaults(fn=cmd_marcar)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
