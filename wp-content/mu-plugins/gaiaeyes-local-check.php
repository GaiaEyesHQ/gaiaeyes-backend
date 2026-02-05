<?php
/**
 * Plugin Name: Gaia Eyes – Local Health Check
 * Description: Renders a local health snapshot from the backend /v1/local/check endpoint.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
  exit;
}

require_once __DIR__ . '/gaiaeyes-api-helpers.php';

if (!defined('GAIAEYES_API_BASE')) {
  $api_base = getenv('GAIAEYES_API_BASE');
  define('GAIAEYES_API_BASE', $api_base ? rtrim(esc_url_raw($api_base), '/') : '');
}
if (!defined('GAIAEYES_API_BEARER')) {
  $api_bearer = getenv('GAIAEYES_API_BEARER');
  define('GAIAEYES_API_BEARER', $api_bearer ? trim($api_bearer) : '');
}
if (!defined('GAIAEYES_API_DEV_USERID')) {
  $api_dev = getenv('GAIAEYES_API_DEV_USERID');
  define('GAIAEYES_API_DEV_USERID', $api_dev ? trim($api_dev) : '');
}

function gaiaeyes_local_value($value, $suffix = '') {
  if ($value === null || $value === '' || $value === false) {
    return '—';
  }
  if (is_numeric($value)) {
    $value = number_format_i18n((float)$value, 1);
  }
  return $suffix ? $value . ' ' . $suffix : (string)$value;
}

add_shortcode('gaia_local_check', function ($atts) {
  $a = shortcode_atts([
    'zip' => '78209',
    'cache' => 10,
    'api_base' => GAIAEYES_API_BASE,
    'api_bearer' => GAIAEYES_API_BEARER,
    'api_dev_userid' => GAIAEYES_API_DEV_USERID,
  ], $atts, 'gaia_local_check');

  $zip = preg_replace('/[^0-9A-Za-z]/', '', (string)$a['zip']);
  $api_base = trim((string)$a['api_base']);
  if (!$api_base || !$zip) {
    return '<div class="ge-card">Local health unavailable.</div>';
  }

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $endpoint = rtrim($api_base, '/') . '/v1/local/check?zip=' . rawurlencode($zip);
  $cache_key = 'gaia_local_' . md5($endpoint);
  $payload = gaiaeyes_http_get_json_api_cached(
    $endpoint,
    $cache_key,
    $ttl,
    (string)$a['api_bearer'],
    (string)$a['api_dev_userid']
  );

  if (!is_array($payload) || empty($payload['ok'])) {
    return '<div class="ge-card">Local health unavailable.</div>';
  }

  $weather = $payload['weather'] ?? [];
  $air = $payload['air'] ?? [];
  $moon = $payload['moon'] ?? [];

  $temp = gaiaeyes_local_value($weather['temp_c'] ?? null, '°C');
  $temp_delta = gaiaeyes_local_value($weather['temp_delta_24h_c'] ?? null, '°C');
  $humidity = gaiaeyes_local_value($weather['humidity_pct'] ?? null, '%');
  $precip = gaiaeyes_local_value($weather['precip_prob_pct'] ?? null, '%');

  $aqi = gaiaeyes_local_value($air['aqi'] ?? null);
  $aqi_category = gaiaeyes_local_value($air['category'] ?? null);
  $pollutant = gaiaeyes_local_value($air['pollutant'] ?? null);

  $moon_phase = gaiaeyes_local_value($moon['phase'] ?? null);
  $moon_illum = gaiaeyes_local_value($moon['illum'] ?? null, '%');

  ob_start();
  ?>
  <section class="ge-panel ge-local-health">
    <h3>Local Health (<?php echo esc_html($zip); ?>)</h3>
    <div class="ge-grid">
      <div class="ge-card">
        <h4>Weather</h4>
        <div class="ge-row"><span>Temp</span><strong><?php echo esc_html($temp); ?></strong></div>
        <div class="ge-row"><span>24h Δ</span><strong><?php echo esc_html($temp_delta); ?></strong></div>
        <div class="ge-row"><span>Humidity</span><strong><?php echo esc_html($humidity); ?></strong></div>
        <div class="ge-row"><span>Precip</span><strong><?php echo esc_html($precip); ?></strong></div>
      </div>
      <div class="ge-card">
        <h4>Air Quality</h4>
        <div class="ge-row"><span>AQI</span><strong><?php echo esc_html($aqi); ?></strong></div>
        <div class="ge-row"><span>Category</span><strong><?php echo esc_html($aqi_category); ?></strong></div>
        <div class="ge-row"><span>Pollutant</span><strong><?php echo esc_html($pollutant); ?></strong></div>
      </div>
      <div class="ge-card">
        <h4>Moon</h4>
        <div class="ge-row"><span>Phase</span><strong><?php echo esc_html($moon_phase); ?></strong></div>
        <div class="ge-row"><span>Illumination</span><strong><?php echo esc_html($moon_illum); ?></strong></div>
      </div>
    </div>
    <style>
      .ge-local-health .ge-grid { display: grid; gap: 12px; }
      @media (min-width: 900px) { .ge-local-health .ge-grid { grid-template-columns: repeat(3, 1fr); } }
      .ge-local-health .ge-card { padding: 16px; border-radius: 12px; background: rgba(20, 20, 20, 0.6); }
      .ge-local-health .ge-row { display: flex; justify-content: space-between; margin-top: 6px; }
      .ge-local-health h4 { margin-bottom: 8px; }
    </style>
  </section>
  <?php
  return ob_get_clean();
});
