<?php
/**
 * Plugin Name: Gaia Eyes – Aurora Detail
 * Description: Scientific Aurora detail page with Ovation map(s), forecast headline, confidence, alerts, and photo tips.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) exit;

if (!defined('GAIAEYES_SW_JSON')) {
  define('GAIAEYES_SW_JSON', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_weather.json');
}
if (!defined('GAIAEYES_SW_JSON_MIRROR')) {
  define('GAIAEYES_SW_JSON_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/space_weather.json');
}
if (!defined('GAIAEYES_OVATION_NH')) {
  define('GAIAEYES_OVATION_NH', 'https://services.swpc.noaa.gov/images/aurora-forecast-northern-hemisphere.jpg');
}
if (!defined('GAIAEYES_OVATION_SH')) {
  define('GAIAEYES_OVATION_SH', 'https://services.swpc.noaa.gov/images/aurora-forecast-southern-hemisphere.jpg');
}

function gaiaeyes_fetch_json_fallback($primary, $mirror, $cache_key, $ttl){
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

function gaiaeyes_aurora_detail_shortcode($atts){
  $a = shortcode_atts([
    'sw_url'     => GAIAEYES_SW_JSON,
    'which'      => 'both', // nh|sh|both
    'ovation_nh' => GAIAEYES_OVATION_NH,
    'ovation_sh' => GAIAEYES_OVATION_SH,
    'cache'      => 10,
  ], $atts, 'gaia_aurora_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $sw = gaiaeyes_fetch_json_fallback($a['sw_url'], GAIAEYES_SW_JSON_MIRROR, 'ge_sw_aurora', $ttl);

  $ts = is_array($sw) && !empty($sw['timestamp_utc']) ? $sw['timestamp_utc'] : '';
  $next = is_array($sw) && !empty($sw['next_72h']) ? $sw['next_72h'] : [];
  $hl   = is_array($next) && !empty($next['headline'])   ? (string)$next['headline']   : '';
  $conf = is_array($next) && !empty($next['confidence']) ? (string)$next['confidence'] : '';
  $alerts = is_array($sw) && !empty($sw['alerts']) ? (array)$sw['alerts'] : [];

  $show_nh = in_array(strtolower($a['which']), ['nh','both'], true);
  $show_sh = in_array(strtolower($a['which']), ['sh','both'], true);

  ob_start(); ?>
  <section class="ge-aur ge-panel">
    <header class="ge-head">
      <h2>Aurora – Scientific Detail</h2>
      <div class="ge-meta">Updated <?php echo esc_html( $ts ?: '—' ); ?></div>
    </header>

    <div class="ge-chips">
      <?php if ($hl): ?><span class="chip chip-aurora"><strong>Aurora:</strong> <?php echo esc_html($hl); ?></span><?php endif; ?>
      <?php if ($conf): ?><span class="chip"><strong>Confidence:</strong> <?php echo esc_html($conf); ?></span><?php endif; ?>
      <?php if ($alerts): ?><span class="chip"><strong>Alerts:</strong> <?php echo esc_html(implode(', ', $alerts)); ?></span><?php endif; ?>
    </div>

    <div class="ge-grid">
      <article class="ge-card">
        <h3 id="map">Ovation Forecast Map <a class="anchor-link" href="#map" aria-label="Link to Ovation Forecast Map">🔗</a></h3>
        <div class="ovation-grid">
          <?php if ($show_nh): ?>
          <figure class="ov-box">
            <img src="<?php echo esc_url($a['ovation_nh']); ?>" alt="Ovation Aurora Forecast – Northern Hemisphere" loading="lazy" />
            <figcaption>Northern Hemisphere</figcaption>
          </figure>
          <?php endif; ?>
          <?php if ($show_sh): ?>
          <figure class="ov-box">
            <img src="<?php echo esc_url($a['ovation_sh']); ?>" alt="Ovation Aurora Forecast – Southern Hemisphere" loading="lazy" />
            <figcaption>Southern Hemisphere</figcaption>
          </figure>
          <?php endif; ?>
        </div>
      </article>

      <article class="ge-card">
        <h3 id="forecast">Next 72h <a class="anchor-link" href="#forecast" aria-label="Link to Next 72h">🔗</a></h3>
        <ul class="ge-list">
          <li><strong>Headline:</strong> <?php echo $hl ? esc_html($hl) : '—'; ?></li>
          <li><strong>Confidence:</strong> <?php echo $conf ? esc_html($conf) : '—'; ?></li>
          <li><strong>Plain-language impacts:</strong> See GPS/Comms/Grids/Aurora in Space Weather detail.</li>
        </ul>
      </article>

      <article class="ge-card">
        <h3 id="photo-tips">Capture Tips <a class="anchor-link" href="#photo-tips" aria-label="Link to Capture Tips">🔗</a></h3>
        <ul class="ge-list">
          <li>Use a wide lens (14–24mm), ISO 1600–3200, 4–6s exposures to start; shoot RAW.</li>
          <li>Manual focus on a bright star; turn off image stabilization on a tripod.</li>
          <li>Dark skies, minimal moonlight, and a stable horizon help visibility.</li>
        </ul>
      </article>

      <article class="ge-card">
        <h3 id="about">About Aurora <a class="anchor-link" href="#about" aria-label="Link to About Aurora">🔗</a></h3>
        <p>Aurora activity is driven by the solar wind and interplanetary magnetic field (Bz). When Bz turns southward and wind speeds increase, coupling with Earth’s magnetosphere rises, increasing auroral probability—especially near local midnight at high latitudes.</p>
      </article>
    </div>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-head h2{margin:0;font-size:1.15rem}
      .ge-meta{opacity:.8;font-size:.9rem}
      .ge-chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
      .chip{display:inline-block;background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:999px;padding:3px 10px;font-size:.78rem;line-height:1}
      .chip-aurora{background:#1b2a22;color:#aef2c0;border-color:#2d624a}
      .ge-grid{display:grid;gap:12px}
      @media(min-width:900px){.ge-grid{grid-template-columns:repeat(2,1fr)}}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px}
      .ge-list{margin:0;padding-left:18px;line-height:1.45}
      .ovation-grid{display:grid;gap:10px}
      @media(min-width:600px){.ovation-grid{grid-template-columns:repeat(2,1fr)}}
      .ov-box{margin:0}
      .ov-box img{width:100%;height:auto;border-radius:8px;border:1px solid rgba(255,255,255,.08)}
      .ov-box figcaption{font-size:.85rem;opacity:.85;margin-top:4px}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
    </style>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_aurora_detail','gaiaeyes_aurora_detail_shortcode');