from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
import numpy as np

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Diccionario para guardar el estado de conversación de cada usuario
conversacion = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    sender = request.form.get('From')
    incoming_msg = normalizar_input(request.form.get('Body', ''))

    # Reinicio explícito
    if incoming_msg in ['hola', 'start']:
        conversacion[sender] = {}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Si no hay conversación iniciada
    if sender not in conversacion:
        conversacion[sender] = {}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    estado = conversacion[sender]

    # Paso 1 - Tipo de opción
    if 'tipo' not in estado:
        if incoming_msg not in ['call', 'put']:
            return responder("Por favor escribe 'call' o 'put'.")
        estado['tipo'] = incoming_msg
        return responder("¿Vas a COMPRAR o VENDER esta opción?")

    # Paso 2 - Operación
    if 'operacion' not in estado:
        if incoming_msg not in ['comprar', 'vender']:
            return responder("Por favor escribe 'comprar' o 'vender'.")
        estado['operacion'] = incoming_msg
        return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

    # Paso 3 - OTM o no
    if 'otm' not in estado:
        if incoming_msg not in ['s', 'n']:
            return responder("Por favor responde 's' o 'n'.")
        estado['otm'] = incoming_msg == 's'
        return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

    # Paso 4 - Prima objetivo
    if 'prima_obj' not in estado:
        try:
            estado['prima_obj'] = float(incoming_msg.replace(",", "."))
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except ValueError:
            return responder("Por favor ingresa un número válido para la prima objetivo.")

    # Paso 5 - Vencimiento
    if 'vencimiento' not in estado:
        opciones_validas = ['1 semana', '2 semanas', '1 mes', '2 meses']
        if incoming_msg not in opciones_validas:
            return responder(f"Por favor elige entre: {', '.join(opciones_validas)}.")
        estado['vencimiento'] = incoming_msg
        return responder("¿Cuántos contratos deseas analizar?")

    # Paso 6 - Contratos
    if 'contratos' not in estado:
        try:
            estado['contratos'] = int(incoming_msg)
            return ejecutar_analisis_opciones(sender)
        except ValueError:
            return responder("Por favor ingresa un número válido de contratos.")

    return responder("❌ Ocurrió un error inesperado. Escribe 'hola' para reiniciar.")

def normalizar_input(texto):
    """
    Devuelve el texto en minúsculas, sin espacios sobrantes.
    """
    return texto.strip().lower()

def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

def ejecutar_analisis_opciones(sender):
    estado = conversacion[sender]
    tipo = estado['tipo']
    operacion = estado['operacion']
    otm = estado['otm']
    prima_obj = estado['prima_obj']
    vencimiento = estado['vencimiento']
    contratos = estado['contratos']

    ticker = yf.Ticker("IBIT")
    precio_actual = ticker.history(period="1d").Close.iloc[-1]

    # Calcular fecha límite
    dias_venc = {
        "1 semana": 7,
        "2 semanas": 14,
        "1 mes": 30,
        "2 meses": 60
    }
    fecha_limite = datetime.now() + timedelta(days=dias_venc[vencimiento])

    # Buscar expiraciones disponibles
    expiraciones = [
        exp for exp in ticker.options
        if datetime.strptime(exp, "%Y-%m-%d") <= fecha_limite
    ]

    if not expiraciones:
        conversacion.pop(sender, None)
        return responder("⚠️ No se encontraron vencimientos en el rango seleccionado.")

    expiracion = expiraciones[0]
    chain = ticker.option_chain(expiracion)
    df = chain.calls if tipo == "call" else chain.puts

    # Filtrado OTM
    if otm:
        if tipo == "call":
            df = df[df["strike"] > precio_actual]
        else:
            df = df[df["strike"] < precio_actual]

    df["prima"] = (df["bid"] + df["ask"]) / 2
    rango = prima_obj * 0.10
    df_filtrado = df[
        (df["prima"] >= prima_obj - rango) &
        (df["prima"] <= prima_obj + rango)
    ]

    if df_filtrado.empty:
        df["diferencia"] = abs(df["prima"] - prima_obj)
        df_filtrado = df.sort_values("diferencia").head(3)
        mensaje = "⚠️ No se encontraron opciones exactas. Aquí tienes las 3 más cercanas:\n"
    else:
        mensaje = "🔍 Opciones encontradas:\n"

    for i, row in df_filtrado.iterrows():
        strike = row["strike"]
        prima = round(row["prima"], 2)
        delta = round(row["delta"], 3) if "delta" in row and not np.isnan(row["delta"]) else "N/A"
        total = round(prima * contratos * 100, 2)
        roi = round((prima / precio_actual) * 100, 2) if precio_actual > 0 else 0
        mensaje += (
            f"➡️ {tipo.upper()} | {operacion.upper()}\n"
            f"🎯 Strike: ${strike}\n"
            f"💰 Prima: ${prima}\n"
            f"⚖️ Delta: {delta}\n"
            f"📆 Vence: {expiracion}\n"
            f"📈 ROI: {roi}%\n"
            f"💵 Total: ${total} por {contratos} contrato(s)\n\n"
        )

    mensaje += "✅ Escribe 'hola' o 'start' para iniciar un nuevo análisis."

    conversacion.pop(sender, None)
    return responder(mensaje)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))


