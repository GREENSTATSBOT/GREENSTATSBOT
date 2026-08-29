import urllib.error
import os
import json
import urllib.request
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

# =========================
# CONFIGURACIÓN DE CALIDAD
# =========================

# Máximo de partidos a los que pedimos predicción cada ejecución.
# Mantenerlo controlado ayuda a ahorrar peticiones de API.
MAX_PREDICCIONES = 25

# Número máximo de pronósticos que se envían a Telegram.
MAX_PRONOSTICOS = 3

# Probabilidad mínima del resultado elegido por el modelo.
# 75% = filtro bastante exigente.
MIN_PROB = 75

# Diferencia mínima entre la mejor opción y la segunda mejor.
# Evita partidos donde el modelo está demasiado dividido.
MIN_DIFERENCIA = 20

# Si hay cuota, no mostrar cuotas absurdamente bajas/altas.
MIN_CUOTA = 1.15
MAX_CUOTA = 3.00

# EV mínimo para marcar una apuesta como value real.
MIN_EV_VALUE = 3.0

# Evita disparar demasiadas peticiones seguidas. API-Sports puede responder
# 429 por límite temporal aunque todavía queden peticiones del cupo diario.
API_MIN_INTERVAL = 6.5
API_MAX_RETRIES = 3
_ultima_peticion_api = 0.0

LIGAS_TOP = {
    39,   # Premier League
    140,  # LaLiga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    88,   # Eredivisie
    94,   # Primeira Liga
    40,   # Championship
    2,    # Champions League
    3,    # Europa League
    848,  # Conference League
}


def api_get(endpoint):
    global _ultima_peticion_api

    url = f"https://v3.football.api-sports.io/{endpoint}"

    for intento in range(API_MAX_RETRIES + 1):
        # Espaciamos llamadas para no confundir un rate-limit temporal
        # con el agotamiento del cupo diario.
        espera = API_MIN_INTERVAL - (time.monotonic() - _ultima_peticion_api)
        if espera > 0:
            time.sleep(espera)

        req = urllib.request.Request(
            url,
            headers={
                "x-apisports-key": API_KEY,
                "User-Agent": "GREENSTATS/3.2"
            }
        )

        try:
            _ultima_peticion_api = time.monotonic()
            with urllib.request.urlopen(req, timeout=25) as response:
                datos = json.loads(response.read().decode("utf-8"))

            # Algunas respuestas de API-Sports pueden llegar con HTTP 200
            # pero incluir un error dentro del JSON.
            errores_api = datos.get("errors")
            if errores_api:
                texto_error = json.dumps(errores_api, ensure_ascii=False).lower()
                if any(x in texto_error for x in [
                    "daily", "per day", "requests limit", "request limit",
                    "quota", "subscription"
                ]):
                    raise RuntimeError("API_DAILY_LIMIT")
                raise RuntimeError(f"API_RESPONSE: {texto_error[:220]}")

            return datos

        except urllib.error.HTTPError as error:
            cuerpo = ""
            try:
                cuerpo = error.read().decode("utf-8", errors="ignore").lower()
            except Exception:
                pass

            if error.code == 429:
                # 429 suele ser un límite de velocidad temporal. Esperamos y
                # reintentamos antes de asumir que el cupo diario se agotó.
                if any(x in cuerpo for x in ["daily", "per day", "quota"]):
                    raise RuntimeError("API_DAILY_LIMIT")

                if intento < API_MAX_RETRIES:
                    retry_after = error.headers.get("Retry-After")
                    try:
                        segundos = max(float(retry_after), API_MIN_INTERVAL)
                    except (TypeError, ValueError):
                        segundos = API_MIN_INTERVAL * (intento + 1)
                    time.sleep(segundos)
                    continue

                raise RuntimeError("API_RATE_LIMIT")

            raise RuntimeError(f"API_HTTP_{error.code}: {cuerpo[:220]}")

        except urllib.error.URLError as error:
            if intento < API_MAX_RETRIES:
                time.sleep(2 * (intento + 1))
                continue
            raise RuntimeError(f"API_CONNECTION: {error.reason}")

    raise RuntimeError("API_UNKNOWN")


def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": texto
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()


def pct(valor):
    try:
        return float(str(valor).replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def obtener_cuota_1x2(fixture_id, signo):
    datos = api_get(f"odds?fixture={fixture_id}")
    respuesta = datos.get("response", [])

    if not respuesta:
        return None

    objetivo = {
        "1": "Home",
        "X": "Draw",
        "2": "Away"
    }.get(signo)

    if not objetivo:
        return None

    mejores = []

    for item in respuesta:
        for bookmaker in item.get("bookmakers", []):
            nombre_casa = bookmaker.get("name", "?")

            for bet in bookmaker.get("bets", []):
                bet_nombre = str(bet.get("name", "")).lower()

                if (
                    "match winner" not in bet_nombre
                    and "1x2" not in bet_nombre
                    and "winner" not in bet_nombre
                ):
                    continue

                for value in bet.get("values", []):
                    nombre = str(value.get("value", "")).strip()

                    if nombre.lower() != objetivo.lower():
                        continue

                    try:
                        cuota = float(value.get("odd"))
                    except (TypeError, ValueError):
                        continue

                    if cuota <= 1:
                        continue

                    mejores.append({
                        "cuota": cuota,
                        "bookmaker": nombre_casa
                    })

    if not mejores:
        return None

    return max(mejores, key=lambda x: x["cuota"])


    def main():
    print("INICIANDO BOT")
    enviar_telegram("✅ PRUEBA GREENSTATS: Telegram conectado")
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    fecha = ahora.strftime("%Y-%m-%d")

    datos = api_get(
        f"fixtures?date={fecha}&timezone=Europe/Madrid"
    )

    partidos = datos.get("response", [])
    futuros = []

    for partido in partidos:
        fixture = partido.get("fixture", {})
        estado = fixture.get("status", {}).get("short")

        if estado not in ["NS", "TBD"]:
            continue

        # Evita incluir partidos cuya hora ya haya pasado si la API
        # todavía conserva un estado pendiente de forma temporal.
        fecha_partido = fixture.get("date")
        if fecha_partido:
            try:
                inicio = datetime.fromisoformat(fecha_partido)
                if inicio.tzinfo is not None:
                    inicio = inicio.astimezone(ZoneInfo("Europe/Madrid"))
                    if inicio < ahora:
                        continue
            except (ValueError, TypeError):
                pass

        futuros.append(partido)

    # Primero ligas importantes y después los partidos más próximos.
    futuros.sort(
        key=lambda partido: (
            0 if partido.get("league", {}).get("id") in LIGAS_TOP else 1,
            partido.get("fixture", {}).get("timestamp", 9999999999)
        )
    )

    candidatos = []
    pred_consultadas = 0
    sin_pred = 0
    descartados_prob = 0
    descartados_diferencia = 0
    errores = 0
    limite_api = False
    rate_limit_temporal = False

    # =========================
    # PREDICCIONES
    # =========================

    for partido in futuros:
        if pred_consultadas >= MAX_PREDICCIONES:
            break

        fixture_id = partido.get("fixture", {}).get("id")
        if not fixture_id:
            continue

        try:
            datos_pred = api_get(f"predictions?fixture={fixture_id}")
            pred_consultadas += 1

            respuesta = datos_pred.get("response", [])
            if not respuesta:
                sin_pred += 1
                continue

            pred = respuesta[0].get("predictions", {})
            porcentajes = pred.get("percent", {})

            p1 = pct(porcentajes.get("home"))
            px = pct(porcentajes.get("draw"))
            p2 = pct(porcentajes.get("away"))

            local = partido.get("teams", {}).get("home", {}).get("name", "Local")
            visitante = partido.get("teams", {}).get("away", {}).get("name", "Visitante")

            opciones = [
                (f"Gana {local}", "1", p1),
                ("Empate", "X", px),
                (f"Gana {visitante}", "2", p2)
            ]

            opciones_ordenadas = sorted(
                opciones,
                key=lambda x: x[2],
                reverse=True
            )

            mercado, signo, prob = opciones_ordenadas[0]
            segunda_prob = opciones_ordenadas[1][2]
            diferencia = prob - segunda_prob

            # Filtro 1: probabilidad alta.
            if prob < MIN_PROB:
                descartados_prob += 1
                continue

            # Filtro 2: ventaja clara frente a la segunda opción.
            if diferencia < MIN_DIFERENCIA:
                descartados_diferencia += 1
                continue

            fixture = partido.get("fixture", {})
            hora = "?"
            fecha_partido = fixture.get("date")
            if fecha_partido:
                try:
                    inicio = datetime.fromisoformat(fecha_partido)
                    if inicio.tzinfo is not None:
                        inicio = inicio.astimezone(ZoneInfo("Europe/Madrid"))
                    hora = inicio.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass

            candidatos.append({
                "fixture_id": fixture_id,
                "partido": f"{local} - {visitante}",
                "liga": partido.get("league", {}).get("name", "Liga desconocida"),
                "liga_top": partido.get("league", {}).get("id") in LIGAS_TOP,
                "hora": hora,
                "mercado": mercado,
                "signo": signo,
                "prob": prob,
                "segunda_prob": segunda_prob,
                "diferencia": diferencia,
                "p1": p1,
                "px": px,
                "p2": p2,
                "consejo": pred.get("advice"),
                "goles": pred.get("under_over")
            })

        except RuntimeError as error:
            if str(error) == "API_DAILY_LIMIT":
                limite_api = True
                break
            if str(error) == "API_RATE_LIMIT":
                rate_limit_temporal = True
                errores += 1
                continue
            errores += 1

        except Exception:
            errores += 1

    # Prioridad: ligas top, probabilidad y claridad del pronóstico.
    candidatos.sort(
        key=lambda x: (
            x["liga_top"],
            x["prob"],
            x["diferencia"]
        ),
        reverse=True
    )

    # Solo pedimos cuotas de los mejores candidatos.
    candidatos = candidatos[:MAX_PRONOSTICOS]

    picks = []
    odds_consultadas = 0

    # =========================
    # CUOTAS + VALUE
    # =========================

    if not limite_api:
        for candidato in candidatos:
            try:
                odds = obtener_cuota_1x2(
                    candidato["fixture_id"],
                    candidato["signo"]
                )
                odds_consultadas += 1

                candidato["cuota"] = None
                candidato["bookmaker"] = None
                candidato["prob_implicita"] = None
                candidato["cuota_justa"] = None
                candidato["ev"] = None

                if odds:
                    cuota = odds["cuota"]

                    # La cuota se muestra, pero la marcamos como fuera de rango
                    # si es demasiado extrema para el perfil conservador.
                    candidato["cuota"] = cuota
                    candidato["bookmaker"] = odds["bookmaker"]
                    candidato["cuota_en_rango"] = MIN_CUOTA <= cuota <= MAX_CUOTA

                    prob_decimal = candidato["prob"] / 100
                    prob_implicita = (1 / cuota) * 100
                    cuota_justa = 1 / prob_decimal
                    ev = (prob_decimal * cuota - 1) * 100

                    candidato["prob_implicita"] = prob_implicita
                    candidato["cuota_justa"] = cuota_justa
                    candidato["ev"] = ev
                else:
                    candidato["cuota_en_rango"] = False

                picks.append(candidato)

            except RuntimeError as error:
                if str(error) == "API_DAILY_LIMIT":
                    limite_api = True
                    break
                if str(error) == "API_RATE_LIMIT":
                    rate_limit_temporal = True
                    errores += 1
                    continue
                errores += 1

            except Exception:
                errores += 1

    # Si se agotó la API antes de consultar cuotas, conservamos
    # igualmente los pronósticos de alta confianza.
    if not picks and candidatos:
        for candidato in candidatos:
            candidato["cuota"] = None
            candidato["bookmaker"] = None
            candidato["prob_implicita"] = None
            candidato["cuota_justa"] = None
            candidato["ev"] = None
            candidato["cuota_en_rango"] = False
            picks.append(candidato)

    # Para un bot orientado a acierto, la probabilidad manda.
    # El EV se usa como información secundaria.
    picks.sort(
        key=lambda x: (
            x["prob"],
            x["diferencia"],
            x["ev"] if x["ev"] is not None else -999
        ),
        reverse=True
    )

    # =========================
    # TELEGRAM
    # =========================

    lineas = [
        "🟢 GREENSTATS V3.2 | ALTA CONFIANZA",
        "",
        f"📅 {fecha}",
        f"⚽ Partidos del día: {len(partidos)}",
        f"🔎 Próximos analizados: {len(futuros)}",
        f"🧠 Predicciones consultadas: {pred_consultadas}",
        f"💰 Cuotas consultadas: {odds_consultadas}",
        f"🚫 Sin predicción: {sin_pred}",
        f"📉 Descartados < {MIN_PROB}%: {descartados_prob}",
        f"⚖️ Descartados por poca diferencia: {descartados_diferencia}",
        f"⚠️ Errores: {errores}",
        ""
    ]

    if limite_api:
        lineas.extend([
            "🛑 Cupo diario de API alcanzado.",
            ""
        ])
    elif rate_limit_temporal:
        lineas.extend([
            "⏳ La API aplicó un límite temporal de velocidad en alguna petición.",
            "El bot esperó/reintentó y continuó cuando fue posible.",
            ""
        ])

    if not picks:
        lineas.extend([
            "🔒 Hoy no encuentro ningún pronóstico que cumpla",
            f"el filtro de seguridad: ≥ {MIN_PROB:.0f}% de probabilidad",
            f"y ≥ {MIN_DIFERENCIA:.0f} puntos de ventaja sobre la segunda opción.",
            "",
            "✅ Mejor no enviar una apuesta que forzar un pronóstico flojo."
        ])

    else:
        for i, pick in enumerate(picks, 1):
            lineas.append(f"{i}️⃣ ⚽ {pick['partido']}")
            lineas.append(f"🏆 {pick['liga']} | 🕒 {pick['hora']}")
            lineas.append(f"🎯 {pick['mercado']}")
            lineas.append(f"🧠 Prob. modelo: {pick['prob']:.1f}%")
            lineas.append(f"🛡️ Ventaja sobre 2ª opción: +{pick['diferencia']:.1f} pts")
            lineas.append(
                f"1️⃣ {pick['p1']:.0f}% | ❎ {pick['px']:.0f}% | 2️⃣ {pick['p2']:.0f}%"
            )

            if pick["cuota"] is not None:
                lineas.append(f"💰 Cuota: {pick['cuota']:.2f}")
                lineas.append(f"🏦 Casa: {pick['bookmaker']}")
                lineas.append(f"📉 Prob. implícita cuota: {pick['prob_implicita']:.1f}%")
                lineas.append(f"⚖️ Cuota justa modelo: {pick['cuota_justa']:.2f}")
                lineas.append(f"💎 EV: {pick['ev']:+.1f}%")

                if not pick["cuota_en_rango"]:
                    lineas.append("⚪ Cuota fuera del rango conservador")
                elif pick["ev"] >= 10:
                    lineas.append("🔥 VALUE ALTO")
                elif pick["ev"] >= MIN_EV_VALUE:
                    lineas.append("🟢 VALUE")
                elif pick["ev"] > 0:
                    lineas.append("🟡 VALUE PEQUEÑO")
                else:
                    lineas.append("🔴 SIN VALUE")
            else:
                lineas.append("💰 Sin cuota disponible")

            if pick["goles"]:
                lineas.append(f"⚽ Goles API: {pick['goles']}")

            if pick["consejo"]:
                lineas.append(f"🧠 Consejo API: {pick['consejo']}")

            lineas.append("")

    lineas.extend([
        "━━━━━━━━━━━━━━",
        "📌 Filtro actual: alta probabilidad + resultado claramente dominante.",
        "⚠️ Una probabilidad alta no garantiza que la apuesta gane.",
        "📌 Las cuotas dependen de las casas disponibles en API-Football."
    ])

    enviar_telegram("\n".join(lineas))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        try:
            enviar_telegram(
                "❌ GREENSTATS V3.2\n\n"
                f"Error: {type(error).__name__}\n"
                f"Detalle: {str(error)[:250]}"
            )
        except Exception:
            print(f"Error fatal: {type(error).__name__}: {error}")
