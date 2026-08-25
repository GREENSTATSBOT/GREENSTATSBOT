import os
import json
import urllib.request
from datetime import datetime

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["API_FOOTBALL_KEY"]


def obtener_partidos():
    fecha = datetime.now().strftime("%Y-%m-%d")

    url = (
        "https://v3.football.api-sports.io/fixtures"
        f"?date={fecha}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": API_KEY
        }
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    datos = json.dumps({
        "chat_id": CHAT_ID,
        "text": mensaje
    }).encode()

    request = urllib.request.Request(
        url,
        data=datos,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    urllib.request.urlopen(request, timeout=20)


try:
    datos = obtener_partidos()

    partidos = datos.get("response", [])

    mensaje = (
        "🧠 GREENSTATS\n\n"
        f"⚽ Partidos encontrados: {len(partidos)}\n\n"
        "✅ API-Football conectada correctamente.\n\n"
        "📊 Próximo paso: analizar estadísticas."
    )

except Exception as error:

    mensaje = (
        "❌ GREENSTATS\n\n"
        "No se pudo conectar con API-Football.\n\n"
        f"Error: {type(error).__name__}"
    )


enviar_telegram(mensaje)
