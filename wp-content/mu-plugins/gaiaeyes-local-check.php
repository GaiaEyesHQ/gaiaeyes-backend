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

function gaiaeyes_trend_label($t) {
  $t = strtolower((string)$t);
  if ($t === 'rising') return '↑ rising';
  if ($t === 'falling') return '↓ falling';
  if ($t === 'steady') return '→ steady';
  return $t ?: '—';
}

function gaiaeyes_resolve_zip_default($atts_zip) {
  // Priority: shortcode attr > ?zip= query > user meta > cookie > fallback
  $zip_attr = preg_replace('/[^0-9A-Za-z]/', '', (string)$atts_zip);
  if ($zip_attr) return $zip_attr;

  $qzip = isset($_GET['zip']) ? preg_replace('/[^0-9A-Za-z]/', '', (string)$_GET['zip']) : '';
  if ($qzip) return $qzip;

  if (is_user_logged_in()) {
    $user_zip = get_user_meta(get_current_user_id(), 'gaiaeyes_default_zip', true);
    $user_zip = preg_replace('/[^0-9A-Za-z]/', '', (string)$user_zip);
    if ($user_zip) return $user_zip;
  }

  if (!empty($_COOKIE['gaia_zip'])) {
    $ck = preg_replace('/[^0-9A-Za-z]/', '', (string)$_COOKIE['gaia_zip']);
    if ($ck) return $ck;
  }

  return '78209';
}

add_shortcode('gaia_local_check', function ($atts) {
  $a = shortcode_atts([
    'zip' => '78209',
    'cache' => 10,
    'api_base' => GAIAEYES_API_BASE,
    'api_bearer' => GAIAEYES_API_BEARER,
    'api_dev_userid' => GAIAEYES_API_DEV_USERID,
  ], $atts, 'gaia_local_check');

  $zip = gaiaeyes_resolve_zip_default($a['zip']);
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
    $err_msg = '';
    if (is_array($payload) && !empty($payload['error'])) {
      // Show a concise reason to help users/admins understand what's wrong (e.g., zip_not_found).
      $err_msg = ' (' . esc_html( (string)$payload['error'] ) . ')';
    }
    return '<div class="ge-card">Local health unavailable' . $err_msg . '.</div>';
  }

  $weather = $payload['weather'] ?? [];
  $air = $payload['air'] ?? [];
  $moon = $payload['moon'] ?? [];

  // Optional derived health signals from backend (with client-side fallback)
  $health           = $payload['health'] ?? [];
  $health_messages  = $health['messages'] ?? [];
  $health_flags_raw = $health['flags'] ?? [];
  $health_pills     = [];

  // If backend already provided pill descriptors, prefer them
  if (isset($health['pills']) && is_array($health['pills']) && !empty($health['pills'])) {
    $health_pills = $health['pills'];
  } else {
    // If 'flags' is an associative map, translate to pills
    if (is_array($health_flags_raw) && array_keys($health_flags_raw) !== range(0, count($health_flags_raw) - 1)) {
      // AQI flag → pill
      $aqi_val  = isset($air['aqi']) ? (float)$air['aqi'] : null;
      $aqi_flag = isset($health_flags_raw['aqi_flag']) ? strtolower((string)$health_flags_raw['aqi_flag']) : null;
      if ($aqi_flag && is_numeric($aqi_val)) {
        $sev = 'ok';
        if (in_array($aqi_flag, ['unhealthy','very_unhealthy','hazardous'], true)) { $sev = 'alert'; }
        elseif (in_array($aqi_flag, ['moderate','usg'], true)) { $sev = 'elevated'; }
        $health_pills[] = ['kind' => 'aqi', 'label' => 'AQI ' . number_format_i18n($aqi_val, 0), 'severity' => $sev];
      }

      // Pressure rapid drop
      if (!empty($health_flags_raw['pressure_rapid_drop'])) {
        $health_pills[] = ['kind' => 'pressure', 'label' => 'Pressure ↓ fast', 'severity' => 'alert'];
      }

      // Big 24h temperature shift
      if (!empty($health_flags_raw['big_temp_shift_24h'])) {
        $td   = isset($weather['temp_delta_24h_c']) ? (float)$weather['temp_delta_24h_c'] : null;
        $lbl  = 'Temp Δ';
        if (is_numeric($td)) { $lbl .= ' ' . number_format_i18n($td, 1) . '°C'; }
        $health_pills[] = ['kind' => 'tempswing', 'label' => $lbl, 'severity' => 'elevated'];
      }

      // 3h trends (informational)
      if (!empty($health_flags_raw['baro_trend_3h'])) {
        $health_pills[] = ['kind' => 'baro3h', 'label' => 'Baro ' . gaiaeyes_trend_label($health_flags_raw['baro_trend_3h']), 'severity' => 'info'];
      }
      if (!empty($health_flags_raw['temp_trend_3h'])) {
        $health_pills[] = ['kind' => 'temp3h', 'label' => 'Temp ' . gaiaeyes_trend_label($health_flags_raw['temp_trend_3h']), 'severity' => 'info'];
      }

      // Moon proximity
      if (!empty($health_flags_raw['moon_sensitivity'])) {
        $health_pills[] = ['kind' => 'moon', 'label' => ($moon['phase'] ?? 'Moon'), 'severity' => 'info'];
      }
    } elseif (is_array($health_flags_raw) && !empty($health_flags_raw)) {
      // Already a list of pill descriptors
      $health_pills = $health_flags_raw;
    }
  }

  // Final fallback: derive simple pills if still empty
  if (empty($health_pills)) {
    // AQI severity
    $aqi_val = isset($air['aqi']) ? (float)$air['aqi'] : null;
    if (is_numeric($aqi_val)) {
      $sev = 'ok';
      if ($aqi_val >= 151) { $sev = 'alert'; }
      elseif ($aqi_val >= 101) { $sev = 'elevated'; }
      elseif ($aqi_val >= 51)  { $sev = 'info'; }
      $health_pills[] = ['kind' => 'aqi', 'label' => 'AQI ' . number_format_i18n($aqi_val, 0), 'severity' => $sev];
    }

    // Pressure trend / delta
    $trend    = isset($weather['pressure_trend']) ? strtolower((string)$weather['pressure_trend'])
               : (isset($weather['baro_trend']) ? strtolower((string)$weather['baro_trend']) : '');
    $delta_hp = isset($weather['baro_delta_24h_hpa']) ? (float)$weather['baro_delta_24h_hpa'] : null;
    if ($trend === 'falling' || (is_numeric($delta_hp) && $delta_hp <= -3)) {
      $sev   = (is_numeric($delta_hp) && $delta_hp <= -6) ? 'alert' : 'elevated';
      $label = 'Pressure ' . ($trend ? $trend : ($delta_hp < 0 ? '↓' : ''));
      $health_pills[] = ['kind' => 'pressure', 'label' => $label, 'severity' => $sev];
    }

    // Temperature swing (24h)
    $temp_dc = isset($weather['temp_delta_24h_c']) ? (float)$weather['temp_delta_24h_c'] : null;
    if (is_numeric($temp_dc) && abs($temp_dc) >= 8) {
      $sev = (abs($temp_dc) >= 12) ? 'alert' : 'elevated';
      $health_pills[] = ['kind' => 'tempswing', 'label' => 'Temp Δ ' . number_format_i18n($temp_dc, 1) . '°C', 'severity' => $sev];
    }

    // Moon sensitivity
    $illum = (isset($moon['illum']) && is_numeric($moon['illum'])) ? (float)$moon['illum'] : null;
    $phase = strtolower((string)($moon['phase'] ?? ''));
    if (is_numeric($illum) && ($illum >= 0.95 || $illum <= 0.05 || strpos($phase, 'full') !== false || strpos($phase, 'new') !== false)) {
      $health_pills[] = ['kind' => 'moon', 'label' => ($moon['phase'] ?? 'Moon'), 'severity' => 'info'];
    }
  }

  // Optional "as of" display (prefer actual observation timestamp if present)
  $obs_iso = isset($weather['obs_time']) ? (string)$weather['obs_time'] : null;
  $asof_raw = $obs_iso ?: ($payload['asof'] ?? null);
  $asof_display = $asof_raw ? wp_date('M j, g:ia', strtotime($asof_raw)) : null;
  $asof_label = $obs_iso ? 'observed' : 'as of';

  // Optional barometric trend (derived by backend when available)
  $baro_trend = $weather['pressure_trend'] ?? ($weather['baro_trend'] ?? null);
  $baro_trend_label = '—';
  if (is_string($baro_trend) && $baro_trend !== '') {
    $t = strtolower($baro_trend);
    if ($t === 'rising') { $baro_trend_label = '↑ rising'; }
    elseif ($t === 'falling') { $baro_trend_label = '↓ falling'; }
    elseif ($t === 'steady') { $baro_trend_label = '→ steady'; }
    else { $baro_trend_label = $baro_trend; }
  }

  // 3h trend labels (if backend provided flags)
  $temp_trend_3h_label = null;
  $baro_trend_3h_label = null;
  if (isset($health_flags_raw) && is_array($health_flags_raw)) {
    if (isset($health_flags_raw['temp_trend_3h'])) {
      $temp_trend_3h_label = gaiaeyes_trend_label($health_flags_raw['temp_trend_3h']);
    }
    if (isset($health_flags_raw['baro_trend_3h'])) {
      $baro_trend_3h_label = gaiaeyes_trend_label($health_flags_raw['baro_trend_3h']);
    }
  }

  // Temperature (°C) plus US (°F)
  $temp_c_raw = $weather['temp_c'] ?? null;
  $temp = gaiaeyes_local_value($temp_c_raw, '°C');
  if (is_numeric($temp_c_raw)) {
    $temp_f_val = ($temp_c_raw * 9/5) + 32;
    $temp .= ' (' . number_format_i18n($temp_f_val, 1) . ' °F)';
  }

  // 24h Temperature delta (°C) plus US (°F)
  $temp_d_c_raw = $weather['temp_delta_24h_c'] ?? null;
  $temp_delta = gaiaeyes_local_value($temp_d_c_raw, '°C');
  if (is_numeric($temp_d_c_raw)) {
    $temp_d_f_val = ($temp_d_c_raw * 9/5);
    $temp_delta .= ' (' . number_format_i18n($temp_d_f_val, 1) . ' °F)';
  }

  $humidity = gaiaeyes_local_value($weather['humidity_pct'] ?? null, '%');
  $precip = gaiaeyes_local_value($weather['precip_prob_pct'] ?? null, '%');

  // Pressure (hPa) plus US (inHg ≈ hPa * 0.02953)
  $pressure_hpa_raw = $weather['pressure_hpa'] ?? null;
  $pressure = gaiaeyes_local_value($pressure_hpa_raw, 'hPa');
  if (is_numeric($pressure_hpa_raw)) {
    $pressure_inhg = $pressure_hpa_raw * 0.02953;
    $pressure .= ' (' . number_format_i18n($pressure_inhg, 2) . ' inHg)';
  }

  // 24h Pressure delta in hPa + inHg
  $pressure_d_hpa_raw = $weather['baro_delta_24h_hpa'] ?? null;
  $pressure_delta = gaiaeyes_local_value($pressure_d_hpa_raw, 'hPa');
  if (is_numeric($pressure_d_hpa_raw)) {
    $pressure_d_inhg = $pressure_d_hpa_raw * 0.02953;
    $pressure_delta .= ' (' . number_format_i18n($pressure_d_inhg, 2) . ' inHg)';
  }

  $aqi = gaiaeyes_local_value($air['aqi'] ?? null);
  $aqi_category = gaiaeyes_local_value($air['category'] ?? null);
  $pollutant = gaiaeyes_local_value($air['pollutant'] ?? null);

  $moon_phase = gaiaeyes_local_value($moon['phase'] ?? null);
  // Backend returns illumination as 0..1; show as whole-percent
  $moon_illum = (isset($moon['illum']) && is_numeric($moon['illum']))
    ? number_format_i18n((float)$moon['illum'] * 100, 0) . ' %'
    : '—';

  ob_start();
  ?>
  <section class="ge-panel ge-local-health">
    <h3>
      Local Health (<?php echo esc_html($zip); ?>)
      <?php if ($asof_display) : ?>
        <small class="ge-asof"><?php echo esc_html($asof_label); ?> <?php echo esc_html($asof_display); ?></small>
      <?php endif; ?>
    </h3>
    <?php if (!empty($health_pills) || !empty($health_messages)) : ?>
      <div class="ge-pills" role="status" aria-label="Local health signals">
        <?php foreach ((array)$health_pills as $f):
          $label = is_array($f) ? ($f['label'] ?? ($f['kind'] ?? 'Flag')) : (string)$f;
          $sev   = is_array($f) ? strtolower((string)($f['severity'] ?? 'info')) : 'info';
          $cls   = 'ge-pill';
          if ($sev === 'alert') { $cls .= ' ge-pill--alert'; }
          elseif ($sev === 'elevated') { $cls .= ' ge-pill--elevated'; }
          elseif ($sev === 'ok') { $cls .= ' ge-pill--ok'; }
        ?>
          <span class="<?php echo esc_attr($cls); ?>"><?php echo esc_html($label); ?></span>
        <?php endforeach; ?>
      </div>
      <?php if (!empty($health_messages)): ?>
        <div class="ge-mini-hints">
          <?php foreach ((array)$health_messages as $m): ?>
            <div class="ge-hint"><?php echo esc_html((string)$m); ?></div>
          <?php endforeach; ?>
        </div>
      <?php endif; ?>
    <?php endif; ?>
    <div class="ge-grid">
      <div class="ge-card">
        <h4>Weather</h4>
        <div class="ge-row"><span>Temp</span><strong><?php echo esc_html($temp); ?></strong></div>
        <div class="ge-row"><span>24h Δ</span><strong><?php echo esc_html($temp_delta); ?></strong></div>
        <div class="ge-row"><span>Humidity</span><strong><?php echo esc_html($humidity); ?></strong></div>
        <div class="ge-row"><span>Precip</span><strong><?php echo esc_html($precip); ?></strong></div>
        <div class="ge-row"><span>Pressure</span><strong><?php echo esc_html($pressure); ?></strong></div>
        <div class="ge-row"><span>Baro 24h Δ</span><strong><?php echo esc_html($pressure_delta); ?></strong></div>
        <div class="ge-row"><span>Baro trend</span><strong><?php echo esc_html($baro_trend_label); ?></strong></div>
        <?php if (!empty($temp_trend_3h_label)) : ?>
          <div class="ge-row"><span>Temp trend (3h)</span><strong><?php echo esc_html($temp_trend_3h_label); ?></strong></div>
        <?php endif; ?>
        <?php if (!empty($baro_trend_3h_label)) : ?>
          <div class="ge-row"><span>Baro trend (3h)</span><strong><?php echo esc_html($baro_trend_3h_label); ?></strong></div>
        <?php endif; ?>
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
      .ge-local-health .ge-asof { font-weight: normal; font-size: 0.85em; margin-left: 8px; opacity: 0.8; }
      .ge-local-health .ge-pills { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px; }
      .ge-local-health .ge-pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-weight: 600;
        font-size: 0.85em;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.15);
      }
      .ge-local-health .ge-pill--elevated {
        background: rgba(255,165,0,0.18);
        border-color: rgba(255,165,0,0.35);
        box-shadow: inset 0 0 10px rgba(255,165,0,0.25);
      }
      .ge-local-health .ge-pill--alert {
        background: rgba(255,64,64,0.20);
        border-color: rgba(255,64,64,0.45);
        box-shadow: inset 0 0 12px rgba(255,64,64,0.30);
      }
      .ge-local-health .ge-pill--ok {
        background: rgba(60,179,113,0.18);
        border-color: rgba(60,179,113,0.35);
      }
      .ge-local-health .ge-mini-hints { font-size: .88em; opacity: .9; margin-bottom: 6px; }
      .ge-local-health .ge-mini-hints .ge-hint { margin-top: 2px; }
    </style>
  </section>
  <?php
  return ob_get_clean();
});

add_shortcode('gaia_local_widget', function ($atts) {
  $a = shortcode_atts([
    'zip' => '',
    'cache' => 10,
    'api_base' => defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : '',
    'api_bearer' => defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '',
    'api_dev_userid' => defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '',
  ], $atts, 'gaia_local_widget');

  // Resolve ZIP via helper (attr / query / user meta / cookie)
  $zip = gaiaeyes_resolve_zip_default($a['zip']);

  // Persist to cookie on view (helps guests keep context)
  if ($zip) {
    setcookie('gaia_zip', $zip, time() + 60*60*24*180, COOKIEPATH ? COOKIEPATH : '/', COOKIE_DOMAIN, is_ssl(), true);
  }

  ob_start();
  ?>
  <form method="get" class="ge-zip-form" style="margin-bottom:12px; display:flex; gap:8px; align-items:center;">
    <label for="ge_zip"><strong>Your ZIP:</strong></label>
    <input id="ge_zip" name="zip" inputmode="numeric" pattern="[0-9A-Za-z]{3,10}" value="<?php echo esc_attr($zip); ?>" style="max-width:140px;">
    <button type="submit">Check</button>
    <?php if (is_user_logged_in()) : ?>
      <button type="button" id="ge_save_zip">Save as my default</button>
      <span id="ge_save_status" style="margin-left:8px; opacity:.8;"></span>
    <?php endif; ?>
  </form>

  <?php
    // Reuse the existing card renderer with the resolved ZIP
    echo do_shortcode(sprintf('[gaia_local_check zip="%s" cache="%d" api_base="%s" api_bearer="%s" api_dev_userid="%s"]',
      esc_attr($zip),
      intval($a['cache']),
      esc_attr($a['api_base']),
      esc_attr($a['api_bearer']),
      esc_attr($a['api_dev_userid'])
    ));
  ?>

  <?php if (is_user_logged_in()) : ?>
    <script>
      (function() {
        const btn = document.getElementById('ge_save_zip');
        if (!btn) return;
        btn.addEventListener('click', async function() {
          const zipEl = document.getElementById('ge_zip');
          const zip = (zipEl && zipEl.value || '').trim();
          const statusEl = document.getElementById('ge_save_status');
          if (!zip) { if (statusEl) statusEl.textContent = 'Enter a ZIP first.'; return; }
          try {
            const resp = await fetch('<?php echo esc_url_raw( rest_url('gaiaeyes/v1/local/save-zip') ); ?>', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-WP-Nonce': '<?php echo esc_js( wp_create_nonce('wp_rest') ); ?>'
              },
              body: JSON.stringify({ zip })
            });
            const data = await resp.json();
            if (resp.ok && data && data.ok) {
              if (statusEl) statusEl.textContent = 'Saved!';
            } else {
              if (statusEl) statusEl.textContent = (data && data.error) ? data.error : 'Save failed';
            }
          } catch (e) {
            if (statusEl) statusEl.textContent = 'Network error';
          }
        });
      })();
    </script>
  <?php endif; ?>

  <style>
    .ge-zip-form input { padding:6px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.05); color:inherit; }
    .ge-zip-form button { padding:6px 10px; border-radius:6px; border:0; background:#2b7cff; color:#fff; cursor:pointer; }
    .ge-zip-form button[type="button"] { background:#555; }
  </style>
  <?php
  return ob_get_clean();
});

add_action('rest_api_init', function () {
  register_rest_route('gaiaeyes/v1', '/local/save-zip', [
    'methods'  => 'POST',
    'permission_callback' => function() { return is_user_logged_in(); },
    'callback' => function( WP_REST_Request $req ) {
      $zip = preg_replace('/[^0-9A-Za-z]/', '', (string)$req->get_param('zip'));
      if (!$zip) {
        return new WP_REST_Response(['ok' => false, 'error' => 'Invalid ZIP'], 400);
      }
      $uid = get_current_user_id();
      update_user_meta($uid, 'gaiaeyes_default_zip', $zip);
      // Refresh cookie too
      setcookie('gaia_zip', $zip, time() + 60*60*24*180, COOKIEPATH ? COOKIEPATH : '/', COOKIE_DOMAIN, is_ssl(), true);

      // Optional: mirror to Supabase app.user_locations if keys are available
      if (defined('SUPABASE_REST_URL') && defined('SUPABASE_SERVICE_ROLE_KEY') && SUPABASE_REST_URL && SUPABASE_SERVICE_ROLE_KEY) {
        $endpoint = rtrim(SUPABASE_REST_URL, '/') . '/app.user_locations?on_conflict=user_id';
        $row = [
          'user_id'  => 'wp:' . $uid,
          'provider' => 'wp',
          'zip'      => $zip,
          'updated_at' => gmdate('c'),
        ];
        $args = [
          'headers' => [
            'Content-Type' => 'application/json',
            'apikey'       => SUPABASE_SERVICE_ROLE_KEY,
            'Authorization'=> 'Bearer ' . SUPABASE_SERVICE_ROLE_KEY,
            'Prefer'       => 'resolution=merge-duplicates'
          ],
          'body'    => wp_json_encode([$row]),
          'timeout' => 10,
        ];
        $r = wp_remote_post($endpoint, $args);
        if (is_wp_error($r)) {
          // Log but don’t fail the request
          error_log('[gaiaeyes] Supabase user_locations upsert failed: ' . $r->get_error_message());
        }
      }

      return new WP_REST_Response(['ok' => true, 'zip' => $zip], 200);
    }
  ]);
});
