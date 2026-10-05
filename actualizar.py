"""Descarga el CSV de AWX (DPS-Promatic) y actualiza data/lecturas.csv y data/reciente.json."""
import csv, io, json, os, re, time
import datetime as dt
import requests

BASE = "https://www.dps-promatic.com/webapps/gprsmeteo"
STATION = os.getenv("STATION", "PERU")
COLS = ["smsc","si","was","press","wmins","wgust","dwgust","leaf","wdir","wdsd","sun","temp","dmintemp",
        "dmaxtemp","soilt","rf","drf","soilw","dp","rh","dminrh","dmaxrh","pwr","vbatt"]
PANTALLA = ["ts"] + COLS   # todos los parámetros que envía la estación
DIAS = 35   # días que la página puede mostrar en pantalla (el historial completo queda en lecturas.csv)

def _descargar_una_vez(extra, limite):
    """Un intento completo. 'limite' = segundos máximos para TODO el intento (no solo por petición)."""
    t0 = time.monotonic()
    def restante(): 
        r = limite - (time.monotonic() - t0)
        if r <= 0: raise TimeoutError("AWX tardó demasiado")
        return (10, min(30, r))          # (conexión, lectura)
    s = requests.Session(); s.headers["User-Agent"] = "EstacionMeteoProyecto/1.0"
    s.get(BASE + "/demo_login.php", timeout=restante())             # acceso de invitado
    datos = {"AWS0": STATION, "datetype": 3, "action": "csv", "view": "0"}   # por defecto: últimos 7 días
    if extra: datos.update(extra)
    r = s.post(BASE + "/graphic.php", timeout=restante(), data=datos)
    r.raise_for_status()
    m = re.search(r"window\.open\('(getcsv\.php[^']*)'", r.text)
    if not m: raise RuntimeError("AWX no indicó la dirección de descarga (getcsv.php)")
    c = s.get(BASE + "/" + m.group(1), timeout=restante()); c.raise_for_status()
    if not c.text.lstrip("\ufeff").lstrip().startswith('"date"'): raise RuntimeError("getcsv.php no devolvió un CSV")
    return c.text

def descargar(extra=None, intentos=3, limite=60):
    """AWX funciona en dos pasos: el POST guarda la selección y señala getcsv.php, que entrega el CSV.
    Si AWX está lento, se corta a los 'limite' segundos y se reintenta, en vez de quedarse colgado minutos."""
    ultimo = None
    for i in range(1, intentos + 1):
        try:
            return _descargar_una_vez(extra, limite)
        except Exception as e:
            ultimo = e; print(f"Intento {i}/{intentos} falló: {e}")
            time.sleep(3)
    raise SystemExit(f"AWX no respondió tras {intentos} intentos: {ultimo}")

def leer_awx(texto):
    for fila in csv.DictReader(io.StringIO(texto)):
        f = {k.lower(): v for k, v in fila.items()}
        ts = dt.datetime.strptime(f["date"] + " " + f["time"], "%Y/%m/%d %H:%M").isoformat(timespec="minutes")
        yield {"ts": ts, **{c: f.get(c, "") for c in COLS}}

def numero(v):
    if v == "": return None
    try: return float(v)
    except ValueError: return v

def main():
    os.makedirs("data", exist_ok=True)
    ruta = "data/lecturas.csv"
    filas = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f): filas[r["ts"]] = r
    nuevas = 0
    for r in leer_awx(descargar()):
        if r["ts"] not in filas:
            nuevas += 1; filas[r["ts"]] = r
    try:   # si la página pide columnas nuevas, se reescribe aunque no haya lecturas nuevas
        al_dia = json.load(open("data/reciente.json", encoding="utf-8"))["cols"] == PANTALLA
    except Exception:
        al_dia = False
    if not nuevas and al_dia:
        print("Sin lecturas nuevas"); return
    guardar(filas)
    print(nuevas, "lecturas nuevas; total", len(filas))

def guardar(filas):
    """Escribe el historial completo (lecturas.csv) y la ventana reciente que lee la página (reciente.json)."""
    orden = sorted(filas)
    with open("data/lecturas.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["ts"] + COLS); w.writeheader()
        for k in orden: w.writerow(filas[k])
    corte = (dt.datetime.fromisoformat(orden[-1]) - dt.timedelta(days=DIAS)).isoformat(timespec="minutes")
    rows = [[k] + [numero(filas[k][c]) for c in PANTALLA[1:]] for k in orden if k >= corte]
    with open("data/reciente.json", "w", encoding="utf-8") as f:
        json.dump({"cols": PANTALLA, "rows": rows}, f, separators=(",", ":"))

if __name__ == "__main__":
    main()
