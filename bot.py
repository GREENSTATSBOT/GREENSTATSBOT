import os
import json
import math
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

# Premier League, LaLiga, Serie A, Bundesliga y Ligue 1
LIGAS = {39, 140, 135, 78, 61}


def api_get(endpoint):
    url = f"https://v3.football.api-sports.io/{endpoint}"

    request = urllib.request.Request(
        url,
        headers={"x-apisports-key": API_KEY}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    datos = json.dumps({
        "chat_id": CHAT_ID,
        "text": mensaje
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=datos,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    urllib.request.urlopen(request, timeout=20)


def numero(valor, defecto=0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def estadisticas_equipo(team_id, league_id, season):
    datos = api_get(
        f"teams/statistics?team={team_id}&league={league_id}&season={season}"
    )

    return datos.get("response", {})


def calcular_probabilidades(local_stats, visitante_stats):
    # Goles marcados
    local_gf = numero(
        local_stats.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("home")
    )

    visitante_gf = numero(
        visitante_stats.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("away")
    )

    # Goles recibidos
    local_ga = numero(
        local_stats.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("home")
    )

    visitante_ga = numero(
        visitante_stats.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("away")
    )

    if local_gf <= 0 or visitante_gf <= 0:
        return None

    # Goles esperados aproximados
    lambda_local = (local_gf + visitante_ga) / 2
    lambda_visitante = (visitante_gf + local_ga) / 2

    lambda_total = lambda_local + lambda_visitante

    # OVER 1.5
    p_0 = poisson(0, lambda_total)
    p_1 = poisson(1, lambda_total)

    over15 = 1 - p_0 - p_1

    # OVER 2.5
    p_2 = poisson(2, lambda_total)
    over25 = 1 - p_0 - p_1 - p_2

    # UNDER 3.5
    p_3 = poisson(3, lambda_total)
    under35 = p_0 + p_1 + p_2 + p_3

    # Ambos marcan
    p_local_0 = poisson(0, lambda_local)
    p_visitante_0 = poisson(0, lambda_visitante)

    btts = (
        1
        - p_local_0
        - p_visitante_0
        + (p_local_0 * p_visitante_0)
    )

    return {
        "Over 1.5 goles": over15,
        "Over 2.5 goles": over25,
        "Under 3.5 goles": under35,
        "Ambos marcan": btts
    }


def main():
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    fecha = ahora.strftime("%Y-%m-%d")

    datos = api_get(
        f"fixtures?date={fecha}&timezone=Europe/Madrid"
    )

    partidos = datos.get("response", [])

    # Solo ligas principales
    partidos = [
        p for p in partidos
        if p.get("league", {}).get("id") in LIGAS
    ]

    picks = []

    for partido in partidos:
        league = partido["league"]
        teams = partido["teams"]

        league_id = league["id"]
        season = league["season"]

        local = teams["home"]
        visitante = teams["away"]

        try:
            stats_local = estadisticas_equipo(
                local["id"], league_id, season
            )

            stats_visitante = estadisticas_equipo(
                visitante["id"], league_id, season
            )

            probabilidades = calcular_probabilidades(
                stats_local,
                stats_visitante
            )

            if not probabilidades:
                continue

            for mercado, probabilidad in probabilidades.items():

                porcentaje = probabilidad * 100

                # Solo pronósticos con probabilidad alta
                if porcentaje >= 65:

                    picks.append({
                        "partido": f"{local['name']} - {visitante['name']}",
                        "liga": league["name"],
                        "mercado": mercado,
                        "probabilidad": porcentaje
                    })

        except Exception:
            continue

    picks.sort(
        key=lambda x: x["probabilidad"],
        reverse=True
    )

    # Top 7
    picks = picks[:7]

    if not picks:
        mensaje = (
            "🧠 GREENSTATS\n\n"
            "📊 No he encontrado hoy pronósticos "
            "que superen el filtro del 65%."
        )

    else:
        lineas = [
            "🟢 GREENSTATS | TOP ESTADÍSTICO",
            f"📅 {fecha}",
            ""
        ]

        for i, pick in enumerate(picks, 1):

            prob = pick["probabilidad"]

            if prob >= 80:
                confianza = "🔥 MUY ALTA"
            elif prob >= 72:
                confianza = "🟢 ALTA"
            else:
                confianza = "🟡 BUENA"

            lineas.append(
                f"{i}️⃣ {pick['partido']}"
            )

            lineas.append(
                f"🏆 {pick['liga']}"
            )

            lineas.append(
                f"⚽ {pick['mercado']}"
            )

            lineas.append(
                f"📊 Probabilidad: {prob:.1f}%"
            )

            lineas.append(
                f"⭐ {confianza}"
            )

            lineas.append("")

        lineas.append(
            "⚠️ Probabilidad estadística estimada, "
            "no garantía de acierto."
        )

        mensaje = "\n".join(lineas)

    enviar_telegram(mensaje)


try:
    main()

except Exception as error:

    enviar_telegram(
        "❌ GREENSTATS\n\n"
        f"Error general: {type(error).__name__}"
    )
