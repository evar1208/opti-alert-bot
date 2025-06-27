from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()

# Cliente de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Estado por sesión (simple cache)
usuarios_estado = {}

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    numero = request.form.get('From')
    mensaje = request.form.get('Body', '').strip().lower()

    if numero not in usuarios_estado or mensaje == "hola":
        usuarios_estado[numero] = {
            "paso": "tipo_opcion"
        }
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    estado = usuarios_estado[numero]

    try:
        paso = estado["paso"]

        if paso == "tipo_opcion":
            if mensaje not in ["call", "put"]:
                return responder("❌ Por favor responde 'call' o 'put'")
            estado["tipo"] = mensaje
            estado["paso"] = "operacion"
            return responder("¿Vas a COMPRAR o VENDER esta opción?")

        if paso == "operacion":
            if mensaje not in ["comprar", "vender"]:
                return responder("❌ Responde 'comprar' o 'vender'")
            estado["operacion"] = mensaje
            estado["paso"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

        if paso == "otm":
            if mensaje not in ["s", "n"]:
                return responder("❌ Responde con 's' (sí) o 'n' (no)")
            estado["otm"] = mensaje == "s"
            estado["paso"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

        if paso == "prima":
            try:
                estado["prima"] = float(mensaje)
                estado["paso"] = "vencimiento"
                return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
            except:
                return responder("❌ Escribe un número como 0.5 o 1.2")

        if paso == "vencimiento":
            if mensaje not in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
                return responder("❌ Elige: 1 semana, 2 semanas, 1 mes o 2 meses")
            estado["vencimiento"] = mensaje
            estado["paso"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?")

        if paso == "contratos":
            try:
                estado["contratos"] = int(mensaje)
                resultado = analizar_opciones(estado)
                del usuarios_estado[numero]
                return responder(resultado + "\n\n✅ Escribe 'hola' para iniciar otro análisis.")
            except:
                return responder("❌ Escribe un número entero como 10 o 50")

    except Exception as e:
        return responder(f"❌ Error: {str(e)}")

def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

def analizar_opciones(data):
    ticker = yf.Ticker("IBIT")
    tipo = data["tipo"]
    operacion = data["operacion"]
    otm = data["otm"]
    prima_obj = data["prima"]
    contratos = data["contratos"]
    dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[data["vencimiento"]]
    fecha_limite = datetime.now() + timedelta(days=dias)

    expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
    if not expiraciones:
        return "⚠️ No se encontraron vencimientos disponibles en ese rango."

    resultados = []
    for exp in expiraciones:
        chain = ticker.option_chain(exp)
        df = chain.calls if tipo == "call" else chain.puts
        precio_actual = ticker.history(period="1d").Close.iloc[-1]
        df["prima"] = (df["bid"] + df["ask"]) / 2

        if otm:
            df = df[df["strike"] > precio_actual] if tipo == "call" else df[df["strike"] < precio_actual]

        df["diferencia"] = abs(df["prima"] - prima_obj)
        similares = df.sort_values("diferencia").head(5)

        for _, opcion in similares.iterrows():
            strike = opcion["strike"]
            prima = round(opcion["prima"], 2)
            total = round(prima * contratos * 100, 2)
            roi = round((prima * 100) / (strike * 100) * 100, 2)
            delta = opcion.get("delta", "N/A")
            resultados.append(
                f"➡️ Tipo: {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${strike} | Prima: ${prima}\n"
                f"📆 Vence: {exp}\n"
                f"💰 Total: ${total} por {contratos} contrato(s)\n"
                f"📈 ROI: {roi}%\n"
                f"⚖️ Delta: {delta}\n"
            )

    if not resultados:
        return "⚠️ No se encontraron opciones cercanas."

    return "🔍 Opciones encontradas:\n\n" + "\n---\n".join(resultados)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))



