/**
 * 📊 PROXY SUPABASE PARA NETLIFY
 * Obtiene datos históricos y alertas
 */

const fetch = require('node-fetch');

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_KEY;

async function fetchSupabase(table, options = {}) {
  const { limit = 10, order = 'created_at', ascending = false } = options;
  
  const url = `${SUPABASE_URL}/rest/v1/${table}?order=${order}.${ascending ? 'asc' : 'desc'}&limit=${limit}`;
  
  const response = await fetch(url, {
    headers: {
      'apikey': SUPABASE_KEY,
      'Authorization': `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error(`Supabase error: ${response.statusText}`);
  }

  return await response.json();
}

exports.handler = async (event, context) => {
  // CORS Headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle OPTIONS
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'GET') {
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  try {
    const { queryStringParameters } = event;
    const type = queryStringParameters?.type || 'history';

    let data = {};

    switch (type) {
      case 'history':
        data = await fetchSupabase('sensor_readings', { limit: 10 });
        break;
      
      case 'alerts':
        data = await fetchSupabase('system_alerts', { limit: 5 });
        break;
      
      case 'all':
        const [history, alerts] = await Promise.all([
          fetchSupabase('sensor_readings', { limit: 10 }),
          fetchSupabase('system_alerts', { limit: 5 })
        ]);
        data = { history, alerts };
        break;
      
      default:
        return {
          statusCode: 400,
          headers,
          body: JSON.stringify({ error: 'Invalid type parameter' })
        };
    }

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        success: true,
        data
      })
    };

  } catch (error) {
    console.error('Supabase Error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        success: false,
        error: error.message
      })
    };
  }
};