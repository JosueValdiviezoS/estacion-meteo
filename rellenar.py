"""Recupera historial anterior desde AWX, por tramos de 30 días, y lo agrega a data/lecturas.csv.
Uso: python rellenar.py AAAA-MM-DD [AAAA-MM-DD]      (desde, hasta; si no hay 'hasta', usa hoy)"""
import csv, os, sys, time
import datetime as dt
import actualizar as A

def main():
    desde = dt.date.fromisoformat(sys.argv[1])
    hasta = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].strip() else dt.date.today()
    if desde.year < 2012: raise SystemExit("AWX solo ofrece fechas desde 2012")
    os.makedirs("data", exist_ok=True)
    filas = {}
    if os.path.exists("data/lecturas.csv"):
        with open("data/lecturas.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f): filas[r["ts"]] = r
    antes, d = len(filas), desde
    while d <= hasta:
        e = min(d + dt.timedelta(days=29), hasta)
        try:
            texto = A.descargar({"datetype": 1, "from_yyyy": d.year, "from_mm": d.month, "from_dd": d.day,
                                 "to_yyyy": e.year, "to_mm": e.month, "to_dd": e.day})
            n = 0
            for r in A.leer_awx(texto):
                if r["ts"] not in filas: filas[r["ts"]] = r; n += 1
            print(f"{d} a {e}: {n} lecturas nuevas")
        except (SystemExit, Exception) as err:
            print(f"{d} a {e}: sin datos ({err})")
        d = e + dt.timedelta(days=1); time.sleep(2)
    if len(filas) == antes:
        print("No se encontró historial nuevo en ese rango"); return
    A.guardar(filas)
    print(f"Listo: {len(filas) - antes} lecturas agregadas; total {len(filas)}")

if __name__ == "__main__":
    main()
