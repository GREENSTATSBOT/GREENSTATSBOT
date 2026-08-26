import os
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

# Para no gastar las 100 consultas/día
MAX_PREDICCIONES = 15

# Competiciones preferidas
LIGAS_PRIORITARIAS = {
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
    url = f"https://v3.football.api-sports.io/{endpoint}"

    request = urllib.request.Request(
        url,
        headers={"x-apisports-key": API_KEY}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


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


def porcentaje(valor):
    if valor is None:
        return 0.0

    try:
        return float(
            str(valor).replace("%", "").strip()
        )
    except:
        return 0.0


def main():

    ahora = datetime.now(
        ZoneInfo("Europe/Madrid")
    )

    fecha = ahora.strftime("%Y-%m-%d")

    # 1 consulta
    datos = api_get(
        f"fixtures?date={fecha}"
        f"&timezone=Europe/Madrid"
    )

    todos = datos.get("response", [])

    futuros = []

    for partido in todos:

        estado = (
            partido
            .get("fixture", {})
            .get("status", {})
            .get("short")
        )

        if estado not in ["NS", "TBD"]:
            continue

        futuros.append(partido)


    # Primero colocamos las ligas importantes
    futuros.sort(
        key=lambda p:
        0 if p.get("league", {}).get("id")
        in LIGAS_PRIORITARIAS
        else 1
    )


    candidatos = []

    consultados = 0
    sin_prediccion = 0
    errores = 0


    for partido in futuros:

        if consultados >= MAX_PREDICCIONES:
            break

        fixture_id = (
            partido
            .get("fixture", {})
            .get("id")
        )

        if not fixture_id:
            continue

        try:

            datos_pred = api_get(
                f"predictions?fixture={fixture_id}"
            )

            consultados += 1

            respuesta = datos_pred.get(
                "response", []
            )

            if not respuesta:
                sin_prediccion += 1
                continue

            pred = respuesta[0]

            prediction = pred.get(
                "predictions", {}
            )

            percent = prediction.get(
                "percent", {}
            )

            home_p = porcentaje(
                percent.get("home")
            )

            draw_p = porcentaje(
                percent.get("draw")
            )

            away_p = porcentaje(
                percent.get("away")
            )


            local = (
                partido["teams"]["home"]["name"]
            )

            visitante = (
                partido["teams"]["away"]["name"]
            )

            liga = (
                partido["league"]["name"]
            )


            mercados = [
                (
                    f"Gana {local}",
                    home_p
                ),
                (
                    "Empate",
                    draw_p
                ),
                (
                    f"Gana {visitante}",
                    away_p
                ),
                (
                    f"{local} o empate",
                    home_p + draw_p
                ),
                (
                    f"{visitante} o empate",
                    away_p + draw_p
                )
            ]


            mejor_mercado = max(
                mercados,
                key=lambda x: x[1]
            )


            under_over = prediction.get(
                "under_over"
            )

            advice = prediction.get(
                "advice"
            )


            candidatos.append({

                "partido":
                    f"{local} - {visitante}",

                "liga": liga,

                "mercado":
                    mejor_mercado[0],

                "prob":
                    mejor_mercado[1],

                "goles":
                    under_over,

                "consejo":
                    advice
            })


        except Exception:
            errores += 1


    candidatos.sort(
        key=lambda x: x["prob"],
        reverse=True
    )

    top = candidatos[:10]


    lineas = [

        "🧠 GREENSTATS",

        "",

        f"📅 {fecha}",

        f"⚽ Partidos encontrados: "
        f"{len(todos)}",

        f"⏳ Próximos: "
        f"{len(futuros)}",

        f"🔎 Predicciones consultadas: "
        f"{consultados}",

        f"🚫 Sin predicción: "
        f"{sin_prediccion}",

        f"⚠️ Errores: {errores}",

        ""
    ]


    if not top:

        lineas.append(
            "No hay predicciones "
            "disponibles para los "
            "partidos consultados."
        )

    else:

        lineas.append(
            "🏆 TOP GREENSTATS"
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
                f"{i}️⃣ "
                f"{pick['partido']}"
            )

            lineas.append(
                f"🏆 {pick['liga']}"
            )

            lineas.append(
                f"🎯 {pick['mercado']}"
            )

            lineas.append(
                f"📊 Probabilidad API: "
                f"{prob:.1f}%"
            )

            lineas.append(
                f"⭐ {nivel}"
            )


            if pick["goles"]:

                lineas.append(
                    f"⚽ Tendencia goles: "
                    f"{pick['goles']}"
                )


            if pick["consejo"]:

                lineas.append(
                    f"🧠 Modelo: "
                    f"{pick['consejo']}"
                )


            lineas.append("")


        lineas.append(
            "⚠️ Son estimaciones "
            "estadísticas, no resultados "
            "garantizados."
        )


    enviar_telegram(
        "\n".join(lineas)
    )


try:

    main()

except Exception as error:

    enviar_telegram(
        "❌ GREENSTATS\n\n"
        f"Error general: "
        f"{type(error).__name__}"
    )
