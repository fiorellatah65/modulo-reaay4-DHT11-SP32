// proyecto/netlify/functions/mqtt-status.js
const mqtt = require('mqtt');

let mqttClient = null;
let lastSensorData = null;
let lastRelayStatus = null;
let lastConfig = null;

const MQTT_CONFIG = {
  host: 'e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud',
  port: 8883,
  username: process.env.MQTT_USER || 'esp32user',
  password: process.env.MQTT_PASS || 'Esp32pass123',
  protocol: 'mqtts'
};

function connectMQTT() {
  if (mqttClient && mqttClient.connected) return mqttClient;
  
  mqttClient = mqtt.connect(MQTT_CONFIG);
  
  mqttClient.on('connect', () => {
    console.log('✅ MQTT conectado desde función');
    mqttClient.subscribe([
      'esp32/sensores',
      'esp32/status',
      'esp32/relay/status',
      'esp32/config'
    ]);
  });
  
  mqttClient.on('message', (topic, message) => {
    try {
      const msg = message.toString();
      
      if (topic === 'esp32/sensores') {
        lastSensorData = JSON.parse(msg);
      } else if (topic === 'esp32/relay/status') {
        lastRelayStatus = JSON.parse(msg);
      } else if (topic === 'esp32/config') {
        lastConfig = JSON.parse(msg);
      }
    } catch (e) {
      console.error('Error parsing:', e);
    }
  });
  
  return mqttClient;
}

// Mantener conexión activa
connectMQTT();

exports.handler = async (event, context) => {
  // Configurar CORS
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Manejar preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    const client = connectMQTT();
    
    // GET - Obtener estado actual
    if (event.httpMethod === 'GET') {
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          connected: client && client.connected,
          sensors: lastSensorData,
          relays: lastRelayStatus,
          config: lastConfig,
          timestamp: new Date().toISOString()
        })
      };
    }
    
    // POST - Enviar comandos
    if (event.httpMethod === 'POST') {
      const { action, topic, message } = JSON.parse(event.body);
      
      if (!client || !client.connected) {
        return {
          statusCode: 503,
          headers,
          body: JSON.stringify({ error: 'MQTT no conectado' })
        };
      }
      
      if (action === 'publish' && topic && message !== undefined) {
        client.publish(topic, typeof message === 'string' ? message : JSON.stringify(message));
        
        return {
          statusCode: 200,
          headers,
          body: JSON.stringify({ success: true, topic, message })
        };
      }
      
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ error: 'Acción no válida' })
      };
    }
    
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ error: 'Método no permitido' })
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