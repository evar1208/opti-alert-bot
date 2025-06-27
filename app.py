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

# Estado conversacional por número de teléfono
usuarios = {}

# Ruta de prueba
@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

# Ruta para recibir mensajes de WhatsApp
@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    from_number = request.form.get("From")
    incoming_msg = request.form.get("Body", "").strip().lower()

    if from_number not in usuarios:
        usuarios[from_number] = {"estado": "inicio"}

    estado = usuarios[from_number]["estado"]

    if estado == "inicio":
        usuarios[from_number]["estado"] = "esperando_tipo"
        return responder("¿Vas a analizar un CALL o PUT?")

    elif estado == "esperando_tipo":
        if "call" in incoming_msg:
            usuarios[from_number]["tipo"] = "call"
        elif "put" in incoming_msg:
            usuarios[from_number]["tipo"] = "put"
        else:
            return responder("Por favor indica si es CALL o PUT.")
        usuarios[from_number]["estado"] = "esperando_operacion"
        return responder("¿Vas a COMPRAR o VENDER esta opción?")

    elif estado == "esperando_operacion":
        if "comprar" in incoming_msg:
            usuarios[from_number]["operacion"] = "comprar"
        elif "vender" in incoming_msg:
            usuarios[from_number]["operacion"] = "vender"
        else:
            return responder("Por favor responde COMPRAR o VENDER.")
        usuarios[from_number]["estado"] = "esperando_otm"
        return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")

    elif estado == "esperando_otm":
        usuarios[from_number]["otm"] = incoming_msg == "s"
        usuarios[from_number]["estado"] = "esperando_prima"
        return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")

    elif estado == "esperando_prima":
        try:
            usuarios[from_number]["prima"] = float(incoming_msg)
        except:
            return responder("Por favor escribe un valor numérico. Ejemplo: 0.6")
        usuarios[from_number]["estado"] = "esperando_vencimiento"
        return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")

    elif estado == "esperando_vencimiento":
        if incoming_msg not in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            return responder("Vencimiento no reconocido. Escribe: 1 semana, 2 semanas, 1 mes o 2 meses.")
        usuarios[from_number]["vencimiento"] = incoming_msg
        usuarios[from_number]["estado"] = "esperando_contratos"
        return responder("¿Cuántos contratos deseas analizar?")

    elif estado == "esperando_contratos":
        try:
            usuarios[from_number]["contratos"] = int(incoming_msg)
        except:
            return responder("Por favor indica un número entero de contratos.")

        # Realizar análisis
        respuesta = ejecutar_analisis_opciones(usuarios[from_number])
        usuarios[from_number]["estado"] = "inicio"
        return responder(respuesta)

    else:
        usuarios[from_number]["estado"] = "inicio"
        return responder("Escribe 'hola' para comenzar un nuevo análisis.")

def responder(mensaje):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

# Función para analizar opciones de IBIT
def ejecutar_analisis_opciones(datos):
    try:
        ticker = yf.Ticker("IBIT")
        tipo = datos["tipo"]
        operacion = datos["operacion"]
        otm = datos["otm"]
        prima_objetivo = datos["prima"]
        contratos = datos["contratos"]
        vencimiento = datos["vencimiento"]

        dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[vencimiento]
        fecha_limite = datetime.now() + timedelta(days=dias)
        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]
        if not expiraciones:
            return "⚠️ No se encontraron vencimientos disponibles en ese rango."

        expiracion = expiraciones[0]
        chain = ticker.option_chain(expiracion)
        df = chain.calls if tipo == "call" else chain.puts

        precio_actual = ticker.history(period="1d").Close.iloc[-1]
        if otm:
            df = df[df["strike"] > precio_actual] if tipo == "call" else df[df["strike"] < precio_actual]

        df["prima"] = (df["bid"] + df["ask"]) / 2
        rango = prima_objetivo * 0.2
        df_filtrado = df[(df["prima"] >= prima_objetivo - rango) & (df["prima"] <= prima_objetivo + rango)]

        if df_filtrado.empty:
            df["desviacion"] = abs(df["prima"] - prima_objetivo)
            df_filtrado = df.sort_values("desviacion").head(5)

        resultados = []
        for _, opcion in df_filtrado.iterrows():
            strike = opcion["strike"]
            prima = round(opcion["prima"], 2)
            fecha = expiracion
            total = round(prima * contratos * 100, 2)
            roi = 100 * prima / precio_actual if operacion == "vender" else -100 * prima / precio_actual
            delta = opcion["delta"] if "delta" in opcion else "N/A"

            resultados.append(
                f"➡️ Tipo: {tipo.upper()} | {operacion.upper()}
"
                f"🎯 Strike: ${strike} | Prima: ${prima}
"
                f"📆 Vence: {fecha}
"
                f"💰 Total: ${total} por {contratos} contrato(s)
"
                f"📈 ROI: {round(roi,2)}%
"
                f"⚖️ Delta: {delta}"
            )

        respuesta = "📊 Resultado:
" + "

".join(resultados)
        return respuesta + "

✅ Escribe 'hola' para iniciar otro análisis."
    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

# Ejecutar localmente
if __name__ == '__main__':
   app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
