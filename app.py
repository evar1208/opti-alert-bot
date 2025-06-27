from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
usuarios = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    numero = request.form.get('From')
    mensaje = request.form.get('Body', '').strip().lower()

    if numero not in usuarios or mensaje in ['hola', 'hi']:
        usuarios[numero] = {"estado": "tipo"}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    estado = usuarios[numero]["estado"]

    if estado == "tipo":
        if mensaje in ["call", "put"]:
            usuarios[numero]["tipo"] = mensaje
            usuarios[numero]["estado"] = "operacion"
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor escribe 'call' o 'put'.")

    if estado == "operacion":
        if mensaje in ["comprar", "vender"]:
            usuarios[numero]["operacion"] = mensaje
            usuarios[numero]["estado"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Por favor escribe 'comprar' o 'vender'.")

    if estado == "otm":
        if mensaje in ["s", "n"]:
            usuarios[numero]["otm"] = mensaje == "s"
            usuarios[numero]["estado"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Por favor responde con 's' o 'n'.")

    if estado == "prima":
        try:
            usuarios[numero]["prima"] = float(mensaje)
            usuarios[numero]["estado"] = "vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except ValueError:
            return responder("Por favor escribe un número para la prima.")

    if estado == "vencimiento":
        if mensaje in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            usuarios[numero]["vencimiento"] = mensaje
            usuarios[numero]["estado"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Elige entre: 1 semana, 2 semanas, 1 mes, 2 meses.")

    if estado == "contratos":
        try:
            usuarios[numero]["contratos"] = int(mensaje)
            respuesta = ejecutar_analisis_opciones(usuarios[numero])
            usuarios.pop(numero)
            return responder(respuesta)
        except ValueError:
            return responder("Por favor escribe un número para la cantidad de contratos.")

    return responder("No entendí tu mensaje. Escribe 'hola' para empezar de nuevo.")

def responder(texto):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{texto}</Message>
</Response>"""

def ejecutar_analisis_opciones(data):
    try:
        ticker = yf.Ticker("IBIT")
        tipo = data["tipo"]
        operacion = data["operacion"]
        otm = data["otm"]
        prima_objetivo = data["prima"]
        contratos = data["contratos"]
        vencimiento = data["vencimiento"]

        dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[vencimiento]
        fecha_limite = datetime.now() + timedelta(days=dias)

        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones:
            return "⚠️ No se encontraron vencimientos disponibles en ese rango."

        precios = ticker.history(period="1d")
        if precios.empty:
            return "⚠️ No se pudo obtener el precio actual de IBIT."

        precio_actual = precios.Close.iloc[-1]
        opciones_candidatas = []

        for fecha in expiraciones:
            chain = ticker.option_chain(fecha)
            df = chain.calls if tipo == "call" else chain.puts
            df["prima"] = (df["bid"] + df["ask"]) / 2
            df = df.dropna(subset=["strike", "bid", "ask", "prima"])

            if otm:
                df = df[df["strike"] > precio_actual] if tipo == "call" else df[df["strike"] < precio_actual]

            rango = prima_objetivo * 0.1
            df_filtrado = df[(df["prima"] >= prima_objetivo - rango) & (df["prima"] <= prima_objetivo + rango)].copy()
            df_filtrado["fecha"] = fecha

            if not df_filtrado.empty:
                opciones_candidatas.append(df_filtrado)

        if not opciones_candidatas:
            return "⚠️ No se encontraron opciones cercanas a la prima solicitada."

        df_final = (
            yf.pd.concat(opciones_candidatas)
            .copy()
            .sort_values(by="fecha")
            .head(5)
        )

        mensaje = "🔍 Opciones encontradas:\n"
        for idx, fila in df_final.iterrows():
            mensaje += (
                f"\n➡️ Tipo: {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${fila['strike']} | Prima: ${round(fila['prima'],2)}\n"
                f"📆 Vence: {fila['fecha']}\n"
                f"💰 Total: ${round(fila['prima'] * contratos * 100, 2)} por {contratos} contrato(s)\n"
                f"⚖️ Delta: {fila['delta'] if 'delta' in fila else 'N/A'}\n"
            )

        mensaje += "\n✅ Escribe 'hola' para iniciar otro análisis."
        return mensaje

    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))


