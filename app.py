from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
import numpy as np

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Diccionario para manejar conversaciones
conversacion = {}

# Función para Black-Scholes Delta
def calcular_delta(precio_actual, strike, tiempo_a_vencimiento, tasa, volatilidad, tipo):
    try:
        d1 = (np.log(precio_actual / strike) + (tasa + 0.5 * volatilidad ** 2) * tiempo_a_vencimiento) / (volatilidad * np.sqrt(tiempo_a_vencimiento))
        if tipo == 'call':
            delta = norm.cdf(d1)
        else:
            delta = -norm.cdf(-d1)
        return round(delta, 2)
    except Exception:
        return "N/A"

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    sender = request.form.get('From')
    incoming_msg = request.form.get('Body', '').strip().lower()

    # Inicializar conversación si es nueva
    if sender not in conversacion:
        conversacion[sender] = {}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # No reiniciar si dice hola en medio
    if incoming_msg in ["hola", "start"]:
        if conversacion[sender]:
            return responder("Estás en medio de un análisis. Responde las preguntas para continuar.")
        else:
            conversacion[sender] = {}
            return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    estado = conversacion[sender]

    if 'tipo' not in estado:
        if incoming_msg not in ['call', 'put']:
            return responder("Por favor escribe 'call' o 'put'.")
        estado['tipo'] = incoming_msg
        return responder("¿Vas a COMPRAR o VENDER esta opción?")

    if 'operacion' not in estado:
        if incoming_msg not in ['comprar', 'vender']:
            return responder("Por favor escribe 'comprar' o 'vender'.")
        estado['operacion'] = incoming_msg
        return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

    if 'otm' not in estado:
        if incoming_msg not in ['s', 'n']:
            return responder("Por favor responde 's' o 'n'.")
        estado['otm'] = incoming_msg == 's'
        return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

    if 'prima_obj' not in estado:
        try:
            estado['prima_obj'] = float(incoming_msg.replace(',', '.'))
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Por favor indica un número válido para la prima.")

    if 'vencimiento' not in estado:
        if incoming_msg not in ['1 semana', '2 semanas', '1 mes', '2 meses']:
            return responder("Por favor elige entre: 1 semana, 2 semanas, 1 mes o 2 meses.")
        estado['vencimiento'] = incoming_msg
        return responder("¿Cuántos contratos deseas analizar?")

    if 'contratos' not in estado:
        try:
            estado['contratos'] = int(incoming_msg)
            # Cuando ya tengo toda la info, ejecutar el análisis:
            return ejecutar_analisis_opciones(sender)
        except:
            return responder("Por favor indica un número entero de contratos.")

    return responder("❌ Ocurrió un error inesperado.")

def ejecutar_analisis_opciones(sender):
    estado = conversacion[sender]
    ticker = yf.Ticker("IBIT")
    tipo = estado['tipo']
    operacion = estado['operacion']
    otm = estado['otm']
    prima_obj = estado['prima_obj']
    vencimiento = estado['vencimiento']
    contratos = estado['contratos']

    dias_dict = {
        "1 semana": 7,
        "2 semanas": 14,
        "1 mes": 30,
        "2 meses": 60
    }
    dias = dias_dict[vencimiento]
    fecha_limite = datetime.now() + timedelta(days=dias)

    expiraciones = [
        d for d in ticker.options
        if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
    ]
    if not expiraciones:
        conversacion.pop(sender)
        return responder("⚠️ No se encontraron vencimientos en ese rango.")

    expiracion = expiraciones[0]
    chain = ticker.option_chain(expiracion)
    df = chain.calls if tipo == "call" else chain.puts

    precio_actual = ticker.history(period="1d").Close.iloc[-1]

    if otm:
        if tipo == "call":
            df = df[df["strike"] > precio_actual]
        else:
            df = df[df["strike"] < precio_actual]

    df["prima"] = (df["bid"] + df["ask"]) / 2
    rango = prima_obj * 0.1
    df_filtrado = df[
        (df["prima"] >= prima_obj - rango) &
        (df["prima"] <= prima_obj + rango)
    ]

    if df_filtrado.empty:
        # Tomar las 3 más cercanas
        df["diferencia"] = abs(df["prima"] - prima_obj)
        df_filtrado = df.sort_values("diferencia").head(3)

    mensaje = "🔍 Opciones más cercanas:\n"
    for i, row in df_filtrado.iterrows():
        strike = row["strike"]
        prima = round(row["prima"], 2)
        total = round(prima * contratos * 100, 2)
        delta = round(row["delta"], 2) if "delta" in row and not np.isnan(row["delta"]) else "N/A"
        roi = round((prima / precio_actual) * 100, 2) if precio_actual > 0 else 0

        mensaje += (
            f"➡️ {tipo.upper()} | {operacion.upper()}\n"
            f"🎯 Strike: ${strike} | Prima: ${prima}\n"
            f"📆 Vence: {expiracion}\n"
            f"💰 Total: ${total}\n"
            f"📈 ROI: {roi}%\n"
            f"⚖️ Delta: {delta}\n\n"
        )

    mensaje += "✅ Si deseas reiniciar, escribe 'hola' o 'start'."

    conversacion.pop(sender, None)
    return responder(mensaje)

def responder(msg):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{msg}</Message>
</Response>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))






