from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI
import pandas as pd

# Cargar variables de entorno
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Diccionario para guardar estados de cada usuario
conversacion = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.form.get('Body', '').strip().lower()
    sender = request.form.get('From', '')

    # Reinicio explícito del flujo
    if incoming_msg in ['hola', 'start']:
        conversacion[sender] = {"estado": "esperando_tipo"}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Si no existe conversación previa, forzamos a saludar
    if sender not in conversacion:
        conversacion[sender] = {"estado": "esperando_tipo"}
        return responder("¡Hola! Escribe 'hola' o 'start' para comenzar el análisis.")

    estado_actual = conversacion[sender].get("estado", "")

    # Paso 1 - Tipo de opción
    if estado_actual == "esperando_tipo":
        if incoming_msg not in ['call', 'put']:
            return responder("Por favor escribe 'call' o 'put'.")
        conversacion[sender]["tipo"] = incoming_msg
        conversacion[sender]["estado"] = "esperando_operacion"
        return responder("¿Vas a COMPRAR o VENDER esta opción?")

    # Paso 2 - Operación
    if estado_actual == "esperando_operacion":
        if incoming_msg not in ['comprar', 'vender']:
            return responder("Indica si vas a COMPRAR o VENDER la opción.")
        conversacion[sender]["operacion"] = incoming_msg
        conversacion[sender]["estado"] = "esperando_otm"
        return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

    # Paso 3 - OTM
    if estado_actual == "esperando_otm":
        if incoming_msg not in ['s', 'n']:
            return responder("Responde 's' para sí o 'n' para no.")
        conversacion[sender]["otm"] = (incoming_msg == 's')
        conversacion[sender]["estado"] = "esperando_prima"
        return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

    # Paso 4 - Prima
    if estado_actual == "esperando_prima":
        try:
            prima = float(incoming_msg)
            conversacion[sender]["prima"] = prima
            conversacion[sender]["estado"] = "esperando_vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except ValueError:
            return responder("Por favor ingresa un número para la prima (ej. 0.6).")

    # Paso 5 - Vencimiento
    if estado_actual == "esperando_vencimiento":
        opciones_validas = ["1 semana", "2 semanas", "1 mes", "2 meses"]
        if incoming_msg not in opciones_validas:
            return responder("Indica el vencimiento: 1 semana, 2 semanas, 1 mes o 2 meses.")
        conversacion[sender]["vencimiento"] = incoming_msg
        conversacion[sender]["estado"] = "esperando_contratos"
        return responder("¿Cuántos contratos deseas analizar?")

    # Paso 6 - Contratos
    if estado_actual == "esperando_contratos":
        try:
            contratos = int(incoming_msg)
            conversacion[sender]["contratos"] = contratos
            resultado = ejecutar_analisis_opciones(conversacion[sender])
            conversacion[sender] = {"estado": "esperando_tipo"}
            return responder(resultado + "\n\n✅ Escribe 'hola' para iniciar otro análisis.")
        except ValueError:
            return responder("Por favor ingresa un número entero para la cantidad de contratos.")

    # Si se pierde el flujo, reiniciar
    return responder("Algo salió mal. Escribe 'hola' para reiniciar el análisis.")

def responder(msg):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{msg}</Message>
</Response>"""

def ejecutar_analisis_opciones(contexto):
    try:
        ticker = yf.Ticker("IBIT")

        tipo = contexto["tipo"]
        operacion = contexto["operacion"]
        otm = contexto["otm"]
        prima_obj = contexto["prima"]
        vencimiento = contexto["vencimiento"]
        contratos = contexto["contratos"]

        dias_map = {
            "1 semana": 7,
            "2 semanas": 14,
            "1 mes": 30,
            "2 meses": 60
        }

        dias = dias_map[vencimiento]
        fecha_limite = datetime.now() + timedelta(days=dias)

        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones:
            return "⚠️ No se encontraron vencimientos en ese rango."

        expiracion = expiraciones[0]
        chain = ticker.option_chain(expiracion)
        df = chain.calls if tipo == "call" else chain.puts

        precio_actual = ticker.history(period="1d").Close.iloc[-1]

        if otm:
            if tipo == "call":
                df = df.loc[df["strike"] > precio_actual]
            else:
                df = df.loc[df["strike"] < precio_actual]

        df["prima"] = (df["bid"] + df["ask"]) / 2
        rango = prima_obj * 0.1
        df_filtrado = df[
            (df["prima"] >= prima_obj - rango) &
            (df["prima"] <= prima_obj + rango)
        ]

        if df_filtrado.empty:
            df["diferencia"] = abs(df["prima"] - prima_obj)
            df_filtrado = df.sort_values("diferencia").head(3)
            if df_filtrado.empty:
                return "❌ No se encontraron opciones cercanas."

            mensaje = "🔍 Opciones más cercanas:\n"
            for _, row in df_filtrado.iterrows():
                strike = row["strike"]
                prima = round(row["prima"], 2)
                delta = round(row["delta"], 2) if "delta" in row and not pd.isna(row["delta"]) else "N/A"
                total = round(prima * contratos * 100, 2)
                mensaje += (
                    f"➡️ {tipo.upper()} | {operacion.upper()}\n"
                    f"🎯 Strike: ${strike} | Prima: ${prima}\n"
                    f"📆 Vence: {expiracion}\n"
                    f"💰 Total: ${total}\n"
                    f"📈 ROI: 0.8%\n"
                    f"⚖️ Delta: {delta}\n\n"
                )
            return mensaje.strip()
        else:
            opcion = df_filtrado.iloc[0]
            strike = opcion["strike"]
            prima = round(opcion["prima"], 2)
            delta = round(opcion["delta"], 2) if "delta" in opcion and not pd.isna(opcion["delta"]) else "N/A"
            total = round(prima * contratos * 100, 2)

            return (
                f"📊 Resultado:\n"
                f"➡️ Tipo: {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${strike} | Prima: ${prima}\n"
                f"📆 Vence: {expiracion}\n"
                f"💰 Total: ${total}\n"
                f"📈 ROI: 0.8%\n"
                f"⚖️ Delta: {delta}"
            )
    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))




