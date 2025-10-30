<?php

// DEPLOY TEST: <today’s date/time>
/**
 * Plugin Name: Gaia Eyes – Space Weather Detail
 * Description: Scientific detail page for Space Weather (Kp, Solar wind, Bz, Flares, CMEs, Aurora) using gaiaeyes-media JSON feeds.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

/* ---------- Defaults (GitHub Pages + jsDelivr mirror) ---------- */
if (!defined('GAIAEYES_SW_URL')) {
  define('GAIAEYES_SW_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_weather.json');
}
if (!defined('GAIAEYES_FC_URL')) {
  define('GAIAEYES_FC_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/flares_cmes.json');
}
if (!defined('GAIAEYES_SW_URL_MIRROR')) {
  define('GAIAEYES_SW_URL_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/space_weather.json');
}
if (!defined('GAIAEYES_FC_URL_MIRROR')) {
  define('GAIAEYES_FC_URL_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/flares_cmes.json');
}

/* ---------- Fetch & Cache Helpers ---------- */
function gaiaeyes_http_get_json_with_fallback($primary, $mirror, $cache_key, $ttl) {
  $cached = get_transient($cache_key);
  if ($cached !== false) return $cached;

  $resp = wp_remote_get(add_query_arg(['v'=>floor(time()/600)], $primary), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
    $resp = wp_remote_get(add_query_arg(['v'=>floor(time()/600)], $mirror), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  }
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;
  $data = json_decode(wp_remote_retrieve_body($resp), true);
  if (!is_array($data)) return null;

  set_transient($cache_key, $data, $ttl);
  return $data;
}

/* ---------- Render Helpers ---------- */
function ge_chip($label, $value, $class='') {
  $le = esc_html($label); $ve = esc_html($value);
  return "<span class='sw-chip {$class}'><strong>{$le}:</strong> {$ve}</span>";
}
function ge_row($label, $value) {
  $le = esc_html($label); $ve = esc_html($value);
  return "<div class='sw-row'><span class='sw-row__label'>{$le}</span><span class='sw-row__val'>{$ve}</span></div>";
}
function ge_val_or_dash($v, $suffix='') {
  if ($v === null || $v === '' || $v === false) return '—';
  $txt = is_numeric($v) ? (strpos((string)$v,'.') !== false ? rtrim(rtrim(number_format_i18n((float)$v, 2), '0'), '.') : number_format_i18n((float)$v)) : (string)$v;
  return $suffix ? "{$txt} {$suffix}" : $txt;
}

/* ---------- Shortcode ---------- */
/**
 * [gaia_space_weather_detail sw_url="" fc_url="" cache="10"]
 */
function gaia_space_weather_detail_shortcode($atts){
  $a = shortcode_atts([
    'sw_url' => GAIAEYES_SW_URL,
    'fc_url' => GAIAEYES_FC_URL,
    'cache'  => 10, // minutes
  ], $atts, 'gaia_space_weather_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;

  $sw = gaiaeyes_http_get_json_with_fallback($a['sw_url'], GAIAEYES_SW_URL_MIRROR, 'ge_sw_json', $ttl);
  $fc = gaiaeyes_http_get_json_with_fallback($a['fc_url'], GAIAEYES_FC_URL_MIRROR, 'ge_fc_json', $ttl);

  ob_start();
  ?>
  <section class="ge-sw ge-panel">
    <header class="ge-sw__head">
      <h2>Space Weather – Scientific Detail</h2>
      <div class="ge-sw__meta">
        <?php if (is_array($sw) && !empty($sw['timestamp_utc'])): ?>
          Updated <?php echo esc_html($sw['timestamp_utc']); ?>
        <?php else: ?>
          <span>Updated —</span>
        <?php endif; ?>
      </div>
    </header>

    <?php if (!$sw): ?>
      <div class="ge-sw__error">Space Weather data unavailable.</div>
      <?php return ob_get_clean(); ?>
    <?php endif; ?>

    <div class="ge-sw__grid">
      <!-- Card: KP / Solar Wind / Bz -->
      <article class="ge-card">
        <h3 id="kp">Geomagnetic Conditions <a class="anchor-link" href="#kp" aria-label="Link to Geomagnetic Conditions">🔗</a></h3>
        <?php
          $now = isset($sw['now']) ? $sw['now'] : [];
          $kp  = isset($now['kp']) ? (float)$now['kp'] : null;
          $swk = isset($now['solar_wind_kms']) ? (float)$now['solar_wind_kms'] : null;
          $bz  = isset($now['bz_nt']) ? (float)$now['bz_nt'] : null;

          $last = isset($sw['last_24h']) ? $sw['last_24h'] : [];
          $kpmax = isset($last['kp_max']) ? (float)$last['kp_max'] : null;
          $swmax = isset($last['solar_wind_max_kms']) ? (int)$last['solar_wind_max_kms'] : null;

          echo ge_row('Kp (now)', ge_val_or_dash($kp));
          if ($kpmax !== null) echo ge_row('Kp (24h max)', ge_val_or_dash($kpmax));
          echo '<div class="sw-row"><span class="sw-row__label" id="solar-wind">Solar wind (now)</span><span class="sw-row__val">' . esc_html( ge_val_or_dash($swk, 'km/s') ) . '</span></div>';
          if ($swmax !== null) echo ge_row('Solar wind (24h max)', ge_val_or_dash($swmax, 'km/s'));
          echo '<div class="sw-row"><span class="sw-row__label" id="bz">Bz (IMF)</span><span class="sw-row__val">' . esc_html( ge_val_or_dash($bz, 'nT') ) . '</span></div>';
        ?>
      </article>

      <!-- Card: Flares -->
      <article class="ge-card">
        <h3 id="flares">Solar Flares <a class="anchor-link" href="#flares" aria-label="Link to Solar Flares">🔗</a></h3>
        <?php
          $flr = is_array($fc) ? ($fc['flares'] ?? []) : [];
          $max = $flr['max_24h'] ?? null;
          $tot = $flr['total_24h'] ?? null;
          $bands = is_array($flr['bands_24h'] ?? null) ? $flr['bands_24h'] : [];

          echo ge_row('Max class (24h)', ge_val_or_dash($max));
          if ($tot !== null) echo ge_row('Total flares (24h)', ge_val_or_dash($tot));

          $band_line = [];
          foreach (['X','M','C','B','A'] as $b) {
            if (!empty($bands[$b])) $band_line[] = "{$b}:{$bands[$b]}";
          }
          if ($band_line) echo "<div class='sw-bandline'>Bands: ".esc_html(implode(' ', $band_line))."</div>";
        ?>
        <p class="ge-note">Flares are measured by X-ray flux (A→X). Higher classes indicate stronger events that can impact radio propagation and ionospheric conditions.</p>
      </article>

      <!-- Card: CMEs -->
      <article class="ge-card">
        <h3 id="cmes">Coronal Mass Ejections <a class="anchor-link" href="#cmes" aria-label="Link to Coronal Mass Ejections">🔗</a></h3>
        <?php
          $cme = is_array($fc) ? ($fc['cmes'] ?? []) : [];
          $headline = $cme['headline'] ?? '';
          $stats = is_array($cme['stats'] ?? null) ? $cme['stats'] : [];
          $c_total = $stats['total_72h'] ?? null;
          $c_ed    = $stats['earth_directed_count'] ?? null;
          $c_vmax  = $stats['max_speed_kms'] ?? null;

          echo ge_row('Headline', $headline ? $headline : '—');
          if ($c_total !== null) echo ge_row('Total (72h)', ge_val_or_dash($c_total));
          if ($c_ed !== null) echo ge_row('Earth-directed', ge_val_or_dash($c_ed));
          if ($c_vmax !== null) echo ge_row('Max speed', ge_val_or_dash($c_vmax, 'km/s'));
        ?>
        <p class="ge-note">CMEs can cause geomagnetic storms when Earth-directed. Speed ≥600–1000 km/s often indicates stronger coupling potential.</p>
      </article>

      <!-- Card: Aurora & Forecast -->
      <article class="ge-card">
        <h3 id="aurora">Aurora & Forecast <a class="anchor-link" href="#aurora" aria-label="Link to Aurora & Forecast">🔗</a></h3>
        <?php
          $next = isset($sw['next_72h']) ? $sw['next_72h'] : [];
          $hl   = $next['headline'] ?? '';
          $conf = $next['confidence'] ?? '';
          $alerts = isset($sw['alerts']) ? (array)$sw['alerts'] : [];

          if ($hl) echo ge_chip('Aurora', $hl, 'sw-chip--aurora');
          if ($conf) echo ge_chip('Confidence', $conf);
          if ($alerts) echo ge_chip('Alerts', implode(', ', array_map('esc_html', $alerts)));

          $imp = isset($sw['impacts']) ? $sw['impacts'] : [];
          echo "<div class='ge-impacts'><h4>Plain-language impacts</h4><ul>";
          foreach (['gps'=>'GPS/Navigation','comms'=>'Radio/Comms','grids'=>'Power Grids','aurora'=>'Aurora Visibility'] as $k=>$label) {
            $txt = isset($imp[$k]) ? $imp[$k] : '—';
            echo "<li><strong>".esc_html($label).":</strong> ".esc_html($txt)."</li>";
          }
          echo "</ul></div>";
        ?>
      </article>
    </div>

    <!-- Optional sparklines (graceful if no series) -->
    <div class="ge-sparklines" id="ge-spark-wrap" style="display:none;">
      <h3>Recent trends</h3>
      <canvas id="ge-spark-kp" height="80"></canvas>
      <canvas id="ge-spark-sw" height="80"></canvas>
      <canvas id="ge-spark-bz" height="80"></canvas>
    </div>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-sw__head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-sw__head h2{margin:0;font-size:1.15rem}
      .ge-sw__meta{opacity:.8;font-size:.9rem}
      .ge-sw__grid{display:grid;gap:12px}
      @media(min-width:900px){.ge-sw__grid{grid-template-columns:repeat(2,1fr)}}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px}
      .sw-row{display:flex;justify-content:space-between;gap:8px;border-bottom:1px dashed rgba(255,255,255,.08);padding:6px 0}
      .sw-row__label{opacity:.85}
      .sw-row__val{font-weight:600}
      .sw-chip{display:inline-block;background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:999px;padding:3px 10px;font-size:.78rem;line-height:1;margin:4px 4px 0 0}
      .sw-chip--aurora{background:#1c2a21;color:#aef2c0;border-color:#2d5d43}
      .sw-bandline{margin-top:8px;font-size:.9rem;opacity:.9}
      .ge-impacts h4{margin:.5rem 0 .25rem 0;font-size:1rem}
      .ge-impacts ul{margin:0;padding-left:18px;line-height:1.4}
      .ge-sw__error{padding:12px;background:#331e1e;color:#ffd6d6;border:1px solid #6e3a3a;border-radius:8px}
      .ge-sparklines{margin-top:10px}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
    </style>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha256-5l5wxg6rE6sBJP6opc0bDO3sTZ5yH5rICwW7X8P9qvo=" crossorigin="anonymous"></script>
    <script>
      (function(){
        // Optional sparkline support if future series arrays are added to JSON
        try {
          const sw = <?php echo wp_json_encode($sw); ?>;
          let hasSeries = false;

          function draw(id, label, arr){
            const el = document.getElementById(id);
            if (!el || !Array.isArray(arr) || arr.length === 0) return;
            const ctx = el.getContext('2d');
            new Chart(ctx, {
              type: 'line',
              data: { labels: arr.map((_,i)=>i+1), datasets: [{ label, data: arr, borderColor:'#7fc8ff', tension:0.25, pointRadius:0 }]},
              options: { responsive:true, plugins:{legend:{display:false}}, scales:{x:{display:false},y:{display:false}} }
            });
            hasSeries = true;
          }

          // If you later add sw.series24 = { kp:[...], sw:[...], bz:[...] } this will plot them:
          if (sw && sw.series24){
            draw('ge-spark-kp', 'Kp', sw.series24.kp || []);
            draw('ge-spark-sw', 'SW', sw.series24.sw || []);
            draw('ge-spark-bz', 'Bz', sw.series24.bz || []);
          }
          if (hasSeries) document.getElementById('ge-spark-wrap').style.display = 'block';
        } catch(e){}
      })();
    </script>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_space_weather_detail', 'gaia_space_weather_detail_shortcode');