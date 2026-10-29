"""ETo diaria FAO-56 Penman-Monteith con los datos de la estación (data/lecturas.csv).

Replica exactamente el cálculo del Excel/Apps Script (hoja ETo_FAO56_Diaria):
  - 631 de 633 días históricos coinciden con diferencia < 0,01 mm/día.
  - Se usa la temperatura de las lecturas (temp) para Tmin/Tmax/Tmedia.
  - Rs = suma(W/m2 de cada lectura) * 1800 s / 1e6  (MJ/m2/día)  -> un día con lecturas
    faltantes subestima Rs y por eso se marca 'completo' = False.
  - Viento: was (km/h) -> m/s -> altura 2 m.   Presión: press (hPa) -> kPa.
  - ea desde el punto de rocío medio (dp).     Flujo de calor del suelo G = 0.
ETc por lote (data/cultivos.csv -> data/etc_diaria.csv), igual que la hoja ETc_Diaria del Excel:
  ETc = Kc x ETo x factor de ambiente;  lámina bruta = ETc / 0,90.
  Kc: etapas FAO-56 (inicial, desarrollo, media, final) con sus duraciones reescaladas a la
  duración real del lote (cosecha - inicio + 1; inicio = trasplante, o siembra si es directa);
  Kc constante en inicial y media, interpolación lineal en desarrollo y final.
Uso:  python eto.py           (reescribe data/diario.csv y data/etc_diaria.csv)
"""
import csv, math, os
import datetime as dt
from collections import defaultdict

LAT_GRADOS = -5.177     # latitud de la estación (deducida de Ra del Excel; confirmar con el ingeniero)
ALTITUD_M = 30.0        # altitud (deducida de Rso del Excel; confirmar con el ingeniero)
LECTURAS_ESPERADAS = 48 # una lectura cada 30 min
MIN_COMPLETO = 44       # desde 44 de 48 lecturas se considera día completo

def _es(t):
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))

def _ra(lat, doy):
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dec = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(lat) * math.tan(dec))
    return 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(lat) * math.sin(dec)
                                              + math.cos(lat) * math.cos(dec) * math.sin(ws))

def eto_dia(fecha, filas):
    """filas: lista de dicts de lecturas de ese día. Devuelve dict con el resumen y la ETo, o None."""
    v = [f for f in filas if all(isinstance(f.get(c), float) for c in ("temp", "dp", "was", "press", "sun"))]
    n = len(v)
    if n < 2: return None
    m = lambda c: sum(f[c] for f in v) / n
    tmin = min(f["temp"] for f in v); tmax = max(f["temp"] for f in v); tm = m("temp")
    hr = m("rh") if all(isinstance(f.get("rh"), float) for f in v) else None
    u2 = (m("was") / 3.6) * 4.87 / math.log(67.8 * 4 - 5.42)
    P = m("press") / 10
    rs = sum(f["sun"] for f in v) * 1800 / 1e6
    lat = math.radians(LAT_GRADOS)
    ra = _ra(lat, fecha.timetuple().tm_yday)
    rso = (0.75 + 2e-5 * ALTITUD_M) * ra
    es = (_es(tmin) + _es(tmax)) / 2
    ea = _es(m("dp"))
    delta = 4098 * _es(tm) / (tm + 237.3) ** 2
    gamma = 0.000665 * P
    rnl = 4.903e-9 * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) * (0.34 - 0.14 * math.sqrt(ea)) \
          * (1.35 * min(rs / rso, 1.0) - 0.35)
    rn = 0.77 * rs - rnl
    eto = (0.408 * delta * rn + gamma * 900 / (tm + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return {"fecha": fecha.isoformat(), "lecturas": n, "completo": n >= MIN_COMPLETO,
            "tmin": round(tmin, 1), "tmax": round(tmax, 1), "tmedia": round(tm, 2),
            "hr_media": round(hr, 1) if hr is not None else "", "viento_2m_ms": round(u2, 2),
            "rs_mj": round(rs, 2), "rn_mj": round(rn, 2), "eto_mm": round(eto, 2), "_eto": eto}

def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return v

def calcular(ruta="data/lecturas.csv"):
    dias = defaultdict(list)
    with open(ruta, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r = {k: _num(x) for k, x in r.items()}
            dias[r["ts"][:10]].append(r)
    out = []
    for k in sorted(dias):
        d = eto_dia(dt.date.fromisoformat(k), dias[k])
        if d: out.append(d)
    return out

def _fecha(t):
    return dt.date.fromisoformat(t) if t else None

def _kc(c, dia):
    """Etapa, Kc y día en campo del lote c (dict de cultivos.csv) para la fecha dia."""
    ini = _fecha(c["fecha_trasplante"]) if c["tipo_siembra"] == "Trasplante" and c["fecha_trasplante"] else _fecha(c["fecha_siembra"])
    cos = _fecha(c["fecha_cosecha"])
    if not ini or not cos: return None
    L = [float(c[k]) for k in ("l_ini", "l_des", "l_med", "l_fin")]
    k = ((cos - ini).days + 1) / sum(L)
    a, b, m, _ = [x * k for x in L]
    d = (dia - ini).days + 1
    if d < 1 or dia > cos: return None
    ki, km, kf = float(c["kc_ini"]), float(c["kc_med"]), float(c["kc_fin"])
    if d <= a: return "Inicial", ki, d
    if d <= a + b: return "Desarrollo", ki + (km - ki) * (d - a) / b, d
    if d <= a + b + m: return "Media", km, d
    return "Final", km + (kf - km) * (d - a - b - m) / (L[3] * k), d

def calcular_etc(diario, ruta="data/cultivos.csv"):
    if not os.path.exists(ruta): return []
    with open(ruta, encoding="utf-8", newline="") as f:
        lotes = [c for c in csv.DictReader(f) if c["activo"] in ("SI", "COSECHADO")]
    out = []
    for c in lotes:
        for d in diario:
            r = _kc(c, dt.date.fromisoformat(d["fecha"]))
            if not r: continue
            etapa, kc, dia = r
            etc = kc * d["_eto"] * float(c["factor_ambiente"])
            out.append({"fecha": d["fecha"], "id": c["id"], "cultivo": c["cultivo"], "campo": c["campo"],
                        "dia_en_campo": dia, "etapa": etapa, "kc": round(kc, 3), "eto_mm": d["eto_mm"],
                        "etc_mm": round(etc, 2), "lamina_bruta_mm": round(etc / 0.90, 2), "completo": d["completo"]})
    return sorted(out, key=lambda x: (x["fecha"], int(x["id"])))

def main():
    filas = calcular()
    cab = ["fecha", "lecturas", "completo", "tmin", "tmax", "tmedia", "hr_media", "viento_2m_ms", "rs_mj", "rn_mj", "eto_mm"]
    with open("data/diario.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cab, extrasaction="ignore"); w.writeheader(); w.writerows(filas)
    etc = calcular_etc(filas)
    cab2 = ["fecha", "id", "cultivo", "campo", "dia_en_campo", "etapa", "kc", "eto_mm", "etc_mm", "lamina_bruta_mm", "completo"]
    with open("data/etc_diaria.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cab2); w.writeheader(); w.writerows(etc)
    print(len(filas), "días de ETo y", len(etc), "filas de ETc escritos")

if __name__ == "__main__":
    main()
