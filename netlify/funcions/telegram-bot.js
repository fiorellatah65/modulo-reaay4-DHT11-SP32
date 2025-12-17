// 🤖 BOT DE TELEGRAM PARA NETLIFY FUNCTIONS
// Adaptado de Python a JavaScript con máxima funcionalidad

const mqtt = require('mqtt');
const fetch = require('node-fetch');
const FormData = require('form-data');
const googleTTS = require('google-tts-api');

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN;
const TELEGRAM_API = `https://api.telegram.org/bot${TELEGRAM_TOKEN}`;

const MQTT_CONFIG = {
  host: 'mqtts://e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud:8883',
  username: 'esp32user',
  password: 'Esp32pass123'
};

// Variable para cachear datos del sensor (limitación de serverless)
let cachedSensorData = {
  temp: 24.0,
  hum: 50.0,
  alert: 'OK',
  setpoint: 24.0
};

// ========================================
// HANDLER PRINCIPAL
// ========================================
exports.handler = async (event, context) => {
  // Solo POST de Telegram
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 200,
      body: JSON.stringify({ message: 'Bot funcionando. Webhook configurado correctamente.' })
    };
  }

  try {
    const update = JSON.parse(event.body);
    console.log('📩 Update recibido:', JSON.stringify(update).substring(0, 200));

    // MENSAJE DE TEXTO
    if (update.message?.text) {
      const chatId = update.message.chat.id;
      const text = update.message.text;

      // Comando /start
      if (text.startsWith('/start')) {
        await sendStartMessage(chatId);
        return successResponse();
      }

      // Comando /temp
      if (text.startsWith('/temp')) {
        await handleTempCommand(chatId);
        return successResponse();
      }

      // Comando /status
      if (text.startsWith('/status')) {
        await handleStatusCommand(chatId);
        return successResponse();
      }

      // Cualquier otro texto
      await handleTextMessage(chatId, text);
      return successResponse();
    }

    // NOTA DE VOZ
    if (update.message?.voice) {
      const chatId = update.message.chat.id;
      const fileId = update.message.voice.file_id;
      
      await sendTelegramMessage(chatId, '🎤 Procesando tu nota de voz...');
      await handleVoiceMessage(chatId, fileId);
      return successResponse();
    }

    // CALLBACK DE BOTONES
    if (update.callback_query) {
      await handleCallback(update.callback_query);
      return successResponse();
    }

    return successResponse();

  } catch (error) {
    console.error('❌ Error:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};

// ========================================
// FUNCIONES DE TELEGRAM
// ========================================

async function sendStartMessage(chatId) {
  const keyboard = {
    inline_keyboard: [
      [{ text: '📊 Estado', callback_data: 'status' }],
      [{ text: '🌡️ Temperatura', callback_data: 'temp' }]
    ]
  };

  const text = `
🤖 *Bot ESP32 - Control Completo*

*💬 Escribe TEXTO:*
• temperatura
• enciende ventilador
• apaga luz
• estado
• setpoint 26

*🎤 Envía NOTA DE VOZ:*
• "¿Qué temperatura hay?"
• "Enciende el ventilador"
• "¿Cómo está el sistema?"

*🔊 RECIBIRÁS:*
1️⃣ 📱 Respuesta en texto
2️⃣ 🎵 Audio en Telegram
3️⃣ 🔊 Voz en Parlante ESP32

¡Pruébalo ahora! 🚀
  `;

  await sendTelegramMessage(chatId, text, keyboard);
}

async function handleTempCommand(chatId) {
  try {
    // Intentar obtener datos actuales de MQTT
    const sensorData = await getSensorDataFromMQTT();
    
    const textMsg = `
🌡️ *TEMPERATURA*

Temperatura: *${sensorData.temp.toFixed(1)}°C*
Humedad: *${sensorData.hum.toFixed(0)}%*
Setpoint: *${sensorData.setpoint.toFixed(1)}°C*
    `;

    // 1️⃣ TEXTO
    await sendTelegramMessage(chatId, textMsg);

    // 2️⃣ AUDIO TELEGRAM
    const audioText = `La temperatura es ${sensorData.temp.toFixed(1)} grados celsius y la humedad es ${sensorData.hum.toFixed(0)} por ciento`;
    await sendAudioToTelegram(chatId, audioText);

    // 3️⃣ PARLANTE ESP32
    await sendAudioToESP32Speaker(audioText);

  } catch (error) {
    console.error('Error en temp:', error);
    await sendTelegramMessage(chatId, '❌ Error obteniendo temperatura. Intenta de nuevo.');
  }
}

async function handleStatusCommand(chatId) {
  try {
    const sensorData = await getSensorDataFromMQTT();
    const emoji = sensorData.alert === 'OK' ? '✅' : '⚠️';

    const textMsg = `
${emoji} *ESTADO DEL SISTEMA*

🌡️ Temperatura: ${sensorData.temp.toFixed(1)}°C
💧 Humedad: ${sensorData.hum.toFixed(0)}%
🎯 Setpoint: ${sensorData.setpoint.toFixed(1)}°C
📊 Estado: ${sensorData.alert}
    `;

    await sendTelegramMessage(chatId, textMsg);

    const audioText = `Sistema funcionando. Temperatura ${sensorData.temp.toFixed(1)} grados`;
    await sendAudioToTelegram(chatId, audioText);
    await sendAudioToESP32Speaker(audioText);

  } catch (error) {
    console.error('Error en status:', error);
    await sendTelegramMessage(chatId, '❌ Error obteniendo estado.');
  }
}

async function handleTextMessage(chatId, text) {
  const response = processCommand(text);
  
  // 1️⃣ TEXTO
  await sendTelegramMessage(chatId, `💬 ${response}`);
  
  // 2️⃣ AUDIO TELEGRAM
  await sendAudioToTelegram(chatId, response);
  
  // 3️⃣ PARLANTE ESP32
  await sendAudioToESP32Speaker(response);
}

async function handleVoiceMessage(chatId, fileId) {
  try {
    // Descargar archivo de voz
    const fileData = await fetch(`${TELEGRAM_API}/getFile?file_id=${fileId}`).then(r => r.json());
    
    if (!fileData.ok) {
      throw new Error('No se pudo obtener el archivo');
    }

    const filePath = fileData.result.file_path;
    const fileUrl = `https://api.telegram.org/file/bot${TELEGRAM_TOKEN}/${filePath}`;

    // Descargar el audio
    const audioBuffer = await fetch(fileUrl).then(r => r.buffer());

    // ⚠️ LIMITACIÓN: Speech-to-text requiere API externa
    // Usaremos Google Cloud Speech (requiere configuración adicional)
    // Por ahora, simulamos reconocimiento básico
    
    await sendTelegramMessage(chatId, '⚠️ Reconocimiento de voz en desarrollo. Usa texto por ahora.');
    
    // ALTERNATIVA: Podrías usar API de Google Cloud Speech
    // const text = await speechToText(audioBuffer);
    // const response = processCommand(text);
    // await sendTelegramMessage(chatId, `📝 Entendí: "${text}"\n\n${response}`);

  } catch (error) {
    console.error('Error procesando voz:', error);
    await sendTelegramMessage(chatId, '❌ Error procesando nota de voz. Intenta con texto.');
  }
}

async function handleCallback(callbackQuery) {
  const chatId = callbackQuery.message.chat.id;
  const data = callbackQuery.data;

  // Responder al callback
  await fetch(`${TELEGRAM_API}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackQuery.id })
  });

  if (data === 'temp') {
    await handleTempCommand(chatId);
  } else if (data === 'status') {
    await handleStatusCommand(chatId);
  }
}

// ========================================
// FUNCIONES DE PROCESAMIENTO
// ========================================

function processCommand(text) {
  const t = text.toLowerCase();

  // TEMPERATURA
  if (t.includes('temperatura') || t.includes('temp') || t.includes('cuánto') || t.includes('cuánta') || t.includes('grados')) {
    return `La temperatura actual es ${cachedSensorData.temp.toFixed(1)} grados celsius y la humedad es ${cachedSensorData.hum.toFixed(0)} por ciento`;
  }

  // HUMEDAD
  if (t.includes('humedad') || t.includes('húmedo')) {
    return `La humedad actual es del ${cachedSensorData.hum.toFixed(0)} por ciento`;
  }

  // ESTADO
  if (t.includes('estado') || t.includes('cómo está') || t.includes('sistema')) {
    if (cachedSensorData.alert === 'OK') {
      return `Todo está bien. Temperatura ${cachedSensorData.temp.toFixed(1)} grados, Humedad ${cachedSensorData.hum.toFixed(0)} por ciento`;
    } else {
      return `Alerta: ${cachedSensorData.alert}. Temperatura ${cachedSensorData.temp.toFixed(1)} grados`;
    }
  }

  // ENCENDER
  if (t.includes('enciende') || t.includes('prende')) {
    if (t.includes('ventilador') || t.includes('1')) {
      sendMQTTCommand('esp32/relay/1/cmd', 'ON');
      return 'He encendido el ventilador';
    }
    if (t.includes('calefactor') || t.includes('2')) {
      sendMQTTCommand('esp32/relay/2/cmd', 'ON');
      return 'He encendido el calefactor';
    }
    if (t.includes('humidificador') || t.includes('3')) {
      sendMQTTCommand('esp32/relay/3/cmd', 'ON');
      return 'He encendido el humidificador';
    }
    if (t.includes('luz') || t.includes('foco') || t.includes('4')) {
      sendMQTTCommand('esp32/relay/4/cmd', 'ON');
      return 'He encendido la luz';
    }
    if (t.includes('todo')) {
      for (let i = 1; i <= 4; i++) {
        sendMQTTCommand(`esp32/relay/${i}/cmd`, 'ON');
      }
      return 'He encendido todos los dispositivos';
    }
    return 'No entendí qué dispositivo encender. Especifica: ventilador, calefactor, humidificador o luz';
  }

  // APAGAR
  if (t.includes('apaga')) {
    if (t.includes('ventilador') || t.includes('1')) {
      sendMQTTCommand('esp32/relay/1/cmd', 'OFF');
      return 'He apagado el ventilador';
    }
    if (t.includes('calefactor') || t.includes('2')) {
      sendMQTTCommand('esp32/relay/2/cmd', 'OFF');
      return 'He apagado el calefactor';
    }
    if (t.includes('humidificador') || t.includes('3')) {
      sendMQTTCommand('esp32/relay/3/cmd', 'OFF');
      return 'He apagado el humidificador';
    }
    if (t.includes('luz') || t.includes('foco') || t.includes('4')) {
      sendMQTTCommand('esp32/relay/4/cmd', 'OFF');
      return 'He apagado la luz';
    }
    if (t.includes('todo')) {
      for (let i = 1; i <= 4; i++) {
        sendMQTTCommand(`esp32/relay/${i}/cmd`, 'OFF');
      }
      return 'He apagado todos los dispositivos';
    }
    return 'No entendí qué dispositivo apagar';
  }

  // SETPOINT
  if (t.includes('setpoint') || t.includes('cambia')) {
    const words = t.split(/\s+/);
    for (const word of words) {
      const temp = parseFloat(word);
      if (!isNaN(temp) && temp >= 15 && temp <= 35) {
        sendMQTTCommand('esp32/config/set', JSON.stringify({ setpoint: temp }));
        return `Setpoint cambiado a ${temp} grados`;
      }
    }
    return 'No entendí la temperatura. Debe estar entre 15 y 35 grados';
  }

  return 'No entendí tu comando. Puedes preguntar por temperatura, humedad, o controlar dispositivos (enciende/apaga ventilador, luz, etc.)';
}

// ========================================
// FUNCIONES MQTT
// ========================================

async function getSensorDataFromMQTT() {
  return new Promise((resolve) => {
    const client = mqtt.connect(MQTT_CONFIG.host, {
      username: MQTT_CONFIG.username,
      password: MQTT_CONFIG.password,
      rejectUnauthorized: false
    });

    let resolved = false;

    client.on('connect', () => {
      console.log('📡 MQTT conectado');
      client.subscribe('esp32/sensores');
    });

    client.on('message', (topic, message) => {
      if (topic === 'esp32/sensores' && !resolved) {
        try {
          const data = JSON.parse(message.toString());
          cachedSensorData = data;
          resolved = true;
          client.end();
          resolve(data);
        } catch (e) {
          console.error('Error parsing sensor data:', e);
        }
      }
    });

    // Timeout: usar datos cacheados si no hay respuesta
    setTimeout(() => {
      if (!resolved) {
        client.end();
        resolve(cachedSensorData);
      }
    }, 3000);
  });
}

async function sendMQTTCommand(topic, payload) {
  return new Promise((resolve) => {
    const client = mqtt.connect(MQTT_CONFIG.host, {
      username: MQTT_CONFIG.username,
      password: MQTT_CONFIG.password,
      rejectUnauthorized: false
    });

    client.on('connect', () => {
      console.log(`📤 Publicando en ${topic}: ${payload}`);
      client.publish(topic, payload);
      
      setTimeout(() => {
        client.end();
        resolve();
      }, 1000);
    });

    setTimeout(() => {
      client.end();
      resolve();
    }, 5000);
  });
}

// ========================================
// FUNCIONES DE AUDIO
// ========================================

async function sendAudioToTelegram(chatId, text) {
  try {
    // Usar Google TTS API
    const audioUrl = googleTTS.getAudioUrl(text, {
      lang: 'es',
      slow: false,
      host: 'https://translate.google.com'
    });

    // Descargar el audio
    const audioResponse = await fetch(audioUrl);
    const audioBuffer = await audioResponse.buffer();

    // Enviar como voice message
    const formData = new FormData();
    formData.append('chat_id', chatId);
    formData.append('voice', audioBuffer, { filename: 'voice.ogg', contentType: 'audio/ogg' });

    await fetch(`${TELEGRAM_API}/sendVoice`, {
      method: 'POST',
      body: formData
    });

    console.log('🎵 Audio enviado a Telegram');

  } catch (error) {
    console.error('Error enviando audio a Telegram:', error);
  }
}

async function sendAudioToESP32Speaker(text) {
  try {
    console.log(`🔊 Enviando audio al parlante ESP32: "${text.substring(0, 50)}..."`);

    // Obtener audio de Google TTS
    const audioUrl = googleTTS.getAudioUrl(text, {
      lang: 'es',
      slow: false,
      host: 'https://translate.google.com'
    });

    const audioResponse = await fetch(audioUrl);
    const audioBuffer = await audioResponse.buffer();

    // Convertir a base64
    const base64Audio = audioBuffer.toString('base64');

    // Enviar por MQTT en chunks
    const client = mqtt.connect(MQTT_CONFIG.host, {
      username: MQTT_CONFIG.username,
      password: MQTT_CONFIG.password,
      rejectUnauthorized: false
    });

    client.on('connect', () => {
      console.log('📡 Enviando audio al ESP32...');
      
      // Señal de inicio
      client.publish('esp32/tts/audio/start', '');

      // Enviar chunks
      const chunkSize = 1000;
      for (let i = 0; i < base64Audio.length; i += chunkSize) {
        const chunk = base64Audio.substring(i, i + chunkSize);
        client.publish('esp32/tts/audio/chunk', chunk);
      }

      // Señal de fin
      client.publish('esp32/tts/audio/end', '');

      setTimeout(() => {
        client.end();
        console.log('✅ Audio enviado al parlante ESP32');
      }, 2000);
    });

  } catch (error) {
    console.error('Error enviando audio al ESP32:', error);
  }
}

// ========================================
// UTILIDADES
// ========================================

async function sendTelegramMessage(chatId, text, keyboard = null) {
  const body = {
    chat_id: chatId,
    text: text,
    parse_mode: 'Markdown'
  };

  if (keyboard) {
    body.reply_markup = keyboard;
  }

  await fetch(`${TELEGRAM_API}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function successResponse() {
  return {
    statusCode: 200,
    body: JSON.stringify({ ok: true })
  };
}