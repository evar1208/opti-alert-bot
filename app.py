from flask import Flask, request
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import yfinance as yf
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Memoria simple para mantener estado por usuario
usuarios = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    from_number = request.form.get('From')
    mensaje = request.form.get('Body', '').strip().lower()

    if from_number not in usuarios:
        usuarios[from_number] = {"estado": "inicio"}

    estado_usuario = usuarios[from_number]

    if estado_usuario["estado"] == "inicio":
        estado_usuario["estado"] = "tipo"
        return respuesta("Hola 👋 ¿Qué tipo de opción deseas analizar? (call o put)")

    elif estado_usuario["estado"] == "tipo":
        if mensaje not in ["call", "put"]:
            return respuesta("Por favor responde solo con 'call' o 'put'.")
        estado_usuario["tipo"] = mensaje
        estado_usuario["estado"] = "operacion"
        return respuesta("¿Vas a COMPRAR o VENDER esta opción?")

    elif estado_usuario["estado"] == "operacion":
        if mensaje not in ["comprar", "vender"]:
            return respuesta("Por favor responde solo con 'comprar' o 'vender'.")
        estado_usuario["operacion"] = mensaje
        estado_usuario["estado"] = "otm"
        return respuesta("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

    elif estado_usuario["estado"] == "otm":
        if mensaje not in ["s", "n"]:
            return respuesta("Responde con 's' o 'n'.")
        estado_usuario["otm"] = mensaje == "s"
        estado_usuario["estado"] = "prima"
        return respuesta("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

    elif estado_usuario["estado"] == "prima":
        try:
            estado_usuario["prima"] = float(mensaje)
            estado_usuario["estado"] = "vencimiento"
            return respuesta("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return respuesta("Por favor ingresa un número válido para la prima.")

    elif estado_usuario["estado"] == "vencimiento":
        if mensaje not in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            return respuesta("Elige entre: 1 semana, 2 semanas, 1 mes o 2 meses.")
        estado_usuario["vencimiento"] = mensaje
        estado_usuario["estado"] = "contratos"
        return respuesta("¿Cuántos contratos deseas analizar?")

    elif estado_usuario["estado"] == "contratos":
        try:
            estado_usuario["contratos"] = int(mensaje)
            usuarios[from_number]["estado"] = "hecho"
            return respuesta(analizar_opcion(estado_usuario))
        except:
            return respuesta("Por favor ingresa un número entero válido.")

    else:
        usuarios[from_number]["estado"] = "inicio"
        return respuesta("Vamos a comenzar de nuevo. ¿Qué tipo de opción deseas analizar? (call o put)")

def respuesta(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

def analizar_opcion(data):
    try:
        ticker = yf.Ticker("IBIT")
        dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[data["vencimiento"]]
        fecha_limite = datetime.now() + timedelta(days=dias)
        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones:
            return "⚠️ No se encontraron vencimientos en ese rango."

        expiracion = expiraciones[0]
        df = ticker.option_chain(expiracion).calls if data["tipo"] == "call" else ticker.option_chain(expiracion).puts

        precio_actual = ticker.history(period="1d").Close.iloc[-1]
        if data["otm"]:
            df = df[df["strike"] > precio_actual] if data["tipo"] == "call" else df[df["strike"] < precio_actual]

        df["prima"] = (df["bid"] + df["ask"]) / 2
        rango = data["prima"] * 0.1
        df_filtrado = df[(df["prima"] >= data["prima"] - rango) & (df["prima"] <= data["prima"] + rango)]

        if df_filtrado.empty:
            df["desviacion"] = abs(df["prima"] - data["prima"])
            df_filtrado = df.sort_values("desviacion").head(1)

        opcion = df_filtrado.iloc[0]
        strike = opcion["strike"]
        prima = round(opcion["prima"], 2)
        fecha = expiracion
        contratos = data["contratos"]
        total = round(prima * contratos * 100, 2)
        delta = opcion.get("delta", "N/A")
        roi = round((prima / (strike * 100)) * 100, 2) if strike else "N/A"

        return (
            f"📊 Resultado:\n"
            f"➡️ Tipo: {data['tipo'].upper()} | {data['operacion'].upper()}\n"
            f"🎯 Strike: ${strike} | Prima: ${prima}\n"
            f"📆 Vence: {fecha}\n"
            f"💰 Total: ${total} por {contratos} contrato(s)\n"
            f"📈 ROI: {roi}%\n"
            f"⚖️ Delta: {delta}\n"
            f"\n✅ Escribe 'hola' para iniciar otro análisis."
        )

    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

# Ejecutar localmente
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
