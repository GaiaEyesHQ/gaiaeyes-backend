<?php
if (!defined('ABSPATH')) {
    exit;
}

$defaults = [
    'initial_hemisphere' => 'north',
    'refresh_interval'   => 300,
    'rest_base'          => '/wp-json/gaia/v1/aurora',
];

$args = isset($args) && is_array($args) ? $args : [];
$config = wp_parse_args($args, $defaults);
$initial = strtolower($config['initial_hemisphere']) === 'south' ? 'south' : 'north';
$refresh = (int) $config['refresh_interval'];
if ($refresh < 60) {
    $refresh = 300;
}
$rest_base = trailingslashit($config['rest_base']);
$section_id = 'ga-aurora-' . wp_unique_id();
?>
<section id="<?php echo esc_attr($section_id); ?>" class="ga-aurora" data-rest-base="<?php echo esc_attr($rest_base); ?>" data-refresh="<?php echo esc_attr($refresh); ?>" data-initial="<?php echo esc_attr($initial); ?>">
  <header class="ga-aurora__header">
    <div>
      <h2 class="ga-aurora__title">Aurora Tracker</h2>
      <p class="ga-aurora__subtitle">Live OVATION nowcast with experimental viewline overlays</p>
    </div>
    <div class="ga-aurora__status">
      <span class="ga-aurora__badge" data-role="kp-badge">Kp —</span>
      <span class="ga-aurora__timestamp" data-role="timestamp">Updated —</span>
    </div>
  </header>

  <div class="ga-aurora__controls">
    <div class="ga-aurora__tabs" role="tablist">
      <button class="ga-aurora__tab is-active" role="tab" data-target="nowcast" aria-selected="true">Nowcast (Live)</button>
      <button class="ga-aurora__tab" role="tab" data-target="tonight" aria-selected="false">Tonight (Forecast)</button>
      <button class="ga-aurora__tab" role="tab" data-target="tomorrow" aria-selected="false">Tomorrow (Forecast)</button>
      <button class="ga-aurora__tab" role="tab" data-target="kp" aria-selected="false">Kp Lines (Live)</button>
    </div>
    <div class="ga-aurora__hemis" role="radiogroup" aria-label="Hemisphere selector">
      <button class="ga-aurora__hemi is-active" data-hemi="north" role="radio" aria-checked="true">Northern hemisphere</button>
      <button class="ga-aurora__hemi" data-hemi="south" role="radio" aria-checked="false">Southern hemisphere</button>
    </div>
  </div>

  <div class="ga-aurora__panels">
    <section class="ga-aurora__panel is-active" data-panel="nowcast" role="tabpanel">
      <div class="ga-aurora__alert" data-role="fallback" hidden>Showing cached map (latest live fetch unavailable).</div>
      <div class="ga-aurora__grid">
        <figure class="ga-aurora__figure">
          <img data-role="ovation-image" src="" alt="Aurora nowcast imagery" loading="lazy" />
          <figcaption data-role="hemisphere-label">—</figcaption>
        </figure>
        <div class="ga-aurora__svgwrap">
          <svg viewBox="0 0 320 320" role="img" aria-label="Derived 10% probability viewline" class="ga-aurora__svg">
            <defs>
              <radialGradient id="gaAuroraGlow" cx="50%" cy="50%" r="60%">
                <stop offset="0%" stop-color="rgba(41,64,90,0.9)" />
                <stop offset="100%" stop-color="rgba(16,22,32,0.95)" />
              </radialGradient>
            </defs>
            <rect x="0" y="0" width="320" height="320" fill="url(#gaAuroraGlow)" rx="18" />
            <circle cx="160" cy="160" r="130" fill="rgba(0,0,0,0.35)" stroke="rgba(255,255,255,0.05)" stroke-width="1" />
            <path data-role="viewline" d="" fill="none" stroke="rgba(92,220,160,0.9)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />
            <g class="ga-aurora__latlines">
              <path d="M20 160 H300" stroke="rgba(255,255,255,0.08)" stroke-dasharray="4 6" />
              <path d="M20 100 H300" stroke="rgba(255,255,255,0.05)" stroke-dasharray="3 7" />
              <path d="M20 220 H300" stroke="rgba(255,255,255,0.05)" stroke-dasharray="3 7" />
            </g>
          </svg>
          <div class="ga-aurora__metrics">
            <div><span class="ga-aurora__metric" data-role="metric-min">—</span><span>southernmost latitude</span></div>
            <div><span class="ga-aurora__metric" data-role="metric-median">—</span><span>median viewline latitude</span></div>
            <div><span class="ga-aurora__metric" data-role="metric-prob">—</span><span>mean probability along line</span></div>
          </div>
          <p class="ga-aurora__note">Data © NOAA SWPC / OVATION. Viewline derived from 10% probability contour and refreshed every five minutes.</p>
        </div>
      </div>
    </section>

    <section class="ga-aurora__panel" data-panel="tonight" role="tabpanel" aria-hidden="true">
      <article class="ga-aurora__forecast">
        <div class="ga-aurora__forecast-head">
          <h3>Experimental viewline – Tonight</h3>
          <span class="ga-aurora__badge ga-aurora__badge--experimental">Experimental</span>
        </div>
        <figure>
          <img data-role="forecast-tonight" src="" alt="NOAA experimental aurora viewline forecast for tonight" loading="lazy" />
          <figcaption>Last fetched <span data-role="forecast-tonight-time">—</span></figcaption>
        </figure>
        <p class="ga-aurora__disclaimer">The experimental viewline is a research preview from NOAA SWPC. Timing differences of several hours are possible.</p>
      </article>
    </section>

    <section class="ga-aurora__panel" data-panel="tomorrow" role="tabpanel" aria-hidden="true">
      <article class="ga-aurora__forecast">
        <div class="ga-aurora__forecast-head">
          <h3>Experimental viewline – Tomorrow</h3>
          <span class="ga-aurora__badge ga-aurora__badge--experimental">Experimental</span>
        </div>
        <figure>
          <img data-role="forecast-tomorrow" src="" alt="NOAA experimental aurora viewline forecast for tomorrow" loading="lazy" />
          <figcaption>Last fetched <span data-role="forecast-tomorrow-time">—</span></figcaption>
        </figure>
        <p class="ga-aurora__disclaimer">Use alongside alerts: tomorrow’s panel updates hourly and may lag the latest SWPC guidance.</p>
      </article>
    </section>

    <section class="ga-aurora__panel" data-panel="kp" role="tabpanel" aria-hidden="true">
      <article class="ga-aurora__kp">
        <h3>Live Kp interpretation</h3>
        <ul>
          <li><strong>Quiet (Kp 0–2):</strong> Aurora mainly poleward of 65° magnetic latitude.</li>
          <li><strong>Unsettled to Active (Kp 3–4):</strong> Watch high-lat windows; mid-lat glimpses possible under clear skies.</li>
          <li><strong>Storm levels (Kp ≥5):</strong> Expect deeper south visibility; allow 20–40 min for dark adaptation.</li>
        </ul>
        <p>The viewline overlay mirrors the live nowcast. As Kp climbs, the curve slides equatorward; the SVG uses the same coordinates so the UI and JSON payload stay aligned for iOS.</p>
      </article>
    </section>
  </div>

  <footer class="ga-aurora__footer">
    <div>Need push alerts? <a class="ga-aurora__link" href="/aurora/#alerts">Get Aurora Alerts →</a></div>
    <div class="ga-aurora__diagnostics" data-role="diagnostics">Diagnostics pending…</div>
  </footer>
</section>

<style>
  .ga-aurora{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:16px;padding:18px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
  .ga-aurora__header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px}
  .ga-aurora__title{margin:0;font-size:1.35rem}
  .ga-aurora__subtitle{margin:2px 0 0;font-size:.92rem;opacity:.85}
  .ga-aurora__status{display:flex;gap:8px;align-items:center;font-size:.85rem}
  .ga-aurora__badge{display:inline-flex;align-items:center;gap:6px;background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:999px;padding:4px 10px;font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.03em}
  .ga-aurora__badge--experimental{background:#2a1f33;border-color:#523d78;color:#d4b8ff}
  .ga-aurora__badge--quiet{background:#1b2a22;border-color:#265d41;color:#aef2c0}
  .ga-aurora__badge--unsettled{background:#243226;border-color:#427d44;color:#c8f59b}
  .ga-aurora__badge--active{background:#2e2b20;border-color:#8f7a33;color:#ffe48b}
  .ga-aurora__badge--minor{background:#34241f;border-color:#b45d42;color:#ffbc9a}
  .ga-aurora__badge--moderate{background:#3b2226;border-color:#c74665;color:#ff9cb5}
  .ga-aurora__badge--strong{background:#3d2030;border-color:#d03c8d;color:#ff9ce0}
  .ga-aurora__badge--severe{background:#411d2c;border-color:#f24c7f;color:#ffc2d7}
  .ga-aurora__badge--extreme{background:#421823;border-color:#ff4b6d;color:#ffc2c2}
  .ga-aurora__badge--unknown{background:#1b2233;border-color:#344a72;color:#cfe3ff}
  .ga-aurora__timestamp{opacity:.8}
  .ga-aurora__controls{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
  .ga-aurora__tabs{display:flex;gap:6px;flex-wrap:wrap}
  .ga-aurora__tab{background:#131a27;color:inherit;border:1px solid rgba(255,255,255,.1);border-radius:999px;padding:6px 14px;font-size:.82rem;cursor:pointer;transition:background .2s ease, border-color .2s ease}
  .ga-aurora__tab.is-active{background:#1e2a3f;border-color:#5ba6ff;color:#d5e8ff}
  .ga-aurora__hemi{background:#161e2b;border:1px solid rgba(255,255,255,.12);color:inherit;border-radius:999px;padding:6px 14px;font-size:.82rem;cursor:pointer}
  .ga-aurora__hemi.is-active{background:#24354f;border-color:#66d9a3;color:#aaf5c8}
  .ga-aurora__panels{position:relative}
  .ga-aurora__panel{display:none}
  .ga-aurora__panel.is-active{display:block}
  .ga-aurora__grid{display:grid;gap:18px}
  @media(min-width:900px){.ga-aurora__grid{grid-template-columns:repeat(2,1fr)}}
  .ga-aurora__figure{margin:0;background:#121822;border-radius:14px;padding:14px;border:1px solid rgba(255,255,255,.06)}
  .ga-aurora__figure img{width:100%;height:auto;border-radius:10px;border:1px solid rgba(255,255,255,.08)}
  .ga-aurora__figure figcaption{margin-top:6px;font-size:.85rem;opacity:.85}
  .ga-aurora__svgwrap{background:#121822;border-radius:14px;padding:16px;border:1px solid rgba(255,255,255,.06);display:flex;flex-direction:column;gap:12px}
  .ga-aurora__svg{width:100%;height:auto;border-radius:12px}
  .ga-aurora__metrics{display:grid;gap:6px;font-size:.85rem}
  @media(min-width:520px){.ga-aurora__metrics{grid-template-columns:repeat(3,1fr)}}
  .ga-aurora__metric{display:block;font-size:1.1rem;font-weight:600;color:#aef2c0}
  .ga-aurora__note{margin:0;font-size:.75rem;opacity:.75}
  .ga-aurora__forecast{background:#121822;border-radius:14px;padding:16px;border:1px solid rgba(255,255,255,.06);display:flex;flex-direction:column;gap:12px}
  .ga-aurora__forecast img{width:100%;height:auto;border-radius:12px;border:1px solid rgba(255,255,255,.08)}
  .ga-aurora__forecast-head{display:flex;justify-content:space-between;align-items:center;gap:12px}
  .ga-aurora__disclaimer{margin:0;font-size:.85rem;opacity:.8}
  .ga-aurora__kp{background:#121822;border-radius:14px;padding:18px;border:1px solid rgba(255,255,255,.06);font-size:.9rem;line-height:1.45}
  .ga-aurora__alert{background:#3a2a2a;border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:8px 12px;font-size:.85rem;margin-bottom:10px}
  .ga-aurora__footer{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:18px;font-size:.85rem}
  .ga-aurora__link{color:#aef2c0;text-decoration:none;border-bottom:1px dotted rgba(174,242,192,.6)}
  .ga-aurora__link:hover{text-decoration:none;border-bottom-color:#aef2c0}
  .ga-aurora__diagnostics{opacity:.75;font-family:monospace;white-space:pre-wrap}
  .ga-aurora__tab:focus-visible,.ga-aurora__hemi:focus-visible{outline:2px solid #66d9a3;outline-offset:2px}
  .ga-aurora__svgwrap.fade{animation:gaAuroraFade .7s ease}
  @keyframes gaAuroraFade{from{opacity:.35}to{opacity:1}}
</style>

<script>
(() => {
  const root = document.getElementById('<?php echo esc_js($section_id); ?>');
  if (!root) return;
  const state = {
    hemisphere: root.getAttribute('data-initial') === 'south' ? 'south' : 'north',
    refreshSeconds: parseInt(root.getAttribute('data-refresh'), 10) || 300,
    timer: null,
    reduceMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    lastDiagnostics: null,
  };
  const restBase = root.getAttribute('data-rest-base') || '/wp-json/gaia/v1/aurora/';
  const endpoints = {
    nowcast: (hemi) => restBase.replace(/\/$/, '') + '/nowcast?hemi=' + encodeURIComponent(hemi || 'north'),
    tonight: restBase.replace(/\/$/, '') + '/viewline/tonight',
    tomorrow: restBase.replace(/\/$/, '') + '/viewline/tomorrow',
    diagnostics: restBase.replace(/\/$/, '') + '/diagnostics',
  };

  const els = {
    tabs: root.querySelectorAll('.ga-aurora__tab'),
    panels: root.querySelectorAll('.ga-aurora__panel'),
    hemis: root.querySelectorAll('.ga-aurora__hemi'),
    kpBadge: root.querySelector('[data-role="kp-badge"]'),
    timestamp: root.querySelector('[data-role="timestamp"]'),
    image: root.querySelector('[data-role="ovation-image"]'),
    hemisphereLabel: root.querySelector('[data-role="hemisphere-label"]'),
    fallback: root.querySelector('[data-role="fallback"]'),
    path: root.querySelector('[data-role="viewline"]'),
    metricMin: root.querySelector('[data-role="metric-min"]'),
    metricMedian: root.querySelector('[data-role="metric-median"]'),
    metricProb: root.querySelector('[data-role="metric-prob"]'),
    svgWrap: root.querySelector('.ga-aurora__svgwrap'),
    diag: root.querySelector('[data-role="diagnostics"]'),
    forecastTonightImg: root.querySelector('[data-role="forecast-tonight"]'),
    forecastTonightTime: root.querySelector('[data-role="forecast-tonight-time"]'),
    forecastTomorrowImg: root.querySelector('[data-role="forecast-tomorrow"]'),
    forecastTomorrowTime: root.querySelector('[data-role="forecast-tomorrow-time"]'),
  };

  const kpClass = (bucket) => {
    switch(bucket){
      case 'quiet': return 'ga-aurora__badge--quiet';
      case 'unsettled': return 'ga-aurora__badge--unsettled';
      case 'active': return 'ga-aurora__badge--active';
      case 'minor': return 'ga-aurora__badge--minor';
      case 'moderate': return 'ga-aurora__badge--moderate';
      case 'strong': return 'ga-aurora__badge--strong';
      case 'severe': return 'ga-aurora__badge--severe';
      case 'extreme': return 'ga-aurora__badge--extreme';
      default: return 'ga-aurora__badge--unknown';
    }
  };

  const setTab = (target) => {
    els.tabs.forEach(btn => {
      const active = btn.getAttribute('data-target') === target;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    els.panels.forEach(panel => {
      const active = panel.getAttribute('data-panel') === target;
      panel.classList.toggle('is-active', active);
      panel.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
  };

  els.tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      setTab(btn.getAttribute('data-target'));
    });
  });

  els.hemis.forEach(btn => {
    btn.addEventListener('click', () => {
      const hemi = btn.getAttribute('data-hemi');
      if (hemi === state.hemisphere) return;
      state.hemisphere = hemi;
      els.hemis.forEach(h => {
        const active = h.getAttribute('data-hemi') === hemi;
        h.classList.toggle('is-active', active);
        h.setAttribute('aria-checked', active ? 'true' : 'false');
      });
      fetchNowcast();
    });
  });

  const formatTs = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      if (!Number.isFinite(d.getTime())) return ts;
      return d.toLocaleString(undefined, {hour:'2-digit', minute:'2-digit', second:'2-digit', timeZoneName:'short'});
    } catch (err) {
      return ts;
    }
  };

  const buildPath = (coords) => {
    if (!coords || !coords.length) return '';
    const width = 320;
    const height = 320;
    const path = [];
    coords.forEach((point, idx) => {
      const lon = Number(point.lon);
      const lat = Number(point.lat);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
        return;
      }
      const x = ((lon + 180) / 360) * width;
      const y = height - ((lat + 90) / 180) * height;
      path.push((idx ? 'L' : 'M') + x.toFixed(2) + ' ' + y.toFixed(2));
    });
    return path.join(' ');
  };

  const updateMetrics = (metrics) => {
    const formatLat = (value) => {
      const num = Number(value);
      return Number.isFinite(num) ? num.toFixed(1) + '°' : '—';
    };
    const formatProb = (value) => {
      const num = Number(value);
      return Number.isFinite(num) ? num.toFixed(1) + '%' : '—';
    };
    if (!metrics) {
      els.metricMin.textContent = '—';
      els.metricMedian.textContent = '—';
      els.metricProb.textContent = '—';
      return;
    }
    els.metricMin.textContent = formatLat(metrics.min_lat);
    els.metricMedian.textContent = formatLat(metrics.median_lat);
    els.metricProb.textContent = formatProb(metrics.mean_prob_line);
  };

  const updateNowcast = (payload) => {
    if (!payload) return;
    const badge = els.kpBadge;
    badge.className = 'ga-aurora__badge ' + kpClass(payload.kp_bucket);
    badge.textContent = 'Kp ' + (payload.kp !== null && payload.kp !== undefined ? payload.kp : '—');
    els.timestamp.textContent = 'Updated ' + formatTs(payload.ts);
    els.hemisphereLabel.textContent = payload.hemisphere === 'south' ? 'Southern hemisphere' : 'Northern hemisphere';
    const diagnostics = payload.diagnostics || {};
    if (diagnostics.fallback) {
      els.fallback.hidden = false;
    } else {
      els.fallback.hidden = true;
    }
    const imgUrl = (payload.images && payload.images.ovation_latest) ? payload.images.ovation_latest : '';
    if (imgUrl) {
      const bust = Math.floor(Date.now() / (state.refreshSeconds * 1000));
      els.image.src = imgUrl + '?t=' + bust;
    }
    const coords = payload.viewline_coords || [];
    els.path.setAttribute('d', buildPath(coords));
    if (!state.reduceMotion) {
      els.svgWrap.classList.remove('fade');
      void els.svgWrap.offsetWidth;
      els.svgWrap.classList.add('fade');
    }
    updateMetrics(payload.metrics);
    state.lastDiagnostics = diagnostics;
    refreshDiagnostics();
  };

  const fetchJson = (url) => fetch(url, {cache: 'no-store'}).then(r => {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });

  const fetchNowcast = () => {
    fetchJson(endpoints.nowcast(state.hemisphere))
      .then(updateNowcast)
      .catch(() => {
        els.fallback.hidden = false;
      });
  };

  const updateForecast = (label, data) => {
    if (!data) return;
    const bust = Math.floor(Date.now() / 3600000);
    if (label === 'tonight') {
      if (data.url) els.forecastTonightImg.src = data.url + '?t=' + bust;
      els.forecastTonightTime.textContent = formatTs(data.fetched_at);
    } else {
      if (data.url) els.forecastTomorrowImg.src = data.url + '?t=' + bust;
      els.forecastTomorrowTime.textContent = formatTs(data.fetched_at);
    }
  };

  const refreshDiagnostics = () => {
    const diagState = state.lastDiagnostics || {};
    const fallback = diagState.fallback ? 'fallback:true' : 'fallback:false';
    const duration = diagState.duration_ms ? 'duration_ms:' + diagState.duration_ms : '';
    const cache = diagState.cache_updated !== undefined ? 'cache_updated:' + (diagState.cache_updated ? 'true' : 'false') : '';
    const trace = Array.isArray(diagState.trace) ? diagState.trace.slice(-2).join(' | ') : '';
    els.diag.textContent = ['hemi:' + state.hemisphere, fallback, cache, duration, trace].filter(Boolean).join('  ');
  };

  const pollNowcast = () => {
    if (state.timer) window.clearInterval(state.timer);
    state.timer = window.setInterval(fetchNowcast, state.refreshSeconds * 1000);
  };

  const bootstrap = () => {
    fetchNowcast();
    pollNowcast();
    fetchJson(endpoints.tonight).then(data => updateForecast('tonight', data)).catch(() => {});
    fetchJson(endpoints.tomorrow).then(data => updateForecast('tomorrow', data)).catch(() => {});
    fetchJson(endpoints.diagnostics).then(diag => {
      if (diag && diag.aurora) {
        state.lastDiagnostics = state.lastDiagnostics || {};
        state.lastDiagnostics.cache_updated = diag.aurora.cache_updated;
        state.lastDiagnostics.trace = diag.aurora.trace || state.lastDiagnostics.trace;
        refreshDiagnostics();
      }
    }).catch(() => {});
  };

  bootstrap();
})();
</script>
