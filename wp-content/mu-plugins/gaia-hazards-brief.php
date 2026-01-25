<?php
/**
 * Plugin Name: Gaia Eyes – Hazards Brief
 * Description: Front-page "Global Hazards Brief" cards sourced from the Gaia Eyes backend /v1/hazards/brief endpoint.
 * Author: Gaia Eyes
 * Version: 0.2.0
 */

if (!defined('ABSPATH')) exit;

// Ensure shared API helper is available
if (file_exists(__DIR__ . '/gaiaeyes-api-helpers.php')) {
    require_once __DIR__ . '/gaiaeyes-api-helpers.php';
}

/**
 * Render the hazards brief section.
 *
 * Expects backend endpoint /v1/hazards/brief to return:
 * {
 *   "ok": true,
 *   "generated_at": "...",
 *   "items": [
 *     {
 *       "title": "M5.8 – Off the coast of ...",
 *       "url": "https://...",
 *       "source": "usgs",
 *       "kind": "earthquake",
 *       "location": "Off the coast of ...",
 *       "severity": "M5.8",
 *       "started_at": "2025-11-24T12:34:00Z"
 *     },
 *     ...
 *   ]
 * }
 */
function gaia_hazards_brief_shortcode($atts = []) {
    $a = shortcode_atts(
        [
            'limit' => 4,
            'cache' => 10, // minutes
        ],
        $atts,
        'gaia_hazards_brief'
    );

    $limit = max(1, intval($a['limit']));
    $ttl   = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;

    $items = [];
    $generated_at = null;
    $all_items   = [];
    $sev_counts  = ['red' => 0, 'orange' => 0, 'yellow' => 0, 'info' => 0];
    $type_counts = ['earthquakes' => 0, 'cyclones' => 0, 'volcano' => 0, 'other' => 0];

    if (function_exists('gaiaeyes_http_get_json_api_cached') && defined('GAIAEYES_API_BASE')) {
        $api_base = GAIAEYES_API_BASE;
        $bearer   = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
        $dev_user = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';

        $url      = rtrim($api_base, '/') . '/v1/hazards/brief';
        $payload  = gaiaeyes_http_get_json_api_cached($url, 'ge_hazards_brief', $ttl, $bearer, $dev_user);

        if (is_array($payload) && !empty($payload['ok']) && !empty($payload['items']) && is_array($payload['items'])) {
            $all_items = $payload['items'];
            // Compute severity and type counts over the full window
            foreach ($all_items as $it) {
                $sev = isset($it['severity']) ? strtolower(trim($it['severity'])) : '';
                if ($sev !== '') {
                    if (strpos($sev, 'red') !== false) {
                        $sev_counts['red']++;
                    } elseif (strpos($sev, 'orange') !== false) {
                        $sev_counts['orange']++;
                    } elseif (strpos($sev, 'yellow') !== false) {
                        $sev_counts['yellow']++;
                    } else {
                        $sev_counts['info']++;
                    }
                } else {
                    $sev_counts['info']++;
                }

                $kind = isset($it['kind']) ? strtolower(trim($it['kind'])) : '';
                if ($kind !== '') {
                    if (strpos($kind, 'quake') !== false || strpos($kind, 'earth') !== false) {
                        $type_counts['earthquakes']++;
                    } elseif (strpos($kind, 'cyclone') !== false || strpos($kind, 'storm') !== false || strpos($kind, 'severe') !== false) {
                        $type_counts['cyclones']++;
                    } elseif (strpos($kind, 'volcano') !== false || strpos($kind, 'ash') !== false) {
                        $type_counts['volcano']++;
                    } else {
                        $type_counts['other']++;
                    }
                } else {
                    $type_counts['other']++;
                }
            }

            // Sort items so larger earthquakes and more recent events bubble up
            usort($all_items, function($a, $b) {
                $sevA = isset($a['severity']) ? strtolower(trim($a['severity'])) : '';
                $sevB = isset($b['severity']) ? strtolower(trim($b['severity'])) : '';
                $magA = 0.0;
                $magB = 0.0;
                if (preg_match('/m\\s*([0-9]+(?:\\.[0-9]+)?)/i', $sevA, $mA)) {
                    $magA = (float) $mA[1];
                }
                if (preg_match('/m\\s*([0-9]+(?:\\.[0-9]+)?)/i', $sevB, $mB)) {
                    $magB = (float) $mB[1];
                }
                if ($magA !== $magB) {
                    // Descending magnitude
                    return ($magA < $magB) ? 1 : -1;
                }
                $tA = isset($a['started_at']) ? $a['started_at'] : '';
                $tB = isset($b['started_at']) ? $b['started_at'] : '';
                // Newest first
                return strcmp($tB, $tA);
            });

            $items = array_slice($all_items, 0, $limit);
            if (!empty($payload['generated_at'])) {
                $generated_at = $payload['generated_at'];
            }
        }
    }

    ob_start();
    ?>
    <section class="gaia-hazards-brief">
      <header class="ghb-header">
        <h2>Global Hazards Brief</h2>
        <?php if ($generated_at): ?>
          <span class="ghb-updated">Updated <?php echo esc_html(str_replace('T', ' ', preg_replace('/\..+$/', '', $generated_at))); ?> UTC</span>
        <?php endif; ?>
      </header>

      <?php if (empty($items)): ?>
        <div class="ghb-card ghb-empty">
          <strong>Global Hazards:</strong> unavailable at the moment. Data feed may be delayed.
        </div>
      <?php else: ?>
        <div class="ghb-grid-summary">
          <article class="ghb-card ghb-card-summary">
            <h3>Severity (48h)</h3>
            <dl class="ghb-summary-list">
              <div><dt>RED:</dt><dd><?php echo intval($sev_counts['red']); ?></dd></div>
              <div><dt>ORANGE:</dt><dd><?php echo intval($sev_counts['orange']); ?></dd></div>
              <div><dt>YELLOW:</dt><dd><?php echo intval($sev_counts['yellow']); ?></dd></div>
              <div><dt>INFO:</dt><dd><?php echo intval($sev_counts['info']); ?></dd></div>
            </dl>
          </article>

          <article class="ghb-card ghb-card-summary">
            <h3>By Type (48h)</h3>
            <dl class="ghb-summary-list">
              <div><dt>Earthquakes:</dt><dd><?php echo intval($type_counts['earthquakes']); ?></dd></div>
              <div><dt>Cyclones/Severe:</dt><dd><?php echo intval($type_counts['cyclones']); ?></dd></div>
              <div><dt>Volcano/Ash:</dt><dd><?php echo intval($type_counts['volcano']); ?></dd></div>
              <div><dt>Other:</dt><dd><?php echo intval($type_counts['other']); ?></dd></div>
            </dl>
          </article>

          <article class="ghb-card ghb-card-highlights">
            <h3>Recent Highlights</h3>
            <ul class="ghb-highlights">
              <?php foreach ($items as $item): ?>
                <?php
                  $title    = isset($item['title']) ? trim($item['title']) : '';
                  $url      = isset($item['url']) ? trim($item['url']) : '';
                  $source   = isset($item['source']) ? trim($item['source']) : '';
                  $kind     = isset($item['kind']) ? trim($item['kind']) : '';
                  $location = isset($item['location']) ? trim($item['location']) : '';
                  $severity = isset($item['severity']) ? trim($item['severity']) : '';
                  $started  = isset($item['started_at']) ? trim($item['started_at']) : '';

                  $sev_class = 'sev-info';
                  $sev_label = strtoupper($severity ?: 'info');
                  $sev_lower = strtolower($severity);
                  if (strpos($sev_lower, 'red') !== false) {
                    $sev_class = 'sev-red';
                  } elseif (strpos($sev_lower, 'orange') !== false) {
                    $sev_class = 'sev-orange';
                  } elseif (strpos($sev_lower, 'yellow') !== false) {
                    $sev_class = 'sev-yellow';
                  }

                  $time_label = '';
                  if ($started) {
                    $time_label = str_replace('T', ' ', preg_replace('/\..+$/', '', $started)) . ' UTC';
                  }

                  // Build a compact detail line: location – type • time
                  $kind_lower = strtolower($kind);
                  $type_label = '';
                  if ($kind_lower) {
                    if (strpos($kind_lower, 'volcano') !== false) {
                      $type_label = 'Volcano';
                    } elseif (strpos($kind_lower, 'quake') !== false || strpos($kind_lower, 'earth') !== false) {
                      $type_label = 'Quake';
                    } elseif (strpos($kind_lower, 'cyclone') !== false || strpos($kind_lower, 'storm') !== false || strpos($kind_lower, 'severe') !== false) {
                      $type_label = 'Cyclone/Storm';
                    } else {
                      $type_label = ucfirst($kind_lower);
                    }
                  }
                  $detail_parts = [];
                  if ($location) {
                    $detail_parts[] = $location;
                  }
                  if ($type_label) {
                    $detail_parts[] = $type_label;
                  }
                  $detail_line = $detail_parts ? implode(' – ', $detail_parts) : '';
                  if ($time_label) {
                    $detail_line = $detail_line ? ($detail_line . ' • ' . $time_label) : $time_label;
                  }
                ?>
                <li>
                  <span class="sev-pill <?php echo esc_attr($sev_class); ?>"><?php echo esc_html($sev_label); ?></span>
                  <div class="ghb-highlight-main">
                    <?php if ($title && $url): ?>
                      <a href="<?php echo esc_url($url); ?>" target="_blank" rel="noopener"><?php echo esc_html($title); ?></a>
                    <?php elseif ($title): ?>
                      <?php echo esc_html($title); ?>
                    <?php else: ?>
                      <?php echo esc_html($location ?: 'Hazard'); ?>
                    <?php endif; ?>
                    <?php if ($detail_line): ?>
                      <div class="ghb-highlight-meta"><?php echo esc_html($detail_line); ?></div>
                    <?php endif; ?>
                  </div>
                </li>
              <?php endforeach; ?>
            </ul>
          </article>
        </div>
      <?php endif; ?>
    </section>
    <style>
      .gaia-hazards-brief{
        margin: 1.25rem 0;
      }
      .gaia-hazards-brief .ghb-header{
        display:flex;
        justify-content:space-between;
        align-items:baseline;
        margin-bottom:.75rem;
      }
      .gaia-hazards-brief .ghb-header h2{
        font-size:1.4rem;
        margin:0;
      }
      .gaia-hazards-brief .ghb-updated{
        font-size:.85rem;
        opacity:.75;
      }
      .gaia-hazards-brief .ghb-card{
        background:#111822;
        border:1px solid #24324b;
        border-radius:12px;
        padding:12px 14px;
      }
      .gaia-hazards-brief .ghb-card h3{
        font-size:1rem;
        margin:0 0 .5rem;
      }
      .gaia-hazards-brief .ghb-grid-summary{
        display:grid;
        grid-template-columns:repeat(3,minmax(0,1fr));
        gap:12px;
      }
      @media (max-width:900px){
        .gaia-hazards-brief .ghb-grid-summary{
          grid-template-columns:1fr;
        }
      }
      .ghb-summary-list{
        margin:0;
        padding:0;
      }
      .ghb-summary-list div{
        display:flex;
        justify-content:space-between;
        font-size:.9rem;
        margin-bottom:2px;
      }
      .ghb-summary-list dt{
        font-weight:600;
      }
      .ghb-summary-list dd{
        margin:0;
        font-weight:700;
      }
      .ghb-highlights{
        list-style:none;
        margin:0;
        padding:0;
      }
      .ghb-highlights li{
        display:grid;
        grid-template-columns:auto 1fr auto;
        align-items:flex-start;
        gap:8px;
        font-size:.9rem;
        padding:6px 0;
        border-bottom:1px solid rgba(255,255,255,.05);
      }
      .ghb-highlights li:last-child{
        border-bottom:none;
      }
      .sev-pill{
        display:inline-flex;
        align-items:center;
        padding:2px 8px;
        border-radius:999px;
        font-size:.75rem;
        font-weight:600;
      }
      .sev-info{
        background:#24324b;
        color:#dbe6ff;
      }
      .sev-yellow{
        background:#524f26;
        color:#ffe58a;
      }
      .sev-orange{
        background:#5a3b20;
        color:#ffd089;
      }
      .sev-red{
        background:#5a2222;
        color:#ff8787;
      }
      .ghb-highlight-main a{
        color:inherit;
        text-decoration:none;
      }
      .ghb-highlight-main a:hover{
        text-decoration:underline;
      }
      .ghb-highlight-meta{
        font-size:.8rem;
        opacity:.8;
      }
      .ghb-highlight-time{
        font-size:.8rem;
        opacity:.7;
        white-space:nowrap;
      }
      .ghb-card.ghb-empty{
        text-align:center;
        font-size:.95rem;
      }
    </style>
    <?php
    return ob_get_clean();
}
add_shortcode('gaia_hazards_brief', 'gaia_hazards_brief_shortcode');

/**
 * Optional: Auto-insert hazards brief on the front page when GAIA_HAZARDS_AUTO_HOME is true.
 * By default, this plugin is shortcode-only:
 *   [gaia_hazards_brief limit="4"]
 * To re-enable automatic insertion on the homepage, add to wp-config.php:
 *   define('GAIA_HAZARDS_AUTO_HOME', true);
 */
if (defined('GAIA_HAZARDS_AUTO_HOME') && GAIA_HAZARDS_AUTO_HOME) {
    function gaia_hazards_auto_insert($content) {
        if (is_admin() || !in_the_loop() || !is_main_query()) {
            return $content;
        }

        if (!function_exists('is_front_page') || !is_front_page()) {
            return $content;
        }

        if (function_exists('has_shortcode') && has_shortcode($content, 'gaia_hazards_brief')) {
            return $content;
        }

        return do_shortcode('[gaia_hazards_brief]') . $content;
    }
    add_filter('the_content', 'gaia_hazards_auto_insert');
}