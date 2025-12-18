#!/usr/bin/env python3
"""
🤖 BOT DE TELEGRAM COMPLETO - CONTROL TOTAL ESP32
✅ Control de dispositivos via Supabase (usando requests)
✅ Configuración de temperaturas mín/máx
✅ Sistema de alertas automáticas
✅ Sincronización en tiempo real
✅ Respuesta triple: Texto + Audio Telegram + Parlante ESP32
"""

import os
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

# Supabase
SUPABASE_URL = "https://yxwinzfhokugvtpmvyqz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl4d2luemZob2t1Z3Z0cG12eXF6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MzIyNjcsImV4cCI6MjA4MTQwODI2N30.xbNWsxmQ4MwbjaQgzfZLkvLE66XqaANiUD4pggr43Vg"

# Headers para Supabase REST API
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
# FUNCIONES SUPABASE (usando requests)
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
        # Obtener config actual
        url_get = f"{SUPABASE_URL}/rest/v1/system_config?select=*&order=id.desc&limit=1"
        response = requests.get(url_get, headers=SUPABASE_HEADERS)
        
        if response.status_code == 200:
            data_list = response.json()
            if data_list and len(data_list) > 0:
                config_id = data_list[0]['id']
                
                # Preparar datos a actualizar
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
                        print(f"✅ Config actualizada en Supabase: {update_data}")
                        
                        # Publicar en MQTT para que ESP32 se actualice
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
            print(f"✅ Relay {relay_number} actualizado en Supabase: {state}")
            
            # Publicar en MQTT
            mqtt_client.publish(f"esp32/relay/{relay_number}/cmd", "ON" if state else "OFF")
            if mode is not None:
                mqtt_client.publish(f"esp32/relay/{relay_number}/mode", str(mode))
            
            return True
    except Exception as e:
        print(f"❌ Error actualizando relay: {e}")
    return False

def get_relay_states():
    """Obtiene el último estado de cada relay desde Supabase"""
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
            print(f"✅ Alerta creada: {alert_type} - {message}")
            return True
    except Exception as e:
        print(f"❌ Error creando alerta: {e}")
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
    
    # Apagar todos los dispositivos al inicio
    print("🔴 Apagando todos los dispositivos al iniciar...")
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
                print(f"📊 Temp: {latest_sensor_data['temp']:.1f}°C | Hum: {latest_sensor_data['hum']:.0f}%")
            
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
    print(f"⚠️ Error MQTT: {e}")

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
    """Genera audio WAV y lo envía al parlante ESP32"""
    try:
        print(f"🔊 Generando audio para parlante: {text[:60]}...")
        
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
            chunk = b64_data[i:i+chunk_size]
            mqtt_client.publish("esp32/tts/audio/chunk", chunk)
        
        mqtt_client.publish("esp32/tts/audio/end", "")
        print("✅ Audio enviado al parlante ESP32")
        
    except Exception as e:
        print(f"❌ Error enviando audio: {e}")

def speech_to_text(audio_file_path: str) -> str:
    """Convierte nota de voz a texto"""
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
        return None
    except Exception as e:
        print(f"❌ Error procesando audio: {e}")
        return None

# ========================================
# PROCESAMIENTO DE COMANDOS
# ========================================

def process_command(text: str) -> str:
    """Procesa comandos y retorna respuesta"""
    t = text.lower()
    
    # Actualizar config desde Supabase
    global current_config
    db_config = get_system_config()
    if db_config:
        current_config = db_config
    
    # CONSULTAS
    if any(w in t for w in ['temperatura', 'temp', 'cuánto', 'cuánta', 'grados', 'clima']):
        data = get_latest_sensor_data()
        if data and data['temp'] is not None:
            return f"La temperatura actual es {data['temp']:.1f} grados celsius y la humedad es {data['hum']:.0f} por ciento"
        
        if not mqtt_connected:
            return "No puedo conectarme al sistema ESP32. Verifica que esté encendido."
        return "Aún no he recibido datos del sensor. Espera unos segundos."
    
    elif any(w in t for w in ['humedad', 'húmedo', 'húmeda']):
        data = get_latest_sensor_data()
        if data and data['hum'] is not None:
            return f"La humedad actual es del {data['hum']:.0f} por ciento"
        return "Aún no he recibido datos del sensor de humedad."
    
    elif any(w in t for w in ['estado', 'cómo está', 'sistema', 'todo bien']):
        data = get_latest_sensor_data()
        if not data or data['temp'] is None:
            return "El sistema está iniciando. Aún no he recibido datos."
        
        states = get_relay_states()
        relay_info = ""
        if states:
            on_count = sum(1 for r in states.values() if r.get('state', False))
            relay_info = f" Dispositivos activos: {on_count} de 4."
        
        temp_status = "Todo está bien"
        if data['temp'] > current_config['tempMax']:
            temp_status = f"⚠️ Temperatura ALTA ({data['temp']:.1f}°C)"
        elif data['temp'] < current_config['tempMin']:
            temp_status = f"⚠️ Temperatura BAJA ({data['temp']:.1f}°C)"
        
        return f"{temp_status}. Temperatura {data['temp']:.1f} grados, Humedad {data['hum']:.0f} por ciento.{relay_info}"
    
    elif 'dispositivos' in t or 'relays' in t or 'qué está encendido' in t:
        states = get_relay_states()
        if not states:
            return "No tengo información de los dispositivos"
        
        status = []
        for key in ['r1', 'r2', 'r3', 'r4']:
            relay = states.get(key)
            if relay:
                state_text = "encendido" if relay.get('state', False) else "apagado"
                status.append(f"{relay['name']}: {state_text}")
        
        return "Estado actual: " + ", ".join(status)
    
    elif 'configuración' in t or 'config' in t:
        return f"Configuración actual: Temperatura objetivo {current_config['setpoint']}°C, Histéresis {current_config['hysteresis']}°C, Temperatura máxima {current_config['tempMax']}°C, Temperatura mínima {current_config['tempMin']}°C"
    
    # CONTROL DE DISPOSITIVOS - ON
    elif 'enciende' in t or 'prende' in t or 'activa' in t or 'encender' in t:
        if 'ventilador' in t or '1' in t:
            if update_relay_state(1, True, mode=3):
                return "✅ He encendido el ventilador correctamente"
        elif 'calefactor' in t or 'calor' in t or '2' in t:
            if update_relay_state(2, True, mode=3):
                return "✅ He encendido el calefactor correctamente"
        elif 'humidificador' in t or '3' in t:
            if update_relay_state(3, True, mode=3):
                return "✅ He encendido el humidificador correctamente"
        elif 'luz' in t or 'foco' in t or 'lámpara' in t or '4' in t:
            if update_relay_state(4, True, mode=3):
                return "✅ He encendido la luz correctamente"
        elif 'todo' in t or 'todos' in t:
            for i in range(1, 5):
                update_relay_state(i, True, mode=3)
            return "✅ He encendido todos los dispositivos"
        return "No entendí qué dispositivo encender. Di: ventilador, calefactor, humidificador o luz"
    
    # CONTROL DE DISPOSITIVOS - OFF
    elif 'apaga' in t or 'desactiva' in t or 'apagar' in t:
        if 'ventilador' in t or '1' in t:
            if update_relay_state(1, False, mode=3):
                return "✅ He apagado el ventilador"
        elif 'calefactor' in t or 'calor' in t or '2' in t:
            if update_relay_state(2, False, mode=3):
                return "✅ He apagado el calefactor"
        elif 'humidificador' in t or '3' in t:
            if update_relay_state(3, False, mode=3):
                return "✅ He apagado el humidificador"
        elif 'luz' in t or 'foco' in t or 'lámpara' in t or '4' in t:
            if update_relay_state(4, False, mode=3):
                return "✅ He apagado la luz"
        elif 'todo' in t or 'todos' in t:
            for i in range(1, 5):
                update_relay_state(i, False, mode=3)
            return "✅ He apagado todos los dispositivos"
        return "No entendí qué dispositivo apagar. Di: ventilador, calefactor, humidificador o luz"
    
    # CAMBIO DE MODOS
    elif 'modo' in t:
        relay_num = None
        mode_val = None
        mode_name = None
        
        if 'ventilador' in t or '1' in t:
            relay_num = 1
        elif 'calefactor' in t or '2' in t:
            relay_num = 2
        elif 'humidificador' in t or '3' in t:
            relay_num = 3
        elif 'luz' in t or '4' in t:
            relay_num = 4
        
        if 'automático' in t or 'auto' in t:
            mode_name = 'automático'
            mode_val = 2
        elif 'manual' in t:
            mode_name = 'manual'
            mode_val = 3
        elif 'siempre encendido' in t or 'forzado on' in t:
            mode_name = 'siempre encendido'
            mode_val = 1
        elif 'siempre apagado' in t or 'forzado off' in t:
            mode_name = 'siempre apagado'
            mode_val = 0
        else:
            return "Modos: automático, manual, siempre encendido, siempre apagado"
        
        if relay_num and mode_val is not None:
            states = get_relay_states()
            current_state = False
            if states and f'r{relay_num}' in states:
                current_state = states[f'r{relay_num}'].get('state', False)
            
            if update_relay_state(relay_num, current_state, mode=mode_val):
                relay_names = ['ventilador', 'calefactor', 'humidificador', 'luz']
                return f"✅ He cambiado el {relay_names[relay_num-1]} a modo {mode_name}"
        
        return "Especifica el dispositivo: ventilador, calefactor, humidificador o luz"
    
    # CONFIGURACIÓN DE SISTEMA
    elif any(word in t for word in ['cambia', 'ajusta', 'modifica', 'pon', 'configura', 'configuración']):
        words = t.split()
        
        temp_value = None
        for word in words:
            try:
                temp_value = float(word.replace(',', '.'))
                break
            except:
                continue
        
        if temp_value is None:
            return "No entendí el valor. Di un número. Ejemplo: 'temperatura mínima 18'"
        
        # SETPOINT
        if any(w in t for w in ['setpoint', 'objetivo', 'temperatura objetivo']):
            if 15 <= temp_value <= 35:
                if update_system_config(setpoint=temp_value):
                    return f"✅ Temperatura objetivo cambiada a {temp_value}°C"
            return "El setpoint debe estar entre 15 y 35 grados"
        
        # HISTÉRESIS
        elif any(w in t for w in ['histéresis', 'histeresis', 'margen']):
            if 0.5 <= temp_value <= 5:
                if update_system_config(hysteresis=temp_value):
                    return f"✅ Histéresis cambiada a {temp_value}°C"
            return "La histéresis debe estar entre 0.5 y 5 grados"
        
        # TEMPERATURA MÁXIMA
        elif any(w in t for w in ['máxima', 'maxima', 'max', 'alta', 'máx']):
            if 20 <= temp_value <= 50:
                if update_system_config(temp_max=int(temp_value)):
                    create_alert('CONFIG_CHANGE', f'Temp máxima configurada en {int(temp_value)}°C', 'WARNING')
                    return f"✅ Temperatura máxima configurada en {int(temp_value)}°C. Te avisaré si se supera este valor"
            return "La temperatura máxima debe estar entre 20 y 50 grados"
        
        # TEMPERATURA MÍNIMA
        elif any(w in t for w in ['mínima', 'minima', 'min', 'baja', 'mín']):
            if 5 <= temp_value <= 25:
                if update_system_config(temp_min=int(temp_value)):
                    create_alert('CONFIG_CHANGE', f'Temp mínima configurada en {int(temp_value)}°C', 'WARNING')
                    return f"✅ Temperatura mínima configurada en {int(temp_value)}°C. Te avisaré si baja de este valor"
            return "La temperatura mínima debe estar entre 5 y 25 grados"
        
        return "Especifica qué cambiar: temperatura mínima, temperatura máxima, setpoint o histéresis"
    
    # AYUDA
    elif 'ayuda' in t or 'comandos' in t or 'qué puedes hacer' in t:
        return """Puedo ayudarte con:

📊 CONSULTAS:
• temperatura / humedad / estado / dispositivos

🎛️ CONTROL:
• enciende/apaga ventilador, calefactor, humidificador, luz

⚙️ CONFIGURACIÓN:
• "cambia setpoint a 25"
• "temperatura mínima 18"
• "temperatura máxima 30"

🔄 MODOS:
• modo ventilador automático / manual"""
    
    return "No entendí tu comando. Escribe 'ayuda' para ver todos los comandos"

# ========================================
# HANDLERS DE TELEGRAM
# ========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Estado", callback_data='status')],
        [InlineKeyboardButton("🌡️ Temperatura", callback_data='temp')],
        [InlineKeyboardButton("🔌 Dispositivos", callback_data='devices')],
        [InlineKeyboardButton("⚙️ Configuración", callback_data='config')],
        [InlineKeyboardButton("❓ Ayuda", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """
🤖 *Bot ESP32 - Control Total*

*🎤 ENVÍA NOTA DE VOZ:*
• "¿Qué temperatura hay?"
• "Enciende el ventilador"
• "Temperatura mínima 18"

*💬 O ESCRIBE TEXTO:*
• temperatura
• enciende luz
• apaga todo

Escribe *ayuda* para ver todos los comandos 🚀
    """
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📚 *COMANDOS DISPONIBLES*

*📊 CONSULTAS:*
• temperatura / humedad / estado

*🎛️ CONTROL:*
• enciende/apaga ventilador, calefactor, luz

*⚙️ CONFIGURACIÓN:*
• temperatura mínima/máxima
• cambia setpoint

*🎤 NOTA DE VOZ:*
Envía cualquier comando por voz
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def temp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_latest_sensor_data()
    
    if not data or data['temp'] is None:
        await update.message.reply_text("⏳ Aún no he recibido datos del sensor.")
        return
    
    text_msg = f"""
🌡️ *TEMPERATURA*

Temperatura: *{data['temp']:.1f}°C*
Humedad: *{data['hum']:.0f}%*
Setpoint: *{current_config['setpoint']:.1f}°C*

Límites:
📈 Máx: *{current_config['tempMax']}°C*
📉 Mín: *{current_config['tempMin']}°C*
    """
    await update.message.reply_text(text_msg, parse_mode='Markdown')
    
    audio_text = f"La temperatura es {data['temp']:.1f} grados celsius y la humedad es {data['hum']:.0f} por ciento"
    audio = text_to_speech_telegram(audio_text)
    if audio:
        await update.message.reply_voice(voice=audio)
    
    send_audio_to_esp32_speaker(audio_text)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_latest_sensor_data()
    
    if not data or data['temp'] is None:
        await update.message.reply_text("⏳ Sistema iniciando.")
        return
    
    temp_status = "✅"
    if data['temp'] > current_config['tempMax']:
        temp_status = "🔥"
    elif data['temp'] < current_config['tempMin']:
        temp_status = "❄️"
    
    devices = ""
    states = get_relay_states()
    if states:
        for key in ['r1', 'r2', 'r3', 'r4']:
            r = states.get(key)
            if r:
                state = "🟢" if r.get('state', False) else "🔴"
                devices += f"\n{state} {r['name']}"
    
    text_msg = f"""
{temp_status} *ESTADO*

🌡️ {data['temp']:.1f}°C | 💧 {data['hum']:.0f}%
🎯 Setpoint: {current_config['setpoint']:.1f}°C

*Dispositivos:*{devices}
    """
    await update.message.reply_text(text_msg, parse_mode='Markdown')
    
    audio_text = f"Temperatura {data['temp']:.1f} grados"
    audio = text_to_speech_telegram(audio_text)
    if audio:
        await update.message.reply_voice(voice=audio)
    
    send_audio_to_esp32_speaker(audio_text)

async def devices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    states = get_relay_states()
    if not states:
        await update.message.reply_text("No hay información de dispositivos")
        return
    
    text = "*🔌 DISPOSITIVOS*\n\n"
    
    modes = ["🔴 OFF", "🟢 ON", "🤖 AUTO", "✋ MANUAL"]
    
    for key in ['r1', 'r2', 'r3', 'r4']:
        r = states.get(key)
        if r:
            state = "🟢" if r.get('state', False) else "🔴"
            mode = modes[r.get('mode', 0)]
            text += f"{state} *{r['name']}* - {mode}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
⚙️ *CONFIGURACIÓN*

🎯 Objetivo: *{current_config['setpoint']}°C*
📊 Histéresis: *{current_config['hysteresis']}°C*
🔥 Max: *{current_config['tempMax']}°C*
❄️ Min: *{current_config['tempMin']}°C*
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para NOTAS DE VOZ"""
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
            await update.message.reply_text("❌ No entendí la voz.")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para MENSAJES DE TEXTO"""
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
    elif query.data == 'config':
        await config_command(fake_update, context)
    elif query.data == 'help':
        await help_command(fake_update, context)

# ========================================
# MAIN
# ========================================

def main():
    print("\n" + "="*70)
    print("🤖 BOT ESP32 - CONTROL TOTAL (sin librería supabase)")
    print("="*70)
    print("✅ Usa requests directamente a Supabase REST API")
    print("✅ Control completo de dispositivos")
    print("✅ Configuración de temperaturas")
    print("✅ Sistema de alertas")
    print("="*70 + "\n")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("temp", temp_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("devices", devices_command))
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ayuda", help_command))
    
    app.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Bot listo")
    print("\n📱 Prueba:")
    print("   • temperatura")
    print("   • enciende ventilador")
    print("   • temperatura mínima 18")
    print("\n🤖 CORRIENDO...\n")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
