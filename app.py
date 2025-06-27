from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI
import math

# === Configuración ===

# Cargar variables de entorno
load_dotenv()

# Inicializar cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Inicializar app Flask
app = Flask(__name__)

# === Funciones auxiliares ===

def norm_cdf(x):
    """
    Función de distribución acumulada normal estándar
    (sustituto de scipy.stats.norm.cdf)
    """
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def calcular_delta_call(S, K, T, r, sigma):
    """
    Calcula delta de una call europea usando Black-Scholes.
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1)

# === Lógica del bot ===

# Estado conversacional
conversacion = {}

@app.route("/")
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.form.get("Body", "").strip().lower()
    sender = request.form.get("From", "unknown")

    # Verificar si el usuario tiene un flujo activo
    estado = conversacion.get(sender, {})

    if incoming_msg in ["hola", "start"]:
        conversacion[sender] = {}
        return responder("👋 ¡Hola! Vamos a analizar una opción.\n¿Qué tipo de opción quieres analizar? (call o put)")

    if "tipo" not in estado:
        if incoming_msg in ["call", "put"]:
            estado["tipo"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor responde 'call' o 'put'.")

    if "operacion" not in estado:
        if incoming_msg in ["comprar", "vender"]:
            estado["operacion"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Responde 'comprar' o 'vender'.")

    if "otm" not in estado:
        if incoming_msg in ["s", "n"]:
            estado["otm"] = incoming_msg == "s"
            conversacion[sender] = estado
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde 's' o 'n'.")

    if "prima" not in estado:
        try:
            estado["prima"] = float(incoming_msg.replace("$","").strip())
            conversacion[sender] = estado
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Por favor indica un número para la prima.")

    if "vencimiento" not in estado:
        opciones = ["1 semana", "2 semanas", "1 mes", "2 meses"]
        if incoming_msg in opciones:
            estado["vencimiento"] = incoming_msg
            conversacion[sender] = estado
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Indica el vencimiento: 1 semana, 2 semanas, 1 mes o 2 meses.")

    if "contratos" not in estado:
        try:
            estado["contratos"] = int(incoming_msg)
            conversacion[sender] = estado
            return mostrar_opciones(sender)
        except:
            return responder("Indica la cantidad de contratos como un número entero.")

    # Si envía un índice de selección
    if estado.get("opciones_mostradas") and incoming_msg.isdigit():
        idx = int(incoming_msg)
        opciones = estado["opciones_mostradas"]
        if 0 <= idx < len(opciones):
            opcion = opciones[idx]
            return analizar_opcion(sender, opcion)
        else:
            return responder(f"Índice inválido. Ingresa un número entre 0 y {len(opciones)-1}.")

    return responder("No entendí. Escribe 'hola' para comenzar de nuevo.")

def mostrar_opciones(sender):
    """
    Busca opciones y muestra las 3 más cercanas.
    """
    estado = conversacion[sender]
    tipo = estado["tipo"]
    operacion = estado["operacion"]
    otm = estado["otm"]
    prima_obj = estado["prima"]
    vencimiento = estado["vencimiento"]
    contratos = estado["contratos"]

    ticker = yf.Ticker("IBIT")
    dias = {
        "1 semana": 7,
        "2 semanas": 14,
        "1 mes": 30,
        "2 meses": 60,
    }[vencimiento]
    fecha_limite = datetime.now() + timedelta(days=dias)
    expiraciones = [
        d for d in ticker.options
        if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
    ]

    if not expiraciones:
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
    df["diferencia"] = abs(df["prima"] - prima_obj)

    opciones = df.sort_values("diferencia").head(3)

    if opciones.empty:
        return responder("⚠️ No se encontraron opciones cercanas.")

    mensajes = []
    opciones_data = []
    for i, row in opciones.iterrows():
        total = row["prima"] * contratos * 100
        mensajes.append(
            f"[{len(opciones_data)}] Strike: ${row['strike']}, Prima: ${round(row['prima'], 2)}, Vence: {expiracion}, Total: ${round(total,2)}"
        )
        opciones_data.append({
            "strike": row["strike"],
            "prima": row["prima"],
            "expiracion": expiracion,
            "total": total,
        })

    estado["opciones_mostradas"] = opciones_data
    conversacion[sender] = estado

    mensaje = "🔍 Opciones más cercanas:\n" + "\n".join(mensajes)
    mensaje += "\n\nResponde con el número de la opción que quieres analizar (ej. 0)."
    return responder(mensaje)

def analizar_opcion(sender, opcion):
    """
    Devuelve un análisis detallado de la opción seleccionada.
    """
    estado = conversacion[sender]
    tipo = estado["tipo"]
    operacion = estado["operacion"]
    contratos = estado["contratos"]

    # Parámetros dummy para volatilidad y tasa (puedes ajustar según tu data real)
    S = yf.Ticker("IBIT").history(period="1d").Close.iloc[-1]
    K = opcion["strike"]
    T = max((datetime.strptime(opcion["expiracion"], "%Y-%m-%d") - datetime.now()).days / 365, 1/365)
    r = 0.02
    sigma = 0.5

    delta = calcular_delta_call(S, K, T, r, sigma) if tipo == "call" else None
    prob_asignacion = round(delta * 100, 2) if delta is not None else "N/A"
    roi = round((opcion["prima"] * 100) / S * 100, 2)

    mensaje = (
        f"📊 Análisis detallado:\n"
        f"➡️ {tipo.upper()} | {operacion.upper()}\n"
        f"🎯 Strike: ${K}\n"
        f"💰 Prima por contrato: ${round(opcion['prima'], 2)}\n"
        f"💵 Total: ${round(opcion['total'],2)} por {contratos} contrato(s)\n"
        f"📆 Vence: {opcion['expiracion']}\n"
        f"📈 ROI estimado: {roi}%\n"
        f"⚖️ Delta: {round(delta, 4) if delta else 'N/A'}\n"
        f"🔗 Probabilidad de asignación: {prob_asignacion}%\n"
        f"✅ Escribe 'hola' o 'start' para empezar otro análisis."
    )

    conversacion[sender] = {}
    return responder(mensaje)

def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

# Ejecutar localmente
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))




