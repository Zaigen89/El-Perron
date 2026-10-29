"""Base de datos local (SQLite): guarda lo descargado para no volver a pedirlo a la API."""
import json
import sqlite3
from datetime import datetime

ESQUEMA = """
CREATE TABLE IF NOT EXISTS licitaciones (
    codigo TEXT PRIMARY KEY,
    nombre TEXT,
    fecha_cierre TEXT,
    visto_primera_vez TEXT,
    visto_ultima_vez TEXT,
    detalle_json TEXT,
    detalle_en TEXT,
    puntos REAL,
    motivos TEXT,
    descarte TEXT,
    decision TEXT
);
"""


def ahora():
    return datetime.now().isoformat(timespec="seconds")


class BD:
    def __init__(self, ruta):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)

    def registrar_activas(self, listado):
        t = ahora()
        nuevas = 0
        for lic in listado:
            codigo = lic.get("CodigoExterno")
            if not codigo:
                continue
            cur = self.con.execute(
                "UPDATE licitaciones SET nombre=?, fecha_cierre=?, visto_ultima_vez=? WHERE codigo=?",
                (lic.get("Nombre"), lic.get("FechaCierre"), t, codigo),
            )
            if cur.rowcount == 0:
                self.con.execute(
                    "INSERT INTO licitaciones (codigo, nombre, fecha_cierre, visto_primera_vez, visto_ultima_vez)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (codigo, lic.get("Nombre"), lic.get("FechaCierre"), t, t),
                )
                nuevas += 1
        self.con.commit()
        return nuevas

    def obtener(self, codigo):
        return self.con.execute("SELECT * FROM licitaciones WHERE codigo=?", (codigo,)).fetchone()

    def detalle(self, codigo):
        fila = self.obtener(codigo)
        return json.loads(fila["detalle_json"]) if fila and fila["detalle_json"] else None

    def guardar_detalle(self, codigo, detalle):
        self.con.execute(
            "INSERT INTO licitaciones (codigo, nombre, visto_primera_vez) VALUES (?, ?, ?)"
            " ON CONFLICT(codigo) DO NOTHING",
            (codigo, detalle.get("Nombre"), ahora()),
        )
        self.con.execute(
            "UPDATE licitaciones SET detalle_json=?, detalle_en=?, fecha_cierre=COALESCE(?, fecha_cierre) WHERE codigo=?",
            (json.dumps(detalle, ensure_ascii=False), ahora(), detalle.get("FechaCierre"), codigo),
        )
        self.con.commit()

    def guardar_evaluacion(self, codigo, puntos, motivos, descarte):
        self.con.execute(
            "UPDATE licitaciones SET puntos=?, motivos=?, descarte=? WHERE codigo=?",
            (puntos, "; ".join(motivos), descarte, codigo),
        )

    def marcar(self, codigo, decision):
        self.con.execute("UPDATE licitaciones SET decision=? WHERE codigo=?", (decision, codigo))
        self.con.commit()

    def vistas_en(self, marca):
        """Licitaciones vistas como activas en la última descarga (marca = visto_ultima_vez de esa corrida)."""
        return self.con.execute("SELECT * FROM licitaciones WHERE visto_ultima_vez >= ?", (marca,)).fetchall()

    def commit(self):
        self.con.commit()
