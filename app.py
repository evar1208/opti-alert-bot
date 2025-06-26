from flask import Flask, request
import os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

# Crear cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# Ruta de prueba
@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

# Ruta webhook de WhatsApp
@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.form.get('Body', '').strip().lower()
    response_msg = generar_respuesta(incoming_msg)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_msg}</Message>
</Response>"""

# Generar respuesta con IA
def generar_respuesta(mensaje):
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",  # o usa "gpt-4" si tienes acceso
            messages=[
                {"role": "system", "content": "Eres un asesor de trading experto en opciones sobre IBIT."},
                {"role": "user", "content": mensaje}
            ],
            temperature=0.5
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Ocurrió un error: {e}"

# Ejecutar localmente
if __name__ == '__main__':
   app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

