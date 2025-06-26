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

@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.form.get('Body', '').strip()
    print("📩 Mensaje recibido:", incoming_msg)
    response_msg = generar_respuesta(incoming_msg)
    print("🤖 Respuesta generada:", response_msg)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_msg}</Message>
</Response>"""

def generar_respuesta(mensaje):
    try:
        if "analizar" in mensaje.lower():
            return ejecutar_analisis_opciones(mensaje)
        else:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asesor de trading experto en opciones sobre IBIT."},
                    {"role": "user", "content": mensaje}
                ],
                temperature=0.5
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ Error en generar_respuesta:", e)
        return f"❌ Ocurrió un error: {str(e)}"

def ejecutar_analisis_opciones(mensaje_usuario: str) -> str:
    try:
        print("🔍 Ejecutando análisis de opciones...")
        ticker = yf.Ticker("IBIT")

        expiraciones = ticker.options
        if not expiraciones:
            print("⚠️ No se encontraron expiraciones.")
            return "⚠️ No se encontraron fechas de vencimiento para IBIT. Intenta más tarde."

        mensaje = mensaje_usuario.lower()
        tipo = "call" if "call" in mensaje else "put"
        operacion = "vender" if "vender" in mensaje else "comprar"
        otm = "otm" in mensaje
        prima_str = mensaje.split("prima")[1].split()[0].replace("$", "").strip()
        contratos_str = mensaje.split("contratos")[1].split()[0].strip()

        vencimiento = (
            "1 semana" if "1 semana" in mensaje else
            "2 semanas" if "2 semanas" in mensaje else
            "1 mes" if "1 mes" in mensaje else
            "2 meses"
        )

        prima_objetivo = float(prima_str)
        contratos = int(contratos_str)
        dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[vencimiento]
        fecha_limite = datetime.now() + timedelta(days=dias)

        expiraciones_validas = [d for d in expiraciones if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones_validas:
            print("⚠️ No hay expiraciones en el rango.")
            return "⚠️ No hay vencimientos disponibles en ese rango de fechas."

        expiracion = expiraciones_validas[0]
        print(f"📆 Vencimiento elegido: {expiracion}")

        chain = ticker.option_chain(expiracion)
        df = chain.calls if tipo == "call" else chain.puts

        precio_actual = ticker.history(period="1d").Close.iloc[-1]
        print(f"💰 Precio actual IBIT: {precio_actual}")

        if otm:
            df = df[df["strike"] > precio_actual] if tipo == "call" else df[df["strike"] < precio_actual]

        df["prima"] = (df["bid"] + df["ask"]) / 2
        rango = prima_objetivo * 0.1
        df_filtrado = df[(df["prima"] >= prima_objetivo - rango) & (df["prima"] <= prima_objetivo + rango)]

        if df_filtrado.empty:
            df_filtrado = df.copy()
            df_filtrado["desviacion"] = abs(df_filtrado["prima"] - prima_objetivo)
            df_filtrado = df_filtrado.sort_values("desviacion").head(1)

        opcion = df_filtrado.iloc[0]
        strike = opcion["strike"]
        prima = round(opcion["prima"], 2)
        fecha = expiracion
        total = round(prima * contratos * 100, 2)

        return (
            f"📊 Análisis de opción {tipo.upper()} para IBIT\n"
            f"✅ Operación: {operacion.upper()}\n"
            f"🎯 Strike: ${strike}\n"
            f"💰 Prima estimada: ${prima} x {contratos} contratos = ${total}\n"
            f"📆 Vencimiento: {fecha}\n"
            f"📉 Precio actual IBIT: ${round(precio_actual, 2)}\n"
            f"\nRecuerda: Si el precio está {'por debajo' if tipo == 'call' else 'por encima'} del strike al vencimiento, la opción expirará sin valor."
        )

    except Exception as e:
        print("❌ Error durante el análisis:", e)
        return f"❌ Error durante el análisis: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))




