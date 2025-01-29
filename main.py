# Importación de librerías necesarias
import os
import json
import asyncio
import websockets
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime

# Carga de variables de entorno
load_dotenv()
assert os.getenv("SIMPLEFX_CLIENT_ID"), "❌ SIMPLEFX_CLIENT_ID no configurada"
assert os.getenv("SIMPLEFX_CLIENT_SECRET"), "❌ SIMPLEFX_CLIENT_SECRET no configurada"
assert os.getenv("GEMINI_API_KEY"), "❌ GEMINI_API_KEY no configurada"

# Configuración de Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-pro')

# Variables globales para el control del procesamiento
processing_lock = asyncio.Lock()
last_processed = 0
tick_count = 0
last_100_ticks = []

# Función para analizar datos de mercado con Gemini AI
def analyze_with_gemini(market_data):
    prompt = f"""
    Eres un experto trader cuantitativo.
    Analiza estos datos de mercado y proporciona una señal de trading detallada:
    Símbolo: {market_data['symbol']}
    Precio de oferta: {market_data['bid']}
    Precio de demanda: {market_data['ask']}
    Marca de tiempo: {market_data['timestamp']}

    Genera una respuesta concisa con una recomendación de trading, un porcentaje de confianza,
    y sugerencias para Take Profit (TP) y Stop Loss (SL) basadas en una estrategia de medias móviles.
    Formato de respuesta: 
    "Acción: [comprar/vender/mantener], Confianza: [0-100]%, TP: [precio], SL: [precio], Explicación: "
    """

    try:
        response = model.generate_content(prompt)
        return {"analysis": response.text.strip()}
    except Exception as e:
        return {"error": f"Error en el análisis: {str(e)}"}


# Función para manejar los datos de mercado recibidos
async def handle_market_data(quote: dict):
    global last_processed, tick_count, last_100_ticks
    try:
        async with processing_lock:
            current_time = asyncio.get_event_loop().time()
            tick_count += 1
            last_100_ticks.append(quote)
            if len(last_100_ticks) > 100:
                last_100_ticks.pop(0)

            if tick_count % 100 == 0 and current_time - last_processed >= 30:
                market_data = {
                    "symbol": quote['s'],
                    "bid": quote['b'],
                    "ask": quote['a'],
                    "timestamp": quote['t']
                }

                formatted_time = datetime.fromtimestamp(market_data['timestamp'] / 1000).strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n🔔 Nuevos datos (Delay: {current_time - last_processed:.1f}s):")
                print(f"   Precio: {market_data['bid']} | Hora: {formatted_time}")

                print("🧠 Procesando con Gemini...")
                analysis = analyze_with_gemini(market_data)
                last_processed = current_time

                print("\n📈 Señal Generada:")
                if "error" in analysis:
                    print(f"   Error: {analysis['error']}")
                else:
                    print(f"   {analysis['analysis']}")
                print("─" * 50)

    except Exception as e:
        print(f"⚠️  Error crítico: {str(e)}")


# Función para gestionar la conexión WebSocket
async def manage_websocket():
    uri = "wss://web-quotes-core.simplefx.com/websocket/quotes"

    async with websockets.connect(uri) as ws:
        # Autenticación con SimpleFX
        await ws.send(json.dumps({
            "p": "/auth/key",
            "i": 1,
            "d": {
                "clientId": os.getenv("SIMPLEFX_CLIENT_ID"),
                "clientSecret": os.getenv("SIMPLEFX_CLIENT_SECRET")
            }
        }))
        await ws.recv()

        # Suscripción a BTCUSD
        await ws.send(json.dumps({
            "p": "/subscribe/addList",
            "i": 2,
            "d": ["BTCUSD"]
        }))

        # Bucle principal para recibir y procesar datos
        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(message)

                if data.get('p') == '/quotes/subscribed':
                    for quote in data['d']:
                        asyncio.create_task(handle_market_data(quote))

            except (websockets.ConnectionClosed, asyncio.TimeoutError):
                print("🔁 Reconectando...")
                await manage_websocket()
                break
            except Exception as e:
                print(f"⚠️  Error: {str(e)}")

# Punto de entrada principal del script
if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("🚀 Sistema de Trading Activo")
    print("🔑 Usando Gemini Pro")

    try:
        asyncio.run(manage_websocket())
    except KeyboardInterrupt:
        print("\n🔴 Sistema detenido")
