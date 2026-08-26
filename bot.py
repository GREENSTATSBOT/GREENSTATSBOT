import urllib.error
import os
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]

MAX_PREDICCIONES = 8
MAX_ODDS = 3
MIN_PROB = 70
MIN_DIFERENCIA = 25

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
    url = f"https://v3.football.api-sports.io/{endpoint}"

    req = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": API_KEY
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise RuntimeError("API_LIMIT")
        raise


def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": texto
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    urllib.request.urlopen(req, timeout=20)


def pct(valor):
    try:
        return float(
            str(valor).replace("%", "").strip()
        )
    except Exception:
        return 0.0


def obtener_cuota_1x2(fixture_id, signo):
    datos = api_get(
        f"odds?fixture={fixture_id}"
    )

    respuesta = datos.get(
        "response", []
    )

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

        for bookmaker in item.get(
            "bookmakers", []
        ):

            nombre_casa = bookmaker.get(
                "name", "?"
            )

            for bet in bookmaker.get(
                "bets", []
            ):

                bet_nombre = str(
                    bet.get("name", "")
                ).lower()

                if (
                    "match winner"
                    not in bet_nombre
                    and "1x2"
                    not in bet_nombre
                    and "winner"
                    not in bet_nombre
                ):
                    continue

                for value in bet.get(
                    "values", []
                ):

                    nombre = str(
                        value.get("value", "")
                    ).strip()

                    if (
                        nombre.lower()
                        != objetivo.lower()
                    ):
                        continue

                    try:
                        cuota = float(
                            value.get("odd")
                        )

                    except (
                        TypeError,
                        ValueError
                    ):
                        continue

                    mejores.append({
                        "cuota": cuota,
                        "bookmaker": nombre_casa
                    })

    if not mejores:
        return None

    return max(
        mejores,
        key=lambda x: x["cuota"]
    )


def main():

    ahora = datetime.now(
        ZoneInfo("Europe/Madrid")
    )

    fecha = ahora.strftime(
        "%Y-%m-%d"
    )

    datos = api_get(
        f"fixtures?date={fecha}"
        f"&timezone=Europe/Madrid"
    )

    partidos = datos.get(
        "response", []
    )

    futuros = []

    for partido in partidos:

        estado = (
            partido
            .get("fixture", {})
            .get("status", {})
            .get("short")
        )

        if estado in ["NS", "TBD"]:
            futuros.append(partido)

    futuros.sort(
        key=lambda partido: (
            0
            if partido
            .get("league", {})
            .get("id")
            in LIGAS_TOP
            else 1
        )
    )

    candidatos = []

    pred_consultadas = 0
    sin_pred = 0
    errores = 0
    limite_api = False

    # =========================
    # PREDICCIONES
    # =========================

    for partido in futuros:

        if (
            pred_consultadas
            >= MAX_PREDICCIONES
        ):
            break

        fixture_id = (
            partido["fixture"]["id"]
        )

        try:

            datos_pred = api_get(
                f"predictions?"
                f"fixture={fixture_id}"
            )

            pred_consultadas += 1

            respuesta = datos_pred.get(
                "response", []
            )

            if not respuesta:
                sin_pred += 1
                continue

            pred = (
                respuesta[0]
                .get("predictions", {})
            )

            porcentajes = pred.get(
                "percent", {}
            )

            p1 = pct(
                porcentajes.get("home")
            )

            px = pct(
                porcentajes.get("draw")
            )

            p2 = pct(
                porcentajes.get("away")
            )
            diferencia = abs(p1 - p2)

            
              
    
            local = (
                partido["teams"]
                ["home"]["name"]
            )

            visitante = (
                partido["teams"]
                ["away"]["name"]
            )

            opciones = [
                (
                    f"Gana {local}",
                    "1",
                    p1
                ),
                (
                    "Empate",
                    "X",
                    px
                ),
                (
                    f"Gana {visitante}",
                    "2",
                    p2
                )
            ]

            mercado, signo, prob = max(
                opciones,
                key=lambda x: x[2]
            )

            if prob < MIN_PROB:
                continue

            candidatos.append({
                "fixture_id": fixture_id,
                "partido":
                    f"{local} - "
                    f"{visitante}",
                "liga":
                    partido["league"]
                    ["name"],
                "liga_top":
                    partido["league"]
                    ["id"]
                    in LIGAS_TOP,
                "mercado": mercado,
                "signo": signo,
                "prob": prob,
                "p1": p1,
                "px": px,
                "p2": p2,
                "consejo":
                    pred.get("advice"),
                "goles":
                    pred.get(
                        "under_over"
                    )
            })

        except RuntimeError as error:

            if str(error) == "API_LIMIT":
                limite_api = True
                break

            errores += 1

        except Exception:
            errores += 1

    candidatos.sort(
        key=lambda x: (
            x["liga_top"],
            x["prob"]
        ),
        reverse=True
    )

    candidatos = (
        candidatos[:MAX_ODDS]
    )

    picks = []
    odds_consultadas = 0

    # =========================
    # CUOTAS + VALUE
    # =========================

    if not limite_api:

        for candidato in candidatos:

            try:

                odds = obtener_cuota_1x2(
                    candidato[
                        "fixture_id"
                    ],
                    candidato[
                        "signo"
                    ]
                )

                odds_consultadas += 1

                if not odds:

                    candidato[
                        "cuota"
                    ] = None

                    candidato[
                        "bookmaker"
                    ] = None

                    candidato[
                        "ev"
                    ] = None

                    picks.append(
                        candidato
                    )

                    continue

                cuota = odds["cuota"]

                prob_decimal = (
                    candidato["prob"]
                    / 100
                )

                prob_implicita = (
                    1 / cuota
                ) * 100

                cuota_justa = (
                    1 / prob_decimal
                )

                ev = (
                    prob_decimal
                    * cuota
                    - 1
                ) * 100

                candidato[
                    "cuota"
                ] = cuota

                candidato[
                    "bookmaker"
                ] = odds[
                    "bookmaker"
                ]

                candidato[
                    "prob_implicita"
                ] = prob_implicita

                candidato[
                    "cuota_justa"
                ] = cuota_justa

                candidato[
                    "ev"
                ] = ev

                picks.append(
                    candidato
                )

            except RuntimeError as error:

                if (
                    str(error)
                    == "API_LIMIT"
                ):
                    limite_api = True
                    break

                errores += 1

            except Exception:
                errores += 1

    # Si no hubo cuotas por límite,
    # al menos conservamos candidatos
    if not picks and candidatos:
        for candidato in candidatos:
            candidato["cuota"] = None
            candidato["bookmaker"] = None
            candidato["ev"] = None
            picks.append(candidato)

    picks.sort(
        key=lambda x: (
            x["ev"]
            if x["ev"] is not None
            else -999
        ),
        reverse=True
    )

    # =========================
    # TELEGRAM
    # =========================

    lineas = [
        "💎 GREENSTATS V3 | VALUE",
        "",
        f"📅 {fecha}",
        f"⚽ Partidos: {len(partidos)}",
        (
            "🧠 Predicciones "
            f"consultadas: "
            f"{pred_consultadas}"
        ),
        (
            "💰 Cuotas "
            f"consultadas: "
            f"{odds_consultadas}"
        ),
        (
            "🚫 Sin predicción: "
            f"{sin_pred}"
        ),
        f"⚠️ Errores: {errores}",
        ""
    ]

    if limite_api:
        lineas.extend([
            "🛑 Límite diario de API "
            "alcanzado.",
            ""
        ])

    if not picks:

        lineas.append(
            "Hoy no hay candidatos "
            "que superen el filtro."
        )

    else:

        for i, pick in enumerate(
            picks,
            1
        ):

            lineas.append(
                f"{i}️⃣ ⚽ "
                f"{pick['partido']}"
            )

            lineas.append(
                f"🏆 {pick['liga']}"
            )

            lineas.append(
                f"🎯 {pick['mercado']}"
            )

            lineas.append(
                "🧠 Prob. modelo: "
                f"{pick['prob']:.1f}%"
            )

            lineas.append(
                f"1️⃣ {pick['p1']:.0f}%"
                f" | ❎ {pick['px']:.0f}%"
                f" | 2️⃣ {pick['p2']:.0f}%"
            )

            if (
                pick["cuota"]
                is not None
            ):

                lineas.append(
                    "💰 Cuota: "
                    f"{pick['cuota']:.2f}"
                )

                lineas.append(
                    "🏦 Casa: "
                    f"{pick['bookmaker']}"
                )

                lineas.append(
                    "📉 Prob. cuota: "
                    f"{pick['prob_implicita']:.1f}%"
                )

                lineas.append(
                    "⚖️ Cuota justa modelo: "
                    f"{pick['cuota_justa']:.2f}"
                )

                lineas.append(
                    "💎 EV: "
                    f"{pick['ev']:+.1f}%"
                )

                if pick["ev"] >= 10:
                    lineas.append(
                        "🔥 VALUE ALTO"
                    )

                elif pick["ev"] >= 5:
                    lineas.append(
                        "🟢 VALUE"
                    )

                elif pick["ev"] > 0:
                    lineas.append(
                        "🟡 VALUE PEQUEÑO"
                    )

                else:
                    lineas.append(
                        "🔴 SIN VALUE"
                    )

            else:

                lineas.append(
                    "💰 Sin cuota "
                    "disponible"
                )

            if pick["goles"]:

                lineas.append(
                    "⚽ Goles: "
                    f"{pick['goles']}"
                )

            if pick["consejo"]:

                lineas.append(
                    "🧠 Consejo API: "
                    f"{pick['consejo']}"
                )

            lineas.append("")

    lineas.extend([
        "━━━━━━━━━━━━━━",
        (
            "⚠️ EV positivo no "
            "garantiza que la apuesta "
            "gane."
        ),
        "",
        (
            "📌 Las cuotas son las que "
            "API-Football tenga "
            "disponibles. No asumimos "
            "que sean de Danz."
        )
    ])

    enviar_telegram(
        "\n".join(lineas)
    )


try:
    main()

except Exception as error:

    enviar_telegram(
        "❌ GREENSTATS V3\n\n"
        f"Error: "
        f"{type(error).__name__}"
    )
