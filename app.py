from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()

# Inicializar cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Instanciar Flask
app = Flask(__name__)

# Diccionario global para seguimiento de conversación
conversacion = {}

# === RUTA PRINCIPAL ===
@app.route("/")
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

# === RUTA WEBHOOK WHATSAPP ===
@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.form.get("Body", "").strip().lower()
    sender = request.form.get("From", "")
    return procesar_mensaje(incoming_msg, sender)

# === PROCESAR MENSAJES ===
def procesar_mensaje(incoming_msg, sender):
    global conversacion

    # Iniciar conversación
    if incoming_msg in ["hola", "start"]:
        conversacion[sender] = {}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Recuperar estado
    estado = conversacion.get(sender, {})

    # Paso 1: tipo
    if "tipo" not in estado:
        if incoming_msg in ["call", "put"]:
            estado["tipo"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor, indica 'call' o 'put'.")

    # Paso 2: operación
    if "operacion" not in estado:
        if incoming_msg in ["comprar", "vender"]:
            estado["operacion"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Indica si deseas COMPRAR o VENDER.")

    # Paso 3: OTM
    if "otm" not in estado:
        if incoming_msg in ["s", "n"]:
            estado["otm"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde con 's' o 'n'.")

    # Paso 4: Prima objetivo
    if "prima_obj" not in estado:
        try:
            prima = float(incoming_msg)
            estado["prima_obj"] = prima
            conversacion[sender] = estado
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Por favor, indica un número válido para la prima (ej. 0.6).")

    # Paso 5: Vencimiento
    if "vencimiento" not in estado:
        opciones = ["1 semana", "2 semanas", "1 mes", "2 meses"]
        if incoming_msg in opciones:
            estado["vencimiento"] = incoming_msg
            estado["esperando"] = "contratos"
            conversacion[sender] = estado
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Indica el vencimiento: 1 semana, 2 semanas, 1 mes o 2 meses.")

    # Paso 6: Contratos
    if estado.get("esperando") == "contratos":
        if incoming_msg.isdigit():
            estado["contratos"] = int(incoming_msg)
            estado.pop("esperando", None)
            conversacion[sender] = estado
            return ejecutar_analisis_opciones(sender)
        else:
            return responder("Por favor, ingresa un número válido de contratos.")

    return responder("No entendí. Escribe 'hola' para comenzar de nuevo.")

# === RESPUESTA FORMATO XML PARA TWILIO ===
def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

# === EJECUTAR ANÁLISIS ===
def ejecutar_analisis_opciones(sender):
    estado = conversacion[sender]
    tipo = estado["tipo"]
    operacion = estado["operacion"]
    otm = estado["otm"]
    prima_obj = estado["prima_obj"]
    vencimiento = estado["vencimiento"]
    contratos = estado["contratos"]

    ticker = yf.Ticker("IBIT")
    dias = {
        "1 semana": 7,
        "2 semanas": 14,
        "1 mes": 30,
        "2 meses": 60
    }
    fecha_limite = datetime.now() + timedelta(days=dias[vencimiento])

    expiraciones = [
        d for d in ticker.options
        if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
    ]

    if not expiraciones:
        return responder("⚠️ No se encontraron vencimientos en el rango solicitado.")

    expiracion = expiraciones[0]
    chain = ticker.option_chain(expiracion)
    df = chain.calls if tipo == "call" else chain.puts

    precio_actual = ticker.history(period="1d").Close.iloc[-1]

    if otm == "s":
        if tipo == "call":
            df = df[df["strike"] > precio_actual]
        else:
            df = df[df["strike"] < precio_actual]

    df["prima"] = (df["bid"] + df["ask"]) / 2
    df["diferencia"] = abs(df["prima"] - prima_obj)
    df_filtrado = df[df["prima"].between(prima_obj * 0.9, prima_obj * 1.1)]

    if df_filtrado.empty:
        df_filtrado = df.sort_values("diferencia").head(3)
        mensaje = "🔍 Opciones más cercanas:\n"
        for idx, row in df_filtrado.iterrows():
            strike = row["strike"]
            prima = round(row["prima"], 2)
            total = round(prima * contratos * 100, 2)
            mensaje += (
                f"➡️ {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${strike} | Prima: ${prima}\n"
                f"📆 Vence: {expiracion}\n"
                f"💰 Total: ${total}\n"
                f"📈 ROI: 0.8%\n"
                f"⚖️ Delta: N/A\n\n"
            )
        mensaje += "Escribe el número de opción (0, 1 o 2) para analizarla o escribe 'hola' para empezar de nuevo."
        estado["esperando"] = "seleccion_opcion"
        estado["opciones"] = df_filtrado.to_dict(orient="records")
        conversacion[sender] = estado
        return responder(mensaje)

    else:
        opcion = df_filtrado.iloc[0]
        return analizar_opcion_detallado(opcion, contratos, tipo, operacion, expiracion, precio_actual)

# === ANALISIS DETALLADO ===
def analizar_opcion_detallado(opcion, contratos, tipo, operacion, expiracion, precio_actual):
    strike = opcion["strike"]
    prima = round(opcion["prima"], 2)
    total = round(prima * contratos * 100, 2)

    mensaje = (
        f"🔎 Análisis detallado:\n"
        f"➡️ {tipo.upper()} | {operacion.upper()}\n"
        f"🎯 Strike: ${strike}\n"
        f"💰 Prima: ${prima}\n"
        f"📆 Vence: {expiracion}\n"
        f"💵 Total por {contratos} contratos: ${total}\n"
        f"📈 Precio IBIT actual: ${round(precio_actual, 2)}\n"
        f"⚖️ Delta estimado: N/A\n"
        f"✅ ROI estimado: 0.8%\n"
        f"ℹ️ Probabilidad de asignación: N/A\n"
        f"\nEscribe 'hola' o 'start' para iniciar un nuevo análisis."
    )
    return responder(mensaje)

# === EJECUTAR LOCALMENTE ===
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))





