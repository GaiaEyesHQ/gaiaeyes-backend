<?php
/**
 * Plugin Name: Gaia Eyes – Schumann Detail
 * Description: Scientific Schumann Resonance detail page with combined F1, source images (Tomsk/Cumiana) and health notes.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

// Defaults (GitHub Pages + jsDelivr mirrors)
if (!defined('GAIAEYES_SCH_COMBINED_URL')) {
  define('GAIAEYES_SCH_COMBINED_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/schumann_combined.json');
}
if (!defined('GAIAEYES_SCH_COMBINED_MIRROR')) {
  define('GAIAEYES_SCH_COMBINED_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/schumann_combined.json');
}
if (!defined('GAIAEYES_SCH_LATEST_URL')) {
  define('GAIAEYES_SCH_LATEST_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/schumann_latest.json');
}
if (!defined('GAIAEYES_SCH_LATEST_MIRROR')) {
  define('GAIAEYES_SCH_LATEST_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/schumann_latest.json');
}

function gaiaeyes_http_json_fallback($primary, $mirror, $cache_key, $ttl){
  $cached = get_transient($cache_key);
  if ($cached !== false) return $cached;
  $v = array('v' => floor(time()/600));
  $resp = wp_remote_get(add_query_arg($v, esc_url_raw($primary)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
    $resp = wp_remote_get(add_query_arg($v, esc_url_raw($mirror)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  }
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;
  $data = json_decode(wp_remote_retrieve_body($resp), true);
  if (!is_array($data)) return null;
  set_transient($cache_key, $data, $ttl);
  return $data;
}

function gaiaeyes_schumann_detail_shortcode($atts){
  $a = shortcode_atts([
    'combined_url' => '',
    'latest_url'   => GAIAEYES_SCH_LATEST_URL,
    'series_url'   => '',
    'station'      => 'cumiana',
    'cache'        => 10,
  ], $atts, 'gaia_schumann_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $latest   = gaiaeyes_http_json_fallback($a['latest_url'], GAIAEYES_SCH_LATEST_MIRROR, 'ge_sch_latest', $ttl);
  $combined = null;

  // Prepare 24h series endpoint (F1). Prefer configured backend; hard‑fallback to public Render base.
  $series_url_default = (defined('GAIAEYES_API_BASE')
    ? rtrim(GAIAEYES_API_BASE, '/') . '/v1/earth/schumann/series?hours=24&station=' . rawurlencode($a['station'])
    : 'https://gaiaeyes-backend.onrender.com/v1/earth/schumann/series?hours=24&station=' . rawurlencode($a['station'])
  );
  $series_url = !empty($a['series_url']) ? $a['series_url'] : $series_url_default;

  // Extract/derive combined block and source images
  $f1 = $delta = null; $method = $primary = '';
  $sources = [];
  $media_img_base = 'https://gaiaeyeshq.github.io/gaiaeyes-media/images/';

  if (is_array($combined)) {
    $comb = isset($combined['combined']) && is_array($combined['combined']) ? $combined['combined'] : [];
    $f1    = isset($comb['f1_hz']) ? floatval($comb['f1_hz']) : null;
    $delta = isset($comb['delta_hz']) ? floatval($comb['delta_hz']) : null;
    $method= isset($comb['method']) ? (string)$comb['method'] : '';
    $primary = isset($comb['primary']) ? (string)$comb['primary'] : '';
    $srcs = isset($combined['sources']) && is_array($combined['sources']) ? $combined['sources'] : [];
    foreach (['tomsk','cumiana'] as $k){
      if (!empty($srcs[$k]) && is_array($srcs[$k])){
        $img = isset($srcs[$k]['image']) ? esc_url($srcs[$k]['image']) : '';
        if (!$img) {
          // fallback to known image filenames in media repo
          if ($k==='tomsk') $img = $media_img_base.'tomsk_latest.png';
          if ($k==='cumiana') $img = $media_img_base.'cumiana_latest.png';
        }
        $sources[$k] = [
          'label' => ucfirst($k),
          'image' => $img,
          'f1_hz' => isset($srcs[$k]['f1_hz']) ? $srcs[$k]['f1_hz'] : null,
        ];
      }
    }
  }

  // If combined missing or incomplete, try deriving from latest.json
  if ((!is_array($combined) || $f1===null) && is_array($latest)) {
    $srcs = isset($latest['sources']) && is_array($latest['sources']) ? $latest['sources'] : [];
    $t_f1 = isset($srcs['tomsk']['fundamental_hz']) ? floatval($srcs['tomsk']['fundamental_hz']) : null;
    $c_f1 = isset($srcs['cumiana']['fundamental_hz']) ? floatval($srcs['cumiana']['fundamental_hz']) : null;
    // simple confidence-weighted blend (tomsk 0.7, cumiana 0.3) when both exist
    if ($t_f1!==null && $c_f1!==null) {
      $f1 = round(($t_f1*0.7 + $c_f1*0.3)/1.0, 2);
      $method = 'derived_from_latest';
      $primary = 'tomsk';
    } elseif ($t_f1!==null) {
      $f1 = round($t_f1, 2); $method='derived_from_latest'; $primary='tomsk';
    } elseif ($c_f1!==null) {
      $f1 = round($c_f1, 2); $method='derived_from_latest'; $primary='cumiana';
    }
    // Build sources images if not set
    foreach (['tomsk','cumiana'] as $k){
      if (empty($sources[$k])) {
        $img = '';
        if ($k==='tomsk') $img = $media_img_base.'tomsk_latest.png';
        if ($k==='cumiana') $img = $media_img_base.'cumiana_latest.png';
        $f1_src = null;
        if ($k==='tomsk' && $t_f1!==null) $f1_src = $t_f1;
        if ($k==='cumiana' && $c_f1!==null) $f1_src = $c_f1;
        $sources[$k] = [ 'label'=>ucfirst($k), 'image'=>$img, 'f1_hz'=>$f1_src ];
      }
    }
  }

  ob_start(); ?>
  <section class="ge-sch ge-panel">
    <header class="ge-head">
      <h2>Schumann Resonance – Scientific Detail</h2>
      <div class="ge-meta">
        <?php
          $ts = '';
          if (is_array($latest) && !empty($latest['timestamp_utc'])) $ts = $latest['timestamp_utc'];
          elseif (is_array($combined) && !empty($combined['timestamp_utc'])) $ts = $combined['timestamp_utc'];
        ?>
        Updated <?php echo esc_html( $ts ?: '—' ); ?>
      </div>
    </header>

    <div class="ge-grid">
      <article class="ge-card">
        <h3 id="combined">Combined F1 <a class="anchor-link" href="#combined" aria-label="Link to Combined F1">🔗</a></h3>
        <div class="row"><span class="lab">F1 (combined)</span><span class="val"><?php echo $f1!==null? esc_html(number_format($f1,2)).' Hz' : '—'; ?></span></div>
        <?php if ($method): ?><div class="note">Method: <?php echo esc_html($method); ?><?php if($primary) echo ' • primary: '.esc_html(ucfirst($primary)); ?></div><?php endif; ?>
      </article>

      <article class="ge-card">
        <h3 id="images">Source Images <a class="anchor-link" href="#images" aria-label="Link to Source Images">🔗</a></h3>
        <div class="img-grid">
          <?php foreach (['tomsk','cumiana'] as $k): if (!empty($sources[$k]['image'])): ?>
            <figure class="img-box">
              <a href="<?php echo esc_url($sources[$k]['image']); ?>" class="sch-lightbox-link" data-caption="<?php echo esc_attr(ucfirst($k)); ?><?php if($sources[$k]['f1_hz']!==null) echo ' • f1 '.esc_attr(number_format((float)$sources[$k]['f1_hz'],2)).' Hz'; ?>">
                <img src="<?php echo esc_url($sources[$k]['image']); ?>" alt="<?php echo esc_attr(ucfirst($k)); ?> latest plot" loading="lazy" />
              </a>
              <figcaption><?php echo esc_html(ucfirst($k)); ?><?php if($sources[$k]['f1_hz']!==null) echo ' • f1 '.esc_html(number_format((float)$sources[$k]['f1_hz'],2)).' Hz'; ?></figcaption>
            </figure>
          <?php endif; endforeach; ?>
        </div>
      </article>

      <article class="ge-card">
        <h3 id="chart">Last 24 hours (F1) <a class="anchor-link" href="#chart" aria-label="Link to 24h F1 chart">🔗</a></h3>
        <div id="ge-sch-chart-wrap" data-series-url="<?php echo esc_attr($series_url); ?>">
          <canvas id="ge-sch-chart" height="220"></canvas>
          <div id="ge-sch-fallback" class="ge-muted" aria-live="polite" style="display:none">No 24 h series available.</div>
        </div>
        <noscript>Enable JavaScript to see the live F1 chart.</noscript>
      </article>

      <article class="ge-card">
        <h3 id="health">Health context <a class="anchor-link" href="#health" aria-label="Link to Health Context">🔗</a></h3>
        <ul class="health-list">
          <li><strong>Nervous system:</strong> Shifts in EM environment can increase reactivity in sensitives; paced breathing and brief outdoor breaks may help.</li>
          <li><strong>Sleep:</strong> Keep evenings low-light and devices dimmed during elevated variability.</li>
          <li><strong>Cardio/HRV:</strong> Some see HRV dips during geomagnetic activity; hydrate and take short daylight breaks.</li>
        </ul>
      </article>

      <article class="ge-card">
        <h3 id="about">About Schumann <a class="anchor-link" href="#about" aria-label="Link to About Schumann">🔗</a></h3>
        <p>The Schumann resonances are global EM resonances excited mainly by lightning discharges. The fundamental (f1) is near ~7.8 Hz with higher harmonics. Measurements vary by station, time, and processing, so a combined snapshot offers a practical indicator for daily monitoring.</p>
      </article>
    </div>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-head h2{margin:0;font-size:1.15rem}
      .ge-meta{opacity:.8;font-size:.9rem}
      .ge-grid{display:grid;gap:12px}
      @media(min-width:900px){.ge-grid{grid-template-columns:repeat(2,1fr)}}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px}
      #ge-sch-chart-wrap{width:100%;min-height:220px}
      .row{display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,.08)}
      .row .lab{opacity:.85}
      .row .val{font-weight:600}
      .note{margin-top:6px;opacity:.85}
      .ge-muted{opacity:.75;font-size:.9rem;margin-top:6px}
      .img-grid{display:grid;gap:10px}
      @media(min-width:600px){.img-grid{grid-template-columns:repeat(3,1fr)}}
      .img-box{margin:0}
      .img-box img{width:100%;height:auto;border-radius:8px;border:1px solid rgba(255,255,255,.08)}
      .img-box figcaption{font-size:.85rem;opacity:.85;margin-top:4px}
      .health-list{margin:0;padding-left:18px;line-height:1.45}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      .sch-lightbox{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.85);z-index:9999;padding:20px}
      .sch-lightbox__figure{margin:0;max-width:90vw;max-height:90vh;text-align:center}
      .sch-lightbox__figure img{max-width:90vw;max-height:80vh;border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,.6)}
      .sch-lightbox__figure figcaption{margin-top:8px;font-size:.95rem;opacity:.9}
      .sch-close{position:absolute;top:10px;right:14px;font-size:28px;line-height:1;background:transparent;color:#e9eef7;border:0;cursor:pointer}
      .sch-close:hover{opacity:.85}
    </style>
    <div class="sch-lightbox" id="schLightbox" aria-hidden="true" role="dialog" aria-label="Schumann source image">
      <button type="button" class="sch-close" id="schLightboxClose" aria-label="Close">×</button>
      <figure class="sch-lightbox__figure">
        <img id="schLightboxImg" src="" alt="Expanded source image" />
        <figcaption id="schLightboxCap"></figcaption>
      </figure>
    </div>
    <script>
      (function(){
        const overlay = document.getElementById('schLightbox');
        const img = document.getElementById('schLightboxImg');
        const cap = document.getElementById('schLightboxCap');
        const btn = document.getElementById('schLightboxClose');
        function openLightbox(src, caption){
          img.src = src; cap.textContent = caption || '';
          overlay.style.display = 'flex';
          overlay.setAttribute('aria-hidden','false');
          document.body.style.overflow = 'hidden';
          btn.focus();
        }
        function closeLightbox(){
          overlay.style.display = 'none';
          overlay.setAttribute('aria-hidden','true');
          img.src = '';
          document.body.style.overflow = '';
        }
        overlay.addEventListener('click', function(e){ if(e.target===overlay) closeLightbox(); });
        btn.addEventListener('click', closeLightbox);
        document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeLightbox(); });
        document.querySelectorAll('.sch-lightbox-link').forEach(function(a){
          a.addEventListener('click', function(e){ e.preventDefault(); openLightbox(this.href, this.getAttribute('data-caption')); });
        });
      })();
    </script>
    <script>
      (function(){
        var seriesUrl = <?php echo json_encode($series_url); ?>;
        var wrapEl = document.getElementById('ge-sch-chart-wrap');
        if ((!seriesUrl || !seriesUrl.length) && wrapEl && wrapEl.dataset && wrapEl.dataset.seriesUrl) {
          seriesUrl = wrapEl.dataset.seriesUrl;
        }
        if (!seriesUrl || !seriesUrl.length) {
          // Nothing to render
          var fb = document.getElementById('ge-sch-fallback');
          if (fb) fb.style.display = 'block';
          return;
        }
        function normalize(data){
          var arr = Array.isArray(data) ? data
                   : (data && Array.isArray(data.series)) ? data.series
                   : (data && Array.isArray(data.points)) ? data.points
                   : (data && Array.isArray(data.data)) ? data.data
                   : [];
          return arr.map(function(p){
            var t = p.ts || p.ts_utc || p.time || p.timestamp || p.t || p.day;
            var v = (p.f1 !== undefined ? p.f1 : (p.f1_hz !== undefined ? p.f1_hz : (p.fundamental_hz !== undefined ? p.fundamental_hz : (p.hz !== undefined ? p.hz : p.value))));
            if (!t || v === undefined || v === null) return null;
            return { t: t, v: Number(v) };
          }).filter(Boolean);
        }
        function initChart(points){
          var fb = document.getElementById('ge-sch-fallback');
          if (fb) fb.style.display = 'none';
          var el = document.getElementById('ge-sch-chart');
          if (!el) return;
          var labels = points.map(function(p){
            try { return new Date(p.t).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}); }
            catch(e){ return String(p.t); }
          });
          var data = points.map(function(p){ return p.v; });
          var ctx = el.getContext('2d');
          new (window.Chart)(ctx, {
            type: 'line',
            data: {
              labels: labels,
              datasets: [{ label: 'F1 (Hz)', data: data, borderWidth: 2, pointRadius: 0, tension: 0.25 }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                y: { title: { display: true, text: 'Hz' } }
              },
              plugins: {
                legend: { display: true }
              }
            }
          });
        }
        function fetchAndRender(){
          fetch(seriesUrl, { headers: { 'Accept': 'application/json' }, mode: 'cors' })
            .then(function(r){ return r.json(); })
            .then(function(d){
              var pts = normalize(d);
              if (pts.length) {
                initChart(pts);
              } else {
                var fb = document.getElementById('ge-sch-fallback');
                if (fb) fb.style.display = 'block';
                if (window.console && console.warn) console.warn('GE Schumann: empty series', seriesUrl);
              }
            })
            .catch(function(err){
              var fb = document.getElementById('ge-sch-fallback');
              if (fb) fb.style.display = 'block';
              if (window.console && console.error) console.error('GE Schumann: series fetch failed', seriesUrl, err);
            });
        }
        function ensureChartJs(cb){
          if (window.Chart) return cb();
          var s = document.createElement('script');
          s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1';
          s.onload = cb;
          document.head.appendChild(s);
        }
        ensureChartJs(fetchAndRender);
      })();
    </script>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_schumann_detail','gaiaeyes_schumann_detail_shortcode');
