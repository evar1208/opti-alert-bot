from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
app = Flask(__name__)

user_sessions = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    from_number = request.form.get('From')
    incoming_msg = request.form.get('Body', '').strip().lower()

    if from_number not in user_sessions:
        user_sessions[from_number] = {"estado": "inicio"}

    session = user_sessions[from_number]
    estado = session.get("estado")

    if estado == "inicio":
        session["estado"] = "tipo"
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    elif estado == "tipo":
        if incoming_msg in ["call", "put"]:
            session["tipo"] = incoming_msg
            session["estado"] = "operacion"
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor responde 'call' o 'put'.")

    elif estado == "operacion":
        if incoming_msg in ["comprar", "vender"]:
            session["operacion"] = incoming_msg
            session["estado"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Responde 'comprar' o 'vender'.")

    elif estado == "otm":
        if incoming_msg in ["s", "n"]:
            session["otm"] = incoming_msg == "s"
            session["estado"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde 's' para sí o 'n' para no.")

    elif estado == "prima":
        try:
            session["prima"] = float(incoming_msg)
            session["estado"] = "vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Ingresa un número válido para la prima.")

    elif estado == "vencimiento":
        if incoming_msg in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            session["vencimiento"] = incoming_msg
            session["estado"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Opciones válidas: 1 semana, 2 semanas, 1 mes, 2 meses.")

    elif estado == "contratos":
        try:
            session["contratos"] = int(incoming_msg)
            session["estado"] = "completo"
            return responder(ejecutar_analisis_opciones(session))
        except:
            return responder("Ingresa un número válido de contratos.")

    else:
        user_sessions[from_number] = {"estado": "inicio"}
        return responder("✅ Escribe 'hola' para iniciar otro análisis.")

def responder(msg):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>{msg}</Message></Response>"""

def ejecutar_analisis_opciones(datos):
    try:
        tipo = datos["tipo"]
        operacion = datos["operacion"]
        otm = datos["otm"]
        prima_objetivo = datos["prima"]
        vencimiento = datos["vencimiento"]
        contratos = datos["contratos"]

        ticker = yf.Ticker("IBIT")
        dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[vencimiento]
        fecha_limite = datetime.now() + timedelta(days=dias)

        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones:
            return "⚠️ No se encontraron vencimientos dentro del rango solicitado."

        precio_actual = ticker.history(period="1d").Close.iloc[-1]
        opciones = []

        for exp in expiraciones:
            df = ticker.option_chain(exp).calls if tipo == "call" else ticker.option_chain(exp).puts
            if otm:
                df = df[df["strike"] > precio_actual] if tipo == "call" else df[df["strike"] < precio_actual]

            df = df.copy()
            df["prima"] = (df["bid"] + df["ask"]) / 2
            df["diferencia"] = abs(df["prima"] - prima_objetivo)
            opciones.extend([
                {
                    "strike": row["strike"],
                    "prima": round(row["prima"], 2),
                    "exp": exp,
                    "diferencia": row["diferencia"]
                }
                for _, row in df.iterrows()
            ])

        if not opciones:
            return "❌ No se encontraron opciones similares."

        opciones = sorted(opciones, key=lambda x: x["diferencia"])[:3]

        mensaje = "🔍 Opciones más cercanas:"
        for opt in opciones:
            total = round(opt["prima"] * contratos * 100, 2)
            roi = round((opt["prima"] * 100) / (opt["strike"] * 100) * 100, 2)
            mensaje += (
    f"➡️ {tipo.upper()} | {operacion.upper()}\n"
    f"🎯 Strike: ${opt['strike']} | Prima: ${opt['prima']}\n"
    f"📆 Vence: {opt['exp']}\n"
    f"💰 Total: ${total}\n"
    f"📈 ROI: {roi}%\n"
    f"⚖️ Delta: N/A\n\n"
)

        return mensaje.strip()

    except Exception as e:
        return f"❌ Error: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))


