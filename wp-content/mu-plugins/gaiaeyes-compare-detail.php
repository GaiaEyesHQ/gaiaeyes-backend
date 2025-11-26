<?php
/**
 * Plugin Name: Gaia Eyes – Compare Detail
 * Description: Overlay two metrics (e.g., KP vs M5+ quakes) with correlation and lag tools.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) exit;

require_once __DIR__ . '/gaiaeyes-api-helpers.php';

  $base = defined('GAIA_MEDIA_BASE') ? rtrim(GAIA_MEDIA_BASE, '/') : '';
if (!defined('GAIAEYES_COMPARE_URL')) {
  define('GAIAEYES_COMPARE_URL', $base ? ($base . '/data/compare_series.json') : '');
}
if (!defined('GAIAEYES_COMPARE_MIRROR')) {
  define('GAIAEYES_COMPARE_MIRROR', GAIAEYES_COMPARE_URL);
}
if (!defined('GAIAEYES_QH_URL')) {
  define('GAIAEYES_QH_URL', $base ? ($base . '/data/quakes_history.json') : '');
}
if (!defined('GAIAEYES_QH_MIRROR')) {
  define('GAIAEYES_QH_MIRROR', GAIAEYES_QH_URL);
}
if (!defined('GAIAEYES_SH_URL')) {
  define('GAIAEYES_SH_URL', $base ? ($base . '/data/space_history.json') : '');
}
if (!defined('GAIAEYES_SH_MIRROR')) {
  define('GAIAEYES_SH_MIRROR', GAIAEYES_SH_URL);
}

function gaiaeyes_compare_fetch($primary, $mirror, $cache_key, $ttl){
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

/**
 * Shortcode: [gaia_compare_metrics url="" a="m5p_daily" b="m5p_daily" range="30" lag="0" smooth="0" cache="10"]
 */
function gaiaeyes_compare_detail_shortcode($atts){
  $a = shortcode_atts([
    'url'    => GAIAEYES_COMPARE_URL,
    'a'      => 'm5p_daily',
    'b'      => 'kp_daily_max',
    'range'  => 90,   // 7, 30, 90, 180, 365
    'lag'    => 0,    // shift B by N days vs A
    'smooth' => 0,    // 0, 3, 7 rolling avg
    'cache'  => 10
  ], $atts, 'gaia_compare_metrics');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $d = gaiaeyes_compare_fetch($a['url'], GAIAEYES_COMPARE_MIRROR, 'ge_compare_series', $ttl);
  $ser = is_array($d) && !empty($d['series']) ? $d['series'] : [];
  $labels = is_array($d) && !empty($d['labels']) ? $d['labels'] : [];

  // Augment missing series from quakes/space histories if not present in compare_series
  $need_sh = !(isset($ser['kp_daily_max']) && isset($ser['bz_daily_min']) && isset($ser['sw_daily_avg']));
  $need_qh = !(isset($ser['m5p_daily']) && (isset($ser['all_daily']) || isset($ser['m4p_daily']) || isset($ser['m6p_daily'])));

  if ($need_qh) {
    $qh = gaiaeyes_compare_fetch(GAIAEYES_QH_URL, GAIAEYES_QH_MIRROR, 'ge_qh_fallback', $ttl);
    if (is_array($qh) && !empty($qh['series'])) {
      $qser = $qh['series'];
      foreach (['all_daily','m4p_daily','m5p_daily','m6p_daily','m5p_monthly','m6p_monthly'] as $k) {
        if (!empty($qser[$k]) && empty($ser[$k])) $ser[$k] = $qser[$k];
      }
      if (empty($labels) && !empty($qh['labels']) && is_array($qh['labels'])) $labels = $qh['labels'];
    }
  }

  if ($need_sh) {
    $sh = gaiaeyes_compare_fetch(GAIAEYES_SH_URL, GAIAEYES_SH_MIRROR, 'ge_sh_fallback', $ttl);
    if (is_array($sh) && !empty($sh['series'])) {
      $sser = $sh['series'];
      foreach (['kp_daily_max','bz_daily_min','sw_daily_avg'] as $k) {
        if (!empty($sser[$k]) && empty($ser[$k])) $ser[$k] = $sser[$k];
      }
      if (empty($labels) && !empty($sh['labels']) && is_array($sh['labels'])) $labels = $sh['labels'];
    }
  }

  // If still no labels, supply a minimal default map
  if (empty($labels)) {
    $labels = [
      'all_daily'=>'Quakes (all, daily)', 'm4p_daily'=>'Quakes M4+ (daily)', 'm5p_daily'=>'Quakes M5+ (daily)', 'm6p_daily'=>'Quakes M6+ (daily)',
      'm5p_monthly'=>'Quakes M5+ (monthly)', 'm6p_monthly'=>'Quakes M6+ (monthly)',
      'kp_daily_max'=>'Kp (daily max)', 'bz_daily_min'=>'Bz (daily min, nT)', 'sw_daily_avg'=>'Solar wind (daily avg, km/s)'
    ];
  }

  // Build metric options from keys present
  $keys = array_keys($ser);
  sort($keys);
  // Sanitize controls (prefer m5p_daily and kp_daily_max when available)
  $metricA = in_array($a['a'], $keys, true) ? $a['a'] : ( in_array('m5p_daily',$keys,true) ? 'm5p_daily' : ( $keys[0] ?? 'm5p_daily' ) );
  $metricB = in_array($a['b'], $keys, true) ? $a['b'] : ( in_array('kp_daily_max',$keys,true) ? 'kp_daily_max' : ( $keys[0] ?? 'm5p_daily' ) );
  $range   = max(7, min(365, intval($a['range'])));
  $lag     = max(-30, min(30, intval($a['lag'])));
  $smooth  = max(0, min(14, intval($a['smooth'])));

  ob_start(); ?>
  <section class="ge-compare ge-panel">
    <header class="ge-head">
      <h2>Compare Metrics – Scientific Overlay</h2>
      <div class="ge-meta"><?php echo !empty($d['timestamp_utc']) ? 'Updated '.esc_html($d['timestamp_utc']) : ''; ?></div>
    </header>

    <div class="ge-controls" id="controls">
      <div class="ctl">
        <label>Metric A</label>
        <select id="cmpA">
          <?php foreach ($keys as $k): ?>
            <option value="<?php echo esc_attr($k); ?>" <?php selected($k, $metricA); ?>><?php echo esc_html( $labels[$k] ?? $k ); ?></option>
          <?php endforeach; ?>
        </select>
      </div>
      <div class="ctl">
        <label>Metric B</label>
        <select id="cmpB">
          <?php foreach ($keys as $k): ?>
            <option value="<?php echo esc_attr($k); ?>" <?php selected($k, $metricB); ?>><?php echo esc_html( $labels[$k] ?? $k ); ?></option>
          <?php endforeach; ?>
        </select>
      </div>
      <div class="ctl">
        <label>Range (days)</label>
        <select id="cmpRange">
          <?php foreach ([7,30,90,180,365] as $r): ?>
            <option value="<?php echo $r; ?>" <?php selected($r, $range); ?>><?php echo $r; ?></option>
          <?php endforeach; ?>
        </select>
      </div>
      <div class="ctl">
        <label>Lag B (days)</label>
        <input id="cmpLag" type="number" min="-30" max="30" step="1" value="<?php echo esc_attr($lag); ?>" />
      </div>
      <div class="ctl">
        <label>Smooth (days)</label>
        <select id="cmpSmooth">
          <?php foreach ([0,3,7] as $s): ?>
            <option value="<?php echo $s; ?>" <?php selected($s, $smooth); ?>><?php echo $s; ?></option>
          <?php endforeach; ?>
        </select>
      </div>
      <button id="cmpApply" class="btn-apply">Apply</button>
    </div>

    <article class="ge-card" id="chart">
      <h3>Overlay</h3>
      <div class="chart-container"><canvas id="cmpChart"></canvas></div>
      <div class="ge-legend" id="cmpLegend"></div>
    </article>

    <article class="ge-card" id="stats">
      <h3>Quick Stats</h3>
      <div class="stats-grid">
        <div><strong>Pearson r:</strong> <span id="statR">—</span></div>
        <div><strong>Best lag (B vs A):</strong> <span id="statLag">—</span></div>
      </div>
      <div class="ge-note" id="statNote">Correlation does not imply causation; use for exploratory context.</div>
    </article>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-meta{opacity:.8;font-size:.9rem}
      .ge-controls{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
      .ctl{display:flex;flex-direction:column;gap:4px}
      .btn-apply{background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:8px;padding:6px 10px;cursor:pointer}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px;margin-top:10px}
      .stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
      @media(min-width:900px){ .stats-grid{grid-template-columns:repeat(2,1fr)} }
      @media(max-width: 640px){ .ge-controls{ gap: 8px; } .ctl{ width: calc(50% - 6px); } .ctl select, .ctl input{ width: 100%; } }
      .chart-container{position:relative;width:100%;max-width:100%;aspect-ratio: 2 / 1;}
      .chart-container canvas{position:absolute;inset:0;width:100% !important;height:100% !important;}
      @media(max-width:640px){.chart-container{aspect-ratio: 16 / 9;}}
    </style>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
      (function(){
        const data = <?php echo wp_json_encode($ser); ?>;
        const LABELS = <?php echo wp_json_encode($labels ?: []); ?>;
        function parseSeries(k){ return Array.isArray(data[k]) ? data[k].slice() : []; }

        function rolling(arr, win){
          if (!win || win <= 1) return arr;
          const out = [];
          let sum = 0, buf = [];
          for (let i=0;i<arr.length;i++){
            sum += arr[i][1]; buf.push(arr[i][1]);
            if (buf.length > win) sum -= buf.shift();
            out.push([arr[i][0], sum / buf.length]);
          }
          return out;
        }

        function align(a, b, range, lag){
          // Keep last N days; shift B by lag (positive = B trails A)
          const keep = (arr) => arr.slice(Math.max(0, arr.length-range));
          const A = keep(a), B = keep(b);
          const mapA = new Map(A.map(d => [d[0], d[1]]));
          const mapB = new Map(B.map(d => [d[0], d[1]]));
          // Build date list from A
          const dates = A.map(d => d[0]);
          // Shift B's values by lag days relative to A
          const outA = [], outB = [];
          for (let i=0;i<dates.length;i++){
            const d = dates[i];
            const vA = mapA.get(d);
            // find B at lag: simplistic by index shift
            const j = i + lag;
            const vB = (j>=0 && j<dates.length) ? mapB.get(dates[j]) : undefined;
            if (typeof vA === 'number' && typeof vB === 'number'){
              outA.push(vA); outB.push(vB);
            }
          }
          return {dates, outA, outB};
        }

        function pearson(x,y){
          if (x.length !== y.length || x.length < 3) return NaN;
          let sx=0, sy=0, sxx=0, syy=0, sxy=0, n=x.length;
          for (let i=0;i<n;i++){
            sx+=x[i]; sy+=y[i];
            sxx+=x[i]*x[i]; syy+=y[i]*y[i]; sxy+=x[i]*y[i];
          }
          const cov = sxy - (sx*sy)/n;
          const vx  = sxx - (sx*sx)/n;
          const vy  = syy - (sy*sy)/n;
          const denom = Math.sqrt(vx*vy);
          return denom>0 ? (cov/denom) : NaN;
        }

        let chart;
        function draw(){
          const Akey = document.getElementById('cmpA').value;
          const Bkey = document.getElementById('cmpB').value;
          const range = parseInt(document.getElementById('cmpRange').value,10);
          const lag = parseInt(document.getElementById('cmpLag').value,10);
          const smooth = parseInt(document.getElementById('cmpSmooth').value,10);
          const nmA = (LABELS || {})[Akey] || Akey;
          const nmB = (LABELS || {})[Bkey] || Bkey;

          let A = parseSeries(Akey);
          let B = parseSeries(Bkey);
          A = rolling(A, smooth);
          B = rolling(B, smooth);

          const {dates, outA, outB} = align(A,B,range,lag);
          const r = pearson(outA, outB);
          document.getElementById('statR').textContent = isFinite(r)? r.toFixed(2) : '—';
          document.getElementById('statLag').textContent = (lag>=0? "+"+lag : lag) + " d";

          if (chart) chart.destroy();
          const ctx = document.getElementById('cmpChart').getContext('2d');
          chart = new Chart(ctx, {
            type: 'line',
            data: {
              labels: dates.slice(-range),
              datasets: [
                {label: nmA, data: outA.slice(-range), borderColor:'#7fc8ff', tension:0.25, pointRadius:0},
                {label: nmB, data: outB.slice(-range), borderColor:'#ffd089', tension:0.25, pointRadius:0}
              ]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              animation: false,
              plugins:{legend:{labels:{color:'#cfe3ff'}}},
              scales:{
                x:{ticks:{color:'#cfe3ff'}, grid:{display:false}},
                y:{ticks:{color:'#cfe3ff'}, grid:{color:'rgba(255,255,255,.08)'}}
              }
            }
          });
          const legend = document.getElementById('cmpLegend');
          if (legend){
            legend.textContent = `A = ${nmA}   |   B = ${nmB}`;
          }
        }

        document.getElementById('cmpApply').addEventListener('click', draw);
        // Init selects with defaults and draw:
        document.getElementById('cmpA').value = "<?php echo esc_js($metricA); ?>";
        document.getElementById('cmpB').value = "<?php echo esc_js($metricB); ?>";
        document.getElementById('cmpRange').value = "<?php echo (int)$range; ?>";
        document.getElementById('cmpLag').value = "<?php echo (int)$lag; ?>";
        document.getElementById('cmpSmooth').value = "<?php echo (int)$smooth; ?>";
        draw();
      })();
    </script>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_compare_metrics','gaiaeyes_compare_detail_shortcode');
