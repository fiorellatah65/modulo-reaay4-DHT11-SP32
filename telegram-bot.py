#!/usr/bin/env python3
"""
🤖 BOT DE TELEGRAM CON AUDIO TRIPLE COMPLETO
Responde con: Texto + Audio Telegram + Audio Parlante ESP32
"""

import os
import json
import base64
import tempfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import paho.mqtt.client as mqtt
from gtts import gTTS
from io import BytesIO
import speech_recognition as sr
from pydub import AudioSegment

# ========================================
# CONFIGURACIÓN
# ========================================

TELEGRAM_TOKEN = "8491255978:AAFfDy6smKSAhkcGjtX8HxHh6cXe9RB4Y44"

MQTT_HOST = "e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "esp32user"
MQTT_PASS = "Esp32pass123"

# ========================================
# INICIALIZAR MQTT
# ========================================

print("🚀 Iniciando Bot con Audio Triple...")

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set()

latest_sensor_data = {"temp": 0, "hum": 0, "alert": "OK", "setpoint": 24}
relay_states = {}

def on_mqtt_connect(client, userdata, flags, rc):
    print(f"✅ MQTT conectado (rc={rc})")
    client.subscribe("esp32/sensores")
    client.subscribe("esp32/relay/status")
    client.subscribe("esp32/config")

def on_mqtt_message(client, userdata, msg):
    global latest_sensor_data, relay_states
    try:
        data = json.loads(msg.payload.decode())
        
        if msg.topic == "esp32/sensores":
            latest_sensor_data = data
            print(f"📊 Temp: {data.get('temp', 0):.1f}°C | Hum: {data.get('hum', 0):.0f}%")
        elif msg.topic == "esp32/relay/status":
            relay_states = data
        elif msg.topic == "esp32/config":
            latest_sensor_data['setpoint'] = data.get('setpoint', 24)
    except Exception as e:
        print(f"❌ Error MQTT: {e}")

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message

try:
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print("✅ MQTT conectado")
except Exception as e:
    print(f"⚠️ MQTT: {e}")

# ========================================
# FUNCIONES DE AUDIO
# ========================================

def text_to_speech_telegram(text: str) -> BytesIO:
    """Audio MP3 para Telegram"""
    try:
        tts = gTTS(text=text, lang='es', slow=False)
        buffer = BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"❌ Error TTS Telegram: {e}")
        return None

def send_audio_to_esp32_speaker(text: str):
    """Genera audio WAV y lo envía al parlante ESP32 en chunks base64"""
    try:
        print(f"🔊 Generando audio para parlante: {text[:60]}...")
        
        # 1. Generar audio MP3 con gTTS
        tts = gTTS(text=text, lang='es', slow=False)
        mp3_buffer = BytesIO()
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)
        
        # 2. Convertir MP3 a WAV optimizado para ESP32
        audio = AudioSegment.from_file(mp3_buffer, format="mp3")
        
        # Optimizar para ESP32: mono, 16kHz, 8-bit
        audio = audio.set_channels(1)          # Mono
        audio = audio.set_frame_rate(16000)    # 16kHz
        audio = audio.set_sample_width(1)      # 8-bit
        
        # 3. Exportar a WAV
        wav_buffer = BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_bytes = wav_buffer.getvalue()
        
        print(f"📦 Tamaño audio: {len(wav_bytes)} bytes")
        
        # 4. Codificar en base64
        b64_data = base64.b64encode(wav_bytes).decode('utf-8')
        
        # 5. Enviar en chunks por MQTT
        chunk_size = 1000
        total_chunks = (len(b64_data) + chunk_size - 1) // chunk_size
        
        print(f"📤 Enviando {total_chunks} chunks al ESP32...")
        
        # Señal de inicio
        mqtt_client.publish("esp32/tts/audio/start", "")
        
        # Enviar chunks
        for i in range(0, len(b64_data), chunk_size):
            chunk = b64_data[i:i+chunk_size]
            mqtt_client.publish("esp32/tts/audio/chunk", chunk)
            print(f"  Chunk {i//chunk_size + 1}/{total_chunks}")
        
        # Señal de fin
        mqtt_client.publish("esp32/tts/audio/end", "")
        
        print("✅ Audio enviado al parlante ESP32")
        
    except Exception as e:
        print(f"❌ Error enviando audio al parlante: {e}")

def speech_to_text(audio_file_path: str) -> str:
    """Convierte nota de voz de Telegram a texto"""
    recognizer = sr.Recognizer()
    
    try:
        print("🎤 Procesando nota de voz...")
        
        audio = AudioSegment.from_file(audio_file_path)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
            wav_path = wav_file.name
            audio.export(wav_path, format='wav')
        
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='es-ES')
            print(f"✅ Reconocido: {text}")
            
        try:
            os.unlink(wav_path)
        except:
            pass
            
        return text
        
    except sr.UnknownValueError:
        print("❌ No se entendió el audio")
        return None
    except Exception as e:
        print(f"❌ Error procesando audio: {e}")
        return None

# ========================================
# FUNCIONES DE CONSULTA
# ========================================

def get_sensor_data():
    return latest_sensor_data

def process_command(text: str) -> str:
    """Procesa comandos y retorna respuesta"""
    t = text.lower()
    
    if any(w in t for w in ['temperatura', 'temp', 'cuánto', 'cuánta', 'grados']):
        data = get_sensor_data()
        return f"La temperatura actual es {data['temp']:.1f} grados celsius y la humedad es {data['hum']:.0f} por ciento"
    
    elif any(w in t for w in ['humedad', 'húmedo']):
        data = get_sensor_data()
        return f"La humedad actual es del {data['hum']:.0f} por ciento"
    
    elif any(w in t for w in ['estado', 'cómo está', 'sistema']):
        data = get_sensor_data()
        if data['alert'] == 'OK':
            return f"Todo está bien. Temperatura {data['temp']:.1f} grados, Humedad {data['hum']:.0f} por ciento"
        else:
            return f"Alerta: {data['alert']}. Temperatura {data['temp']:.1f} grados"
    
    elif 'enciende' in t or 'prende' in t:
        if 'ventilador' in t or '1' in t:
            mqtt_client.publish("esp32/relay/1/cmd", "ON")
            return "He encendido el ventilador"
        elif 'calefactor' in t or '2' in t:
            mqtt_client.publish("esp32/relay/2/cmd", "ON")
            return "He encendido el calefactor"
        elif 'humidificador' in t or '3' in t:
            mqtt_client.publish("esp32/relay/3/cmd", "ON")
            return "He encendido el humidificador"
        elif 'luz' in t or 'foco' in t or '4' in t:
            mqtt_client.publish("esp32/relay/4/cmd", "ON")
            return "He encendido la luz"
        elif 'todo' in t:
            for i in range(1, 5):
                mqtt_client.publish(f"esp32/relay/{i}/cmd", "ON")
            return "He encendido todos los dispositivos"
        return "No entendí qué dispositivo encender"
    
    elif 'apaga' in t:
        if 'ventilador' in t or '1' in t:
            mqtt_client.publish("esp32/relay/1/cmd", "OFF")
            return "He apagado el ventilador"
        elif 'calefactor' in t or '2' in t:
            mqtt_client.publish("esp32/relay/2/cmd", "OFF")
            return "He apagado el calefactor"
        elif 'humidificador' in t or '3' in t:
            mqtt_client.publish("esp32/relay/3/cmd", "OFF")
            return "He apagado el humidificador"
        elif 'luz' in t or 'foco' in t or '4' in t:
            mqtt_client.publish("esp32/relay/4/cmd", "OFF")
            return "He apagado la luz"
        elif 'todo' in t:
            for i in range(1, 5):
                mqtt_client.publish(f"esp32/relay/{i}/cmd", "OFF")
            return "He apagado todos los dispositivos"
        return "No entendí qué dispositivo apagar"
    
    elif 'setpoint' in t or 'cambia' in t:
        words = t.split()
        for word in words:
            try:
                temp = float(word)
                if 15 <= temp <= 35:
                    mqtt_client.publish("esp32/config/set", json.dumps({"setpoint": temp}))
                    return f"Setpoint cambiado a {temp} grados"
            except:
                pass
        return "No entendí la temperatura. Debe estar entre 15 y 35 grados"
    
    return "No entendí tu comando. Puedes preguntar por temperatura, humedad, o controlar dispositivos"

# ========================================
# HANDLERS DE TELEGRAM
# ========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Estado", callback_data='status')],
        [InlineKeyboardButton("🌡️ Temperatura", callback_data='temp')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """
🤖 *Bot ESP32 - Audio Triple*

*🎤 Envía NOTA DE VOZ:*
• "¿Qué temperatura hay?"
• "Enciende el ventilador"
• "¿Cómo está el sistema?"

*💬 O escribe TEXTO:*
• temperatura
• enciende luz
• estado

*🔊 RECIBIRÁS 3 RESPUESTAS:*
1️⃣ 📱 Texto en Telegram
2️⃣ 🎵 Audio en Telegram
3️⃣ 🔊 Voz en Parlante ESP32

¡Pruébalo! 🚀
    """
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def temp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_sensor_data()
    
    # 1️⃣ TEXTO
    text_msg = f"""
🌡️ *TEMPERATURA*

Temperatura: *{data['temp']:.1f}°C*
Humedad: *{data['hum']:.0f}%*
Setpoint: *{data['setpoint']:.1f}°C*
    """
    await update.message.reply_text(text_msg, parse_mode='Markdown')
    
    # 2️⃣ AUDIO TELEGRAM
    audio_text = f"La temperatura es {data['temp']:.1f} grados celsius y la humedad es {data['hum']:.0f} por ciento"
    audio = text_to_speech_telegram(audio_text)
    if audio:
        await update.message.reply_voice(voice=audio)
    
    # 3️⃣ PARLANTE ESP32
    send_audio_to_esp32_speaker(audio_text)
    
    print("✅ Respuesta TRIPLE enviada")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_sensor_data()
    emoji = "✅" if data['alert'] == 'OK' else "⚠️"
    
    # 1️⃣ TEXTO
    text_msg = f"""
{emoji} *ESTADO*

🌡️ {data['temp']:.1f}°C
💧 {data['hum']:.0f}%
🎯 Setpoint: {data['setpoint']:.1f}°C
    """
    await update.message.reply_text(text_msg, parse_mode='Markdown')
    
    # 2️⃣ + 3️⃣ AUDIO
    audio_text = f"Sistema funcionando. Temperatura {data['temp']:.1f} grados"
    audio = text_to_speech_telegram(audio_text)
    if audio:
        await update.message.reply_voice(voice=audio)
    
    send_audio_to_esp32_speaker(audio_text)

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para NOTAS DE VOZ"""
    await update.message.reply_text("🎤 Procesando tu nota de voz...")
    
    try:
        voice_file = await update.message.voice.get_file()
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_path = temp_file.name
            await voice_file.download_to_drive(temp_path)
        
        # Convertir voz a texto
        text = speech_to_text(temp_path)
        
        try:
            os.unlink(temp_path)
        except:
            pass
        
        if text:
            await update.message.reply_text(f"📝 Entendí: *\"{text}\"*", parse_mode='Markdown')
            
            # Procesar comando
            response = process_command(text)
            
            # 1️⃣ TEXTO
            await update.message.reply_text(f"💬 {response}")
            
            # 2️⃣ AUDIO TELEGRAM
            audio = text_to_speech_telegram(response)
            if audio:
                await update.message.reply_voice(voice=audio)
            
            # 3️⃣ PARLANTE ESP32
            send_audio_to_esp32_speaker(response)
            
            print("✅ Respuesta TRIPLE enviada (Voz → Texto + Audio Telegram + Parlante)")
            
        else:
            await update.message.reply_text("❌ No pude entender tu nota de voz. Habla más claro.")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para MENSAJES DE TEXTO"""
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    # Procesar comando
    response = process_command(text)
    
    # 1️⃣ TEXTO
    await update.message.reply_text(f"💬 {response}")
    
    # 2️⃣ AUDIO TELEGRAM
    audio = text_to_speech_telegram(response)
    if audio:
        await update.message.reply_voice(voice=audio)
    
    # 3️⃣ PARLANTE ESP32
    send_audio_to_esp32_speaker(response)
    
    print("✅ Respuesta TRIPLE enviada (Texto → Texto + Audio Telegram + Parlante)")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'status':
        await status_command(update, context)
    elif query.data == 'temp':
        await temp_command(update, context)

# ========================================
# MAIN
# ========================================

def main():
    print("\n" + "="*70)
    print("🎤 BOT CON AUDIO TRIPLE")
    print("="*70)
    print("1️⃣  Texto en Telegram")
    print("2️⃣  Audio en Telegram (MP3)")
    print("3️⃣  Voz en Parlante ESP32 (WAV)")
    print("="*70 + "\n")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("temp", temp_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # HANDLERS PRINCIPALES
    app.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Bot listo")
    print("📱 Abre Telegram → tu bot")
    print("🎤 Envía NOTA DE VOZ: '¿temperatura?'")
    print("💬 O TEXTO: 'temperatura'\n")
    print("🔊 ESCUCHARÁS:")
    print("   📱 Mensaje en Telegram")
    print("   🎵 Audio en Telegram")
    print("   🔊 Voz en Parlante físico\n")
    print("="*70)
    print("🤖 BOT CORRIENDO (Ctrl+C para detener)")
    print("="*70 + "\n")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()