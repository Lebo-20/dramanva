const express = require('express');
const axios = require('axios');

const app = express();

// ================= CONFIG =================
const CONFIG = {
  port: 3200,
  baseURL: 'https://api.sansekai.my.id/api/dramanova',
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
};

// ================= HTTP CLIENT =================
async function fetchAPI(endpoint, params = {}) {
  const url = `${CONFIG.baseURL}${endpoint}`;

  const res = await axios.get(url, {
    params,
    timeout: 15000,
    headers: {
      'Accept': '*/*',
      'User-Agent': CONFIG.userAgent,
      'Referer': 'https://sansekai.my.id/',
    },
  });

  return res.data;
}

// ================= MIDDLEWARE =================
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// ================= ENDPOINTS =================
app.get('/home', async (req, res) => {
  try {
    const page = req.query.page || 1;
    const data = await fetchAPI('/home', { page });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/drama18', async (req, res) => {
  try {
    const page = req.query.page || 1;
    const data = await fetchAPI('/drama18', { page });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/search', async (req, res) => {
  try {
    const query = req.query.query;
    const data = await fetchAPI('/search', { query });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/detail', async (req, res) => {
  try {
    const dramaId = req.query.dramaId;
    const data = await fetchAPI('/detail', { dramaId });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get('/getvideo', async (req, res) => {
  try {
    const fileId = req.query.fileId;
    const data = await fetchAPI('/getvideo', { fileId });
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ================= START SERVER =================
app.listen(CONFIG.port, () => {
  console.log(`🚀 Dramanova Proxy bridge running on port ${CONFIG.port}`);
});
