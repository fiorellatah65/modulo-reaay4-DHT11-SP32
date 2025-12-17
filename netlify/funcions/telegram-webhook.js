/**
 * 🤖 BOT TELEGRAM EN JAVASCRIPT PARA NETLIFY FUNCTIONS
 * Webhook que recibe mensajes y responde con texto + audio
 */

const mqtt = require('mqtt');
const fetch = require('node-fetch');
const gtts = require('node-gtts')('es');

// ========================================
// CONFIGURACIÓN
// ========================================

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN || "8491255978:AAFfDy6smKSAhkcGjtX8HxHh6cXe9RB4Y44";
const TELEGRAM_API = `https://api.telegram.org/bot${TELEGRAM_TOKEN}`;

const MQTT_CONFIG = {
  host: 'e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud',
  port: 8883,
  username: 'esp32user',
  password: 'Esp32pass123',
  protocol: 'mqtts'
};

// Datos en memoria (en producción usa Redis/Database)
let sensorData = { temp: 0, hum: 0, alert: 'OK', setpoint: 24 };

// ========================================
// MQTT CLIENT
// ========================================

let mqttClient = null;

function connectMQTT() {
  if (mqttClient && mqttClient.connected) return mqttClient;
  
  mqttClient = mqtt.connect(MQTT_CONFIG);
  
  mqttClient.on('connect', () => {
    console.log('✅ MQTT conectado');
    mqttClient.subscribe('esp32/sensores');
  });
  
  mqttClient.on('message', (topic, message) => {
    if (topic === 'esp32/sensores') {
      try {
        sensorData = JSON.parse(message.toString());
      } catch (e) {}
    }
  });
  
  return mqttClient;
}

// ========================================
// FUNCIONES TELEGRAM
// ========================================

async function sendMessage(chatId, text) {
  try {
    await fetch(`${TELEGRAM_API}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown' })
    });
  } catch (error) {
    console.error('Error enviando mensaje:', error);
  }
}

async function sendVoice(chatId, text) {
  try {
    // Generar audio con gTTS
    const audioBuffer = await new Promise((resolve, reject) => {
      gtts.save(text, 'audio.mp3', (err) => {
        if (err) reject(err);
        else {
          const fs = require('fs');
          resolve(fs.readFileSync('audio.mp3'));
        }
      });
    });
    
    // Enviar audio a Telegram
    const FormData = require('form-data');
    const form = new FormData();
    form.append('chat_id', chatId);
    form.append('voice', audioBuffer, { filename: 'voice.ogg' });
    
    await fetch(`${TELEGRAM_API}/sendVoice`, {
      method: 'POST',
      body: form
    });
    
  } catch (error) {
    console.error('Error enviando audio:', error);
  }
}

function sendTextToESP32Speaker(text) {
  try {
    const client = connectMQTT();
    const cleanText = text.replace(/[🌡️💧✅⚠️*]/g, '').trim().substring(0, 150);
    client.publish('esp32/tts/text', cleanText);
    console.log('📤 Texto enviado al parlante ESP32');
  } catch (error) {
    console.error('Error enviando al parlante:', error);
  }
}

// ========================================
// PROCESAMIENTO DE COMANDOS
// ========================================

function processCommand(text) {
  const t = text.toLowerCase();
  const client = connectMQTT();
  
  // Temperatura
  if (t.includes('temperatura') || t.includes('temp') || t.includes('grados')) {
    return `La temperatura actual es ${sensorData.temp.toFixed(1)} grados celsius y la humedad es ${sensorData.hum.toFixed(0)} por ciento`;
  }
  
  // Humedad
  if (t.includes('humedad') || t.includes('húmedo')) {
    return `La humedad actual es del ${sensorData.hum.toFixed(0)} por ciento`;
  }
  
  // Estado
  if (t.includes('estado') || t.includes('cómo está') || t.includes('sistema')) {
    if (sensorData.alert === 'OK') {
      return `Todo está bien. Temperatura ${sensorData.temp.toFixed(1)} grados, Humedad ${sensorData.hum.toFixed(0)} por ciento`;
    }
    return `Alerta: ${sensorData.alert}. Temperatura ${sensorData.temp.toFixed(1)} grados`;
  }
  
  // Encender dispositivos
  if (t.includes('enciende') || t.includes('prende')) {
    if (t.includes('ventilador') || t.includes('1')) {
      client.publish('esp32/relay/1/cmd', 'ON');
      return 'He encendido el ventilador correctamente';
    }
    if (t.includes('calefactor') || t.includes('calor') || t.includes('2')) {
      client.publish('esp32/relay/2/cmd', 'ON');
      return 'He encendido el calefactor correctamente';
    }
    if (t.includes('humidificador') || t.includes('3')) {
      client.publish('esp32/relay/3/cmd', 'ON');
      return 'He encendido el humidificador correctamente';
    }
    if (t.includes('luz') || t.includes('foco') || t.includes('4')) {
      client.publish('esp32/relay/4/cmd', 'ON');
      return 'He encendido la luz correctamente';
    }
    if (t.includes('todo')) {
      for (let i = 1; i <= 4; i++) {
        client.publish(`esp32/relay/${i}/cmd`, 'ON');
      }
      return 'He encendido todos los dispositivos';
    }
  }
  
  // Apagar dispositivos
  if (t.includes('apaga') || t.includes('desactiva')) {
    if (t.includes('ventilador') || t.includes('1')) {
      client.publish('esp32/relay/1/cmd', 'OFF');
      return 'He apagado el ventilador';
    }
    if (t.includes('calefactor') || t.includes('2')) {
      client.publish('esp32/relay/2/cmd', 'OFF');
      return 'He apagado el calefactor';
    }
    if (t.includes('humidificador') || t.includes('3')) {
      client.publish('esp32/relay/3/cmd', 'OFF');
      return 'He apagado el humidificador';
    }
    if (t.includes('luz') || t.includes('foco') || t.includes('4')) {
      client.publish('esp32/relay/4/cmd', 'OFF');
      return 'He apagado la luz';
    }
    if (t.includes('todo')) {
      for (let i = 1; i <= 4; i++) {
        client.publish(`esp32/relay/${i}/cmd`, 'OFF');
      }
      return 'He apagado todos los dispositivos';
    }
  }
  
  return 'No entendí tu comando. Puedes preguntar por temperatura, humedad, o controlar dispositivos';
}

// ========================================
// HANDLER PRINCIPAL
// ========================================

exports.handler = async (event, context) => {
  // Solo aceptar POST
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }
  
  try {
    const update = JSON.parse(event.body);
    
    // Verificar que es un mensaje
    if (!update.message) {
      return { statusCode: 200, body: 'OK' };
    }
    
    const chatId = update.message.chat.id;
    const text = update.message.text || '';
    
    console.log(`📩 Mensaje recibido: ${text}`);
    
    // Comandos especiales
    if (text === '/start') {
      const welcome = `🤖 *Bot ESP32 - Audio Triple*

*💬 Comandos:*
• temperatura
• humedad
• estado
• enciende [ventilador/calefactor/luz]
• apaga [ventilador/calefactor/luz]

*🔊 Responderé con:*
1️⃣ Texto en Telegram
2️⃣ Audio en Telegram
3️⃣ Voz en Parlante ESP32

¡Pruébalo! 🚀`;
      
      await sendMessage(chatId, welcome);
      return { statusCode: 200, body: 'OK' };
    }
    
    // Procesar comando
    const response = processCommand(text);
    
    // 1️⃣ ENVIAR TEXTO
    await sendMessage(chatId, `💬 ${response}`);
    
    // 2️⃣ ENVIAR AUDIO A TELEGRAM
    await sendVoice(chatId, response);
    
    // 3️⃣ ENVIAR AL PARLANTE ESP32
    sendTextToESP32Speaker(response);
    
    console.log('✅ Respuesta triple enviada');
    
    return {
      statusCode: 200,
      body: JSON.stringify({ ok: true })
    };
    
  } catch (error) {
    console.error('❌ Error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};

// Iniciar conexión MQTT al cargar
connectMQTT();