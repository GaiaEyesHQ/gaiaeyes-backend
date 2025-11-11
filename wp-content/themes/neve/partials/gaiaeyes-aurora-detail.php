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
      <button type="button" class="gaia-btn gaia-tab" data-tab="kplines">KP Lines</button>
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
    <svg id="gaia-overlay" viewBox="0 0 1000 1000" role="img" aria-label="Aurora overlay">
      <defs>
        <filter id="glow"><feDropShadow dx="0" dy="0" stdDeviation="2" flood-opacity="0.45"/></filter>
      </defs>
      <g id="gaia-lat-grid" class="gaia-grid"></g>
      <path id="gaia-viewline" d="" fill="none" stroke="#ff6a3a" stroke-width="3" filter="url(#glow)"></path>
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
.gaia-grid line{stroke:#ffffff;stroke-opacity:.18;stroke-width:1}
.gaia-grid text{fill:#fff;font-size:11px;paint-order:stroke;stroke:#000;stroke-width:3;stroke-linejoin:round}
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
    // projection center longitude (tweak if landmasses don't align perfectly)
    lon0: 0,
    freshSeconds: 900 // 15 minutes window for "fresh"
  };

  const elBase = document.getElementById('gaia-base-map');
  const elSVG  = document.getElementById('gaia-overlay');
  const elPath = document.getElementById('gaia-viewline');
  const elGrid = document.getElementById('gaia-lat-grid');
  const elHemi = document.getElementById('gaia-hemi');
  const elKp   = document.getElementById('gaia-kp');
  const elTs   = document.getElementById('gaia-ts');
  const elBanner = document.getElementById('gaia-banner');

  // Tabs (minimal – only Nowcast active visual; others placeholders for now)
  document.querySelectorAll('.gaia-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.gaia-tab').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      // We keep single stage; KP Lines is a toggle; Tonight/Tomorrow are handled elsewhere as needed.
    });
  });

  // Hemisphere selector
  elHemi.value = ctx.hemi;
  elHemi.addEventListener('change', () => setHemisphere(elHemi.value));

  // Projection helpers
  const R = 480, CX = 500, CY = 500;
  function projOrthographic(lonDeg, latDeg, hemi) {
    const lon0 = ctx.lon0;
    const λ = (lonDeg - lon0) * Math.PI/180;
    const φ = latDeg * Math.PI/180;
    const cosφ = Math.cos(φ), sinφ = Math.sin(φ);
    if (hemi === 'north') {
      if (latDeg < 0) return null;
      const x = R * cosφ * Math.sin(λ);
      const y = -R * cosφ * Math.cos(λ);
      return [CX + x, CY + y];
    } else {
      if (latDeg > 0) return null;
      const x = R * cosφ * Math.sin(λ);
      const y =  R * cosφ * Math.cos(λ);
      return [CX + x, CY + y];
    }
  }

  function coordsToPath(coords, hemi) {
    const parts = [];
    for (const p of coords) {
      const pt = projOrthographic(p.lon, p.lat, hemi);
      if (!pt) continue;
      parts.push(parts.length ? `L${pt[0]},${pt[1]}` : `M${pt[0]},${pt[1]}`);
    }
    return parts.join(' ');
  }

  function drawLatGrid(hemi) {
    while (elGrid.firstChild) elGrid.firstChild.remove();
    const step = 10;
    for (let lat = hemi==='north' ? 10 : -10; hemi==='north' ? lat<=80 : lat>=-80; lat += (hemi==='north'?step:-step)) {
      const pA = projOrthographic(ctx.lon0, lat, hemi);
      if (!pA) continue;
      // small tick + label
      const c = document.createElementNS(elSVG.namespaceURI, 'circle');
      c.setAttribute('cx', pA[0]); c.setAttribute('cy', pA[1]); c.setAttribute('r', 2.5);
      const t = document.createElementNS(elSVG.namespaceURI, 'text');
      t.setAttribute('x', pA[0] + 6); t.setAttribute('y', pA[1] + 4);
      t.textContent = `${Math.abs(lat)}°${lat>0?'N':'S'}`;
      elGrid.appendChild(c); elGrid.appendChild(t);
    }
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
    elBase.src = (hemi === 'north') ? ctx.baseMap.north : ctx.baseMap.south;
    drawLatGrid(hemi);
    try { await loadNowcast(hemi); } catch (e) { console.error(e); elBanner.classList.remove('is-hidden'); }
  }

  // Initialize
  setHemisphere(ctx.hemi);
})();
</script>
