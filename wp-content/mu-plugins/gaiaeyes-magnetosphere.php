<?php
/**
 * Plugin Name: Gaia Eyes – Magnetosphere Card
 * Description: Renders a Magnetosphere Status card from gaiaeyes-media/data/magnetosphere_latest.json
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

if (!defined('GAIAEYES_MAGNETO_JSON_URL')) {
  // You can override via wp-config.php if needed
  define('GAIAEYES_MAGNETO_JSON_URL', 'https://cdn.jsdelivr.net/gh/gaiaeyeshq/gaiaeyes-media@main/data/magnetosphere_latest.json');
}
define('GAIAEYES_MAGNETO_CACHE_KEY', 'gaiaeyes_magneto_latest_json');
define('GAIAEYES_MAGNETO_TTL', 10 * MINUTE_IN_SECONDS); // cache 10 min

function gaiaeyes_fetch_magneto_json($url = '') {
  $url = $url ?: GAIAEYES_MAGNETO_JSON_URL;
  $cached = get_transient(GAIAEYES_MAGNETO_CACHE_KEY);
  if ($cached !== false) return $cached;

  $resp = wp_remote_get($url, [
    'timeout' => 10,
    'headers' => ['Accept' => 'application/json']
  ]);

  if (is_wp_error($resp)) return null;
  $code = wp_remote_retrieve_response_code($resp);
  if ($code !== 200) return null;

  $body = wp_remote_retrieve_body($resp);
  $data = json_decode($body, true);
  if (!is_array($data)) return null;

  set_transient(GAIAEYES_MAGNETO_CACHE_KEY, $data, GAIAEYES_MAGNETO_TTL);
  return $data;
}

function gaiaeyes_fetch_magneto_data($override_url = '') {
  // Prefer API-backed data when available; fall back to static JSON if needed.
  if (!empty($override_url)) {
    return gaiaeyes_fetch_magneto_json($override_url);
  }

  $api_base   = defined('GAIAEYES_API_BASE') ? rtrim(GAIAEYES_API_BASE, '/') : '';
  $api_bearer = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
  $api_dev    = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';

  if ($api_base && function_exists('gaiaeyes_http_get_json_api_cached')) {
    $payload = gaiaeyes_http_get_json_api_cached(
      $api_base . '/v1/space/magnetosphere',
      'ge_magnetosphere_api',
      GAIAEYES_MAGNETO_TTL,
      $api_bearer,
      $api_dev
    );
    if (is_array($payload) && !empty($payload['ok']) && !empty($payload['data'])) {
      return $payload['data'];
    }
  }

  // Fallback: legacy JSON from the static URL
  return gaiaeyes_fetch_magneto_json();
}

function gaiaeyes_badge($label, $value, $class = '') {
  $label_esc = esc_html($label);
  $value_esc = esc_html($value);
  $class_esc = esc_attr($class);
  return "<span class='ge-badge {$class_esc}'><strong>{$label_esc}:</strong> {$value_esc}</span>";
}

/**
 * Shortcode: [gaia_magnetosphere url="https://.../magnetosphere_latest.json"]
 */
function gaiaeyes_magnetosphere_shortcode($atts) {
  $atts = shortcode_atts([
    'url'  => '',
    'link' => '', // optional, e.g., /magnetosphere/
  ], $atts, 'gaia_magnetosphere');

  $data = gaiaeyes_fetch_magneto_data($atts['url']);

  $open_a = $close_a = '';
  if (!empty($atts['link'])) {
    $href = esc_url($atts['link']);
    $open_a  = "<a class='ge-card-link' href='{$href}'>";
    $close_a = "</a>";
  }

  if (!$data || empty($data['kpis']) || !is_array($data['kpis'])) {
    return $open_a . "<div class='ge-card ge-magneto'><p>Magnetosphere data unavailable.</p></div>" . $close_a;
  }

  $ts     = isset($data['ts']) ? esc_html($data['ts']) : '';
  $kpis   = $data['kpis'];
  $trend  = isset($data['trend']['r0']) ? sanitize_text_field($data['trend']['r0']) : 'flat';
  $r0     = (isset($kpis['r0_re']) && $kpis['r0_re'] !== null) ? number_format_i18n(floatval($kpis['r0_re']), 1) . ' Rᴇ' : '—';
  $geo    = isset($kpis['geo_risk']) ? sanitize_text_field($kpis['geo_risk']) : 'unknown';
  $storm  = isset($kpis['storminess']) ? sanitize_text_field($kpis['storminess']) : 'unknown';
  $dbdt   = isset($kpis['dbdt']) ? sanitize_text_field($kpis['dbdt']) : 'unknown';
  $kp     = (isset($kpis['kp']) && $kpis['kp'] !== null) ? number_format_i18n(floatval($kpis['kp']), 1) : '—';
  $lpp    = (isset($kpis['lpp_re']) && $kpis['lpp_re'] !== null) ? number_format_i18n(floatval($kpis['lpp_re']), 1) . ' Rᴇ' : '—';

  $state = ($kpis['r0_re'] !== null && floatval($kpis['r0_re']) < 8.0) ? 'Compressed' : 'Expanded';
  $headline = "Magnetosphere: {$state} (r₀ {$r0}) • GEO risk: " . esc_html($geo);

  $badges  = gaiaeyes_badge('Storminess', $storm, 'ge-badge--storm');
  $badges .= gaiaeyes_badge('GIC feel', $dbdt, 'ge-badge--gic');
  $badges .= gaiaeyes_badge('Kp', $kp, 'ge-badge--kp');
  $badges .= gaiaeyes_badge('Plasmapause L', $lpp, 'ge-badge--lpp');
  $badges .= gaiaeyes_badge('Trend r₀', $trend, 'ge-badge--trend');

  $tips = '';
  $storm_l = strtolower($storm);
  if ($geo === 'elevated' || $storm_l === 'storm' || $storm_l === 'strong_storm') {
    $tips = "<ul class='ge-tips'>
      <li>Keep plans flexible; sensitivity/sleep shifts are common.</li>
      <li>Prioritize grounding, hydration, and shorter deep-work blocks.</li>
      <li>If GNSS/comms matter, double-check local conditions.</li>
    </ul>";
  }

  ob_start(); ?>
  <?php echo $open_a; ?>
  <div class="ge-card ge-magneto" data-ts="<?php echo $ts; ?>">
    <div class="ge-header">
      <h3><?php echo esc_html($headline); ?></h3>
      <div class="ge-badges"><?php echo $badges; ?></div>
    </div>
    <?php echo $tips; ?>
    <div class="ge-footnote">Updated <?php echo esc_html($ts); ?></div>
  </div>
  <?php echo $close_a; ?>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_magnetosphere', 'gaiaeyes_magnetosphere_shortcode');

/**
 * Shortcode: [gaia_magnetosphere_detail url="..."]
 * Renders a larger detail panel; safe even if no series present.
 */
function gaiaeyes_magnetosphere_detail_shortcode($atts) {
  $atts = shortcode_atts([
    'url' => '', // optional override
  ], $atts, 'gaia_magnetosphere_detail');

  $data = gaiaeyes_fetch_magneto_data($atts['url']);
  if (!$data || empty($data['kpis']) || !is_array($data['kpis'])) {
    return "<div class='ge-card ge-magneto'><p>Magnetosphere data unavailable.</p></div>";
  }

  $ts   = isset($data['ts']) ? esc_html($data['ts']) : '';
  $kpis = $data['kpis'];
  $trend  = isset($data['trend']['r0']) ? sanitize_text_field($data['trend']['r0']) : 'flat';

  $r0_raw  = isset($kpis['r0_re']) ? floatval($kpis['r0_re']) : null;
  $kp_raw  = isset($kpis['kp']) ? floatval($kpis['kp']) : null;
  $lpp_raw = isset($kpis['lpp_re']) ? floatval($kpis['lpp_re']) : null;

  $r0     = ($r0_raw !== null) ? number_format_i18n($r0_raw, 2) . ' Rᴇ' : '—';
  $geo    = isset($kpis['geo_risk']) ? sanitize_text_field($kpis['geo_risk']) : 'unknown';
  $storm  = isset($kpis['storminess']) ? sanitize_text_field($kpis['storminess']) : 'unknown';
  $dbdt   = isset($kpis['dbdt']) ? sanitize_text_field($kpis['dbdt']) : 'unknown';
  $kp     = ($kp_raw !== null) ? number_format_i18n($kp_raw, 1) : '—';
  $lpp    = ($lpp_raw !== null) ? number_format_i18n($lpp_raw, 2) . ' Rᴇ' : '—';

  // Badge alert classes
  $geo_l   = strtolower($geo);
  $storm_l = strtolower($storm);
  $trend_l = strtolower($trend);

  $geo_class   = 'ge-badge--geo'   . (($geo_l === 'elevated' || $geo_l === 'watch') ? ' ge-badge--alert' : '');
  $storm_class = 'ge-badge--storm' . (in_array($storm_l, ['storm','strong_storm']) ? ' ge-badge--alert' : '');
  $kp_class    = 'ge-badge--kp'    . (($kp_raw !== null && $kp_raw >= 5.0) ? ' ge-badge--alert' : '');

  // Gaia Eyes style summary sentence
  $state_phrase = 'typical';
  if ($r0_raw !== null) {
    if ($r0_raw < 8.0) {
      $state_phrase = 'slightly compressed';
    } elseif ($r0_raw > 10.0) {
      $state_phrase = 'more expanded than usual';
    } else {
      $state_phrase = 'near its typical size';
    }
  }
  $kp_phrase = 'baseline';
  if ($kp_raw !== null) {
    if ($kp_raw >= 6.0) {
      $kp_phrase = 'strongly elevated';
    } elseif ($kp_raw >= 4.0) {
      $kp_phrase = 'a little edgy';
    }
  }
  $geo_phrase = ($geo_l === 'low') ? 'baseline' : $geo_l;
  $storm_phrase = ($storm_l === 'quiet') ? 'calm' : $storm_l;
  $trend_phrase = $trend_l;
  if ($trend_l === 'rising') {
    $trend_phrase = 'slowly relaxing outward';
  } elseif ($trend_l === 'falling') {
    $trend_phrase = 'gradually tightening inward';
  }

  $mag_summary = sprintf(
    'Today the magnetosphere looks %s with GEO risk %s and storminess %s. Kp is %s, so the shield edge is %s.',
    $state_phrase,
    $geo_phrase,
    $storm_phrase,
    $kp_phrase,
    $trend_phrase
  );

  // Media base for visuals
  $media_base = defined('GAIA_MEDIA_BASE') ? rtrim(GAIA_MEDIA_BASE, '/') : '';
  $enlil_img   = $media_base ? $media_base . '/nasa/enlil/latest.jpg' : '';
  $enlil_video = $media_base ? $media_base . '/nasa/enlil/latest.mp4' : '';
  $geospace_3h = $media_base ? $media_base . '/magnetosphere/geospace/3h.png' : '';
  $geospace_1d = $media_base ? $media_base . '/magnetosphere/geospace/1d.png' : '';
  $geospace_7d = $media_base ? $media_base . '/magnetosphere/geospace/7d.png' : '';

  ob_start(); ?>
  <section class="ge-detail ge-magneto-detail">
    <header class="ge-detail__head">
      <div class="ge-detail__title">
        <div class="ge-detail__meta">Updated <?php echo $ts; ?></div>
      </div>
      <div class="ge-detail__chips ge-badges">
        <?php echo gaiaeyes_badge('GEO', $geo, $geo_class); ?>
        <?php echo gaiaeyes_badge('Storm', $storm, $storm_class); ?>
        <?php echo gaiaeyes_badge('Kp', $kp, $kp_class); ?>
      </div>
    </header>

    <div class="ge-detail__grid">
      <div class="ge-card ge-detail__card">
        <h3>Magnetosphere snapshot</h3>
        <p class="ge-detail__lede">Here&rsquo;s how Earth&rsquo;s magnetic shield is behaving right now:</p>
        <ul class="ge-detail__list">
          <li><strong title="Distance to the sun-facing edge of the magnetosphere. Lower values mean the shield is pushed closer to Earth.">Shield size (r₀):</strong> <?php echo $r0; ?></li>
          <li><strong title="Approximate inner edge of the outer radiation belt.">Plasmapause L:</strong> <?php echo $lpp; ?></li>
          <li><strong title="Overall level of geomagnetic disturbance.">Geomagnetic risk:</strong> <?php echo esc_html($geo); ?></li>
          <li><strong title="How unsettled the magnetosphere is at the moment.">Storminess:</strong> <?php echo esc_html($storm); ?></li>
          <li><strong title="Rough feel for how strongly power grids might be shaken by changing currents.">Grid stress (dB/dt):</strong> <?php echo esc_html($dbdt); ?></li>
          <li><strong title="Planetary Kp index; higher values mean stronger geomagnetic activity.">Kp index:</strong> <?php echo $kp; ?></li>
          <li><strong title="Whether the shield edge is mostly steady, expanding, or compressing.">r₀ trend:</strong> <?php echo esc_html($trend); ?></li>
        </ul>
      </div>

      <div class="ge-card ge-detail__card">
        <h3>Why this matters today</h3>
        <p class="ge-detail__lede"><?php echo esc_html($mag_summary); ?></p>
        <ul class="ge-detail__list">
          <li><strong>For technology:</strong> Low to moderate levels generally mean GPS, radio, and power grids operate normally, with only minor tweaks needed during stronger storms.</li>
          <li><strong>For auroras:</strong> When storminess and Kp rise, auroras can dip farther from the poles and night skies become more active.</li>
          <li><strong>For sensitivity:</strong> Some people report mood, focus, or sleep shifts on more disturbed days; today’s level is a good cue for how gently to pace yourself.</li>
        </ul>
      </div>

      <div class="ge-card ge-detail__card">
        <h3>What “compressed” vs “expanded” means</h3>
        <p>The dayside magnetopause distance (r₀ in Earth radii, Rᴇ) describes how far Earth&rsquo;s magnetic shield sits from the planet on the Sun-facing side. Strong solar-wind pressure pushes r₀ inward (compressed), while quiet conditions let it relax outward (expanded).</p>
        <ul>
          <li><strong>r₀ &lt; 8 Rᴇ:</strong> compressed &mdash; stronger coupling, higher chance of disturbances.</li>
          <li><strong>~10 Rᴇ:</strong> typical &mdash; everyday background conditions.</li>
          <li><strong>&gt; 10 Rᴇ:</strong> expanded &mdash; shield sitting farther out than usual.</li>
        </ul>
        <p class="ge-detail__hint">You can think of r₀ as how “puffed up” or “squeezed” Earth&rsquo;s magnetic bubble is at the moment.</p>
      </div>
    </div>

    <?php if ( !empty($data['series']) && is_array($data['series']['r0'] ?? null) ): ?>
      <div class="ge-card ge-detail__card ge-magneto-trend">
        <h3>r₀ trend &amp; visuals</h3>
        <div class="ge-magneto-trend-layout">
          <div class="ge-magneto-trend-chart">
            <canvas id="geR0Chart" height="120" style="max-height: 200px; width: 100%;"></canvas>
          </div>
          <?php if ( $media_base ): ?>
          <div class="ge-magneto-trend-visuals">
          <?php if ( $enlil_img ): ?>
            <div class="ge-magneto-visual">
              <h4>Enlil forecast</h4>
              <?php if ( $enlil_video ): ?>
                <video class="ge-magneto-video" poster="<?php echo esc_url($enlil_img); ?>" controls playsinline>
                  <source src="<?php echo esc_url($enlil_video); ?>" type="video/mp4">
                  <img src="<?php echo esc_url($enlil_img); ?>" alt="Latest Enlil solar-wind forecast" />
                </video>
                <p class="ge-detail__hint">Tap play to watch the latest model run. Use the fullscreen control in the player to expand.</p>
              <?php else: ?>
                <a href="<?php echo esc_url($enlil_img); ?>" target="_blank" rel="noopener">
                  <img src="<?php echo esc_url($enlil_img); ?>" alt="Latest Enlil solar-wind forecast" />
                </a>
              <?php endif; ?>
            </div>
          <?php endif; ?>
            <div class="ge-magneto-visual">
              <h4>Geospace response</h4>
              <div class="ge-magneto-geospace-set">
                <?php if ( $geospace_3h ): ?>
                  <figure>
                    <a href="<?php echo esc_url($geospace_3h); ?>" target="_blank" rel="noopener">
                      <img src="<?php echo esc_url($geospace_3h); ?>" alt="Geospace disturbance (last 3 hours)" />
                    </a>
                    <figcaption>3 hours</figcaption>
                  </figure>
                <?php endif; ?>
                <?php if ( $geospace_1d ): ?>
                  <figure>
                    <a href="<?php echo esc_url($geospace_1d); ?>" target="_blank" rel="noopener">
                      <img src="<?php echo esc_url($geospace_1d); ?>" alt="Geospace disturbance (last 1 day)" />
                    </a>
                    <figcaption>1 day</figcaption>
                  </figure>
                <?php endif; ?>
                <?php if ( $geospace_7d ): ?>
                  <figure>
                    <a href="<?php echo esc_url($geospace_7d); ?>" target="_blank" rel="noopener">
                      <img src="<?php echo esc_url($geospace_7d); ?>" alt="Geospace disturbance (last 7 days)" />
                    </a>
                    <figcaption>7 days</figcaption>
                  </figure>
                <?php endif; ?>
              </div>
            </div>
          </div>
          <?php endif; ?>
        </div>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
      <script>
      (function(){
        const fullSeries = <?php echo wp_json_encode($data['series']['r0']); ?>;
        // Downsample to a maximum of ~60 points so the chart remains compact and readable,
        // but always include first/last and true min/max points so variation is visible.
        const maxPoints = 60;
        let series = fullSeries;
        if (Array.isArray(fullSeries) && fullSeries.length > maxPoints) {
          let minIdx = 0;
          let maxIdx = 0;
          let minVal = Number.POSITIVE_INFINITY;
          let maxVal = Number.NEGATIVE_INFINITY;

          for (let i = 0; i < fullSeries.length; i++) {
            const v = Number(fullSeries[i].v);
            if (!isFinite(v)) continue;
            if (v < minVal) { minVal = v; minIdx = i; }
            if (v > maxVal) { maxVal = v; maxIdx = i; }
          }

          const importantIdx = new Set([0, fullSeries.length - 1, minIdx, maxIdx]);
          const remainingSlots = Math.max(maxPoints - importantIdx.size, 0);
          const step = remainingSlots > 0 ? Math.ceil(fullSeries.length / remainingSlots) : fullSeries.length;

          for (let i = 0; i < fullSeries.length && importantIdx.size < maxPoints; i += step) {
            importantIdx.add(i);
          }

          const sortedIdx = Array.from(importantIdx).sort((a, b) => a - b);
          series = sortedIdx.map(idx => fullSeries[idx]);
        }

        const lab = series.map(x => {
          try {
            const d = new Date(x.t);
            return d.toISOString().slice(11,16); // HH:MM
          } catch (e) {
            return x.t;
          }
        });
        const val = series.map(x => x.v);

        let yMin = null;
        let yMax = null;
        for (let i = 0; i < val.length; i++) {
          const v = Number(val[i]);
          if (!isFinite(v)) continue;
          if (yMin === null || v < yMin) yMin = v;
          if (yMax === null || v > yMax) yMax = v;
        }
        if (yMin === null || yMax === null) {
          yMin = 6;
          yMax = 15;
        } else {
          const padding = (yMax - yMin) * 0.2 || 0.2;
          yMin = yMin - padding;
          yMax = yMax + padding;
        }

        const ctx = document.getElementById('geR0Chart').getContext('2d');
        new Chart(ctx, {
          type: 'line',
          data: {
            labels: lab,
            datasets: [{
              label: 'r₀ (Rᴇ)',
              data: val,
              borderColor: '#7fc8ff',
              tension: 0.25,
              pointRadius: 0
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
              x: {
                ticks: { color: '#cfe3ff' },
                grid: { color: 'rgba(207,227,255,0.1)' }
              },
              y: {
                ticks: { color: '#cfe3ff' },
                grid: { color: 'rgba(207,227,255,0.1)' },
                min: yMin,
                max: yMax
              }
            },
            plugins: {
              legend: { labels: { color: '#cfe3ff' } }
            }
          }
        });
      })();
      </script>
    <?php endif; ?>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_magnetosphere_detail','gaiaeyes_magnetosphere_detail_shortcode');

function gaiaeyes_magnetosphere_styles() {
  ?>
  <style>
    .ge-magneto-detail .ge-badges .ge-badge,
    .ge-magneto .ge-badges .ge-badge {
      background: rgba(255,255,255,0.08);
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 0.85rem;
    }
    .ge-magneto-detail .ge-badge--alert,
    .ge-magneto .ge-badge--alert {
      background: #c0392b;
      color: #fff;
    }
    .ge-magneto-detail .ge-detail__grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
    }
    @media (min-width: 960px) {
      .ge-magneto-detail .ge-detail__grid {
        grid-template-columns: repeat(3, minmax(0,1fr));
      }
    }
    .ge-magneto-trend .ge-magneto-trend-layout {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    @media (min-width: 960px) {
      .ge-magneto-trend .ge-magneto-trend-layout {
        flex-direction: row;
      }
      .ge-magneto-trend-chart,
      .ge-magneto-trend-visuals {
        flex: 1;
      }
    }
    .ge-magneto-trend-visuals img,
    .ge-magneto-trend-visuals .ge-magneto-video {
      display: block;
      width: 100%;
      height: auto;
      border-radius: 8px;
      margin-bottom: 8px;
    }
    .ge-magneto-visual + .ge-magneto-visual {
      margin-top: 12px;
    }
    .ge-magneto-geospace-set {
      display: grid;
      grid-template-columns: repeat(3, minmax(0,1fr));
      gap: 8px;
    }
    .ge-magneto-geospace-set figure {
      margin: 0;
      text-align: center;
      font-size: 0.8rem;
      color: #cfe3ff;
    }
  </style>
  <?php
}
add_action('wp_head','gaiaeyes_magnetosphere_styles');