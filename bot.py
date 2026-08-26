import os
import json
import math
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

# Competiciones que analizaremos
LIGAS = {
    39,   # Premier League
    140,  # LaLiga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    88,   # Eredivisie
    94,   # Primeira Liga
    203,  # Süper Lig
    144,  # Belgian Pro League
    40,   # Championship
    2,    # Champions League
    3,    # Europa League
    848,  # Conference League
}


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


def obtener_stats(team_id, league_id, season):
    return api_get(
        f"teams/statistics?"
        f"team={team_id}&league={league_id}&season={season}"
    ).get("response", {})


def probabilidades(local, visitante):

    # Ataque
    local_gf = numero(
        local.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("home")
    )

    visitante_gf = numero(
        visitante.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("away")
    )

    # Defensa
    local_ga = numero(
        local.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("home")
    )

    visitante_ga = numero(
        visitante.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("away")
    )

    if local_gf <= 0 or visitante_gf <= 0:
        return None

    # Estimación de goles esperados
    lambda_local = (local_gf + visitante_ga) / 2
    lambda_visitante = (visitante_gf + local_ga) / 2

    total = lambda_local + lambda_visitante

    p0 = poisson(0, total)
    p1 = poisson(1, total)
    p2 = poisson(2, total)
    p3 = poisson(3, total)

    over15 = 1 - (p0 + p1)
    over25 = 1 - (p0 + p1 + p2)
    under35 = p0 + p1 + p2 + p3

    local0 = poisson(0, lambda_local)
    visitante0 = poisson(0, lambda_visitante)

    btts = (
        1
        - local0
        - visitante0
        + (local0 * visitante0)
    )

    return {
        "Más de 1.5 goles": over15,
        "Más de 2.5 goles": over25,
        "Menos de 3.5 goles": under35,
        "Ambos marcan - Sí": btts
    }


def main():

    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    fecha = ahora.strftime("%Y-%m-%d")

    datos = api_get(
        f"fixtures?date={fecha}&timezone=Europe/Madrid"
    )

    partidos = datos.get("response", [])

    partidos_validos = [
        p for p in partidos
        if p.get("league", {}).get("id") in LIGAS
    ]

    candidatos = []

    consultas = 1

    # El plan gratuito tiene límite diario.
    # Analizamos máximo 30 partidos.
    partidos_validos = partidos_validos[:30]

    for partido in partidos_validos:

        if consultas >= 90:
            break

        liga = partido["league"]
        equipos = partido["teams"]

        local = equipos["home"]
        visitante = equipos["away"]

        try:

            stats_local = obtener_stats(
                local["id"],
                liga["id"],
                liga["season"]
            )

            consultas += 1

            stats_visitante = obtener_stats(
                visitante["id"],
                liga["id"],
                liga["season"]
            )

            consultas += 1

            probs = probabilidades(
                stats_local,
                stats_visitante
            )

            if not probs:
                continue

            for mercado, prob in probs.items():

                candidatos.append({
                    "partido":
                        f"{local['name']} - {visitante['name']}",
                    "liga": liga["name"],
                    "mercado": mercado,
                    "probabilidad": prob * 100
                })

        except Exception:
            continue


    # Ordenamos TODOS los pronósticos
    candidatos.sort(
        key=lambda x: x["probabilidad"],
        reverse=True
    )

    # Evitamos que un mismo partido monopolice el TOP
    top = []
    partidos_usados = set()

    for candidato in candidatos:

        if candidato["partido"] in partidos_usados:
            continue

        top.append(candidato)
        partidos_usados.add(candidato["partido"])

        if len(top) == 10:
            break


    if not top:

        mensaje = (
            "🧠 GREENSTATS\n\n"
            "No hay suficientes datos estadísticos "
            "para generar el TOP de hoy."
        )

    else:

        lineas = [
            "🧠 GREENSTATS",
            "",
            "🏆 TOP 10 ESTADÍSTICO DEL DÍA",
            f"📅 {fecha}",
            ""
        ]

        for i, pick in enumerate(top, 1):

            prob = pick["probabilidad"]

            if prob >= 80:
                nivel = "🔥 MUY ALTA"

            elif prob >= 70:
                nivel = "🟢 ALTA"

            elif prob >= 60:
                nivel = "🟡 MEDIA"

            else:
                nivel = "⚪ BAJA"

            lineas.append(
                f"{i}. ⚽ {pick['partido']}"
            )

            lineas.append(
                f"🏆 {pick['liga']}"
            )

            lineas.append(
                f"🎯 {pick['mercado']}"
            )

            lineas.append(
                f"📊 {prob:.1f}%"
            )

            lineas.append(
                f"⭐ {nivel}"
            )

            lineas.append("")


        lineas.append(
            "⚠️ Probabilidades estimadas mediante "
            "modelo estadístico. No garantizan resultados."
        )

        lineas.append(
            f"🔎 Consultas API utilizadas aprox.: {consultas}"
        )

        mensaje = "\n".join(lineas)


    enviar_telegram(mensaje)


try:
    main()

except Exception as error:

    enviar_telegram(
        "❌ GREENSTATS\n\n"
        f"Error: {type(error).__name__}"
    )
