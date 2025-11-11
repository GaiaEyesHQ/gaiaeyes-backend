<?php
if (!defined('ABSPATH')) {
    exit;
}

$template = WP_CONTENT_DIR . '/mu-plugins/templates/gaiaeyes-aurora-detail.php';

if (file_exists($template)) {
    $template_args = isset($args) && is_array($args) ? $args : [];
    include $template;
    return;
}
?>

<div id="gaia-aurora" class="gaia-aurora">
  <div class="gaia-aurora__toolbar">
    <div class="gaia-aurora__tabs">
      <button type="button" class="gaia-btn gaia-tab is-active" data-tab="nowcast">Nowcast (Live)</button>
      <button type="button" class="gaia-btn gaia-tab" data-tab="tonight">Tonight</button>
      <button type="button" class="gaia-btn gaia-tab" data-tab="tomorrow">Tomorrow</button>
      <button type="button" class="gaia-btn gaia-tab" data-tab="kplines" data-role="kp-lines-toggle" aria-selected="false" aria-pressed="false">KP Lines</button>
    </div>
    <div class="gaia-aurora__hemi">
      <label>Hemisphere</label>
      <select id="gaia-hemi">
        <option value="north">North</option>
        <option value="south">South</option>
      </select>
    </div>
  </div>

  <div class="gaia-aurora__stage">
    <img id="gaia-base-map" alt="Aurora base map" />
    <svg id="gaia-overlay" viewBox="0 0 320 320" role="img" aria-label="Aurora overlay">
      <defs>
        <filter id="glow"><feDropShadow dx="0" dy="0" stdDeviation="2" flood-opacity="0.45"/></filter>
      </defs>
      <g id="ga-polar-grid" opacity="0.25">
        <circle cx="160" cy="160" r="26"  stroke="white" stroke-opacity="0.12" fill="none" />
        <circle cx="160" cy="160" r="52"  stroke="white" stroke-opacity="0.10" fill="none" />
        <circle cx="160" cy="160" r="78"  stroke="white" stroke-opacity="0.10" fill="none" />
        <circle cx="160" cy="160" r="104" stroke="white" stroke-opacity="0.08" fill="none" />
        <circle cx="160" cy="160" r="130" stroke="white" stroke-opacity="0.06" fill="none" />
        <line x1="160" y1="30" x2="160" y2="290" stroke="white" stroke-opacity="0.10"/>
      </g>
      <path id="gaia-viewline" d="" fill="none" stroke="#ff6a3a" stroke-width="3" filter="url(#glow)" stroke-linejoin="round" stroke-linecap="round"></path>
    </svg>
    <div id="gaia-banner" class="gaia-aurora__banner is-hidden">Showing cached map (latest live fetch unavailable)</div>
  </div>

  <div class="gaia-aurora__legend">
    <span class="chip">Viewline (p=10%)</span>
    <span id="gaia-kp" class="chip">Kp: –</span>
    <span id="gaia-ts" class="chip">As of: –</span>
    <button id="gaia-push" class="gaia-btn gaia-right" hidden>Get Aurora Alerts</button>
  </div>
</div>

<style>
.gaia-aurora{--br:12px;--bd:#e1e5ec;--bg:#0e1116;--fg:#fafbff}
.gaia-aurora__toolbar{display:flex;gap:.5rem;align-items:center;margin-bottom:.5rem}
.gaia-aurora__tabs{display:flex;gap:.5rem}
.gaia-btn{padding:.45rem .75rem;border:1px solid var(--bd);border-radius:8px;background:#f7f9fc;cursor:pointer}
.gaia-tab.is-active{background:#e9f0ff;border-color:#a8b7ff}
.gaia-aurora__hemi{margin-left:auto;display:flex;gap:.5rem;align-items:center}
.gaia-aurora__stage{position:relative;max-width:920px;aspect-ratio:1;margin:auto}
#gaia-base-map{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;border:1px solid var(--bd);border-radius:var(--br);background:#000}
#gaia-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.gaia-aurora__banner{position:absolute;left:50%;transform:translateX(-50%);bottom:10px;background:rgba(10,12,18,.7);color:#fff;padding:.35rem .6rem;border-radius:999px;font-size:.85rem}
.is-hidden{display:none}
.gaia-aurora__legend{display:flex;gap:.5rem;align-items:center;margin-top:.5rem}
.chip{font-size:.8rem;background:#f2f5ff;border:1px solid var(--bd);border-radius:999px;padding:.2rem .5rem}
.gaia-right{margin-left:auto}
</style>

<script>
(() => {
  // Context defaults; allow PHP $args (if present) to override via data-* later if needed
  const ctx = {
    restBase: '<?php echo esc_js( isset($template_args['rest_base']) ? $template_args['rest_base'] : '/wp-json/gaia/v1/aurora' ); ?>',
    hemi:     '<?php echo esc_js( isset($template_args['initial_hemisphere']) ? $template_args['initial_hemisphere'] : 'north' ); ?>',
    baseMap: {
      north: '<?php echo esc_js( isset($template_args['base_map_url']['north']) ? $template_args['base_map_url']['north'] : home_url('/gaiaeyes-media/public/aurora/nowcast/northern-hemisphere.jpg') ); ?>',
      south: '<?php echo esc_js( isset($template_args['base_map_url']['south']) ? $template_args['base_map_url']['south'] : home_url('/gaiaeyes-media/public/aurora/nowcast/southern-hemisphere.jpg') ); ?>',
    },
    freshSeconds: 900 // 15 minutes window for "fresh"
  };

  const elBase = document.getElementById('gaia-base-map');
  const elSVG  = document.getElementById('gaia-overlay');
  const elPath = document.getElementById('gaia-viewline');
  const elHemi = document.getElementById('gaia-hemi');
  const elKp   = document.getElementById('gaia-kp');
  const elTs   = document.getElementById('gaia-ts');
  const elBanner = document.getElementById('gaia-banner');

  // Tabs (minimal – only Nowcast active visual; others placeholders for now)
  document.querySelectorAll('.gaia-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      if (target && target !== 'kplines') {
        document.querySelectorAll('.gaia-tab').forEach(b => {
          if (b.getAttribute('data-tab') === 'kplines') return;
          b.classList.remove('is-active');
        });
        btn.classList.add('is-active');
      }
    });
  });

  // Hemisphere selector
  elHemi.value = ctx.hemi;
  elHemi.addEventListener('change', () => setHemisphere(elHemi.value));

  // --- Projection constants (per hemisphere) ---
  const CX = 160, CY = 160;
  const R_SAFE = 129.5; // slightly smaller than the 130px rim to avoid stroke clipping
  // Tune central longitude to match your base images:
  const LON0_N = 0;     // north map center meridian (adjust ±10..20° if needed)
  const LON0_S = 0;     // south map center meridian (adjust if your south base is rotated)
  function centerLonFor(hemi) { return hemi === 'south' ? LON0_S : LON0_N; }

  function projOrthographic(lonDeg, latDeg, hemi) {
    const lon0 = centerLonFor(hemi);
    if (!Number.isFinite(lonDeg) || !Number.isFinite(latDeg)) return null;

    const λ = (lonDeg - lon0) * Math.PI / 180;
    const φ = latDeg * Math.PI / 180;
    const cosφ = Math.cos(φ);

    // Cull far side (prevents “rim spikes”); keep only the visible pole
    if (hemi === 'north' && latDeg < 0) return null;
    if (hemi === 'south' && latDeg > 0) return null;

    const x = R_SAFE * cosφ * Math.sin(λ);
    const y = (hemi === 'north'
      ? -R_SAFE * cosφ * Math.cos(λ)
      :  R_SAFE * cosφ * Math.cos(λ));

    const X = CX + x, Y = CY + y;
    if (!Number.isFinite(X) || !Number.isFinite(Y)) return null;
    return [X, Y];
  }

  function coordsToPath(coords, hemi) {
    const parts = [];
    for (const p of (coords || [])) {
      const lon = Number(p.lon), lat = Number(p.lat);
      const pt = projOrthographic(lon, lat, hemi);
      if (!pt) continue;
      parts.push(parts.length ? `L${pt[0].toFixed(2)},${pt[1].toFixed(2)}`
                              : `M${pt[0].toFixed(2)},${pt[1].toFixed(2)}`);
    }
    return parts.join(' ');
  }

  function setBanner(tsISO) {
    try {
      const ts = Date.parse(tsISO);
      if (!isNaN(ts) && (Date.now() - ts) / 1000 <= ctx.freshSeconds) {
        elBanner.classList.add('is-hidden');
      } else {
        elBanner.classList.remove('is-hidden');
      }
    } catch(e) {
      elBanner.classList.remove('is-hidden');
    }
  }

  async function loadNowcast(hemi) {
    const url = `${ctx.restBase}/nowcast?hemi=${encodeURIComponent(hemi)}`;
    const resp = await fetch(url, {cache:'no-store'});
    if (!resp.ok) throw new Error(`nowcast ${resp.status}`);
    const data = await resp.json();

    elKp.textContent = `Kp: ${typeof data.kp === 'number' ? data.kp.toFixed(1) : '–'}`;
    elTs.textContent = `As of: ${data.ts || '–'}`;
    setBanner(data.ts);

    const d = coordsToPath(data.viewline_coords || [], hemi);
    elPath.setAttribute('d', d);
  }

  async function setHemisphere(hemi) {
    ctx.hemi = hemi;
    updateBaseMap(hemi);
    try { await loadNowcast(hemi); } catch (e) { console.error(e); elBanner.classList.remove('is-hidden'); }
  }

  function updateBaseMap(hemi) {
    if (!elBase) return;
    elBase.src = (hemi === 'south') ? ctx.baseMap.south : ctx.baseMap.north;
  }

  // Initialize
  setHemisphere(ctx.hemi);

  const kpToggle = document.querySelector('[data-tab="kplines"], [data-role="kp-lines-toggle"]');
  if (kpToggle) {
    kpToggle.addEventListener('click', (e) => {
      e.preventDefault();
      const cur = elPath.style.display;
      elPath.style.display = (cur === 'none' ? 'inline' : 'none');
      kpToggle.classList.toggle('is-active', elPath.style.display !== 'none');
      kpToggle.setAttribute('aria-pressed', elPath.style.display !== 'none' ? 'true' : 'false');
      kpToggle.setAttribute('aria-selected', elPath.style.display !== 'none' ? 'true' : 'false');
    });
    kpToggle.setAttribute('aria-pressed', elPath.style.display !== 'none' ? 'true' : 'false');
    kpToggle.setAttribute('aria-selected', elPath.style.display !== 'none' ? 'true' : 'false');
    kpToggle.classList.toggle('is-active', elPath.style.display !== 'none');
  }
  elPath.style.display = 'inline';
})();
</script>
