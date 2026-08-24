import os
import json
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

mensaje = """🤖 GREENSTATS ONLINE

✅ Bot conectado correctamente.
⚽ Sistema de pronósticos preparado.

📊 Estadísticas
💰 Cuotas
🧠 Probabilidades
🟢 Value bets
📈 Seguimiento de resultados
"""

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

data = json.dumps({
    "chat_id": CHAT_ID,
    "text": mensaje
}).encode("utf-8")

request = urllib.request.Request(
    url,
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(request) as response:
    print(response.read().decode())
