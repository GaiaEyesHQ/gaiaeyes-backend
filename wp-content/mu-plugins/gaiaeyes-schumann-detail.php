<?php
/**
 * Plugin Name: Gaia Eyes – Schumann Detail
 * Description: Scientific Schumann Resonance detail page with combined F1, delta, source images (Tomsk/Cumiana/HeartMath) and health notes.
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
    'combined_url' => GAIAEYES_SCH_COMBINED_URL,
    'latest_url'   => GAIAEYES_SCH_LATEST_URL,
    'cache'        => 10,
  ], $atts, 'gaia_schumann_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $combined = gaiaeyes_http_json_fallback($a['combined_url'], GAIAEYES_SCH_COMBINED_MIRROR, 'ge_sch_combined', $ttl);
  $latest   = gaiaeyes_http_json_fallback($a['latest_url'], GAIAEYES_SCH_LATEST_MIRROR, 'ge_sch_latest', $ttl);

  // Extract combined block
  $f1 = $delta = null; $method = $primary = '';
  $sources = [];
  if (is_array($combined)) {
    $comb = isset($combined['combined']) && is_array($combined['combined']) ? $combined['combined'] : [];
    $f1    = isset($comb['f1_hz']) ? floatval($comb['f1_hz']) : null;
    $delta = isset($comb['delta_hz']) ? floatval($comb['delta_hz']) : null;
    $method= isset($comb['method']) ? (string)$comb['method'] : '';
    $primary = isset($comb['primary']) ? (string)$comb['primary'] : '';
    $srcs = isset($combined['sources']) && is_array($combined['sources']) ? $combined['sources'] : [];
    foreach (['tomsk','cumiana','heartmath'] as $k){
      if (!empty($srcs[$k]) && is_array($srcs[$k])){
        $sources[$k] = [
          'label' => ucfirst($k),
          'image' => isset($srcs[$k]['image']) ? esc_url($srcs[$k]['image']) : '',
          'f1_hz' => isset($srcs[$k]['f1_hz']) ? $srcs[$k]['f1_hz'] : null,
        ];
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
          if (is_array($combined) && !empty($combined['timestamp_utc'])) $ts = $combined['timestamp_utc'];
          elseif (is_array($latest) && !empty($latest['timestamp_utc'])) $ts = $latest['timestamp_utc'];
        ?>
        Updated <?php echo esc_html( $ts ?: '—' ); ?>
      </div>
    </header>

    <div class="ge-grid">
      <article class="ge-card">
        <h3 id="combined">Combined F1 <a class="anchor-link" href="#combined" aria-label="Link to Combined F1">🔗</a></h3>
        <div class="row"><span class="lab">F1 (combined)</span><span class="val"><?php echo $f1!==null? esc_html(number_format($f1,2)).' Hz' : '—'; ?></span></div>
        <div class="row"><span class="lab">Δ (24h)</span><span class="val"><?php echo $delta!==null? esc_html(number_format($delta,2)).' Hz' : '—'; ?></span></div>
        <?php if ($method): ?><div class="note">Method: <?php echo esc_html($method); ?><?php if($primary) echo ' • primary: '.esc_html(ucfirst($primary)); ?></div><?php endif; ?>
      </article>

      <article class="ge-card">
        <h3 id="images">Source Images <a class="anchor-link" href="#images" aria-label="Link to Source Images">🔗</a></h3>
        <div class="img-grid">
          <?php foreach (['tomsk','cumiana','heartmath'] as $k): if (!empty($sources[$k]['image'])): ?>
            <figure class="img-box">
              <img src="<?php echo esc_url($sources[$k]['image']); ?>" alt="<?php echo esc_attr(ucfirst($k)); ?> latest plot" loading="lazy" />
              <figcaption><?php echo esc_html(ucfirst($k)); ?><?php if($sources[$k]['f1_hz']!==null) echo ' • f1 '.esc_html(number_format((float)$sources[$k]['f1_hz'],2)).' Hz'; ?></figcaption>
            </figure>
          <?php endif; endforeach; ?>
        </div>
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
      .row{display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px dashed rgba(255,255,255,.08)}
      .row .lab{opacity:.85}
      .row .val{font-weight:600}
      .note{margin-top:6px;opacity:.85}
      .img-grid{display:grid;gap:10px}
      @media(min-width:600px){.img-grid{grid-template-columns:repeat(3,1fr)}}
      .img-box{margin:0}
      .img-box img{width:100%;height:auto;border-radius:8px;border:1px solid rgba(255,255,255,.08)}
      .img-box figcaption{font-size:.85rem;opacity:.85;margin-top:4px}
      .health-list{margin:0;padding-left:18px;line-height:1.45}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
    </style>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_schumann_detail','gaiaeyes_schumann_detail_shortcode');
