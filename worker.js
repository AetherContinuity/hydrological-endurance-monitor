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

const SYKE_BASE = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/WaterLevelRegisters';
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
      if (url.pathname === '/syke/csv') {
        return await handleSykeCSV(url.searchParams);
      }
      if (url.pathname === '/fmi' || url.pathname === '/fmi/') {
        return await handleFmi(url.searchParams);
      }
      if (url.pathname.startsWith('/vesiraja')) {
        return await handleVesiraja(url);
      }
      if (url.pathname === '/syke/wsfs' || url.pathname === '/syke/wsfs/') {
        return await handleSykeWsfs(url.searchParams);
      }
      if (url.pathname === '/era5' || url.pathname === '/era5/') {
        return await handleERA5(url.searchParams);
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
  // LocationId muoto: '04.112.1.001' (Saimaa Lauritsala)
  const locationId = params.get('location') || params.get('paikka') || '04.112.1.001';
  const start      = params.get('start') || '2024-01-01';
  const end        = params.get('end')   || new Date().toISOString().slice(0, 10);
  const top        = params.get('top')   || '5000';

  const filter = [
    `LocationId eq '${locationId}'`,
    `Timestamp ge ${start}T00:00:00Z`,
    `Timestamp le ${end}T23:59:59Z`,
  ].join(' and ');

  const sykeUrl = `${SYKE_BASE}?$filter=${encodeURIComponent(filter)}&$orderby=Timestamp asc&$top=${top}&$format=json&$select=Timestamp,Wvalue`;

  const resp = await fetch(sykeUrl, { headers: { 'Accept': 'application/json' } });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    return new Response(JSON.stringify({
      error: `SYKE HTTP ${resp.status}`,
      url: sykeUrl,
      detail: errText.slice(0, 300)
    }), { status: 502, headers: CORS });
  }

  const data = await resp.json();
  const rows = (data.value || []).map(r => ({
    date:  r.Timestamp?.slice(0, 10),
    value: r.Wvalue,
  }));

  return new Response(JSON.stringify({
    source: 'SYKE Hydrologiarajapinta 1.1',
    locationId, start, end,
    n: rows.length,
    rows
  }), { headers: CORS });
}

// ─── SYKE asemaluettelo ──────────────────────────────────────────

async function handleSykePaikat() {
  // Hae OData-metadata — näyttää kaikki saatavilla olevat entiteetit
  const metaUrl = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/$metadata';
  const rootUrl = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/';

  // Hae ensin juuridokumentti
  const rootResp = await fetch(rootUrl, { headers: { 'Accept': 'application/json' } });
  const rootText = await rootResp.text().catch(() => '');

  // Sitten metadata
  const metaResp = await fetch(metaUrl);
  const metaText = await metaResp.text().catch(() => '');

  // Poimii EntitySet-nimet XML-metadatasta
  const entities = [...metaText.matchAll(/EntitySet Name="([^"]+)"/g)].map(m => m[1]);
  const entityTypes = [...metaText.matchAll(/EntityType Name="([^"]+)"/g)].map(m => m[1]);

  return new Response(JSON.stringify({
    root_status: rootResp.status,
    root_preview: rootText.slice(0, 500),
    meta_status: metaResp.status,
    entities,
    entityTypes,
    meta_preview: metaText.slice(0, 1000)
  }), { headers: CORS });
}

// ─── FMI ────────────────────────────────────────────────────────

async function handleFmi(params) {
  const station = params.get('station') || '';
  const place   = params.get('place')   || 'Lappeenranta';
  const param   = params.get('param')   || 'tday,rrday';
  const start   = params.get('start')   || '2024-01-01';
  const end     = params.get('end')     || new Date().toISOString().slice(0, 10);

  // Käytä fmisid jos annettu, muuten place-parametria
  const locationParam = station
    ? `&fmisid=${station}`
    : `&place=${encodeURIComponent(place)}`;

  const fmiUrl = `${FMI_BASE}?service=WFS&version=2.0.0&request=getFeature` +
    `&storedquery_id=fmi::observations::weather::daily::simple` +
    locationParam +
    `&parameters=${param}` +
    `&starttime=${start}T00:00:00Z` +
    `&endtime=${end}T23:59:59Z`;

  const resp = await fetch(fmiUrl);
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    return new Response(JSON.stringify({
      error: `FMI HTTP ${resp.status}`,
      url: fmiUrl,
      detail: errText.slice(0, 300)
    }), { status: 502, headers: CORS });
  }

  const xml  = await resp.text();
  const rows = parseFmiXml(xml);

  return new Response(JSON.stringify({
    source: 'FMI WFS',
    station: station || place, param, start, end,
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

// ─── SYKE wwwi2 CSV ──────────────────────────────────────────────

async function handleSykeCSV(params) {
  const tunnus = params.get('tunnus') || '0411200'; // Lauritsala default
  const start  = params.get('start')  || '2024-01-01';
  const end    = params.get('end')    || new Date().toISOString().slice(0,10);

  const csvUrl = `https://wwwi2.ymparisto.fi/i2/95/vesiA.html?tunnus=${tunnus}&alku=${start}&loppu=${end}&type=csv`;

  const resp = await fetch(csvUrl, {
    headers: { 'User-Agent': 'ACI-HEM/1.1', 'Accept': 'text/csv,text/plain,*/*' }
  });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    return new Response(JSON.stringify({
      error: `SYKE wwwi2 HTTP ${resp.status}`,
      url: csvUrl,
      detail: errText.slice(0, 300)
    }), { status: 502, headers: CORS });
  }

  const csv = await resp.text();
  const lines = csv.trim().split('\n').filter(l => l.trim());
  const rows = [];
  for (const line of lines.slice(1)) {
    const parts = line.split(/[;,\t]/);
    if (parts.length >= 2) {
      rows.push({ date: parts[0]?.trim(), value: parseFloat(parts[1]) });
    }
  }

  return new Response(JSON.stringify({
    source: 'SYKE wwwi2', tunnus, start, end,
    n: rows.length,
    csv_preview: csv.slice(0, 400),
    rows: rows.slice(0, 10)
  }), { headers: CORS });
}

// ─── ERA5 via Open-Meteo ──────────────────────────────────────────────────────
// Ei API-avainta tarvita. Toimii suoraan selaimesta ja Workerista.
// Parametrit: ?lat=62.95&lng=26.85&start=2015-01-01
// BEM-käyttö: sadevajeanomalia D_c-komponentille

async function handleERA5(params) {
  const lat   = params.get('lat')   || '62.95';   // Rautalammin reitti default
  const lng   = params.get('lng')   || '26.85';
  const start = params.get('start') || '2015-01-01';
  const end   = new Date().toISOString().slice(0,10);

  const url = `https://archive-api.open-meteo.com/v1/archive?` +
    `latitude=${lat}&longitude=${lng}` +
    `&start_date=${start}&end_date=${end}` +
    `&daily=precipitation_sum,temperature_2m_mean` +
    `&timezone=Europe%2FHelsinki`;

  const r = await fetch(url);
  if (!r.ok) return new Response(JSON.stringify({error: `Open-Meteo ${r.status}`}), {status:502, headers:CORS});

  const d = await r.json();
  const precips = (d.daily?.precipitation_sum || []).filter(v => v != null);
  const temps   = (d.daily?.temperature_2m_mean || []).filter(v => v != null);

  // Laske anomalia: viimeiset 365pv vs referenssi
  const recent = precips.slice(-365).reduce((a,b) => a+b, 0);
  const ref    = precips.slice(0,-365);
  const refAnn = ref.length > 0 ? ref.reduce((a,b)=>a+b,0)/ref.length*365 : null;
  const anomPct = refAnn ? Math.round((recent-refAnn)/refAnn*1000)/10 : null;

  // Lämpötila 30pv keskiarvo
  const lastT = temps.slice(-30);
  const avgT  = lastT.length ? Math.round(lastT.reduce((a,b)=>a+b,0)/lastT.length*10)/10 : null;

  return new Response(JSON.stringify({
    source:   'ERA5-Land via Open-Meteo',
    lat, lng, start, end,
    precip_12mo_mm:     Math.round(recent),
    precip_ref_ann_mm:  refAnn ? Math.round(refAnn) : null,
    precip_anomaly_pct: anomPct,
    temp_30d_avg_c:     avgT,
    n_days:             precips.length,
  }), { headers: CORS });
}

// ─── SYKE WSFS-ennuste ───────────────────────────────────────────────────────
// Hakee minkä tahansa WSFS-pisteen vedenkorkeusennusteen
// ?point=q6700800y  (Muonionjoki Muonio)
// ?point=l147221001y (Iisvesi, default)

async function handleSykeWsfs(params) {
  const point = params.get('point') || 'l147221001y';
  const url = `https://wwwi2.ymparisto.fi/i2/wsfs/${point}_w.json`;
  
  const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!r.ok) {
    return new Response(JSON.stringify({
      error: `WSFS HTTP ${r.status}`,
      point,
      url,
    }), { status: 502, headers: CORS });
  }
  
  const d = await r.json();
  return new Response(JSON.stringify({
    source: 'SYKE WSFS',
    point,
    ...d,
  }), { headers: CORS });
}

