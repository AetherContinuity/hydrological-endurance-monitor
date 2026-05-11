// ACI NVE Hydro Proxy — v11.1: deploy trigger NVE + SYKE + FMI
// Reitti:
//   GET /           → NVE Magasinstatistikk (ennallaan v10)
//   GET /syke       → SYKE OData vedenkorkeus/virtaama
//   GET /syke/paikat→ Saimaa-alueen asemat
//   GET /fmi        → FMI WFS päivittäiset säähavainnot

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json'
};

const SYKE_BASE = 'http://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/Havainto';
const FMI_BASE  = 'https://opendata.fmi.fi/wfs';

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    const url = new URL(request.url);

    try {
      if (url.pathname === '/syke' || url.pathname === '/syke/') {
        return await handleSyke(url.searchParams);
      }
      if (url.pathname === '/syke/paikat') {
        return await handleSykePaikat();
      }
      if (url.pathname === '/fmi' || url.pathname === '/fmi/') {
        return await handleFmi(url.searchParams);
      }
      if (url.pathname.startsWith('/vesiraja')) {
        return await handleVesiraja(url);
      }
      // Default: NVE (v10 — ei muutoksia)
      return await handleNve(env);

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: CORS });
    }
  }
};

// ─── NVE (v10 — täsmälleen ennallaan) ───────────────────────────

async function handleNve(env) {
  const apiKey = env.NVE_API_KEY || '';
  const url = 'https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligDataSisteUke';

  const resp = await fetch(url, {
    headers: {
      'Accept': 'application/json',
      'User-Agent': 'ACI-NVE-Proxy/1.0',
      'X-API-Key': apiKey
    }
  });

  if (!resp.ok) {
    return new Response(JSON.stringify({ error: `HTTP ${resp.status}` }), { status: 502, headers: CORS });
  }

  const rows = await resp.json();
  const allRows = Array.isArray(rows) ? rows : [rows];

  const row = allRows.reduce((best, r) =>
    (r.kapasitet_TWh ?? 0) > (best?.kapasitet_TWh ?? 0) ? r : best
  , allRows[0]);

  const filling     = row.fyllingsgrad * 100;
  const prevFilling = row.fyllingsgrad_forrige_uke != null ? row.fyllingsgrad_forrige_uke * 100 : null;
  const change      = row.endring_fyllingsgrad != null ? Math.round(row.endring_fyllingsgrad * 1000) / 10 : null;
  const HIST_MEDIAN = 58.0;
  const hydro_RF    = Math.min(1.2, Math.max(0.3, filling / HIST_MEDIAN));

  return new Response(JSON.stringify({
    source:       'NVE Magasinstatistikk',
    week:         `${row.iso_aar}-W${String(row.iso_uke).padStart(2,'0')}`,
    date:         row.dato_Id,
    filling_pct:  Math.round(filling * 10) / 10,
    prev_pct:     prevFilling != null ? Math.round(prevFilling * 10) / 10 : null,
    change_pp:    change,
    capacity_twh: row.kapasitet_TWh,
    content_twh:  row.fylling_TWh,
    median_pct:   HIST_MEDIAN,
    hydro_RF:     Math.round(hydro_RF * 1000) / 1000,
    label:        hydro_RF < 0.80 ? 'low' : hydro_RF < 1.05 ? 'normal' : 'high',
    omrnr:        row.omrnr,
    next_update:  row.neste_Publiseringsdato,
    fetched:      new Date().toISOString()
  }), { headers: CORS });
}

// ─── SYKE ────────────────────────────────────────────────────────

async function handleSyke(params) {
  const paikka = params.get('paikka') || '200';   // 200 = Lauritsala (Saimaa)
  const suure  = params.get('suure')  || '1';     // 1=vedenkorkeus 2=virtaama 5=lumi
  const start  = params.get('start')  || '2020-01-01';
  const end    = params.get('end')    || new Date().toISOString().slice(0, 10);
  const top    = params.get('top')    || '5000';

  const filter = [
    `Paikka/PaikkaId eq ${paikka}`,
    `Suure/SuureId eq ${suure}`,
    `Aika ge datetime'${start}T00:00:00'`,
    `Aika le datetime'${end}T23:59:59'`,
  ].join(' and ');

  const sykeUrl = `${SYKE_BASE}?$filter=${encodeURIComponent(filter)}&$top=${top}&$format=json&$select=Aika,Arvo`;

  const resp = await fetch(sykeUrl, { headers: { 'Accept': 'application/json' } });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    return new Response(JSON.stringify({
      error: `SYKE HTTP ${resp.status}`,
      url: sykeUrl,
      detail: errText.slice(0, 200)
    }), { status: 502, headers: CORS });
  }

  const data = await resp.json();
  const rows = (data.value || []).map(r => ({
    date:  r.Aika?.slice(0, 10),
    value: r.Arvo,
  }));

  return new Response(JSON.stringify({
    source: 'SYKE Hydrologiarajapinta',
    paikka, suure, start, end,
    n: rows.length,
    rows
  }), { headers: CORS });
}

// ─── SYKE asemaluettelo ──────────────────────────────────────────

async function handleSykePaikat() {
  const filter = `substringof('Saimaa',Nimi) or substringof('Lauritsala',Nimi) or substringof('Virmasvesi',Nimi) or substringof('Puumala',Nimi)`;
  const url = `https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/odata/Paikka?$format=json&$top=50&$filter=${encodeURIComponent(filter)}`;
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const data = await resp.json();
  return new Response(JSON.stringify(data), { headers: CORS });
}

// ─── FMI ────────────────────────────────────────────────────────

async function handleFmi(params) {
  const station = params.get('station') || '101756'; // Lappeenranta Lepola
  const param   = params.get('param')   || 'tday,rrday';
  const start   = params.get('start')   || '2020-01-01';
  const end     = params.get('end')     || new Date().toISOString().slice(0, 10);

  const fmiUrl = `${FMI_BASE}?service=WFS&version=2.0.0&request=getFeature` +
    `&storedquery_id=fmi::observations::weather::daily::simple` +
    `&fmisid=${station}` +
    `&parameters=${param}` +
    `&starttime=${start}T00:00:00Z` +
    `&endtime=${end}T23:59:59Z`;

  const resp = await fetch(fmiUrl);
  if (!resp.ok) {
    return new Response(JSON.stringify({ error: `FMI HTTP ${resp.status}` }), { status: 502, headers: CORS });
  }

  const xml  = await resp.text();
  const rows = parseFmiXml(xml);

  return new Response(JSON.stringify({
    source: 'FMI WFS',
    station, param, start, end,
    n: rows.length,
    rows
  }), { headers: CORS });
}

// ─── Vesiraja API ────────────────────────────────────────────────

const VESIRAJA_BASE = 'https://api.ymparisto.fi/vesiraja';

async function handleVesiraja(url) {
  const params = url.searchParams;
  const sub = url.pathname.replace('/vesiraja', '').replace(/^\//, '');

  let endpoint;

  if (sub === 'stations') {
    endpoint = `${VESIRAJA_BASE}/stations?api-version=1`;
  } else if (sub === 'variables') {
    endpoint = `${VESIRAJA_BASE}/variables?api-version=1`;
  } else if (sub === 'statistics') {
    const vc    = params.get('variable') || 'WaterLevel';
    const start = params.get('start')    || '2025-01-01';
    const end   = params.get('end')      || today();
    const sc    = params.get('station')  || '';
    let q = `api-version=1&VariableCode=${vc}&DateStart=${start}&DateEnd=${end}`;
    if (sc) q += `&StationCode=${sc}`;
    endpoint = `${VESIRAJA_BASE}/statistics/daily/json?${q}`;
  } else {
    // default: timeseries
    const vc    = params.get('variable') || 'WaterLevel';
    const start = params.get('start')    || '2025-01-01';
    const end   = params.get('end')      || today();
    const sc    = params.get('station')  || '';
    let q = `api-version=1&VariableCode=${vc}&DateStart=${start}&DateEnd=${end}`;
    if (sc) q += `&StationCode=${sc}`;
    endpoint = `${VESIRAJA_BASE}/timeseries/json?${q}`;
  }

  const resp = await fetch(endpoint, {
    headers: { 'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1' }
  });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    return new Response(JSON.stringify({
      error: `Vesiraja HTTP ${resp.status}`,
      url: endpoint,
      detail: errText.slice(0, 300)
    }), { status: 502, headers: CORS });
  }

  const data = await resp.json();
  return new Response(JSON.stringify({
    source: 'SYKE Vesiraja API',
    endpoint,
    data
  }), { headers: CORS });
}

function parseFmiXml(xml) {
  const times  = [...xml.matchAll(/<BsWfs:Time>([^<]+)<\/BsWfs:Time>/g)].map(m => m[1].slice(0,10));
  const pnames = [...xml.matchAll(/<BsWfs:ParameterName>([^<]+)<\/BsWfs:ParameterName>/g)].map(m => m[1]);
  const values = [...xml.matchAll(/<BsWfs:ParameterValue>([^<]+)<\/BsWfs:ParameterValue>/g)].map(m => parseFloat(m[1]));
  return times.map((date, i) => ({
    date,
    param: pnames[i],
    value: isNaN(values[i]) ? null : values[i]
  }));
}
