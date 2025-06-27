from flask import Flask, request
import os
from dotenv import load_dotenv
import yfinance as yf
from openai import OpenAI
from datetime import datetime, timedelta

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
    from_number = request.form.get('From')
    msg = request.form.get('Body', '').strip().lower()

    if from_number not in usuarios:
        usuarios[from_number] = {"estado": "inicio"}
        return responder("¿Vas a COMPRAR o VENDER esta opción?", from_number)

    estado = usuarios[from_number]["estado"]

    if estado == "inicio":
        if msg in ["comprar", "vender"]:
            usuarios[from_number]["operacion"] = msg
            usuarios[from_number]["estado"] = "tipo"
            return responder("¿Qué tipo de opción? (call/put)", from_number)
        else:
            return responder("Por favor indica si deseas COMPRAR o VENDER.", from_number)

    elif estado == "tipo":
        if msg in ["call", "put"]:
            usuarios[from_number]["tipo"] = msg
            usuarios[from_number]["estado"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)", from_number)
        else:
            return responder("Por favor responde 'call' o 'put'.", from_number)

    elif estado == "otm":
        if msg in ["s", "n"]:
            usuarios[from_number]["otm"] = msg == "s"
            usuarios[from_number]["estado"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)", from_number)
        else:
            return responder("Responde con 's' para sí o 'n' para no.", from_number)

    elif estado == "prima":
        try:
            usuarios[from_number]["prima"] = float(msg)
            usuarios[from_number]["estado"] = "vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)", from_number)
        except:
            return responder("Por favor indica una prima válida como 0.6", from_number)

    elif estado == "vencimiento":
        if msg in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            usuarios[from_number]["vencimiento"] = msg
            usuarios[from_number]["estado"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?", from_number)
        else:
            return responder("Elige: 1 semana, 2 semanas, 1 mes o 2 meses", from_number)

    elif estado == "contratos":
        try:
            usuarios[from_number]["contratos"] = int(msg)
            return mostrar_opciones_similares(from_number)
        except:
            return responder("Por favor indica una cantidad válida de contratos", from_number)

    elif estado == "esperando_seleccion":
        try:
            idx = int(msg) - 1
            opcion = usuarios[from_number]["opciones_similares"][idx]
            return hacer_analisis_final(from_number, opcion)
        except:
            return responder("Selecciona una opción válida con el número correspondiente.", from_number)

    return responder("❌ Ocurrió un error inesperado.", from_number)

def responder(texto, from_number):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{texto}</Message>
</Response>"""

def mostrar_opciones_similares(from_number):
    datos = usuarios[from_number]
    ticker = yf.Ticker("IBIT")
    dias = {"1 semana": 7, "2 semanas": 14, "1 mes": 30, "2 meses": 60}[datos["vencimiento"]]
    fecha_limite = datetime.now() + timedelta(days=dias)

    expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite + timedelta(days=5)]
    if not expiraciones:
        return responder("⚠️ No se encontraron vencimientos cercanos.", from_number)

    chain = ticker.option_chain(expiraciones[0])
    df = chain.calls if datos["tipo"] == "call" else chain.puts
    precio_actual = ticker.history(period="1d").Close.iloc[-1]

    if datos["otm"]:
        df = df[df["strike"] > precio_actual] if datos["tipo"] == "call" else df[df["strike"] < precio_actual]

    df["prima"] = (df["bid"] + df["ask"]) / 2
    df["desviacion"] = abs(df["prima"] - datos["prima"])
    df_filtrado = df.sort_values("desviacion").head(5)

    if df_filtrado.empty:
        return responder("⚠️ No se encontraron opciones similares a tu criterio.", from_number)

    usuarios[from_number]["estado"] = "esperando_seleccion"
    usuarios[from_number]["opciones_similares"] = df_filtrado.to_dict(orient="records")

    mensaje = "🔍 Opciones encontradas:
"
    for i, row in enumerate(df_filtrado.itertuples(), start=1):
        mensaje += f"{i}. Strike: ${row.strike}, Prima: ${round(row.prima,2)}, Vence: {expiraciones[0]}
"
    mensaje += "
Responde con el número de la opción que deseas analizar."

    return responder(mensaje, from_number)

def hacer_analisis_final(from_number, opcion):
    datos = usuarios[from_number]
    strike = opcion["strike"]
    prima = round(opcion["prima"], 2)
    total = round(prima * datos["contratos"] * 100, 2)
    fecha = datetime.now().strftime("%Y-%m-%d")
    usuarios[from_number] = {"estado": "inicio"}

    return responder(
        f"📊 Resultado:
"
        f"➡️ Tipo: {datos['tipo'].upper()} | {datos['operacion'].upper()}
"
        f"🎯 Strike: ${strike} | Prima: ${prima}
"
        f"📆 Vence: {fecha}
"
        f"💰 Total: ${total} por {datos['contratos']} contrato(s)
"
        f"
✅ Escribe 'hola' para iniciar otro análisis.",
        from_number
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

