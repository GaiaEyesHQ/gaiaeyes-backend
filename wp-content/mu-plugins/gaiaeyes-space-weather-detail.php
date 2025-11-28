<?php

// DEPLOY TEST: <today’s date/time>
/**
 * Plugin Name: Gaia Eyes – Space Weather Detail
 * Description: Scientific detail page for Space Weather (Kp, Solar wind, Bz, Flares, CMEs, Aurora) using gaiaeyes-media JSON feeds.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;
require_once __DIR__ . '/gaiaeyes-api-helpers.php';

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

/* ---------- Backend API (optional) ---------- */
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
    'aurora_detail' => '/aurora/#map',
    'api_base' => GAIAEYES_API_BASE,
    'api_bearer' => GAIAEYES_API_BEARER,
  ], $atts, 'gaia_space_weather_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;

  $sw = null;
  $fc = null;

  // API-first: try backend if api_base is configured
  $api_base = isset($a['api_base']) ? trim($a['api_base']) : '';
  $api_bearer = isset($a['api_bearer']) ? trim($a['api_bearer']) : '';
  if ($api_base) {
    $outlook = gaiaeyes_http_get_json_api_cached($api_base . '/v1/space/forecast/outlook', 'ge_fc_outlook', $ttl, $api_bearer);
    $features = gaiaeyes_http_get_json_api_cached($api_base . '/v1/features/today', 'ge_sw_features', $ttl, $api_bearer);

    // Shape a minimal legacy-compatible $sw/$fc for rendering
    $sw = [
      'timestamp_utc' => gmdate('Y-m-d H:i:s\\Z'),
      'now' => [
        'kp' => null, 'solar_wind_kms' => null, 'bz_nt' => null
      ],
      'last_24h' => [],
      'next_72h' => [],
      'alerts' => [],
      'impacts' => []
    ];
    if (is_array($features)) {
      // tolerant extraction helpers (support nested {value:...} or strings)
      $pickNum = function($arr, $keys){
        foreach ($keys as $k){
          if (!isset($arr[$k])) continue;
          $v = $arr[$k];
          if (is_numeric($v)) return (float)$v;
          if (is_array($v)) {
            foreach (['value','val','latest','now'] as $nk) {
              if (isset($v[$nk]) && is_numeric($v[$nk])) return (float)$v[$nk];
            }
          }
          if (is_string($v) && is_numeric($v+0)) return (float)$v;
        }
        return null;
      };
      $tryScopes = [
        $features,
        $features['snapshot'] ?? [],
        $features['now'] ?? [],
        $features['today'] ?? [],
        $features['space'] ?? [],
        $features['space_weather'] ?? [],
      ];
      $kp = $swk = $bzv = null;
      $kpKeys = ['kp','kp_now','kp_index','planetary_kp','kp_now_value'];
      $swKeys = ['sw_speed_kms','solar_wind_kms','solar_wind','speed_kms','solar_wind_speed','solar_wind_speed_kms'];
      $bzKeys = ['bz_nt','bz','imf_bz','bz_now','bz_gsm'];
      foreach ($tryScopes as $scope){
        if (is_array($scope)) {
          if ($kp === null)  $kp  = $pickNum($scope, $kpKeys);
          if ($swk === null) $swk = $pickNum($scope, $swKeys);
          if ($bzv === null) $bzv = $pickNum($scope, $bzKeys);
        }
      }
      // If API produced a shell but left values null, try legacy JSON to fill missing now-values
      // Optionally fill missing now/24h/series data from legacy JSON
      $legacy_now = gaiaeyes_http_get_json_with_fallback(GAIAEYES_SW_URL, GAIAEYES_SW_URL_MIRROR, 'ge_sw_json_fill', $ttl);
      if (is_array($legacy_now) && isset($legacy_now['now']) && is_array($legacy_now['now'])) {
        if ($kp === null  && isset($legacy_now['now']['kp']) && is_numeric($legacy_now['now']['kp'])) $kp = (float)$legacy_now['now']['kp'];
        if ($swk === null && isset($legacy_now['now']['solar_wind_kms']) && is_numeric($legacy_now['now']['solar_wind_kms'])) $swk = (float)$legacy_now['now']['solar_wind_kms'];
        if ($bzv === null && isset($legacy_now['now']['bz_nt']) && is_numeric($legacy_now['now']['bz_nt'])) $bzv = (float)$legacy_now['now']['bz_nt'];
        // also fill last_24h maxima if missing
        if (isset($legacy_now['last_24h']) && is_array($legacy_now['last_24h'])) {
          $last = $legacy_now['last_24h'];
          if (!isset($sw['last_24h']['kp_max']) && isset($last['kp_max']) && is_numeric($last['kp_max'])) $sw['last_24h']['kp_max'] = (float)$last['kp_max'];
          if (!isset($sw['last_24h']['solar_wind_max_kms']) && isset($last['solar_wind_max_kms']) && is_numeric($last['solar_wind_max_kms'])) $sw['last_24h']['solar_wind_max_kms'] = (float)$last['solar_wind_max_kms'];
        }
        // Fill series24 (for sparklines) if API did not provide it
        if (!isset($sw['series24']) && isset($legacy_now['series24']) && is_array($legacy_now['series24'])) {
          $sw['series24'] = $legacy_now['series24'];
        }
      }
      $sw['now']['kp'] = $kp;
      $sw['now']['solar_wind_kms'] = $swk;
      $sw['now']['bz_nt'] = $bzv;

      // last 24h maxima if present under common shapes
      $last = $features['last_24h'] ?? $features['last24h'] ?? [];
      if (is_array($last)) {
        if (!isset($sw['last_24h']['kp_max']) && isset($last['kp_max']) && is_numeric($last['kp_max'])) $sw['last_24h']['kp_max'] = (float)$last['kp_max'];
        if (!isset($sw['last_24h']['solar_wind_max_kms']) && isset($last['solar_wind_max_kms']) && is_numeric($last['solar_wind_max_kms'])) $sw['last_24h']['solar_wind_max_kms'] = (float)$last['solar_wind_max_kms'];
      }
    }
    if (is_array($outlook)) {
      // Headline & confidence (tolerant)
      $aur = is_array($outlook['aurora'] ?? null) ? $outlook['aurora'] : [];
      $headline = $outlook['headline'] ?? ($outlook['summary'] ?? ($aur['headline'] ?? ''));
      $sw['next_72h']['headline'] = $headline;

      $conf = $outlook['confidence'] ?? ($outlook['confidence_text'] ?? null);
      if (is_array($conf)) $conf = ($conf['label'] ?? $conf['text'] ?? $conf['value'] ?? null);
      if (!$conf && isset($outlook['summary']) && is_array($outlook['summary'])) {
        $conf = $outlook['summary']['confidence'] ?? ($outlook['summary']['confidence_text'] ?? null);
      }
      if (!$conf && $aur) {
        $conf = $aur['confidence'] ?? ($aur['confidence_text'] ?? null);
        if (is_array($conf)) $conf = ($conf['label'] ?? $conf['text'] ?? $conf['value'] ?? null);
      }
      $sw['next_72h']['confidence'] = $conf;

      // Alerts & impacts (accept alternate shapes and normalize keys)
      $alerts = $outlook['alerts'] ?? ($outlook['advisories'] ?? []);
      $sw['alerts'] = is_array($alerts) ? $alerts : [];

      $imp = $outlook['impacts'] ?? ($outlook['impacts_plain'] ?? ($aur['impacts'] ?? []));
      if (is_array($imp)) {
        // Normalize common synonyms to gps/comms/grids/aurora
        $norm = ['gps'=>null,'comms'=>null,'grids'=>null,'aurora'=>null];
        foreach ($imp as $k=>$v){
          $lk = strtolower(is_string($k)?$k:(is_string($v)?$v:''));
          if (isset($imp['gps'])) $norm['gps'] = $imp['gps'];
          if (isset($imp['gnss'])) $norm['gps'] = $imp['gnss'];
          if (isset($imp['comms'])) $norm['comms'] = $imp['comms'];
          if (isset($imp['radio'])) $norm['comms'] = $imp['radio'];
          if (isset($imp['radio_comms'])) $norm['comms'] = $imp['radio_comms'];
          if (isset($imp['grids'])) $norm['grids'] = $imp['grids'];
          if (isset($imp['power'])) $norm['grids'] = $imp['power'];
          if (isset($imp['power_grids'])) $norm['grids'] = $imp['power_grids'];
          if (isset($imp['aurora'])) $norm['aurora'] = $imp['aurora'];
          if (isset($imp['visibility'])) $norm['aurora'] = $imp['visibility'];
        }
        $sw['impacts'] = array_filter($norm, function($x){ return $x !== null && $x !== ''; });
      } else {
        $sw['impacts'] = [];
      }

      // Flares — accept alternate keys
      $fl = is_array($outlook['flares'] ?? null) ? $outlook['flares'] : [];
      $fl_max   = $fl['max_24h'] ?? $fl['peak_24h'] ?? $fl['peak_class_24h'] ?? $fl['max_class'] ?? null;
      $fl_total = $fl['total_24h'] ?? $fl['total'] ?? $fl['count_24h'] ?? null;
      $fl_bands = $fl['bands_24h'] ?? $fl['bands'] ?? $fl['distribution_24h'] ?? null;
      if (!$fl_bands && is_array($fl)) {
        // if the object itself is banded, pick X/M/C/B/A keys when present
        $cand = [];
        foreach (['X','M','C','B','A','x','m','c','b','a'] as $bk){ if (isset($fl[$bk])) $cand[strtoupper($bk)] = $fl[$bk]; }
        if ($cand) $fl_bands = $cand;
      }

      // CMEs — accept alternate shapes and stats keys
      $cme = is_array($outlook['cmes'] ?? null) ? $outlook['cmes'] : [];
      $c_headline = $cme['headline'] ?? $cme['summary'] ?? ($outlook['cme_headline'] ?? '');
      $c_stats = is_array($cme['stats'] ?? null) ? $cme['stats'] : $cme;
      $c_total = $c_stats['total_72h'] ?? $c_stats['count_72h'] ?? $c_stats['total'] ?? null;
      $c_ed    = $c_stats['earth_directed_count'] ?? $c_stats['earth_directed'] ?? $c_stats['ed'] ?? null;
      $c_vmax  = $c_stats['max_speed_kms'] ?? $c_stats['vmax_kms'] ?? $c_stats['speed_max_kms'] ?? null;

      // Assemble panel data for renderer — include pass‑through so renderer can derive max class from events when needed
      $flares_out = [
        'max_24h'   => $fl_max,
        'total_24h' => $fl_total,
        'bands_24h' => is_array($fl_bands) ? $fl_bands : [],
      ];
      // Pass through helpful alternate keys so the renderer can compute a max class
      foreach (['peak_24h','peak_class_24h','max_class','max_class_24h','peak','bands','counts','recent','events','list','peaks','values','last_24h','24h'] as $k) {
        if (isset($fl[$k])) { $flares_out[$k] = $fl[$k]; }
      }

      $fc = [
        'flares' => $flares_out,
        'cmes' => [
          'headline' => $c_headline,
          'stats'    => [
            'total_72h'           => $c_total,
            'earth_directed_count'=> $c_ed,
            'max_speed_kms'       => $c_vmax,
          ],
        ],
      ];
    }
  }
  // If API failed or not configured, fall back to legacy JSON sources
  if (!$sw) {
    $sw = gaiaeyes_http_get_json_with_fallback($a['sw_url'], GAIAEYES_SW_URL_MIRROR, 'ge_sw_json', $ttl);
  }
  if (!$fc) {
    $fc = gaiaeyes_http_get_json_with_fallback($a['fc_url'], GAIAEYES_FC_URL_MIRROR, 'ge_fc_json', $ttl);
  }

  $aurora_detail = isset($a['aurora_detail']) ? $a['aurora_detail'] : '/aurora/#map';

  ob_start();
  ?>
  <section class="ge-sw ge-panel">
    <header class="ge-sw__head">
      <h2>Space Weather – Scientific Detail</h2>
      <?php
        // Debug comment: shows whether API/values were detected (will appear in page source only)
        $dbg_kp = isset($sw['now']['kp']) ? $sw['now']['kp'] : null;
        $dbg_conf = isset($sw['next_72h']['confidence']) ? $sw['next_72h']['confidence'] : null;
        echo "\n<!-- ge-sw-debug api_base=" . (defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : '(none)') .
             " kp=" . (is_null($dbg_kp)?'null':esc_html((string)$dbg_kp)) .
             " conf=" . (is_null($dbg_conf)?'null':esc_html((string)$dbg_conf)) . " -->\n";
      ?>
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
          // If API flares payload is empty or missing max/total, fall back to legacy JSON flares_cmes feed
          if ((!is_array($flr) || !$flr) && isset($a['fc_url'])) {
            $legacy_fc = gaiaeyes_http_get_json_with_fallback($a['fc_url'], GAIAEYES_FC_URL_MIRROR, 'ge_fc_json_fill', $ttl);
            if (is_array($legacy_fc) && !empty($legacy_fc['flares']) && is_array($legacy_fc['flares'])) {
              $flr = $legacy_fc['flares'];
            }
          }

          // Tolerant max class extraction: accept strings, nested objects, or derive from events/bands
          $max = $flr['max_24h'] ?? $flr['peak_24h'] ?? $flr['peak_class_24h'] ?? $flr['max_class'] ?? $flr['peak_class'] ?? null;
          if (is_array($max)) {
            // Nested like {class:'M2.1'} or {label|text|value}
            $max = $max['class'] ?? $max['label'] ?? $max['text'] ?? $max['value'] ?? null;
          }
          if (!is_string($max) || $max === '') {
            // Try recent/events/list/peaks/values arrays for the strongest peak_class
            $candidates = [];
            foreach (['recent','events','list','peaks','values'] as $k) {
              if (!empty($flr[$k]) && is_array($flr[$k])) {
                foreach ($flr[$k] as $ev) {
                  if (!is_array($ev)) continue;
                  $pc = $ev['peak_class'] ?? $ev['class'] ?? $ev['peak'] ?? $ev['max_class'] ?? null;
                  if (is_string($pc) && $pc !== '') $candidates[] = $pc;
                }
              }
            }
            // Also check nested last_24h summary objects
            if (empty($candidates) && !empty($flr['last_24h']) && is_array($flr['last_24h'])) {
              $pc = $flr['last_24h']['peak_class'] ?? $flr['last_24h']['max_class'] ?? null;
              if (is_string($pc) && $pc !== '') $candidates[] = $pc;
            }
            if ($candidates) {
              // Rank by letter (A<B<C<M<X) and magnitude when present
              $rank = function($cls){
                if (!is_string($cls) || $cls === '') return -1;
                if (!preg_match('/([AaBbCcMmXx])\\s*([0-9.]+)?/', $cls, $m)) return -1;
                $L = strtoupper($m[1]); $num = isset($m[2]) && $m[2] !== '' ? (float)$m[2] : 0.0;
                $base = ['A'=>1,'B'=>2,'C'=>3,'M'=>4,'X'=>5][$L] ?? 0;
                return $base * 100 + $num; // simple composite score
              };
              usort($candidates, function($a,$b) use($rank){ return $rank($b) <=> $rank($a); });
              $max = $candidates[0] ?? $max;
            }
          }
          // If still empty, derive letter from bands_24h
          $bands = is_array($flr['bands_24h'] ?? null) ? $flr['bands_24h'] : ($flr['bands'] ?? []);
          if ((!is_string($max) || $max === '') && is_array($bands)) {
            foreach (['X','M','C','B','A'] as $L) {
              if (!empty($bands[$L])) { $max = $L; break; }
            }
          }

          $tot = $flr['total_24h'] ?? $flr['total'] ?? $flr['count_24h'] ?? null;

          // Prepare optional band summary line (X/M/C/B/A:count)
          $band_line = [];
          if (is_array($bands)) {
            foreach (['X','M','C','B','A'] as $b) {
              if (!empty($bands[$b])) $band_line[] = "{$b}:{$bands[$b]}";
            }
          }

          // Debug: emit keys and chosen max in HTML comment for troubleshooting
          $dbg_keys = is_array($flr) ? implode(',', array_keys($flr)) : '';
          echo "\n<!-- ge-flr-debug keys=" . esc_html($dbg_keys) . " max=" . esc_html((string)$max) . " total=" . esc_html((string)($tot ?? '')) . " -->\n";

          echo ge_row('Max class (24h)', ge_val_or_dash($max));
          if ($tot !== null) echo ge_row('Total flares (24h)', ge_val_or_dash($tot));
          if ($band_line) echo "<div class='sw-bandline'>".esc_html('Bands: '.implode(' ', $band_line))."</div>";
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
          echo '<div class="ge-cta"><a class="gaia-link" href="' . esc_url( $aurora_detail ) . '">Open aurora detail →</a></div>';
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
      .ge-sparklines canvas{width:100%;height:120px;max-width:100%;margin-top:6px}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      .ge-cta{margin-top:8px}
      .gaia-link{color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25)}
      .gaia-link:hover{border-bottom-color:rgba(255,255,255,.6)}
    </style>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha256-5l5wxg6rE6sBJP6opc0bDO3sTZ5yH5rICwW7X8P9qvo=" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
    <script>
      (function(){
        try {
          const sw = <?php echo wp_json_encode($sw); ?>;
          const wrap = document.getElementById('ge-spark-wrap');
          let rendered = 0;

          function whenSparkReady(cb){
            if (window.GaiaSpark && window.GaiaSpark.renderSpark) {
              cb(window.GaiaSpark);
              return;
            }
            const handler = () => {
              window.removeEventListener('gaiaSparkReady', handler);
              if (window.GaiaSpark && window.GaiaSpark.renderSpark) {
                cb(window.GaiaSpark);
              }
            };
            window.addEventListener('gaiaSparkReady', handler, { once:true });
          }

          function toSeries(raw){
            if (!Array.isArray(raw)) return [];
            const out = [];
            raw.forEach((entry, idx) => {
              if (entry == null) return;
              if (typeof entry === 'number') {
                if (isFinite(entry)) out.push({ x: idx, y: entry });
                return;
              }
              if (Array.isArray(entry)) {
                const time = entry.length > 1 ? entry[0] : idx;
                const val = entry.length > 1 ? entry[1] : entry[0];
                let x = idx;
                if (time !== undefined && time !== null) {
                  const d = new Date(time);
                  if (!isNaN(+d)) {
                    x = d;
                  } else if (typeof time === 'number' && isFinite(time)) {
                    x = time;
                  }
                }
                const y = Number(val);
                if (isFinite(y)) out.push({ x, y });
                return;
              }
              if (typeof entry === 'object') {
                const time = entry.time ?? entry.timestamp ?? entry.x ?? entry.t ?? entry.date ?? entry[0];
                const val = entry.value ?? entry.y ?? entry.v ?? entry.kp ?? entry.sw ?? entry.bz ?? entry[1];
                let x = idx;
                if (time !== undefined && time !== null) {
                  const d = new Date(time);
                  if (!isNaN(+d)) {
                    x = d;
                  } else if (typeof time === 'number' && isFinite(time)) {
                    x = time;
                  }
                }
                const y = Number(val);
                if (isFinite(y)) out.push({ x, y });
              }
            });
            return out;
          }

          function renderSpark(id, raw, options){
            const data = toSeries(raw);
            if (!data.length) return false;
            const trimmed = data.length > 240 ? data.slice(-240) : data;
            whenSparkReady((spark) => {
              spark.renderSpark(id, trimmed, options);
            });
            return true;
          }

          if (sw && sw.series24){
            if (renderSpark('ge-spark-kp', sw.series24.kp || [], { xLabel:'Sample', yLabel:'Planetary Kp', units:'index', yMin:0, yMax:9, color:'#7fc8ff' })) rendered++;
            if (renderSpark('ge-spark-sw', sw.series24.sw || [], { xLabel:'Sample', yLabel:'Solar wind speed', units:'km/s', yMin:0, color:'#ffd089' })) rendered++;
            if (renderSpark('ge-spark-bz', sw.series24.bz || [], { xLabel:'Sample', yLabel:'IMF Bz', units:'nT', zeroLine:true, color:'#a7d3ff' })) rendered++;
          }
          if (rendered && wrap) wrap.style.display = 'block';
        } catch(e){}
      })();
    </script>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_space_weather_detail', 'gaia_space_weather_detail_shortcode');