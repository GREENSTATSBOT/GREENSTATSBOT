import os
import json
import math
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

MAX_PARTIDOS = 20


def api_get(endpoint):
    url = f"https://v3.football.api-sports.io/{endpoint}"

    request = urllib.request.Request(
        url,
        headers={"x-apisports-key": API_KEY}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    datos = json.dumps({
        "chat_id": CHAT_ID,
        "text": texto
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=datos,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    urllib.request.urlopen(request, timeout=20)


def poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def ultimos_partidos(team_id):
    datos = api_get(
        f"fixtures?team={team_id}&last=5&timezone=Europe/Madrid"
    )

    return datos.get("response", [])


def medias_equipo(partidos, team_id):
    if len(partidos) < 3:
        return None

    goles_favor = []
    goles_contra = []
    ambos_marcan = 0

    for partido in partidos:
        home_id = partido["teams"]["home"]["id"]

        goles_home = partido["goals"]["home"]
        goles_away = partido["goals"]["away"]

        if goles_home is None or goles_away is None:
            continue

        if home_id == team_id:
            gf = goles_home
            gc = goles_away
        else:
            gf = goles_away
            gc = goles_home

        goles_favor.append(gf)
        goles_contra.append(gc)

        if gf > 0 and gc > 0:
            ambos_marcan += 1

    if len(goles_favor) < 3:
        return None

    return {
        "gf": sum(goles_favor) / len(goles_favor),
        "gc": sum(goles_contra) / len(goles_contra),
        "btts": ambos_marcan / len(goles_favor)
    }


def calcular_probabilidades(local, visitante):
    lambda_local = (
        local["gf"] + visitante["gc"]
    ) / 2

    lambda_visitante = (
        visitante["gf"] + local["gc"]
    ) / 2

    # Evita valores absurdos
    lambda_local = max(0.20, min(lambda_local, 3.5))
    lambda_visitante = max(0.20, min(lambda_visitante, 3.5))

    total = lambda_local + lambda_visitante

    p0 = poisson(0, total)
    p1 = poisson(1, total)
    p2 = poisson(2, total)
    p3 = poisson(3, total)

    over15 = 1 - (p0 + p1)
    over25 = 1 - (p0 + p1 + p2)
    under35 = p0 + p1 + p2 + p3

    local_cero = poisson(0, lambda_local)
    visitante_cero = poisson(0, lambda_visitante)

    btts_poisson = (
        1
        - local_cero
        - visitante_cero
        + (local_cero * visitante_cero)
    )

    # Mezclamos Poisson y frecuencia reciente de BTTS
    btts_forma = (
        local["btts"] + visitante["btts"]
    ) / 2

    btts = (
        btts_poisson * 0.7
        + btts_forma * 0.3
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

    todos = datos.get("response", [])

    # Quitamos partidos ya finalizados/cancelados
    partidos = []

    for partido in todos:
        estado = partido["fixture"]["status"]["short"]

        if estado in ["NS", "TBD"]:
            partidos.append(partido)

    partidos = partidos[:MAX_PARTIDOS]

    candidatos = []

    analizados = 0
    sin_datos = 0
    errores = 0
    consultas = 1

    for partido in partidos:
        try:
            local = partido["teams"]["home"]
            visitante = partido["teams"]["away"]

            historial_local = ultimos_partidos(local["id"])
            consultas += 1

            historial_visitante = ultimos_partidos(visitante["id"])
            consultas += 1

            stats_local = medias_equipo(
                historial_local,
                local["id"]
            )

            stats_visitante = medias_equipo(
                historial_visitante,
                visitante["id"]
            )

            if not stats_local or not stats_visitante:
                sin_datos += 1
                continue

            analizados += 1

            probs = calcular_probabilidades(
                stats_local,
                stats_visitante
            )

            for mercado, probabilidad in probs.items():
                candidatos.append({
                    "partido":
                        f"{local['name']} - {visitante['name']}",
                    "liga": partido["league"]["name"],
                    "mercado": mercado,
                    "prob": probabilidad * 100
                })

        except Exception:
            errores += 1


    candidatos.sort(
        key=lambda x: x["prob"],
        reverse=True
    )

    # Máximo una selección por partido
    top = []
    usados = set()

    for candidato in candidatos:
        if candidato["partido"] in usados:
            continue

        usados.add(candidato["partido"])
        top.append(candidato)

        if len(top) >= 10:
            break


    lineas = [
        "🧠 GREENSTATS",
        "",
        f"📅 {fecha}",
        f"⚽ Partidos disponibles: {len(todos)}",
        f"🔎 Revisados: {len(partidos)}",
        f"✅ Analizados: {analizados}",
        f"🚫 Sin datos suficientes: {sin_datos}",
        f"⚠️ Errores: {errores}",
        f"📡 Consultas API aprox.: {consultas}",
        ""
    ]


    if not top:
        lineas.append(
            "No se ha podido generar ningún "
            "pronóstico estadístico hoy."
        )

    else:
        lineas.append(
            "🏆 TOP ESTADÍSTICO DEL DÍA"
        )

        lineas.append("")

        for i, pick in enumerate(top, 1):
            prob = pick["prob"]

            if prob >= 80:
                nivel = "🔥 MUY ALTA"
            elif prob >= 70:
                nivel = "🟢 ALTA"
            elif prob >= 60:
                nivel = "🟡 MEDIA"
            else:
                nivel = "⚪ BAJA"

            lineas.append(
                f"{i}️⃣ {pick['partido']}"
            )

            lineas.append(
                f"🏆 {pick['liga']}"
            )

            lineas.append(
                f"🎯 {pick['mercado']}"
            )

            lineas.append(
                f"📊 Prob. modelo: {prob:.1f}%"
            )

            lineas.append(
                f"⭐ {nivel}"
            )

            lineas.append("")


        lineas.append(
            "⚠️ Estimaciones estadísticas, "
            "no garantías de resultado."
        )


    mensaje = "\n".join(lineas)

    enviar_telegram(mensaje)


try:
    main()

except Exception as error:
    enviar_telegram(
        "❌ GREENSTATS\n\n"
        f"Error general: "
        f"{type(error).__name__}"
    )
