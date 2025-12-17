/**
 * 🔌 PROXY MQTT PARA NETLIFY
 * Conecta al broker MQTT y devuelve datos al frontend
 */

const mqtt = require('mqtt');

// Cache para evitar reconexiones constantes
let cachedData = {
  sensores: null,
  relays: null,
  esp32Status: 'offline',
  timestamp: 0
};

let mqttClient = null;

function connectMQTT() {
  if (mqttClient && mqttClient.connected) {
    return mqttClient;
  }

  const options = {
    host: process.env.MQTT_HOST,
    port: parseInt(process.env.MQTT_PORT),
    username: process.env.MQTT_USER,
    password: process.env.MQTT_PASS,
    protocol: 'mqtts',
    rejectUnauthorized: false
  };

  mqttClient = mqtt.connect(options);

  mqttClient.on('connect', () => {
    console.log('✅ MQTT Proxy conectado');
    mqttClient.subscribe('esp32/sensores');
    mqttClient.subscribe('esp32/relay/status');
    mqttClient.subscribe('esp32/status');
  });

  mqttClient.on('message', (topic, message) => {
    const now = Date.now();
    
    try {
      if (topic === 'esp32/sensores') {
        cachedData.sensores = JSON.parse(message.toString());
        cachedData.timestamp = now;
      } else if (topic === 'esp32/relay/status') {
        cachedData.relays = JSON.parse(message.toString());
        cachedData.timestamp = now;
      } else if (topic === 'esp32/status') {
        cachedData.esp32Status = message.toString();
        cachedData.timestamp = now;
      }
    } catch (e) {
      console.error('Error parsing MQTT message:', e);
    }
  });

  mqttClient.on('error', (err) => {
    console.error('MQTT Error:', err);
  });

  return mqttClient;
}

// Control de relays
function controlRelay(num, state) {
  const client = connectMQTT();
  if (client && client.connected) {
    client.publish(`esp32/relay/${num}/cmd`, state);
    return true;
  }
  return false;
}

function setRelayMode(num, mode) {
  const client = connectMQTT();
  if (client && client.connected) {
    client.publish(`esp32/relay/${num}/mode`, mode.toString());
    return true;
  }
  return false;
}

function updateConfig(config) {
  const client = connectMQTT();
  if (client && client.connected) {
    client.publish('esp32/config/set', JSON.stringify(config));
    return true;
  }
  return false;
}

exports.handler = async (event, context) => {
  // CORS Headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle OPTIONS (preflight)
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  // Iniciar conexión MQTT
  connectMQTT();

  try {
    // GET: Obtener datos actuales
    if (event.httpMethod === 'GET') {
      // Verificar si los datos están muy viejos (más de 30 segundos)
      const dataAge = Date.now() - cachedData.timestamp;
      const isStale = dataAge > 30000;

      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          success: true,
          data: cachedData,
          mqtt_connected: mqttClient && mqttClient.connected,
          data_age_seconds: Math.floor(dataAge / 1000),
          is_stale: isStale
        })
      };
    }

    // POST: Controlar dispositivos
    if (event.httpMethod === 'POST') {
      const body = JSON.parse(event.body || '{}');
      const { action, relay, state, mode, config } = body;

      let success = false;
      let message = '';

      switch (action) {
        case 'control_relay':
          success = controlRelay(relay, state);
          message = success ? `Relay ${relay} ${state}` : 'Error controlando relay';
          break;
        
        case 'set_mode':
          success = setRelayMode(relay, mode);
          message = success ? `Modo ${mode} en relay ${relay}` : 'Error cambiando modo';
          break;
        
        case 'update_config':
          success = updateConfig(config);
          message = success ? 'Configuración actualizada' : 'Error actualizando config';
          break;
        
        default:
          message = 'Acción no reconocida';
      }

      return {
        statusCode: success ? 200 : 500,
        headers,
        body: JSON.stringify({ success, message })
      };
    }

    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ error: 'Method not allowed' })
    };

  } catch (error) {
    console.error('Error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: error.message })
    };
  }
};