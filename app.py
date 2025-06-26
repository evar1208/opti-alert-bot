from flask import Flask, request
import os
import openai
from dotenv import load_dotenv
from datetime import datetime

# Carga variables de entorno
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

# Ruta de prueba simple
@app.route('/')
def home():
    return "✅ Bot de WhatsApp con Flask y OpenAI está activo."

# Ruta para manejar mensajes de Twilio WhatsApp
@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    incoming_msg = request.form.get('Body', '').strip().lower()
    response_msg = generar_respuesta(incoming_msg)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response_msg}</Message>
</Response>"""

# Función que genera una respuesta con IA según el mensaje recibido
def generar_respuesta(mensaje):
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # o "gpt-4" si tienes acceso
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
    app.run(port=5000)
