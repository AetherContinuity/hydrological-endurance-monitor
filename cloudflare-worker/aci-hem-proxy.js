/**
 * aci-hem-proxy — Cloudflare Worker
 *
 * Proxies SYKE Hydrologiarajapinta (OData) and FMI open data (WFS)
 * for the Hydrological Endurance Monitor (HEM).
 *
 * Same pattern as aci-fingrid-proxy and aci-transmission-proxy.
 *
 * Routes:
 *   GET /syke?paikka=200&suure=1&start=2024-01-01&end=2024-12-31
 *       → SYKE OData Havainto query for water level
 *
 *   GET /fmi?station=101004&param=temperature,precipitation&start=2024-01-01&end=2024-12-31
 *       → FMI WFS query for weather observations
 *
 * Deploy:
 *   wrangler deploy
 *   Name: aci-hem-proxy
 *
 * Usage in HEM:
 *   const BASE = 'https://aci-hem-proxy.ruotsalainen-marko.workers.dev';
 *   fetch(`${BASE}/syke?paikka=200&suure=1&start=2024-01-01&end=2024-12-31`)
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

// SYKE OData base
const SYKE_BASE = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/odata/Havainto';

// FMI WFS base
const FMI_BASE = 'https://opendata.fmi.fi/wfs';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    try {
      if (url.pathname === '/syke' || url.pathname === '/syke/') {
        return await handleSyke(url.searchParams);
      }
      if (url.pathname === '/fmi' || url.pathname === '/fmi/') {
        return await handleFmi(url.searchParams);
      }
      if (url.pathname === '/syke/paikat') {
        return await handleSykePaikat();
      }
      return jsonError(404, 'Route not found. Use /syke or /fmi');
    } catch (e) {
      return jsonError(500, e.message);
    }
  }
};

// ─── SYKE handler ───────────────────────────────────────────────

async function handleSyke(params) {
  // Required: paikka (station ID), suure (variable ID)
  // suure: 1 = vedenkorkeus, 2 = virtaama, 5 = lumen vesiarvo
  const paikka = params.get('paikka') || '200';   // Lauritsala default
  const suure  = params.get('suure')  || '1';     // vedenkorkeus default
  const start  = params.get('start')  || '2020-01-01';
  const end    = params.get('end')    || new Date().toISOString().slice(0, 10);
  const top    = params.get('top')    || '10000';

  // OData filter
  const filter = [
    `Paikka/PaikkaId eq ${paikka}`,
    `Suure/SuureId eq ${suure}`,
    `Aika ge datetime'${start}T00:00:00'`,
    `Aika le datetime'${end}T23:59:59'`,
  ].join(' and ');

  const sykeUrl = `${SYKE_BASE}?$filter=${encodeURIComponent(filter)}&$top=${top}&$format=json&$select=Aika,Arvo`;

  const resp = await fetch(sykeUrl, {
    headers: { 'Accept': 'application/json' }
  });

  if (!resp.ok) {
    return jsonError(resp.status, `SYKE API error: ${resp.status}`);
  }

  const data = await resp.json();

  // Normalise to [{date, value}] array
  const rows = (data.value || []).map(r => ({
    date: r.Aika?.slice(0, 10),
    value: r.Arvo,
  }));

  return new Response(JSON.stringify({ source: 'syke', paikka, suure, rows }), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── SYKE station list ───────────────────────────────────────────

async function handleSykePaikat() {
  const url = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/odata/Paikka?$format=json&$top=100&$filter=substringof(%27Saimaa%27,Nimi)%20or%20substringof(%27Lauritsala%27,Nimi)%20or%20substringof(%27Virmasvesi%27,Nimi)';
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── FMI handler ────────────────────────────────────────────────

async function handleFmi(params) {
  const station = params.get('station') || '101756'; // Lappeenranta Lepola default
  const param   = params.get('param')   || 'temperature,precipitation';
  const start   = params.get('start')   || '2020-01-01';
  const end     = params.get('end')     || new Date().toISOString().slice(0, 10);

  // FMI WFS stored query for daily observations
  const queryId = 'fmi::observations::weather::daily::simple';

  const fmiUrl = `${FMI_BASE}?service=WFS&version=2.0.0&request=getFeature` +
    `&storedquery_id=${queryId}` +
    `&fmisid=${station}` +
    `&parameters=${param}` +
    `&starttime=${start}T00:00:00Z` +
    `&endtime=${end}T23:59:59Z`;

  const resp = await fetch(fmiUrl);

  if (!resp.ok) {
    return jsonError(resp.status, `FMI API error: ${resp.status}`);
  }

  const xml = await resp.text();

  // Parse XML to simple array — extract gml:pos and BsWfs:ParameterValue
  const rows = parseFmiXml(xml);

  return new Response(JSON.stringify({ source: 'fmi', station, param, rows }), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── FMI XML parser ─────────────────────────────────────────────

function parseFmiXml(xml) {
  const rows = [];
  const timeRe   = /<BsWfs:Time>([^<]+)<\/BsWfs:Time>/g;
  const paramRe  = /<BsWfs:ParameterName>([^<]+)<\/BsWfs:ParameterName>/g;
  const valueRe  = /<BsWfs:ParameterValue>([^<]+)<\/BsWfs:ParameterValue>/g;

  const times  = [...xml.matchAll(timeRe)].map(m => m[1].slice(0, 10));
  const pnames = [...xml.matchAll(paramRe)].map(m => m[1]);
  const values = [...xml.matchAll(valueRe)].map(m => parseFloat(m[1]));

  for (let i = 0; i < times.length; i++) {
    rows.push({ date: times[i], param: pnames[i], value: isNaN(values[i]) ? null : values[i] });
  }
  return rows;
}

// ─── Helpers ────────────────────────────────────────────────────

function jsonError(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}
