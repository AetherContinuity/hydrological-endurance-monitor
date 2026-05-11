/**
 * aci-nve-proxy — Cloudflare Worker (extended v2)
 *
 * Handles all hydrological data sources for WEM and HEM:
 *
 * EXISTING (WEM):
 *   GET /?week=current   → NVE Magasinstatistikk (Norway reservoir fill)
 *   GET /?week=YYYY-Www  → NVE specific week
 *
 * NEW (HEM):
 *   GET /syke?paikka=200&suure=1&start=2024-01-01&end=2024-12-31
 *       → SYKE OData Hydrologiarajapinta (vedenkorkeus, virtaama, lumi)
 *   GET /syke/paikat
 *       → SYKE station list for Saimaa system
 *   GET /fmi?station=101756&param=temperature,precipitation&start=...&end=...
 *       → FMI WFS daily weather observations
 *
 * Deploy: wrangler deploy (name: aci-nve-proxy)
 * Replaces existing aci-nve-proxy — backward compatible.
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const NVE_BASE  = 'https://www.nve.no/api/hydrology/waterreservoir';
const SYKE_BASE = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/odata/Havainto';
const FMI_BASE  = 'https://opendata.fmi.fi/wfs';

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    try {
      // ── NEW: SYKE routes ──────────────────────────────────────
      if (url.pathname === '/syke' || url.pathname === '/syke/') {
        return await handleSyke(url.searchParams);
      }
      if (url.pathname === '/syke/paikat') {
        return await handleSykePaikat();
      }

      // ── NEW: FMI route ────────────────────────────────────────
      if (url.pathname === '/fmi' || url.pathname === '/fmi/') {
        return await handleFmi(url.searchParams);
      }

      // ── EXISTING: NVE route (root path) ──────────────────────
      return await handleNve(url.searchParams);

    } catch (e) {
      return jsonError(500, e.message);
    }
  }
};

// ─── NVE handler (unchanged from v1) ────────────────────────────

async function handleNve(params) {
  const week = params.get('week') || 'current';

  let nveUrl;
  if (week === 'current') {
    nveUrl = `${NVE_BASE}/currentweek`;
  } else {
    // week format: YYYY-Www  e.g. 2024-W12
    const [year, ww] = week.split('-W');
    nveUrl = `${NVE_BASE}/${year}/${ww}`;
  }

  const resp = await fetch(nveUrl, {
    headers: { 'Accept': 'application/json', 'User-Agent': 'ACI-WEM/2.0' }
  });

  if (!resp.ok) {
    return jsonError(resp.status, `NVE API error: ${resp.status}`);
  }

  const data = await resp.json();

  // WEM expects: { fillPct, week, year, source }
  const fillPct = data?.mediaFyllingsgrad ?? data?.fyllingsgrad ?? null;

  return new Response(JSON.stringify({
    source: 'nve',
    week: data?.uke ?? week,
    year: data?.aar ?? null,
    fillPct,
    raw: data,
  }), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── SYKE handler ────────────────────────────────────────────────

async function handleSyke(params) {
  const paikka = params.get('paikka') || '200';   // Lauritsala
  const suure  = params.get('suure')  || '1';     // 1=vedenkorkeus
  const start  = params.get('start')  || '2020-01-01';
  const end    = params.get('end')    || today();
  const top    = params.get('top')    || '10000';

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
  const rows = (data.value || []).map(r => ({
    date:  r.Aika?.slice(0, 10),
    value: r.Arvo,
  }));

  return new Response(JSON.stringify({
    source: 'syke', paikka, suure, n: rows.length, rows
  }), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── SYKE station list ───────────────────────────────────────────

async function handleSykePaikat() {
  const filter = `substringof('Saimaa',Nimi) or substringof('Lauritsala',Nimi) or substringof('Virmasvesi',Nimi) or substringof('Puumala',Nimi)`;
  const url = `https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/odata/Paikka?$format=json&$top=50&$filter=${encodeURIComponent(filter)}`;
  const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const data = await resp.json();
  return new Response(JSON.stringify(data), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── FMI handler ────────────────────────────────────────────────

async function handleFmi(params) {
  const station = params.get('station') || '101756';  // Lappeenranta Lepola
  const param   = params.get('param')   || 'temperature,precipitation';
  const start   = params.get('start')   || '2020-01-01';
  const end     = params.get('end')     || today();

  const fmiUrl = `${FMI_BASE}?service=WFS&version=2.0.0&request=getFeature` +
    `&storedquery_id=fmi::observations::weather::daily::simple` +
    `&fmisid=${station}` +
    `&parameters=${param}` +
    `&starttime=${start}T00:00:00Z` +
    `&endtime=${end}T23:59:59Z`;

  const resp = await fetch(fmiUrl);
  if (!resp.ok) {
    return jsonError(resp.status, `FMI API error: ${resp.status}`);
  }

  const xml  = await resp.text();
  const rows = parseFmiXml(xml);

  return new Response(JSON.stringify({
    source: 'fmi', station, param, n: rows.length, rows
  }), {
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}

// ─── FMI XML parser ──────────────────────────────────────────────

function parseFmiXml(xml) {
  const rows   = [];
  const times  = [...xml.matchAll(/<BsWfs:Time>([^<]+)<\/BsWfs:Time>/g)].map(m => m[1].slice(0,10));
  const pnames = [...xml.matchAll(/<BsWfs:ParameterName>([^<]+)<\/BsWfs:ParameterName>/g)].map(m => m[1]);
  const values = [...xml.matchAll(/<BsWfs:ParameterValue>([^<]+)<\/BsWfs:ParameterValue>/g)].map(m => parseFloat(m[1]));
  for (let i = 0; i < times.length; i++) {
    rows.push({ date: times[i], param: pnames[i], value: isNaN(values[i]) ? null : values[i] });
  }
  return rows;
}

// ─── Helpers ────────────────────────────────────────────────────

function today() {
  return new Date().toISOString().slice(0, 10);
}

function jsonError(status, message) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' }
  });
}
