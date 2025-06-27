from flask import Flask, request
import os
from dotenv import load_dotenv
import yfinance as yf
from datetime import datetime, timedelta
from openai import OpenAI

# Cargar variables de entorno
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Estado global
user_state = {}

@app.route("/")
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    from_number = request.form.get("From", "")
    incoming_msg = request.form.get("Body", "").strip().lower()

    # Reiniciar flujo con hola o start
    if incoming_msg in ["hola", "start"]:
        user_state[from_number] = {"state": "tipo"}
        return responder("¿Qué tipo de opción quieres analizar? (call o put)")

    # Recuperar estado
    estado = user_state.get(from_number, {"state": "tipo"})

    state = estado["state"]

    if state == "tipo":
        if incoming_msg in ["call", "put"]:
            estado["tipo"] = incoming_msg
            estado["state"] = "operacion"
            return responder("¿Vas a COMPRAR o VENDER esta opción?")
        else:
            return responder("Por favor responde solo 'call' o 'put'.")

    elif state == "operacion":
        if incoming_msg in ["comprar", "vender"]:
            estado["operacion"] = incoming_msg
            estado["state"] = "otm"
            return responder("¿Deseas solo opciones fuera del dinero (OTM)? (s/n)")
        else:
            return responder("Indica 'comprar' o 'vender'.")

    elif state == "otm":
        if incoming_msg in ["s", "n"]:
            estado["otm"] = incoming_msg
            estado["state"] = "prima"
            return responder("¿Cuál es la prima objetivo? (por ejemplo, 0.6)")
        else:
            return responder("Indica 's' o 'n'.")

    elif state == "prima":
        try:
            # Quitar símbolos y convertir coma a punto
            msg_clean = incoming_msg.replace("$", "").replace(",", ".").strip()
            prima_obj = float(msg_clean)
            estado["prima"] = prima_obj
            estado["state"] = "vencimiento"
            return responder("¿Cuál es el vencimiento deseado? (1 semana, 2 semanas, 1 mes, 2 meses)")
        except ValueError:
            return responder("Por favor ingresa un número válido. Ejemplo: 0.55")

    elif state == "vencimiento":
        if incoming_msg in ["1 semana", "2 semanas", "1 mes", "2 meses"]:
            estado["vencimiento"] = incoming_msg
            estado["state"] = "contratos"
            return responder("¿Cuántos contratos deseas analizar?")
        else:
            return responder("Por favor indica uno de estos valores: 1 semana, 2 semanas, 1 mes, 2 meses.")

    elif state == "contratos":
        if incoming_msg.isdigit():
            contratos = int(incoming_msg)
            estado["contratos"] = contratos

            # Ejecutar análisis
            tipo = estado["tipo"]
            operacion = estado["operacion"]
            otm = estado["otm"] == "s"
            prima_obj = estado["prima"]
            vencimiento = estado["vencimiento"]

            mensaje = ejecutar_analisis_opciones(
                tipo, operacion, otm, prima_obj, vencimiento, contratos
            )

            user_state[from_number] = {"state": "tipo"}
            return responder(mensaje + "\n\n✅ Escribe 'hola' o 'start' para iniciar otro análisis.")
        else:
            return responder("Por favor indica un número válido de contratos (ejemplo: 60).")

    else:
        return responder("Escribe 'hola' para iniciar un análisis.")

def responder(texto):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{texto}</Message>
</Response>"""

def ejecutar_analisis_opciones(tipo, operacion, otm, prima_obj, vencimiento, contratos):
    try:
        ticker = yf.Ticker("IBIT")
        dias = {
            "1 semana": 7,
            "2 semanas": 14,
            "1 mes": 30,
            "2 meses": 60
        }[vencimiento]

        fecha_limite = datetime.today() + timedelta(days=dias)

        expiraciones = [
            d for d in ticker.options
            if datetime.strptime(d, "%Y-%m-%d") <= fecha_limite
        ]

        if not expiraciones:
            return "⚠️ No se encontraron vencimientos en el rango solicitado."

        expiracion = expiraciones[0]
        chain = ticker.option_chain(expiracion)
        df = chain.calls if tipo == "call" else chain.puts

        precio_actual = float(ticker.history(period="1d").Close[-1])

        if otm:
            if tipo == "call":
                df = df[df["strike"] > precio_actual]
            else:
                df = df[df["strike"] < precio_actual]

        df["prima"] = (df["bid"] + df["ask"]) / 2
        rango = prima_obj * 0.10
        df_filtrado = df[
            (df["prima"] >= prima_obj - rango) &
            (df["prima"] <= prima_obj + rango)
        ]

        if df_filtrado.empty:
            df["diferencia"] = abs(df["prima"] - prima_obj)
            df_filtrado = df.sort_values("diferencia").head(3)

            mensaje = "🔍 Opciones más cercanas:\n"
            for _, row in df_filtrado.iterrows():
                total = round(row["prima"] * contratos * 100, 2)
                mensaje += (
                    f"➡️ {tipo.upper()} | {operacion.upper()}\n"
                    f"🎯 Strike: ${row['strike']} | Prima: ${round(row['prima'], 2)}\n"
                    f"📆 Vence: {expiracion}\n"
                    f"💰 Total: ${total}\n"
                    f"📈 ROI: {round((row['prima'] * 100 / precio_actual), 2)}%\n"
                    f"⚖️ Delta: {round(row['delta'], 2) if 'delta' in row else 'N/A'}\n\n"
                )
            return mensaje.strip()
        else:
            opcion = df_filtrado.iloc[0]
            total = round(opcion["prima"] * contratos * 100, 2)
            delta = round(opcion["delta"], 2) if "delta" in opcion else "N/A"
            roi = round((opcion["prima"] * 100 / precio_actual), 2)

            mensaje = (
                f"📊 Resultado:\n"
                f"➡️ Tipo: {tipo.upper()} | {operacion.upper()}\n"
                f"🎯 Strike: ${opcion['strike']} | Prima: ${round(opcion['prima'], 2)}\n"
                f"📆 Vence: {expiracion}\n"
                f"💰 Total: ${total} por {contratos} contrato(s)\n"
                f"📈 ROI: {roi}%\n"
                f"⚖️ Delta: {delta}"
            )
            return mensaje

    except Exception as e:
        return f"❌ Error durante el análisis: {str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))







