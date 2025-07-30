
import os
import time
import json
from datetime import datetime
from binance.client import Client
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Client(API_KEY, API_SECRET)
telegram_bot = Bot(token=TELEGRAM_TOKEN)

PORCENTAJE_MAX_USDT = 0.8
MIN_USDT_OPERACION = 10
MIN_PRECIO_MONEDA = 0.005
LISTA_NEGRA_PATH = "lista_negra.json"

if not os.path.exists(LISTA_NEGRA_PATH):
    with open(LISTA_NEGRA_PATH, "w") as f:
        json.dump({}, f)

def enviar_telegram(msg):
    try:
        telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("Error al enviar mensaje Telegram:", e)

def cargar_lista_negra():
    with open(LISTA_NEGRA_PATH, "r") as f:
        datos = json.load(f)
    ahora = datetime.utcnow()
    return {k: v for k, v in datos.items() if (ahora - datetime.fromisoformat(v)).total_seconds() < 21600}

def guardar_lista_negra(lista):
    with open(LISTA_NEGRA_PATH, "w") as f:
        json.dump(lista, f)

def obtener_mejor_moneda():
    monedas = client.get_ticker_24hr()
    lista_negra = cargar_lista_negra()
    mejores = sorted([m for m in monedas if m["symbol"].endswith("USDT")
                      and m["symbol"] not in lista_negra
                      and float(m["lastPrice"]) > MIN_PRECIO_MONEDA],
                     key=lambda x: float(x["priceChangePercent"]), reverse=True)
    return mejores[:10]

def intentar_comprar():
    usdt = float(client.get_asset_balance(asset='USDT')["free"])
    if usdt < MIN_USDT_OPERACION:
        print("No hay suficiente USDT para operar.")
        return

    cantidad_usdt = usdt * PORCENTAJE_MAX_USDT
    monedas = obtener_mejor_moneda()
    lista_negra = cargar_lista_negra()

    for moneda in monedas:
        symbol = moneda["symbol"]
        precio = float(moneda["lastPrice"])
        cantidad = round(cantidad_usdt / precio, 5)

        try:
            order = client.order_market_buy(symbol=symbol, quantity=cantidad)
            enviar_telegram("✅ Compra realizada: {} → {}".format(symbol, cantidad))
            return
        except Exception as e:
            mensaje = str(e)
            enviar_telegram("⚠️ No se pudo comprar {}:
{}".format(symbol, mensaje))
            lista_negra[symbol] = datetime.utcnow().isoformat()
            guardar_lista_negra(lista_negra)

def resumen_diario():
    try:
        cuenta = client.get_account()
        balances = [b for b in cuenta["balances"] if float(b["free"]) > 0]
        resumen = "\n".join(["{}: {}".format(b['asset'], b['free']) for b in balances])
        enviar_telegram("📊 Resumen diario de cuenta:\n{}".format(resumen))
    except Exception as e:
        print("Error en resumen diario:", e)

enviar_telegram("🤖 Bot iniciado y analizando mercado...")
scheduler = BackgroundScheduler()
scheduler.add_job(intentar_comprar, 'interval', seconds=30)
scheduler.add_job(resumen_diario, 'cron', hour=23, minute=0)
scheduler.start()

while True:
    time.sleep(10)
