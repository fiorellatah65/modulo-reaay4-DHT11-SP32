#!/usr/bin/env python3
"""
🤖 BOT DE TELEGRAM COMPLETO - CONTROL TOTAL ESP32
✅ Compatible con Python 3.13
✅ Control de dispositivos via Supabase
✅ Configuración de temperaturas mín/máx
✅ Sistema de alertas automáticas
✅ Reconocimiento de voz funcional
"""

import os
import sys
import json
import base64
import tempfile
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import paho.mqtt.client as mqtt
from gtts import gTTS
from io import BytesIO

# Importaciones condicionales para audio
try:
    import speech_recognition as sr
    VOICE_ENABLED = True
    print("✅ Reconocimiento de voz habilitado")
except ImportError:
    VOICE_ENABLED = False
    print("⚠️ Reconocimiento de voz deshabilitado (SpeechRecognition no disponible)")

try:
    from pydub import AudioSegment
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False
    print("⚠️ Procesamiento de audio deshabilitado (pydub no disponible)")

# ========================================
# CONFIGURACIÓN
# ========================================

TELEGRAM_TOKEN = "8491255978:AAFfDy6smKSAhkcGjtX8HxHh6cXe9RB4Y44"

MQTT_HOST = "e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "esp32user"
MQTT_PASS = "Esp32pass123"

# Supabase
SUPABASE_URL = "https://yxwinzfhokugvtpmvyqz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl4d2luemZob2t1Z3Z0cG12eXF6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MzIyNjcsImV4cCI6MjA4MTQwODI2N30.xbNWsxmQ4MwbjaQgzfZLkvLE66XqaANiUD4pggr43Vg"

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ========================================
# VARIABLES GLOBALES
# ========================================

latest_sensor_data = {"temp": None, "hum": None, "alert": "OK", "setpoint": 24}
relay_states = {
    'r1': {'name': 'Ventilador', 'state': False, 'mode': 0},
    'r2': {'name': 'Calefactor', 'state': False, 'mode': 0},
    'r3': {'name': 'Humidificador', 'state': False, 'mode': 0},
    'r4': {'name': 'Foco/Luz', 'state': False, 'mode': 0}
}
current_config = {"setpoint": 24, "hysteresis": 2, "tempMax": 30, "tempMin": 18}
mqtt_connected = False

print("🚀 Iniciando Bot ESP32 con Control Total...")

# ========================================
# FUNCIONES SUPABASE
# ========================================

def get_latest_sensor_data():
    """Obtiene los últimos datos del sensor desde Supabase"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/sensor_readings?select=*&order=created_at.desc&limit=1"
        response = requests.get(url, headers=SUPABASE_HEADERS)
        
        if response.status_code == 200:
            data_list = response.json()
            if data_list and len(data_list) > 0:
                data = data_list[0]
                return {
                    'temp': data.get('temperatura'),
                    'hum': data.get('humedad'),
                    'setpoint': data.get('setpoint', 24)
                }
    except Exception as e:
        print(f"❌ Error leyendo Supabase: {e}")
    return None

def get_system_config():
    """Obtiene la configuración actual desde Supabase"""
    try:
        url = f"{SUPABASE_URL}/rest/v1/system_config?select=*&order=id.desc&limit=1"
        response = requests.get(url, headers=SUPABASE_HEADERS)
        
        if response.status_code == 200:
            data_list = response.json()
            if data_list and len(data_list) > 0:
                cfg = data_list[0]
                return {
                    'setpoint': cfg.get('setpoint', 24),
                    'hysteresis': cfg.get('hysteresis', 2),
                    'tempMax': cfg.get('temp_max', 30),
                    'tempMin': cfg.get('temp_min', 18)
                }
    except Exception as e:
        print(f"❌ Error leyendo config: {e}")
    return current_config

def update_system_config(setpoint=None, hysteresis=None, temp_max=None, temp_min=None):
    """Actualiza la configuración en Supabase"""
    try:
        url_get = f"{SUPABASE_URL}/rest/v1/system_config?select=*&order=id.desc&limit=1"
        response = requests.get(url_get, headers=SUPABASE_HEADERS)
        
        if response.status_code == 200:
            data_list = response.json()
            if data_list and len(data_list) > 0:
                config_id = data_list[0]['id']
                
                update_data = {}
                if setpoint is not None:
                    update_data['setpoint'] = setpoint
                if hysteresis is not None:
                    update_data['hysteresis'] = hysteresis
                if temp_max is not None:
                    update_data['temp_max'] = temp_max
                if temp_min is not None:
                    update_data['temp_min'] = temp_min
                
                if update_data:
                    update_data['updated_at'] = datetime.utcnow().isoformat()
                    
                    url_update = f"{SUPABASE_URL}/rest/v1/system_config?id=eq.{config_id}"
                    response = requests.patch(url_update, headers=SUPABASE_HEADERS, json=update_data)
                    
                    if response.status_code in [200, 204]:
                        print(f"✅ Config actualizada: {update_data}")
                        mqtt_client.publish("esp32/config/set", json.dumps(update_data))
                        return True
    except Exception as e:
        print(f"❌ Error actualizando config: {e}")
    return False

def update_relay_state(relay_number, state, mode=None):
    """Actualiza el estado de un relay en Supabase"""
    try:
        relay_names = {1: 'Ventilador', 2: 'Calefactor', 3: 'Humidificador', 4: 'Foco/Luz'}
        
        data = {
            'relay_number': relay_number,
            'relay_name': relay_names.get(relay_number, f'Relay {relay_number}'),
            'state': state,
            'mode': mode if mode is not None else 3,
            'created_at': datetime.utcnow().isoformat()
        }
        
        url = f"{SUPABASE_URL}/rest/v1/relay_states"
        response = requests.post(url, headers=SUPABASE_HEADERS, json=data)
        
        if response.status_code in [200, 201]:
            print(f"✅ Relay {relay_number} → {'ON' if state else 'OFF'}")
            
            mqtt_client.publish(f"esp32/relay/{relay_number}/cmd", "ON" if state else "OFF")
            if mode is not None:
                mqtt_client.publish(f"esp32/relay/{relay_number}/mode", str(mode))
            
            return True
    except Exception as e:
        print(f"❌ Error relay: {e}")
    return False

def get_relay_states():
    """Obtiene el último estado de cada relay"""
    try:
        states = {}
        for i in range(1, 5):
            url = f"{SUPABASE_URL}/rest/v1/relay_states?select=*&relay_number=eq.{i}&order=created_at.desc&limit=1"
            response = requests.get(url, headers=SUPABASE_HEADERS)
            
            if response.status_code == 200:
                data_list = response.json()
                if data_list and len(data_list) > 0:
                    r = data_list[0]
                    states[f'r{i}'] = {
                        'name': r.get('relay_name', f'Relay {i}'),
                        'state': r.get('state', False),
                        'mode': r.get('mode', 0)
                    }
        return states if states else None
    except Exception as e:
        print(f"❌ Error leyendo relays: {e}")
    return None

def create_alert(alert_type, message, severity='WARNING'):
    """Crea una alerta en Supabase"""
    try:
        data = {
            'alert_type': alert_type,
            'message': message,
            'severity': severity,
            'created_at': datetime.utcnow().isoformat()
        }
        
        url = f"{SUPABASE_URL}/rest/v1/system_alerts"
        response = requests.post(url, headers=SUPABASE_HEADERS, json=data)
        
        if response.status_code in [200, 201]:
            print(f"✅ Alerta: {message}")
            return True
    except Exception as e:
        print(f"❌ Error alerta: {e}")
    return False

# ========================================
# MQTT
# ========================================

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set()

def on_mqtt_connect(client, userdata, flags, rc):
    global mqtt_connected
    print(f"✅ MQTT conectado (rc={rc})")
    mqtt_connected = True
    client.subscribe("esp32/sensores")
    client.subscribe("esp32/relay/status")
    client.subscribe("esp32/config")
    
    print("🔴 Apagando dispositivos...")
    for i in range(1, 5):
        update_relay_state(i, False, mode=0)

def on_mqtt_message(client, userdata, msg):
    global latest_sensor_data, relay_states, current_config
    try:
        data = json.loads(msg.payload.decode())
        
        if msg.topic == "esp32/sensores":
            latest_sensor_data['temp'] = data.get('temp', None)
            latest_sensor_data['hum'] = data.get('hum', None)
            latest_sensor_data['alert'] = data.get('alert', 'OK')
            
            if latest_sensor_data['temp'] is not None:
                print(f"📊 {latest_sensor_data['temp']:.1f}°C | {latest_sensor_data['hum']:.0f}%")
            
        elif msg.topic == "esp32/relay/status":
            for key, value in data.items():
                if key in relay_states and isinstance(value, dict):
                    relay_states[key].update(value)
                    
        elif msg.topic == "esp32/config":
            current_config.update(data)
            latest_sensor_data['setpoint'] = data.get('setpoint', 24)
            
    except Exception as e:
        print(f"❌ Error MQTT: {e}")

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message

try:
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print("✅ MQTT iniciado")
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
        print(f"❌ TTS: {e}")
        return None

def send_audio_to_esp32_speaker(text: str):
    """Audio para parlante ESP32"""
    if not AUDIO_ENABLED:
        return
    
    try:
        tts = gTTS(text=text, lang='es', slow=False)
        mp3_buffer = BytesIO()
        tts.write_to_fp(mp3_buffer)
        mp3_buffer.seek(0)
        
        audio = AudioSegment.from_file(mp3_buffer, format="mp3")
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(1)
        
        wav_buffer = BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_bytes = wav_buffer.getvalue()
        
        b64_data = base64.b64encode(wav_bytes).decode('utf-8')
        chunk_size = 1000
        
        mqtt_client.publish("esp32/tts/audio/start", "")
        for i in range(0, len(b64_data), chunk_size):
            mqtt_client.publish("esp32/tts/audio/chunk", b64_data[i:i+chunk_size])
        mqtt_client.publish("esp32/tts/audio/end", "")
        
    except Exception as e:
        print(f"❌ Audio ESP32: {e}")

def speech_to_text(audio_file_path: str) -> str:
    """Convierte nota de voz a texto"""
    if not VOICE_ENABLED or not AUDIO_ENABLED:
        return None
    
    try:
        recognizer = sr.Recognizer()
        audio = AudioSegment.from_file(audio_file_path)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
            wav_path = wav_file.name
            audio.export(wav_path, format='wav')
        
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='es-ES')
            
        try:
            os.unlink(wav_path)
        except:
            pass
            
        return text
        
    except Exception as e:
        print(f"❌ Voice: {e}")
        return None

# ========================================
# PROCESAMIENTO DE COMANDOS
# ========================================

def process_command(text: str) -> str:
    """Procesa comandos"""
    t = text.lower()
    
    global current_config
    db_config = get_system_config()
    if db_config:
        current_config = db_config
    
    # CONSULTAS
    if any(w in t for w in ['temperatura', 'temp', 'cuánto', 'grados', 'clima']):
        data = get_latest_sensor_data()
        if data and data['temp'] is not None:
            return f"La temperatura actual es {data['temp']:.1f} grados celsius y la humedad es {data['hum']:.0f} por ciento"
        return "Esperando datos del sensor..."
    
    elif any(w in t for w in ['humedad', 'húmedo']):
        data = get_latest_sensor_data()
        if data and data['hum'] is not None:
            return f"La humedad actual es del {data['hum']:.0f} por ciento"
        return "Esperando datos..."
    
    elif any(w in t for w in ['estado', 'sistema']):
        data = get_latest_sensor_data()
        if not data or data['temp'] is None:
            return "Sistema iniciando..."
        
        states = get_relay_states()
        relay_info = ""
        if states:
            on_count = sum(1 for r in states.values() if r.get('state', False))
            relay_info = f" Dispositivos activos: {on_count}/4."
        
        return f"Temperatura {data['temp']:.1f}°C, Humedad {data['hum']:.0f}%.{relay_info}"
    
    elif 'dispositivos' in t:
        states = get_relay_states()
        if not states:
            return "Sin información de dispositivos"
        
        status = []
        for key in ['r1', 'r2', 'r3', 'r4']:
            relay = states.get(key)
            if relay:
                st = "encendido" if relay.get('state', False) else "apagado"
                status.append(f"{relay['name']}: {st}")
        
        return "Estado: " + ", ".join(status)
    
    elif 'configuración' in t or 'config' in t:
        return f"Config: Objetivo {current_config['setpoint']}°C, Max {current_config['tempMax']}°C, Min {current_config['tempMin']}°C"
    
    # CONTROL - ON
    elif 'enciende' in t or 'prende' in t or 'encender' in t:
        if 'ventilador' in t or '1' in t:
            update_relay_state(1, True, mode=3)
            return "✅ Ventilador encendido"
        elif 'calefactor' in t or '2' in t:
            update_relay_state(2, True, mode=3)
            return "✅ Calefactor encendido"
        elif 'humidificador' in t or '3' in t:
            update_relay_state(3, True, mode=3)
            return "✅ Humidificador encendido"
        elif 'luz' in t or 'foco' in t or '4' in t:
            update_relay_state(4, True, mode=3)
            return "✅ Luz encendida"
        elif 'todo' in t:
            for i in range(1, 5):
                update_relay_state(i, True, mode=3)
            return "✅ Todos encendidos"
        return "Especifica: ventilador, calefactor, humidificador, luz"
    
    # CONTROL - OFF
    elif 'apaga' in t or 'apagar' in t:
        if 'ventilador' in t or '1' in t:
            update_relay_state(1, False, mode=3)
            return "✅ Ventilador apagado"
        elif 'calefactor' in t or '2' in t:
            update_relay_state(2, False, mode=3)
            return "✅ Calefactor apagado"
        elif 'humidificador' in t or '3' in t:
            update_relay_state(3, False, mode=3)
            return "✅ Humidificador apagado"
        elif 'luz' in t or 'foco' in t or '4' in t:
            update_relay_state(4, False, mode=3)
            return "✅ Luz apagada"
        elif 'todo' in t:
            for i in range(1, 5):
                update_relay_state(i, False, mode=3)
            return "✅ Todos apagados"
        return "Especifica: ventilador, calefactor, humidificador, luz"
    
    # CONFIGURACIÓN
    elif any(w in t for w in ['cambia', 'configura', 'pon']):
        words = t.split()
        temp_value = None
        for word in words:
            try:
                temp_value = float(word.replace(',', '.'))
                break
            except:
                continue
        
        if temp_value is None:
            return "Especifica un número. Ej: 'temperatura mínima 18'"
        
        if any(w in t for w in ['setpoint', 'objetivo']):
            if 15 <= temp_value <= 35:
                if update_system_config(setpoint=temp_value):
                    return f"✅ Temperatura objetivo: {temp_value}°C"
            return "Setpoint debe estar entre 15-35°C"
        
        elif any(w in t for w in ['máxima', 'maxima', 'max']):
            if 20 <= temp_value <= 50:
                if update_system_config(temp_max=int(temp_value)):
                    create_alert('CONFIG', f'Temp máx: {int(temp_value)}°C', 'WARNING')
                    return f"✅ Temperatura máxima: {int(temp_value)}°C"
            return "Temp máxima debe estar entre 20-50°C"
        
        elif any(w in t for w in ['mínima', 'minima', 'min']):
            if 5 <= temp_value <= 25:
                if update_system_config(temp_min=int(temp_value)):
                    create_alert('CONFIG', f'Temp mín: {int(temp_value)}°C', 'WARNING')
                    return f"✅ Temperatura mínima: {int(temp_value)}°C"
            return "Temp mínima debe estar entre 5-25°C"
        
        return "Especifica: temperatura mínima, máxima o setpoint"
    
    elif 'ayuda' in t:
        return """Comandos:
📊 temperatura / humedad / estado
🎛️ enciende/apaga ventilador, calefactor, luz
⚙️ temperatura mínima/máxima [valor]"""
    
    return "No entendí. Escribe 'ayuda'"

# ========================================
# TELEGRAM HANDLERS
# ========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Estado", callback_data='status')],
        [InlineKeyboardButton("🌡️ Temperatura", callback_data='temp')],
        [InlineKeyboardButton("🔌 Dispositivos", callback_data='devices')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🤖 *Bot ESP32*

Escribe:
• temperatura
• enciende ventilador
• temperatura mínima 18
• ayuda"""
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def temp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_latest_sensor_data()
    
    if not data or data['temp'] is None:
        await update.message.reply_text("⏳ Esperando datos...")
        return
    
    text = f"""🌡️ *TEMPERATURA*

Temp: *{data['temp']:.1f}°C*
Hum: *{data['hum']:.0f}%*

Max: {current_config['tempMax']}°C
Min: {current_config['tempMin']}°C"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
    
    audio_text = f"Temperatura {data['temp']:.1f} grados, humedad {data['hum']:.0f} por ciento"
    audio = text_to_speech_telegram(audio_text)
    if audio:
        await update.message.reply_voice(voice=audio)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_latest_sensor_data()
    
    if not data or data['temp'] is None:
        await update.message.reply_text("⏳ Iniciando...")
        return
    
    devices = ""
    states = get_relay_states()
    if states:
        for key in ['r1', 'r2', 'r3', 'r4']:
            r = states.get(key)
            if r:
                st = "🟢" if r.get('state', False) else "🔴"
                devices += f"\n{st} {r['name']}"
    
    text = f"""✅ *ESTADO*

🌡️ {data['temp']:.1f}°C | 💧 {data['hum']:.0f}%

*Dispositivos:*{devices}"""
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def devices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    states = get_relay_states()
    if not states:
        await update.message.reply_text("Sin info")
        return
    
    text = "*🔌 DISPOSITIVOS*\n\n"
    for key in ['r1', 'r2', 'r3', 'r4']:
        r = states.get(key)
        if r:
            st = "🟢 ON" if r.get('state', False) else "🔴 OFF"
            text += f"{r['name']}: {st}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler notas de voz"""
    if not VOICE_ENABLED:
        await update.message.reply_text("❌ Reconocimiento de voz no disponible. Usa texto.")
        return
    
    await update.message.reply_text("🎤 Procesando...")
    
    try:
        voice_file = await update.message.voice.get_file()
        
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
            temp_path = temp_file.name
            await voice_file.download_to_drive(temp_path)
        
        text = speech_to_text(temp_path)
        
        try:
            os.unlink(temp_path)
        except:
            pass
        
        if text:
            await update.message.reply_text(f"📝 *\"{text}\"*", parse_mode='Markdown')
            response = process_command(text)
            await update.message.reply_text(f"💬 {response}")
            
            audio = text_to_speech_telegram(response)
            if audio:
                await update.message.reply_voice(voice=audio)
            send_audio_to_esp32_speaker(response)
        else:
            await update.message.reply_text("❌ No entendí")
    
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler texto"""
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    response = process_command(text)
    await update.message.reply_text(f"💬 {response}")
    
    audio = text_to_speech_telegram(response)
    if audio:
        await update.message.reply_voice(voice=audio)
    send_audio_to_esp32_speaker(response)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    fake_update = Update(update.update_id)
    fake_update._effective_message = query.message
    
    if query.data == 'status':
        await status_command(fake_update, context)
    elif query.data == 'temp':
        await temp_command(fake_update, context)
    elif query.data == 'devices':
        await devices_command(fake_update, context)

# ========================================
# MAIN
# ========================================

def main():
    print("\n" + "="*60)
    print("🤖 BOT ESP32 - CONTROL TOTAL")
    print("="*60)
    print(f"✅ Python {sys.version.split()[0]}")
    print(f"✅ Voz: {'SI' if VOICE_ENABLED else 'NO'}")
    print(f"✅ Audio: {'SI' if AUDIO_ENABLED else 'NO'}")
    print("="*60 + "\n")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("temp", temp_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("devices", devices_command))
    
    if VOICE_ENABLED:
        app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Bot listo")
    print("🤖 CORRIENDO...\n")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()