from flask import Flask, request
import os
from dotenv import load_dotenv
import yfinance as yf
from openai import OpenAI
from datetime import datetime, timedelta
import math

# Cargar variables de entorno
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Crear app Flask
app = Flask(__name__)

# Estados de conversación por usuario
user_states = {}

# -------- FUNCIONES AUXILIARES --------

def calcular_delta_call(S, K, T, r, sigma):
    """
    Calcula el delta de una call europea usando Black-Scholes.
    """
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        # Distribución normal acumulada
        delta = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
        return round(delta, 4)
    except Exception:
        return "N/A"

# -------- FLUJO PRINCIPAL --------

@app.route("/", methods=["GET"])
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    incoming_msg = request.form.get("Body", "").strip().lower()
    sender = request.form.get("From", "")

    # Reinicio explícito
    if incoming_msg in ["hola", "start"]:
        user_states[sender] = {"state": "tipo_opcion"}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Nuevo usuario → comenzar flujo
    if sender not in user_states:
        user_states[sender] = {"state": "tipo_opcion"}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Estado actual
    state = user_states[sender]["state"]

    # Paso 1: tipo de opción
    if state == "tipo_opcion":
        if incoming_msg in ["call", "put"]:
            user_states[sender]["tipo"] = incoming_msg
            user_states[sender]["state"] = "operacion"
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor escribe 'call' o 'put'.")

    # Paso 2: operación
    if state == "operacion":
        if incoming_msg in ["comprar", "vender"]:
            user_states[sender]["operacion"] = incoming_msg
            user_states[sender]["state"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Indica si deseas COMPRAR o VENDER.")

    # Paso 3: OTM
    if state == "otm":
        if incoming_msg in ["s", "n"]:
            user_states[sender]["otm"] = incoming_msg
            user_states[sender]["state"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde 's' o 'n'.")

    # Paso 4: Prima
    if state == "prima":
        try:
            prima_obj = float(incoming_msg)
            user_states[sender]["prima"] = prima_obj
            user_states[sender]["state"] = "vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Por favor escribe un número como prima objetivo (ej. 0.5).")

    # Paso 5: vencimiento
    if state == "vencimiento":
        opciones_validas = ["1 semana", "2 semanas", "1 mes", "2 meses"]
        if incoming_msg in opciones_validas:
            user_states[sender]["vencimiento"] = incoming_msg
            user_states[sender]["state"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder(f"Responde con una de estas opciones: {', '.join(opciones_validas)}")

    # Paso 6: contratos
    if state == "contratos":
        try:
            contratos = int(incoming_msg)
            user_states[sender]["contratos"] = contratos

            # Ejecutar análisis
            return ejecutar_analisis(sender)
        except:
            return responder("Indica un número entero de contratos.")

    # Si nada matchea → reiniciar
    return responder("Escribe 'hola' para comenzar un nuevo análisis.")

# -------- FUNCIONES DE RESPUESTA --------

def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

def ejecutar_analisis(sender):
    try:
        estado = user_states[sender]
        tipo = estado["tipo"]
        operacion = estado["operacion"]
        otm = estado["otm"] == "s"
        prima_obj = estado["prima"]
        vencimiento_texto = estado["vencimiento"]
        contratos = estado["contratos"]

        # Mapeo vencimiento → días
        dias_vto = {
            "1 semana": 7,
            "2 semanas": 14,
            "1 mes": 30,
            "2 meses": 60
        }[vencimiento_texto]

        fecha_limite = datetime.today() + timedelta(days=dias_vto)

        ticker = yf.Ticker("IBIT")
        expiraciones = [
            d for d in ticker.options
            if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
        ]

        if not expiraciones:
            return responder("⚠️ No hay vencimientos disponibles en el rango solicitado.")

        # Tomar la expiración más cercana
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
        df["diferencia"] = abs(df["prima"] - prima_obj)

        # Buscar matches dentro de ±10%
        rango = prima_obj * 0.1
        df_match = df[
            (df["prima"] >= prima_obj - rango) &
            (df["prima"] <= prima_obj + rango)
        ]

        if df_match.empty:
            # Mostrar las 3 más cercanas
            df_match = df.sort_values("diferencia").head(3)

            mensaje = "🔍 Opciones más cercanas:\n"
            for _, row in df_match.iterrows():
                delta = calcular_delta_call(
                    S=precio_actual,
                    K=row["strike"],
                    T=max(dias_vto/365, 0.0001),
                    r=0.03,
                    sigma=0.5
                )
                total = round(row["prima"] * contratos * 100, 2)
                mensaje += (
                    f"➡️ {tipo.upper()} | {operacion.upper()}\n"
                    f"🎯 Strike: ${row['strike']} | Prima: ${round(row['prima'], 2)}\n"
                    f"📆 Vence: {expiracion}\n"
                    f"💰 Total: ${total}\n"
                    f"📈 ROI: {round((row['prima']/precio_actual)*100, 2)}%\n"
                    f"⚖️ Delta: {delta}\n\n"
                )
            mensaje += "✅ Responde con el STRIKE que deseas analizar en detalle, o escribe 'hola' para empezar de nuevo."
            user_states[sender]["state"] = "esperando_strike"
            user_states[sender]["opciones_sugeridas"] = df_match
            return responder(mensaje)
        else:
            # Tomar la primera encontrada
            row = df_match.iloc[0]
            return generar_analisis_detallado(row, estado, expiracion, precio_actual)

    except Exception as e:
        return responder(f"❌ Ocurrió un error durante el análisis: {e}")

# Manejo de selección de strike
@app.route("/whatsapp", methods=["POST"])
def whatsapp_with_strike():
    incoming_msg = request.form.get("Body", "").strip().lower()
    sender = request.form.get("From", "")

    if sender in user_states and user_states[sender]["state"] == "esperando_strike":
        try:
            strike_elegido = float(incoming_msg)
            df = user_states[sender]["opciones_sugeridas"]
            row = df.loc[df["strike"] == strike_elegido].iloc[0]

            estado = user_states[sender]
            expiracion = ticker.options[0]
            precio_actual = yf.Ticker("IBIT").history(period="1d").Close.iloc[-1]

            return generar_analisis_detallado(row, estado, expiracion, precio_actual)

        except Exception:
            return responder("❌ No encontré esa strike en las opciones sugeridas. Escribe 'hola' para reiniciar.")
    else:
        # Si no está en estado de strike, sigue el flujo normal
        return whatsapp()

def generar_analisis_detallado(row, estado, expiracion, precio_actual):
    tipo = estado["tipo"]
    operacion = estado["operacion"]
    contratos = estado["contratos"]

    delta = calcular_delta_call(
        S=precio_actual,
        K=row["strike"],
        T=max((datetime.strptime(expiracion, "%Y-%m-%d") - datetime.today()).days/365, 0.0001),
        r=0.03,
        sigma=0.5
    )
    total = round(row["prima"] * contratos * 100, 2)

    mensaje = (
        f"🔔 **ANÁLISIS DETALLADO**\n"
        f"➡️ Tipo: {tipo.upper()} | {operacion.upper()}\n"
        f"🎯 Strike: ${row['strike']}\n"
        f"💰 Prima: ${round(row['prima'], 2)}\n"
        f"📆 Vencimiento: {expiracion}\n"
        f"⚖️ Delta estimado: {delta}\n"
        f"📈 ROI estimado: {round((row['prima']/precio_actual)*100, 2)}%\n"
        f"💵 Total prima x {contratos} contrato(s): ${total}\n"
        f"Precio actual IBIT: ${round(precio_actual, 2)}\n\n"
        f"✅ Escribe 'hola' para iniciar un nuevo análisis."
    )
    user_states.pop(sender, None)  # Limpiar estado después del análisis
    return responder(mensaje)

# -------- MAIN --------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))





