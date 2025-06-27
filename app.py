from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import numpy as np
import yfinance as yf
from openai import OpenAI
from scipy.stats import norm

# Cargar variables de entorno
load_dotenv()

# Inicializar OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Diccionario para mantener el estado conversacional por número
# En producción sería ideal usar base de datos o sesión persistente
estado_usuario = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    numero = request.form.get('From')
    incoming_msg = request.form.get('Body', '').strip().lower()

    # Reiniciar conversación si dice hola o start
    if incoming_msg in ["hola", "start"]:
        estado_usuario[numero] = {}
        return responder("👋 ¡Hola! ¿Qué tipo de opción quieres analizar? (call o put)")

    # Recuperar estado de la conversación
    user_state = estado_usuario.get(numero, {})

    # Flujo de preguntas
    if 'tipo' not in user_state:
        if incoming_msg in ['call', 'put']:
            user_state['tipo'] = incoming_msg
            estado_usuario[numero] = user_state
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Indica si deseas analizar una opción 'call' o 'put'.")

    if 'operacion' not in user_state:
        if incoming_msg in ['comprar', 'vender']:
            user_state['operacion'] = incoming_msg
            estado_usuario[numero] = user_state
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Indica si deseas COMPRAR o VENDER la opción.")

    if 'otm' not in user_state:
        if incoming_msg in ['s', 'n']:
            user_state['otm'] = incoming_msg == 's'
            estado_usuario[numero] = user_state
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde s o n para indicar si deseas solo opciones OTM.")

    if 'prima' not in user_state:
        try:
            user_state['prima'] = float(incoming_msg)
            estado_usuario[numero] = user_state
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except ValueError:
            return responder("Introduce un valor numérico para la prima objetivo.")

    if 'vencimiento' not in user_state:
        if incoming_msg in ['1 semana', '2 semanas', '1 mes', '2 meses']:
            user_state['vencimiento'] = incoming_msg
            estado_usuario[numero] = user_state
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Indica el vencimiento: 1 semana, 2 semanas, 1 mes o 2 meses.")

    if 'contratos' not in user_state:
        try:
            user_state['contratos'] = int(incoming_msg)
            estado_usuario[numero] = user_state
            # Ejecutar análisis
            opciones, mensaje = ejecutar_analisis_opciones(user_state)
            if opciones:
                user_state['opciones_encontradas'] = opciones
                estado_usuario[numero] = user_state
                return responder(
                    mensaje +
                    "\n\n➡️ Escribe el número de la opción que quieres analizar en detalle (1, 2 o 3), o 'reiniciar' para empezar de nuevo."
                )
            else:
                return responder(mensaje + "\n\nEscribe 'hola' para reiniciar.")
        except ValueError:
            return responder("Introduce un número entero para los contratos.")

    if 'opciones_encontradas' in user_state:
        if incoming_msg in ['reiniciar', 'hola', 'start']:
            estado_usuario[numero] = {}
            return responder("🔄 Flujo reiniciado. ¿Qué tipo de opción quieres analizar? (call o put)")

        try:
            idx = int(incoming_msg) - 1
            opciones = user_state['opciones_encontradas']
            if 0 <= idx < len(opciones):
                detalle = generar_analisis_detallado(opciones[idx], user_state)
                estado_usuario[numero] = {}  # Reiniciar estado tras análisis
                return responder(detalle + "\n\n✅ Escribe 'hola' o 'start' para analizar otra operación.")
            else:
                return responder("⚠️ Índice fuera de rango. Elige entre 1, 2 o 3.")
        except ValueError:
            return responder("⚠️ Por favor, indica el número de la opción que deseas analizar (1, 2 o 3).")

    return responder("❌ Ha ocurrido un error inesperado. Escribe 'hola' para reiniciar.")

def responder(texto):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{texto}</Message>
</Response>"""

def ejecutar_analisis_opciones(user_state):
    tipo = user_state['tipo']
    operacion = user_state['operacion']
    otm = user_state['otm']
    prima_obj = user_state['prima']
    vencimiento = user_state['vencimiento']
    contratos = user_state['contratos']

    ticker = yf.Ticker("IBIT")

    # Obtener fecha límite
    dias = {
        '1 semana': 7,
        '2 semanas': 14,
        '1 mes': 30,
        '2 meses': 60
    }[vencimiento]
    fecha_limite = datetime.now() + timedelta(days=dias)

    expiraciones = [
        d for d in ticker.options
        if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
    ]
    if not expiraciones:
        return None, "⚠️ No se encontraron vencimientos disponibles en ese rango."

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
    df_filtrado = df[
        (df["prima"] >= prima_obj * 0.9) &
        (df["prima"] <= prima_obj * 1.1)
    ]

    if df_filtrado.empty:
        df_filtrado = df.copy().sort_values("diferencia").head(3)

    opciones = []
    mensaje = "🔍 Opciones más cercanas:\n"

    for i, row in df_filtrado.head(3).iterrows():
        strike = row["strike"]
        prima = round(row["prima"], 2)
        fecha = expiracion
        total = round(prima * contratos * 100, 2)
        roi = round((prima / precio_actual) * 100, 2) if precio_actual else 0
        delta = "N/A"
        opciones.append({
            "tipo": tipo,
            "operacion": operacion,
            "strike": strike,
            "prima": prima,
            "expiracion": fecha,
            "total": total,
            "roi": roi,
            "contratos": contratos,
            "precio_actual": precio_actual
        })
        mensaje += (
            f"[{len(opciones)}] ➡️ {tipo.upper()} | {operacion.upper()}\n"
            f"🎯 Strike: ${strike} | Prima: ${prima}\n"
            f"📆 Vence: {fecha}\n"
            f"💰 Total: ${total}\n"
            f"📈 ROI: {roi}%\n\n"
        )

    return opciones, mensaje

def generar_analisis_detallado(opcion, user_state):
    # Calcular Delta
    delta = calcular_delta(
        tipo=opcion["tipo"],
        S=opcion["precio_actual"],
        K=opcion["strike"],
        T=dias_a_expiracion(opcion["expiracion"]),
        sigma=0.2  # Volatilidad asumida del 20%
    )

    detalle = (
        f"📊 **Análisis Detallado**\n"
        f"Tipo: {opcion['tipo'].upper()}\n"
        f"Operación: {opcion['operacion'].upper()}\n"
        f"Strike: ${opcion['strike']}\n"
        f"Prima: ${opcion['prima']}\n"
        f"Total por {opcion['contratos']} contratos: ${opcion['total']}\n"
        f"Expiración: {opcion['expiracion']}\n"
        f"Precio IBIT actual: ${round(opcion['precio_actual'], 2)}\n"
        f"ROI semanal estimado: {opcion['roi']}%\n"
        f"Delta estimado: {round(delta, 4)}\n"
    )

    return detalle

def dias_a_expiracion(fecha_str):
    fecha_exp = datetime.strptime(fecha_str, "%Y-%m-%d")
    dias = (fecha_exp - datetime.now()).days
    return max(dias / 365, 0.001)

def calcular_delta(tipo, S, K, T, sigma, r=0.05):
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        if tipo == "call":
            delta = norm.cdf(d1)
        else:
            delta = norm.cdf(d1) - 1
        return delta
    except Exception:
        return 0

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))



