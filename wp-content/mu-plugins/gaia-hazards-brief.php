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

    if (function_exists('gaiaeyes_http_get_json_api_cached') && defined('GAIAEYES_API_BASE')) {
        $api_base = GAIAEYES_API_BASE;
        $bearer   = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
        $dev_user = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';

        $url      = rtrim($api_base, '/') . '/v1/hazards/brief';
        $payload  = gaiaeyes_http_get_json_api_cached($url, 'ge_hazards_brief', $ttl, $bearer, $dev_user);

        if (is_array($payload) && !empty($payload['ok']) && !empty($payload['items']) && is_array($payload['items'])) {
            $items = array_slice($payload['items'], 0, $limit);
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
        <div class="ghb-grid">
          <?php foreach ($items as $item): ?>
            <?php
              $title    = isset($item['title']) ? trim($item['title']) : '';
              $url      = isset($item['url']) ? trim($item['url']) : '';
              $source   = isset($item['source']) ? trim($item['source']) : '';
              $kind     = isset($item['kind']) ? trim($item['kind']) : '';
              $location = isset($item['location']) ? trim($item['location']) : '';
              $severity = isset($item['severity']) ? trim($item['severity']) : '';
              $started  = isset($item['started_at']) ? trim($item['started_at']) : '';

              // Basic label line
              $label_parts = [];
              if ($kind)     $label_parts[] = ucfirst($kind);
              if ($severity) $label_parts[] = $severity;
              if ($source)   $label_parts[] = strtoupper($source);
              $label = implode(' • ', $label_parts);
            ?>
            <article class="ghb-card">
              <header>
                <?php if ($title && $url): ?>
                  <h3><a href="<?php echo esc_url($url); ?>" target="_blank" rel="noopener"><?php echo esc_html($title); ?></a></h3>
                <?php elseif ($title): ?>
                  <h3><?php echo esc_html($title); ?></h3>
                <?php else: ?>
                  <h3>Hazard</h3>
                <?php endif; ?>

                <?php if ($label): ?>
                  <div class="ghb-label"><?php echo esc_html($label); ?></div>
                <?php endif; ?>
              </header>

              <?php if ($location): ?>
                <div class="ghb-location">
                  <span class="ghb-meta-label">Region:</span>
                  <span class="ghb-meta-value"><?php echo esc_html($location); ?></span>
                </div>
              <?php endif; ?>

              <?php if ($started): ?>
                <div class="ghb-time">
                  <span class="ghb-meta-label">Started:</span>
                  <span class="ghb-meta-value">
                    <?php echo esc_html(str_replace('T', ' ', preg_replace('/\..+$/', '', $started))); ?> UTC
                  </span>
                </div>
              <?php endif; ?>
            </article>
          <?php endforeach; ?>
        </div>
      <?php endif; ?>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode('gaia_hazards_brief', 'gaia_hazards_brief_shortcode');


/**
 * Auto-insert hazards brief on the front-page main query if not already present.
 */
add_filter('the_content', function ($content) {
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
});