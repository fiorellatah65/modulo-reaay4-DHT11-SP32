// Proxy MQTT para evitar problemas de WebSocket
// Si la conexión directa falla, usa este endpoint

const mqtt = require('mqtt');

exports.handler = async (event, context) => {
  // Solo GET para obtener datos
  if (event.httpMethod !== 'GET') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  try {
    const client = mqtt.connect('mqtts://e311193c90544b20aa5e2fc9b1c06df5.s1.eu.hivemq.cloud:8883', {
      username: 'esp32user',
      password: 'Esp32pass123',
      rejectUnauthorized: false
    });

    return new Promise((resolve) => {
      let resolved = false;
      const data = {};

      client.on('connect', () => {
        console.log('Proxy MQTT conectado');
        client.subscribe('esp32/sensores');
        client.subscribe('esp32/relay/status');
      });

      client.on('message', (topic, message) => {
        if (!resolved) {
          try {
            data[topic] = JSON.parse(message.toString());
            
            // Si ya tenemos datos de sensores, resolver
            if (data['esp32/sensores']) {
              resolved = true;
              client.end();
              resolve({
                statusCode: 200,
                headers: {
                  'Content-Type': 'application/json',
                  'Access-Control-Allow-Origin': '*'
                },
                body: JSON.stringify(data)
              });
            }
          } catch (e) {
            console.error('Error parsing:', e);
          }
        }
      });

      // Timeout de 5 segundos
      setTimeout(() => {
        if (!resolved) {
          client.end();
          resolve({
            statusCode: 200,
            headers: {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*'
            },
            body: JSON.stringify({ 
              error: 'Timeout',
              data: data 
            })
          });
        }
      }, 5000);
    });

  } catch (error) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: error.message })
    };
  }
};