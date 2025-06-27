from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import yfinance as yf
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()

# Crear cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Estructura para mantener contexto entre mensajes
conversacion = {}

# Ruta principal
@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

# Ruta de WhatsApp
@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    sender = request.form.get('From')
    incoming_msg = request.form.get('Body', '').strip()

    # Inicializar estado si no existe
    if sender not in conversacion or incoming_msg.lower() in ["hola", "start"]:
        conversacion[sender] = {}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    estado = conversacion[sender]

    # Paso 1: call o put
    if "tipo" not in estado:
        if incoming_msg.lower() in ["call", "put"]:
            estado["tipo"] = incoming_msg.lower()
            conversacion[sender] = estado
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Responde con 'call' o 'put'.")

    # Paso 2: comprar o vender
    if "operacion" not in estado:
        if incoming_msg.lower() in ["comprar", "vender"]:
            estado["operacion"] = incoming_msg.lower()
            conversacion[sender] = estado
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Responde con 'comprar' o 'vender'.")

    # Paso 3: OTM
    if "otm" not in estado:
        if incoming_msg.lower() in ["s", "n"]:
            estado["otm"] = incoming_msg.lower()
            conversacion[sender] = estado
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Responde con 's' o 'n'.")

    # Paso 4: prima
    if "prima" not in estado:
        try:
            prima = float(incoming_msg.replace(",", "."))
            estado["prima"] = prima
            conversacion[sender] = estado
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except:
            return responder("Escribe un número para la prima, por ejemplo 0.6.")

    # Paso 5: vencimiento
    if "vencimiento" not in estado:
        if incoming_msg.lower() in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            estado["vencimiento"] = incoming_msg.lower()
            conversacion[sender] = estado
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Responde con: 1 semana, 2 semanas, 1 mes o 2 meses.")

    # Paso 6: contratos
    if "contratos" not in estado:
        try:
            contratos = int(incoming_msg)
            estado["contratos"] = contratos
            conversacion[sender] = estado

            # Ejecutar análisis
            resultado = ejecutar_analisis_opciones(estado)
            # Limpiar para reiniciar flujo en la próxima interacción
            conversacion.pop(sender, None)
            return responder(resultado + "\n\n✅ Escribe 'hola' o 'start' para iniciar otro análisis.")
        except:
            return responder("Indica un número válido de contratos.")

    return responder("No entendí tu mensaje. Escribe 'hola' para comenzar de nuevo.")

def responder(msg):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{msg}</Message>
</Response>"""

# Función de análisis
def ejecutar_analisis_opciones(estado):
    try:
        ticker = yf.Ticker("IBIT")
        tipo = estado["tipo"]
        operacion = estado["operacion"]
        otm = estado["otm"] == "s"
        prima_obj = estado["prima"]
        vencimiento = estado["vencimiento"]
        contratos = estado["contratos"]

        dias = {
            "1 semana": 7,
            "2 semanas": 14,
            "1 mes": 30,
            "2 meses": 60
        }[vencimiento]

        fecha_limite = datetime.now() + timedelta(days=dias)
        expiraciones = [d for d in ticker.options if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite]

        if not expiraciones:
            return "⚠️ No se encontraron vencimientos en ese rango."

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
        rango = prima_obj * 0.1
        df_filtrado = df[
            (df["prima"] >= prima_obj - rango) &
            (df["prima"] <= prima_obj + rango)
        ]

        if df_filtrado.empty:
            df["diferencia"] = abs(df["prima"] - prima_obj)
            df_filtrado = df.sort_values("diferencia").head(3)

        mensaje = "🔍 Opciones más cercanas:\n"

        for idx, row in df_filtrado.iterrows():
            total = round(row["prima"] * contratos * 100, 2)
            mensaje += (
                f"➡️ {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${row['strike']} | Prima: ${round(row['prima'],2)}\n"
                f"📆 Vence: {expiracion}\n"
                f"💰 Total: ${total}\n"
                f"📈 ROI: {round((row['prima']/precio_actual)*100,2)}%\n"
                f"⚖️ Delta: {round(row['delta'],2) if 'delta' in row and row['delta']==row['delta'] else 'N/A'}\n\n"
            )

        return mensaje.strip()

    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

# Ejecutar localmente
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))





