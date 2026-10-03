"""Descarga el CSV de AWX (DPS-Promatic) y actualiza data/lecturas.csv y data/reciente.json."""
import csv, io, json, os, re
import datetime as dt
import requests

BASE = "https://www.dps-promatic.com/webapps/gprsmeteo"
STATION = os.getenv("STATION", "PERU")
COLS = ["smsc","si","was","press","wmins","wgust","dwgust","leaf","wdir","wdsd","sun","temp","dmintemp",
        "dmaxtemp","soilt","rf","drf","soilw","dp","rh","dminrh","dmaxrh","pwr","vbatt"]
PANTALLA = ["ts","temp","rh","press","wgust","dp","was","sun","soilt","soilw","rf","drf","leaf","vbatt","pwr"]
DIAS = 35   # días que la página puede mostrar en pantalla (el historial completo queda en lecturas.csv)

def descargar():
    """AWX funciona en dos pasos: el POST guarda la selección y señala getcsv.php, que entrega el CSV."""
    s = requests.Session(); s.headers["User-Agent"] = "EstacionMeteoProyecto/1.0"
    s.get(BASE + "/demo_login.php", timeout=30)                     # acceso de invitado
    r = s.post(BASE + "/graphic.php", timeout=60,
               data={"AWS0": STATION, "datetype": 3, "action": "csv", "view": "0"})   # últimos 7 días
    r.raise_for_status()
    m = re.search(r"window\.open\('(getcsv\.php[^']*)'", r.text)
    if not m: raise SystemExit("AWX no indicó la dirección de descarga (getcsv.php)")
    c = s.get(BASE + "/" + m.group(1), timeout=60); c.raise_for_status()
    if not c.text.lstrip("\ufeff").lstrip().startswith('"date"'): raise SystemExit("getcsv.php no devolvió un CSV")
    return c.text

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
    if not nuevas:
        print("Sin lecturas nuevas"); return
    orden = sorted(filas)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["ts"] + COLS); w.writeheader()
        for k in orden: w.writerow(filas[k])
    corte = (dt.datetime.fromisoformat(orden[-1]) - dt.timedelta(days=DIAS)).isoformat(timespec="minutes")
    rows = [[k] + [numero(filas[k][c]) for c in PANTALLA[1:]] for k in orden if k >= corte]
    with open("data/reciente.json", "w", encoding="utf-8") as f:
        json.dump({"cols": PANTALLA, "rows": rows}, f, separators=(",", ":"))
    print(nuevas, "lecturas nuevas; total", len(orden))

if __name__ == "__main__":
    main()
