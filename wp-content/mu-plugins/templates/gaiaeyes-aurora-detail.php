<?php
if (!defined('ABSPATH')) {
    exit;
}

$context_candidates = [];
if (isset($args) && is_array($args)) {
    $context_candidates[] = $args;
}
if (isset($template_args) && is_array($template_args)) {
    $context_candidates[] = $template_args;
}
if (isset($gaia_aurora_context) && is_array($gaia_aurora_context)) {
    $context_candidates[] = $gaia_aurora_context;
}

$defaults = [
    'initial_hemisphere' => 'north',
    'refresh_interval'   => 300,
    'rest_base'          => '/wp-json/gaia/v1/aurora',
];

$merged = [];
foreach ($context_candidates as $candidate) {
    $merged = array_merge($merged, $candidate);
}

$config = wp_parse_args($merged, $defaults);
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
  .ga-aurora__svgwrap{background:#101623;border-radius:14px;padding:18px;border:1px solid rgba(255,255,255,.06);display:flex;flex-direction:column;gap:14px}
  .ga-aurora__svg{width:100%;height:auto}
  .ga-aurora__metrics{display:grid;gap:10px;font-size:.85rem;color:#d7e7ff}
  .ga-aurora__metrics span{display:block}
  .ga-aurora__metric{font-size:1.05rem;font-weight:600;color:#9bf2c7}
  .ga-aurora__note{margin:0;font-size:.75rem;opacity:.65}
  .ga-aurora__forecast{background:#121a28;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:18px;display:grid;gap:16px}
  .ga-aurora__forecast figure{margin:0}
  .ga-aurora__forecast img{width:100%;height:auto;border-radius:10px;border:1px solid rgba(255,255,255,.08)}
  .ga-aurora__forecast-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
  .ga-aurora__disclaimer{margin:0;font-size:.82rem;opacity:.75}
  .ga-aurora__kp{background:#121a28;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:18px;font-size:.9rem;line-height:1.55}
  .ga-aurora__kp ul{margin:0 0 12px 20px;padding:0}
  .ga-aurora__footer{margin-top:18px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:.82rem;opacity:.8}
  .ga-aurora__link{color:#78caff}
  .ga-aurora__alert{background:#332126;border:1px solid rgba(255,109,109,.35);color:#ffbaba;border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:.85rem}
  .ga-aurora__diagnostics{font-size:.75rem;opacity:.65}
  @media(max-width:720px){
    .ga-aurora__header{flex-direction:column;align-items:flex-start}
    .ga-aurora__controls{flex-direction:column;align-items:flex-start}
    .ga-aurora__tabs{width:100%}
    .ga-aurora__hemis{width:100%}
    .ga-aurora__hemi,.ga-aurora__tab{flex:1;text-align:center}
  }
  @media(prefers-reduced-motion:reduce){
    .ga-aurora__tab,.ga-aurora__hemi{transition:none}
  }
</style>

<script>
(function(){
  const root = document.currentScript.previousElementSibling.previousElementSibling;
  if (!root || !root.classList.contains('ga-aurora')) {
    return;
  }

  const restBase = root.getAttribute('data-rest-base');
  const refreshInterval = parseInt(root.getAttribute('data-refresh'), 10) * 1000;
  const initialHemisphere = root.getAttribute('data-initial');
  const tabs = root.querySelectorAll('.ga-aurora__tab');
  const panels = root.querySelectorAll('.ga-aurora__panel');
  const hemis = root.querySelectorAll('.ga-aurora__hemi');
  const kpBadge = root.querySelector('[data-role="kp-badge"]');
  const timestamp = root.querySelector('[data-role="timestamp"]');
  const diagnostics = root.querySelector('[data-role="diagnostics"]');
  const fallback = root.querySelector('[data-role="fallback"]');
  const hemiLabel = root.querySelector('[data-role="hemisphere-label"]');
  const ovationImg = root.querySelector('[data-role="ovation-image"]');
  const viewlinePath = root.querySelector('[data-role="viewline"]');
  const metricMin = root.querySelector('[data-role="metric-min"]');
  const metricMedian = root.querySelector('[data-role="metric-median"]');
  const metricProb = root.querySelector('[data-role="metric-prob"]');
  const tonightImg = root.querySelector('[data-role="forecast-tonight"]');
  const tonightTime = root.querySelector('[data-role="forecast-tonight-time"]');
  const tomorrowImg = root.querySelector('[data-role="forecast-tomorrow"]');
  const tomorrowTime = root.querySelector('[data-role="forecast-tomorrow-time"]');

  let activeTab = 'nowcast';
  let activeHemisphere = initialHemisphere || 'north';
  let timer = null;

  function setActiveTab(target) {
    activeTab = target;
    tabs.forEach((tab) => {
      const isActive = tab.getAttribute('data-target') === target;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    panels.forEach((panel) => {
      const isActive = panel.getAttribute('data-panel') === target;
      panel.classList.toggle('is-active', isActive);
      panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
    });
  }

  function setActiveHemisphere(target) {
    activeHemisphere = target;
    hemis.forEach((hemi) => {
      const match = hemi.getAttribute('data-hemi') === target;
      hemi.classList.toggle('is-active', match);
      hemi.setAttribute('aria-checked', match ? 'true' : 'false');
    });
    fetchNowcast();
  }

  function kpClass(kp) {
    if (kp >= 9) return 'ga-aurora__badge--extreme';
    if (kp >= 8) return 'ga-aurora__badge--severe';
    if (kp >= 7) return 'ga-aurora__badge--strong';
    if (kp >= 6) return 'ga-aurora__badge--moderate';
    if (kp >= 5) return 'ga-aurora__badge--minor';
    if (kp >= 4) return 'ga-aurora__badge--active';
    if (kp >= 3) return 'ga-aurora__badge--unsettled';
    if (kp >= 0) return 'ga-aurora__badge--quiet';
    return 'ga-aurora__badge--unknown';
  }

  function renderDiagnostics(payload) {
    const diag = payload && payload.diagnostics ? payload.diagnostics : null;
    if (!diag) {
      diagnostics.textContent = 'Diagnostics unavailable.';
      fallback.hidden = true;
      return;
    }
    const parts = [];
    if (diag.fetch_ms) {
      parts.push(`Fetch ${diag.fetch_ms}ms`);
    }
    if (diag.cache_hit) {
      parts.push('cache hit');
    }
    if (diag.fallback) {
      parts.push('fallback payload');
    }
    if (diag.fetched_at) {
      parts.push(`fetched ${diag.fetched_at}`);
    }
    diagnostics.textContent = parts.join(' · ') || 'Diagnostics available.';
    if (diag.fallback) {
      fallback.hidden = false;
    } else {
      fallback.hidden = true;
    }
  }

  function renderMetrics(payload) {
    const metrics = payload && payload.metrics ? payload.metrics : null;
    metricMin.textContent = metrics && metrics.min_lat !== undefined ? `${metrics.min_lat.toFixed(1)}°` : '—';
    metricMedian.textContent = metrics && metrics.median_lat !== undefined ? `${metrics.median_lat.toFixed(1)}°` : '—';
    metricProb.textContent = metrics && metrics.mean_prob !== undefined ? `${(metrics.mean_prob * 100).toFixed(0)}%` : '—';
  }

  function renderViewline(payload) {
    if (!payload || !Array.isArray(payload.viewline_coords)) {
      viewlinePath.setAttribute('d', '');
      return;
    }
    const coords = payload.viewline_coords;
    const radius = 130;
    const centerX = 160;
    const centerY = 160;
    const points = coords.map(({ lon, lat }) => {
      const theta = (lon * Math.PI) / 180;
      const phi = (lat * Math.PI) / 180;
      const x = centerX + radius * Math.sin(theta) * Math.cos(phi);
      const y = centerY - radius * Math.sin(phi);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    viewlinePath.setAttribute('d', points.length ? `M${points.join(' L')}` : '');
    if (payload.kp !== undefined) {
      const kpVal = Number(payload.kp);
      const className = kpClass(kpVal);
      kpBadge.className = `ga-aurora__badge ${className}`;
      kpBadge.textContent = `Kp ${kpVal.toFixed(1)}`;
    } else {
      kpBadge.className = 'ga-aurora__badge ga-aurora__badge--unknown';
      kpBadge.textContent = 'Kp —';
    }
    if (payload.kp_obs_time) {
      timestamp.textContent = `Updated ${new Date(payload.kp_obs_time).toLocaleString()}`;
    } else if (payload.ts) {
      timestamp.textContent = `Updated ${new Date(payload.ts).toLocaleString()}`;
    } else {
      timestamp.textContent = 'Updated —';
    }
    renderMetrics(payload);
    hemiLabel.textContent = payload.hemisphere === 'south' ? 'Southern hemisphere' : 'Northern hemisphere';
  }

  function updateImage(payload) {
    if (!payload || !payload.images) {
      ovationImg.src = '';
      return;
    }
    const key = payload.hemisphere === 'south' ? 'south' : 'north';
    const url = payload.images[`ovation_${key}`] || payload.images.ovation_latest;
    if (url) {
      const stamp = Math.floor(Date.now() / refreshInterval) * refreshInterval;
      ovationImg.src = `${url}?t=${stamp}`;
    }
  }

  function fetchForecast(kind) {
    fetch(`${restBase}viewline/${kind}`)
      .then((res) => res.json())
      .then((data) => {
        const targetImg = kind === 'tonight' ? tonightImg : tomorrowImg;
        const targetTime = kind === 'tonight' ? tonightTime : tomorrowTime;
        if (data && data.url) {
          targetImg.src = `${data.url}?t=${Date.now()}`;
        }
        targetTime.textContent = data && data.fetched_at ? new Date(data.fetched_at).toLocaleString() : '—';
      })
      .catch(() => {
        if (kind === 'tonight') {
          tonightTime.textContent = 'Unavailable';
        } else {
          tomorrowTime.textContent = 'Unavailable';
        }
      });
  }

  function fetchNowcast() {
    fetch(`${restBase}nowcast?hemi=${activeHemisphere}`)
      .then((res) => res.json())
      .then((payload) => {
        renderDiagnostics(payload);
        renderViewline(payload);
        updateImage(payload);
      })
      .catch(() => {
        diagnostics.textContent = 'Failed to load nowcast data.';
        fallback.hidden = false;
      });
  }

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => setActiveTab(tab.getAttribute('data-target')));
  });

  hemis.forEach((hemi) => {
    hemi.addEventListener('click', () => setActiveHemisphere(hemi.getAttribute('data-hemi')));
  });

  setActiveTab(activeTab);
  setActiveHemisphere(activeHemisphere);
  fetchForecast('tonight');
  fetchForecast('tomorrow');

  if (refreshInterval >= 60000) {
    timer = setInterval(fetchNowcast, refreshInterval);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    } else if (!timer && refreshInterval >= 60000) {
      fetchNowcast();
      timer = setInterval(fetchNowcast, refreshInterval);
    }
  });
})();
</script>
