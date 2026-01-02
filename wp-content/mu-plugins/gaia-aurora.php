<?php
/**
 * Plugin Name: Gaia Eyes – Aurora Nowcast Services
 * Description: Schedules OVATION nowcast ingestion, exposes REST endpoints, and persists diagnostics/JSON artifacts.
 * Version: 0.1.0
 */

if (!defined('ABSPATH')) {
    exit;
}

// -----------------------------------------------------------------------------
// Constants & helpers
// -----------------------------------------------------------------------------

if (!defined('GAIA_AURORA_NOWCAST_URL')) {
    $nowcast_env = getenv('GAIA_AURORA_NOWCAST_URL');
    define('GAIA_AURORA_NOWCAST_URL', $nowcast_env ? esc_url_raw($nowcast_env) : 'https://services.swpc.noaa.gov/json/ovation_aurora_latest.json');
}
if (!defined('GAIA_AURORA_KP_URL')) {
    define('GAIA_AURORA_KP_URL', 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json');
}
// Optional Supabase media base (used to prefer Supabase-hosted images)
if (!defined('GAIA_MEDIA_BASE')) {
    $mb = getenv('GAIA_MEDIA_BASE');
    define('GAIA_MEDIA_BASE', $mb ? rtrim(esc_url_raw($mb), '/') : '');
}
if (!defined('GAIA_AURORA_IMAGE_NORTH')) {
    $img_env_n = getenv('GAIA_AURORA_IMAGE_NORTH');
    define('GAIA_AURORA_IMAGE_NORTH', $img_env_n ? esc_url_raw($img_env_n) : 'https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg');
}
if (!defined('GAIA_AURORA_IMAGE_SOUTH')) {
    $img_env_s = getenv('GAIA_AURORA_IMAGE_SOUTH');
    define('GAIA_AURORA_IMAGE_SOUTH', $img_env_s ? esc_url_raw($img_env_s) : 'https://services.swpc.noaa.gov/images/animations/ovation/south/latest.jpg');
}
if (!defined('GAIA_AURORA_VIEWLINE_TONIGHT')) {
    $base = (defined('GAIA_MEDIA_BASE') && GAIA_MEDIA_BASE) ? GAIA_MEDIA_BASE : '';
    define('GAIA_AURORA_VIEWLINE_TONIGHT', $base ? ($base . '/aurora/viewline/tonight.png') : 'https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tonights_static_viewline_forecast.png');
}
if (!defined('GAIA_AURORA_VIEWLINE_TOMORROW')) {
    $base = (defined('GAIA_MEDIA_BASE') && GAIA_MEDIA_BASE) ? GAIA_MEDIA_BASE : '';
    define('GAIA_AURORA_VIEWLINE_TOMORROW', $base ? ($base . '/aurora/viewline/tomorrow.png') : 'https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tomorrow_nights_static_viewline_forecast.png');
}
if (!defined('GAIA_AURORA_CACHE_TTL')) {
    $ttl_env = getenv('GAIA_AURORA_CACHE_TTL_SECONDS');
    define('GAIA_AURORA_CACHE_TTL', $ttl_env !== false ? max(60, (int) $ttl_env) : 300);
}
if (!defined('GAIA_AURORA_VIEWLINE_P')) {
    $p_env = getenv('GAIA_AURORA_VIEWLINE_P');
    $p_val = ($p_env !== false) ? (float) $p_env : 0.10;
    if ($p_val <= 0) {
        $p_val = 0.10;
    }
    define('GAIA_AURORA_VIEWLINE_P', $p_val);
}
if (!defined('GAIA_AURORA_VIEWLINE_P_NORTH')) {
    $p_env_north = getenv('GAIA_AURORA_VIEWLINE_P_NORTH');
    if ($p_env_north !== false && $p_env_north !== '') {
        $p_val_north = (float) $p_env_north;
        if ($p_val_north > 1) {
            $p_val_north /= 100;
        }
        if ($p_val_north <= 0) {
            $p_val_north = GAIA_AURORA_VIEWLINE_P;
        }
        define('GAIA_AURORA_VIEWLINE_P_NORTH', $p_val_north);
    } else {
        define('GAIA_AURORA_VIEWLINE_P_NORTH', null);
    }
}
if (!defined('GAIA_AURORA_SMOOTH_WINDOW')) {
    $w_env = getenv('GAIA_AURORA_SMOOTH_WINDOW');
    $w_val = ($w_env !== false) ? (int) $w_env : 5;
    if ($w_val < 3) {
        $w_val = 3;
    }
    if ($w_val % 2 === 0) {
        $w_val += 1; // moving average window works best with odd length
    }
    define('GAIA_AURORA_SMOOTH_WINDOW', $w_val);
}
if (!defined('GAIA_AURORA_ENABLE_JSON_EXPORT')) {
    $flag = getenv('GAIA_AURORA_ENABLE_JSON_EXPORT');
    define('GAIA_AURORA_ENABLE_JSON_EXPORT', $flag === false || $flag === '' || $flag === '1' || strtolower((string) $flag) === 'true');
}
if (!defined('GAIA_AURORA_LON0_N')) {
    define('GAIA_AURORA_LON0_N', (float) gaia_aurora_env('LON0_N', 0));
}
if (!defined('GAIA_AURORA_LON0_S')) {
    define('GAIA_AURORA_LON0_S', (float) gaia_aurora_env('LON0_S', 0));
}
if (!defined('GAIA_AURORA_KP_LEVELS')) {
    $levels_raw = gaia_aurora_env('GAIA_AURORA_KP_LEVELS', '0.01,0.03,0.05,0.10,0.20,0.30,0.50');
    $levels_list = [];
    foreach (array_filter(array_map('trim', explode(',', (string) $levels_raw)), 'strlen') as $level_str) {
        $value = (float) $level_str;
        if ($value > 1) {
            $value /= 100;
        }
        if ($value <= 0) {
            continue;
        }
        if ($value > 1) {
            $value = 1;
        }
        $levels_list[] = $value;
    }
    sort($levels_list);
    define('GAIA_AURORA_KP_LEVELS', $levels_list);
}

/**
 * Resolve an environment variable with sensible fallbacks.
 */
function gaia_aurora_env($key, $default = null)
{
    // Prefer a WP constant if defined
    if (defined($key)) {
        $const = constant($key);
        if ($const !== '' && $const !== null) {
            return $const;
        }
    }
    // Then environment variables
    $val = getenv($key);
    if ($val !== false && $val !== '') {
        return $val;
    }
    if (!empty($_ENV[$key])) {
        return $_ENV[$key];
    }
    if (!empty($_SERVER[$key])) {
        return $_SERVER[$key];
    }
    return $default;
}

function gaia_aurora_normalize_probability($value, $fallback = null)
{
    if ($value === null) {
        return $fallback;
    }
    if (!is_numeric($value)) {
        return $fallback;
    }
    $val = (float) $value;
    if ($val > 1) {
        $val /= 100;
    }
    if ($val <= 0) {
        return $fallback;
    }
    if ($val > 1) {
        $val = 1;
    }
    return $val;
}

/**
 * Determine the root path of the writable media repo.
 */
function gaia_aurora_media_root()
{
    static $cache = null;
    if ($cache !== null) {
        return $cache;
    }
    $candidates = [
        gaia_aurora_env('GAIAEYES_MEDIA_DIR'),
        gaia_aurora_env('MEDIA_DIR'),
    ];
    foreach ($candidates as $candidate) {
        if ($candidate) {
            $path = rtrim($candidate, '/');
            if (is_dir($path)) {
                return $cache = $path;
            }
        }
    }
    // Fall back to sibling checkout in typical repo layout.
    $fallback = dirname(__DIR__, 2) . '/gaiaeyes-media';
    return $cache = rtrim($fallback, '/');
}

/**
 * Build an absolute path inside the media repo.
 */
function gaia_aurora_media_path($relative)
{
    $root = gaia_aurora_media_root();
    $relative = ltrim($relative, '/');
    return $root . '/' . $relative;
}

/**
 * Fetch a URL with optional ETag support.
 *
 * @param string $url
 * @param array  $args
 * @return array{status:int,duration_ms:int,etag:?string,body:mixed,error:?string}
 */
function gaia_aurora_http_get($url, $args = [])
{
    $defaults = [
        'timeout' => isset($args['timeout']) ? (int) $args['timeout'] : 12,
        'headers' => [
            'Accept'     => isset($args['accept']) ? $args['accept'] : 'application/json',
            'User-Agent' => 'GaiaEyesAurora/1.0 (+https://gaiaeyes.com)',
        ],
    ];
    if (!empty($args['etag'])) {
        $defaults['headers']['If-None-Match'] = $args['etag'];
    }
    if (!empty($args['headers']) && is_array($args['headers'])) {
        $defaults['headers'] = array_merge($defaults['headers'], $args['headers']);
    }
    $start = microtime(true);
    $response = wp_remote_get(esc_url_raw($url), $defaults);
    $duration = (int) round((microtime(true) - $start) * 1000);
    if (is_wp_error($response)) {
        return [
            'status'      => 0,
            'duration_ms' => $duration,
            'etag'        => null,
            'body'        => null,
            'error'       => $response->get_error_message(),
        ];
    }
    $status = (int) wp_remote_retrieve_response_code($response);
    $etag = wp_remote_retrieve_header($response, 'etag');
    if ($status === 304) {
        return [
            'status'      => 304,
            'duration_ms' => $duration,
            'etag'        => $etag ? (string) $etag : null,
            'body'        => null,
            'error'       => null,
        ];
    }
    $body = wp_remote_retrieve_body($response);
    if (isset($args['accept']) && strpos($args['accept'], 'json') === false) {
        $payload = $body;
    } else {
        $payload = json_decode($body, true);
    }
    return [
        'status'      => $status,
        'duration_ms' => $duration,
        'etag'        => $etag ? (string) $etag : null,
        'body'        => $payload,
        'error'       => null,
    ];
}

/**
 * Persist data into Supabase via REST (no-op when credentials missing).
 */
function gaia_aurora_supabase_post($path, $payload, $params = [], $schema = 'marts')
{
    // Resolve REST base: explicit SUPABASE_REST_URL or derive from SUPABASE_URL
    $rest = gaia_aurora_env('SUPABASE_REST_URL');
    if (!$rest) {
        $base = rtrim((string) gaia_aurora_env('SUPABASE_URL'), '/');
        if ($base) {
            $rest = $base . '/rest/v1';
        }
    }
    // Resolve key: prefer service role, then service key, then anon
    $key = gaia_aurora_env('SUPABASE_SERVICE_ROLE_KEY')
        ?: gaia_aurora_env('SUPABASE_SERVICE_KEY')
        ?: gaia_aurora_env('SUPABASE_ANON_KEY');
    if (!$rest || !$key) {
        return null;
    }
    $url = rtrim($rest, '/') . '/' . ltrim($path, '/');
    if ($params) {
        $url = add_query_arg($params, $url);
    }
    $resp = wp_remote_post($url, [
        'timeout' => 12,
        'headers' => [
            'Content-Type'    => 'application/json',
            'Accept'          => 'application/json',
            'apikey'          => $key,
            'Authorization'   => 'Bearer ' . $key,
            'Prefer'          => 'resolution=merge-duplicates',
            'Content-Profile' => $schema,
            'Accept-Profile'  => $schema,
        ],
        'body'    => wp_json_encode($payload),
    ]);
    if (is_wp_error($resp)) {
        return $resp->get_error_message();
    }
    $code = (int) wp_remote_retrieve_response_code($resp);
    if ($code >= 400) {
        return 'HTTP ' . $code . ' ' . wp_remote_retrieve_body($resp);
    }
    return null;
}

/**
 * Try to extract Hemisphere Power (GW) and Wing Kp from a variety of OVATION JSON shapes.
 * Returns ['north' => float|null, 'south' => float|null, 'wing_kp' => float|null].
 */
function gaia_aurora_extract_hemisphere_power($body)
{
    if (!is_array($body)) {
        return ['north' => null, 'south' => null, 'wing_kp' => null];
    }
    $get = function($arr, $paths) {
        foreach ($paths as $p) {
            $cur = $arr;
            $ok = true;
            foreach ($p as $k) {
                if (is_array($cur) && array_key_exists($k, $cur)) {
                    $cur = $cur[$k];
                } else {
                    $ok = false; break;
                }
            }
            if ($ok && (is_numeric($cur) || is_string($cur))) {
                return (float)$cur;
            }
        }
        return null;
    };
    $north = $get($body, [
        ['HemispherePower','North'], ['Hemisphere Power','North'],
        ['hemisphere_power','north'], ['north_power'],
    ]);
    $south = $get($body, [
        ['HemispherePower','South'], ['Hemisphere Power','South'],
        ['hemisphere_power','south'], ['south_power'],
    ]);
    $wing  = $get($body, [['WingKp'], ['Kp'], ['kp'], ['kp_index']]);
    return ['north' => $north, 'south' => $south, 'wing_kp' => $wing];
}

/**
 * Upsert rows into ext.aurora_power for both hemispheres.
 */
function gaia_aurora_persist_ext_aurora_power($ts_iso, $hp)
{
    if (!$ts_iso || !is_array($hp)) {
        return;
    }
    $ts = $ts_iso;
    if (!is_string($ts)) {
        $ts = gmdate('c');
    }
    // Upsert north
    if (isset($hp['north']) && $hp['north'] !== null) {
        $rowN = [
            'ts_utc'               => $ts,
            'hemisphere'           => 'north',
            'hemispheric_power_gw' => $hp['north'],
            'wing_kp'              => isset($hp['wing_kp']) ? $hp['wing_kp'] : null,
            'raw'                  => null,
        ];
        $err = gaia_aurora_supabase_post('aurora_power', $rowN, ['on_conflict' => 'ts_utc,hemisphere'], 'ext');
        if ($err) { error_log('[gaia_aurora] supabase ext.aurora_power north error: ' . $err); }
    }
    // Upsert south
    if (isset($hp['south']) && $hp['south'] !== null) {
        $rowS = [
            'ts_utc'               => $ts,
            'hemisphere'           => 'south',
            'hemispheric_power_gw' => $hp['south'],
            'wing_kp'              => isset($hp['wing_kp']) ? $hp['wing_kp'] : null,
            'raw'                  => null,
        ];
        $err = gaia_aurora_supabase_post('aurora_power', $rowS, ['on_conflict' => 'ts_utc,hemisphere'], 'ext');
        if ($err) { error_log('[gaia_aurora] supabase ext.aurora_power south error: ' . $err); }
    }
}

// -----------------------------------------------------------------------------
// Temporary health endpoint for debugging
// -----------------------------------------------------------------------------

add_action('rest_api_init', function () {
    register_rest_route('gaia/v1', '/aurora/health', [
        'methods'  => 'GET',
        'permission_callback' => '__return_true',
        'callback' => function () {
            $root = gaia_aurora_media_root();
            $probe = gaia_aurora_http_get(GAIA_AURORA_NOWCAST_URL, ['timeout' => 6]);
            return [
                'env' => [
                    'media_root' => $root,
                    'exists'     => is_dir($root),
                    'writable'   => is_writable($root),
                    'supabase'   => (bool) gaia_aurora_env('SUPABASE_REST_URL'),
                ],
                'noaa' => [
                    'status' => $probe['status'],
                    'ms'     => $probe['duration_ms'],
                    'error'  => $probe['error'],
                ],
            ];
        }
    ]);
});
/**
 * Record diagnostics for REST surface.
 */
function gaia_aurora_record_diagnostics($data)
{
    update_option('gaia_aurora_last_diagnostics', $data, false);
}

/**
 * Retrieve the last recorded diagnostics snapshot.
 */
function gaia_aurora_get_diagnostics()
{
    $diag = get_option('gaia_aurora_last_diagnostics');
    return is_array($diag) ? $diag : [];
}

// -----------------------------------------------------------------------------
// Bootstrap
// -----------------------------------------------------------------------------

add_action('plugins_loaded', 'gaia_aurora_bootstrap');

function gaia_aurora_bootstrap()
{
    add_filter('cron_schedules', 'gaia_aurora_register_cron_intervals');
    add_action('gaia_aurora_refresh_nowcast', 'gaia_aurora_refresh_nowcast');
    add_action('gaia_aurora_refresh_viewline', 'gaia_aurora_refresh_viewline');
    add_action('rest_api_init', 'gaia_aurora_register_rest_routes');
    error_log('[gaia_aurora] bootstrap loaded');

    // Ensure schedules exist when WordPress finishes loading.
    add_action('init', 'gaia_aurora_ensure_schedules');
}

function gaia_aurora_register_cron_intervals($schedules)
{
    if (!isset($schedules['gaia_aurora_five_minutes'])) {
        $schedules['gaia_aurora_five_minutes'] = [
            'interval' => 5 * MINUTE_IN_SECONDS,
            'display'  => __('Every Five Minutes (Gaia Aurora)', 'gaiaeyes'),
        ];
    }
    return $schedules;
}

function gaia_aurora_ensure_schedules()
{
    if (!wp_next_scheduled('gaia_aurora_refresh_nowcast')) {
        wp_schedule_event(time(), 'gaia_aurora_five_minutes', 'gaia_aurora_refresh_nowcast');
    }
    if (!wp_next_scheduled('gaia_aurora_refresh_viewline')) {
        wp_schedule_event(time(), 'hourly', 'gaia_aurora_refresh_viewline');
    }
}

// -----------------------------------------------------------------------------
// Core fetch logic
// -----------------------------------------------------------------------------

function gaia_aurora_refresh_nowcast()
{
    $start = microtime(true);
    $etag_key = 'gaia_aurora_nowcast_etag';
    $stored_etag = get_option($etag_key);
    $grid_resp = gaia_aurora_http_get(GAIA_AURORA_NOWCAST_URL, ['etag' => $stored_etag]);
    // Debug: log top-level keys and coordinates info to diagnose parse shape
    error_log('[gaia_aurora] ovation status=' . $grid_resp['status']
        . ' keys=' . (is_array($grid_resp['body']) ? implode(',', array_slice(array_keys($grid_resp['body']), 0, 10)) : 'non-array')
        . (isset($grid_resp['body']['coordinates'])
            ? (' coords_type=' . gettype($grid_resp['body']['coordinates']) . ' len=' . (is_array($grid_resp['body']['coordinates']) ? count($grid_resp['body']['coordinates']) : 0))
            : '')
    );

    $latest_payloads = [
        'north' => gaia_aurora_get_cached_payload('north'),
        'south' => gaia_aurora_get_cached_payload('south'),
    ];

    $diagnostics = [
        'run_started_at' => gmdate('c'),
        'source_urls'    => [GAIA_AURORA_NOWCAST_URL, GAIA_AURORA_KP_URL],
        'duration_ms'    => null,
        'cache_hit'      => false,
        'errors'         => [],
        'trace'          => [],
        'cache_snapshot_initial' => [
            'north_ts' => isset($latest_payloads['north']['ts']) ? $latest_payloads['north']['ts'] : null,
            'south_ts' => isset($latest_payloads['south']['ts']) ? $latest_payloads['south']['ts'] : null,
        ],
        'cache_snapshot_final' => null,
        'cache_updated'        => false,
    ];

    if ($grid_resp['status'] === 304 && $latest_payloads['north'] && $latest_payloads['south']) {
        $diagnostics['trace'][] = 'ovation etag matched – reusing cache';
        $diagnostics['cache_hit'] = true;
        $diagnostics['cache_snapshot_final'] = $diagnostics['cache_snapshot_initial'];
        $diagnostics['payload_summary'] = [
            'aurora' => [
                'north_kp'    => $latest_payloads['north']['kp'] ?? null,
                'south_kp'    => $latest_payloads['south']['kp'] ?? null,
                'north_points'=> isset($latest_payloads['north']['viewline_coords']) ? count($latest_payloads['north']['viewline_coords']) : 0,
                'south_points'=> isset($latest_payloads['south']['viewline_coords']) ? count($latest_payloads['south']['viewline_coords']) : 0,
            ],
        ];
        $diagnostics['duration_ms'] = (int) round((microtime(true) - $start) * 1000);
        gaia_aurora_record_diagnostics($diagnostics);
        return;
    }

    if ($grid_resp['status'] !== 200 || !is_array($grid_resp['body'])) {
        $diagnostics['errors'][] = 'ovation_fetch_failed';
        if ($grid_resp['error']) {
            $diagnostics['errors'][] = $grid_resp['error'];
        }
        $diagnostics['trace'][] = 'serving fallback cache due to fetch failure';
        gaia_aurora_apply_fallback($diagnostics);
        return;
    }

    $grid_data = gaia_aurora_extract_grids($grid_resp['body']);
    if (!$grid_data['north'] || !$grid_data['south']) {
        $diagnostics['errors'][] = 'grid_parse_failed';
        $diagnostics['trace'][] = 'grid parsing failed – serving fallback';
        gaia_aurora_apply_fallback($diagnostics);
        return;
    }

    $kp_resp = gaia_aurora_http_get(GAIA_AURORA_KP_URL);
    $kp_info = gaia_aurora_parse_kp($kp_resp['body']);
    if (!$kp_info) {
        $diagnostics['errors'][] = 'kp_parse_failed';
    }

    $ts = $grid_data['timestamp'] ?: gmdate('c');
    $base_threshold = gaia_aurora_normalize_probability(GAIA_AURORA_VIEWLINE_P, 0.10);
    $north_threshold = GAIA_AURORA_VIEWLINE_P_NORTH !== null
        ? gaia_aurora_normalize_probability(GAIA_AURORA_VIEWLINE_P_NORTH, $base_threshold)
        : $base_threshold;
    $south_threshold = $base_threshold;
    $lon0_north = GAIA_AURORA_LON0_N;
    $lon0_south = GAIA_AURORA_LON0_S;
    $kp_levels = is_array(GAIA_AURORA_KP_LEVELS) ? GAIA_AURORA_KP_LEVELS : [];

    $north_bundle = gaia_aurora_build_payload('north', $ts, $grid_data['north'], $north_threshold, $kp_info, $grid_resp, $grid_data['meta'], $lon0_north, $kp_levels);
    $south_bundle = gaia_aurora_build_payload('south', $ts, $grid_data['south'], $south_threshold, $kp_info, $grid_resp, $grid_data['meta'], $lon0_south, $kp_levels);

    // Persist Hemisphere Power to ext.aurora_power when available
    $hp = gaia_aurora_extract_hemisphere_power($grid_resp['body']);
    if (is_array($hp) && ($hp['north'] !== null || $hp['south'] !== null)) {
        gaia_aurora_persist_ext_aurora_power($ts, $hp);
    }

    $north_payload = $north_bundle['payload'];
    $south_payload = $south_bundle['payload'];

    gaia_aurora_store_payload('north', $north_payload);
    gaia_aurora_store_payload('south', $south_payload);

    if (!empty($grid_resp['etag'])) {
        update_option($etag_key, $grid_resp['etag'], false);
    }

    gaia_aurora_persist_supabase($north_payload, $north_bundle['grid_raw'], $kp_resp['body']);
    gaia_aurora_persist_supabase($south_payload, $south_bundle['grid_raw'], $kp_resp['body']);

    gaia_aurora_write_media_json($north_payload, 'north');
    gaia_aurora_write_media_json($south_payload, 'south');
    gaia_aurora_write_daily_snapshot($north_payload, $south_payload);

    $diagnostics['cache_snapshot_final'] = [
        'north_ts' => $north_payload['ts'],
        'south_ts' => $south_payload['ts'],
    ];
    $diagnostics['cache_updated'] = true;
    $diagnostics['payload_summary'] = [
        'aurora' => [
            'north_kp' => $north_payload['kp'],
            'south_kp' => $south_payload['kp'],
            'north_points' => count($north_payload['viewline_coords']),
            'south_points' => count($south_payload['viewline_coords']),
        ],
    ];

    $diagnostics['trace'][] = 'payloads refreshed';
    $diagnostics['duration_ms'] = (int) round((microtime(true) - $start) * 1000);
    $diagnostics['cache_hit'] = false;
    gaia_aurora_record_diagnostics($diagnostics);
    error_log('[gaia_aurora] nowcast refreshed north=' . count($north_payload['viewline_coords']) . ' south=' . count($south_payload['viewline_coords']) . ' duration_ms=' . $diagnostics['duration_ms']);
}

function gaia_aurora_apply_fallback($diagnostics)
{
    $diagnostics['fallback'] = true;
    foreach (['north', 'south'] as $hemi) {
        $payload = gaia_aurora_get_cached_payload($hemi);
        if (is_array($payload)) {
            if (empty($payload['diagnostics']) || !is_array($payload['diagnostics'])) {
                $payload['diagnostics'] = [];
            }
            $payload['diagnostics']['fallback'] = true;
            gaia_aurora_store_payload($hemi, $payload);
        }
    }
    if (empty($diagnostics['cache_snapshot_final'])) {
        $diagnostics['cache_snapshot_final'] = $diagnostics['cache_snapshot_initial'];
    }
    gaia_aurora_record_diagnostics($diagnostics);
    error_log('[gaia_aurora] fallback triggered: ' . implode(';', $diagnostics['errors']));
}

/**
 * Extract grid arrays from the OVATION payload.
 */
function gaia_aurora_extract_grids($body)
{
    $out = [
        'north'     => null,
        'south'     => null,
        'timestamp' => null,
        'meta'      => [],
    ];

    if (!is_array($body)) {
        return $out;
    }

    // Multiple known formats – attempt to normalize.
    if (isset($body['Data']) && is_array($body['Data'])) {
        $slice = $body['Data'][0] ?? [];
        if (isset($slice['North']) && is_array($slice['North'])) {
            $out['north'] = $slice['North'];
        }
        if (isset($slice['South']) && is_array($slice['South'])) {
            $out['south'] = $slice['South'];
        }
        if (!empty($slice['Date']) && !empty($slice['Time'])) {
            $out['timestamp'] = gmdate('c', strtotime($slice['Date'] . ' ' . $slice['Time'] . ' UTC'));
        }
        if (isset($slice['KP'])) {
            $out['meta']['kp_hint'] = (float) $slice['KP'];
        }
    } elseif (isset($body['north']) && isset($body['south'])) {
        $out['north'] = $body['north'];
        $out['south'] = $body['south'];
        $out['timestamp'] = isset($body['time']) ? (string) $body['time'] : null;
    } elseif (isset($body['coordinates']) && is_array($body['coordinates'])) {
        // New NOAA shape: coordinates as an array of [lon, lat, prob] without hemisphere.
        $recon = gaia_aurora_reconstruct_from_coord_triplets($body['coordinates']);
        $out['north'] = $recon['north'];
        $out['south'] = $recon['south'];
        // Prefer "Observation Time", then "Forecast Time"
        if (!empty($body['Observation Time'])) {
            $out['timestamp'] = (string) $body['Observation Time'];
        } elseif (!empty($body['Forecast Time'])) {
            $out['timestamp'] = (string) $body['Forecast Time'];
        } else {
            $out['timestamp'] = null;
        }
        $out['meta'] = $recon['meta'];
    }

    return $out;
}

function gaia_aurora_reconstruct_from_coordinates($coords)
{
    $north = [];
    $south = [];
    $timestamp = null;

    foreach ($coords as $entry) {
        if (!is_array($entry)) {
            continue;
        }

        $hemi = null; $lat = null; $lon = null; $prob = null; $time = null;

        // Case A: associative object (has string keys, not a pure list)
        $is_assoc = array_keys($entry) !== range(0, count($entry) - 1);
        if ($is_assoc) {
            // normalize keys to lowercase
            $norm = [];
            foreach ($entry as $k => $v) {
                $norm[strtolower((string) $k)] = $v;
            }
            $hemi = $norm['hemisphere'] ?? ($norm['hemi'] ?? null);
            if (is_string($hemi) && strlen($hemi) === 1) {
                $hemi = ($hemi === 'N' || $hemi === 'n') ? 'north' : (($hemi === 'S' || $hemi === 's') ? 'south' : $hemi);
            } elseif (is_string($hemi)) {
                $hemi = strtolower($hemi);
            }
            $lat = $norm['latitude'] ?? ($norm['lat'] ?? ($norm['magnetic_latitude'] ?? ($norm['mlat'] ?? null)));
            $lon = $norm['longitude'] ?? ($norm['lon'] ?? ($norm['magnetic_longitude'] ?? ($norm['mlon'] ?? null)));
            $prob = $norm['probability'] ?? ($norm['oval_prob'] ?? ($norm['prob'] ?? ($norm['value'] ?? null)));
            $time = $norm['time'] ?? null;

        // Case B: positional array, commonly [lon, lat, prob, hemi?]
        } else {
            $lon  = isset($entry[0]) ? (float) $entry[0] : null;
            $lat  = isset($entry[1]) ? (float) $entry[1] : null;
            $prob = isset($entry[2]) ? (float) $entry[2] : null;
            $hraw = isset($entry[3]) ? $entry[3] : null;
            if (is_string($hraw) && strlen($hraw) === 1) {
                $hemi = ($hraw === 'N' || $hraw === 'n') ? 'north' : (($hraw === 'S' || $hraw === 's') ? 'south' : null);
            } elseif (is_string($hraw)) {
                $hemi = strtolower($hraw);
            }
        }

        if ($lat === null || $lon === null || $prob === null || !$hemi) {
            continue;
        }

        // Normalize indices:
        // lon in [-180,180] → col in [0..359]; be robust with negative values
        $col = (int) round(fmod(($lon + 540.0), 360.0) - 180.0 + 180.0);
        // lat in [+90..-90] → row in [0..180]
        $row = (int) round(90 - $lat);

        if ($hemi === 'north') {
            if (!isset($north[$row])) $north[$row] = [];
            $north[$row][$col] = $prob;
        } elseif ($hemi === 'south') {
            if (!isset($south[$row])) $south[$row] = [];
            $south[$row][$col] = $prob;
        }

        if (!$timestamp && $time) {
            $timestamp = (string) $time;
        }
    }

    // Sort rows/cols and convert to dense arrays
    ksort($north); ksort($south);
    foreach ($north as &$r) { ksort($r); $r = array_values($r); }
    foreach ($south as &$r) { ksort($r); $r = array_values($r); }

    return [
        'north'     => array_values($north),
        'south'     => array_values($south),
        'timestamp' => $timestamp,
        'meta'      => [],
    ];
}

/**
 * Reconstruct north/south grids from triplets [lon, lat, prob] (no hemisphere key).
 * Assumes lon in [0..359] degrees and lat in [-90..+90] degrees at 1° resolution.
 * Builds two 181x360 arrays (rows: lat 90..-90, cols: lon -180..+179 mapping) to match downstream logic.
 */
function gaia_aurora_reconstruct_from_coord_triplets($coords)
{
    // Initialize empty 181x360 grids with zeros
    $height = 181; // lat rows
    $width  = 360; // lon cols
    $north = array_fill(0, $height, array_fill(0, $width, 0.0));
    $south = array_fill(0, $height, array_fill(0, $width, 0.0));

    $count = 0;
    foreach ($coords as $e) {
        if (!is_array($e) || count($e) < 3) continue;
        $lon = (float) $e[0];
        $lat = (float) $e[1];
        $prob = (float) $e[2];

        // Normalize indices
        // Incoming lon appears to be 0..359. Our downstream uses -180..+179 columns,
        // but we store as 0..359 and later compute lon via step = 360/width.
        $col = (int) round(fmod($lon + 360.0, 360.0));
        // Lat rows: +90 (row 0) down to -90 (row 180)
        $row = (int) round(90 - $lat);
        if ($row < 0 || $row >= $height || $col < 0 || $col >= $width) continue;

        if ($lat >= 0) {
            $north[$row][$col] = $prob;
        } else {
            $south[$row][$col] = $prob;
        }
        $count++;
    }

    return [
        'north' => $north,
        'south' => $south,
        'meta'  => ['filled_points' => $count, 'width' => $width, 'height' => $height],
    ];
}

/**
 * Parse the NOAA KP JSON array.
 */
function gaia_aurora_parse_kp($body)
{
    if (!is_array($body)) {
        return null;
    }
    $last = null;
    foreach ($body as $row) {
        if (!is_array($row) || count($row) < 2) {
            continue;
        }
        $time = $row[0];
        $kp = $row[1];
        if ($kp === null || $kp === '' || !is_numeric($kp)) {
            continue;
        }
        $last = [
            'kp'      => (float) $kp,
            'kp_time' => is_numeric($time) ? gmdate('c', (int) $time) : (string) $time,
        ];
    }
    return $last;
}

/**
 * Build the REST payload for a hemisphere.
 */
function gaia_aurora_build_payload($hemisphere, $ts, $grid, $viewline_p, $kp_info, $grid_resp, $meta, $lon0, $kp_levels)
{
    $grid = gaia_aurora_normalize_grid($grid);
    $width = $grid['width'];
    $height = $grid['height'];
    $prob_grid = $grid['data'];

    $coords_raw = gaia_isoline_southmost($prob_grid, $viewline_p, $hemisphere);
    $coords_smoothed = gaia_line_smooth($coords_raw, GAIA_AURORA_SMOOTH_WINDOW);
    $coords = gaia_aurora_round_coords($coords_smoothed);
    $metrics = gaia_aurora_compute_metrics($coords, $hemisphere, $prob_grid);

    $effective_p = $viewline_p;
    if ($hemisphere === 'north' && ((int) ($metrics['count'] ?? 0) === 0) && $viewline_p > 0.03) {
        $salvage = max(0.03, $viewline_p - 0.02);
        $coords_raw = gaia_isoline_southmost($prob_grid, $salvage, $hemisphere);
        $coords_smoothed = gaia_line_smooth($coords_raw, GAIA_AURORA_SMOOTH_WINDOW);
        $coords = gaia_aurora_round_coords($coords_smoothed);
        $metrics = gaia_aurora_compute_metrics($coords, $hemisphere, $prob_grid);
        $effective_p = $salvage;
    }
    // Second salvage: if still no line, try a very permissive 1% contour
    if ($hemisphere === 'north' && ((int) ($metrics['count'] ?? 0) === 0) && $effective_p > 0.01) {
        $salvage2 = 0.01;
        $coords_raw = gaia_isoline_southmost($prob_grid, $salvage2, $hemisphere);
        $coords_smoothed = gaia_line_smooth($coords_raw, GAIA_AURORA_SMOOTH_WINDOW);
        $coords = gaia_aurora_round_coords($coords_smoothed);
        $metrics = gaia_aurora_compute_metrics($coords, $hemisphere, $prob_grid);
        $effective_p = $salvage2;
    }

    $kp_lines_payload = gaia_aurora_build_kp_lines($prob_grid, $hemisphere, $kp_levels);

    $kp = $kp_info['kp'] ?? ($meta['kp_hint'] ?? null);
    $kp_time = $kp_info['kp_time'] ?? null;

    $images = [
        'ovation_latest' => $hemisphere === 'north' ? GAIA_AURORA_IMAGE_NORTH : GAIA_AURORA_IMAGE_SOUTH,
    ];

    $diagnostics = [
        'fetched_at'  => gmdate('c'),
        'duration_ms' => $grid_resp['duration_ms'],
        'cache_hit'   => false,
        'source_urls' => [
            'ovation' => GAIA_AURORA_NOWCAST_URL,
            'kp'      => GAIA_AURORA_KP_URL,
        ],
    ];

    $payload = [
        'ts'                  => $ts,
        'hemisphere'          => $hemisphere,
        'kp'                  => $kp,
        'kp_obs_time'         => $kp_time,
        'kp_bucket'           => gaia_aurora_kp_bucket($kp),
        'grid'                => [
            'w'      => $width,
            'h'      => $height,
            'src'    => 'swpc_ovation',
            'sample' => 'omitted',
        ],
        'viewline_p'          => $effective_p,
        'viewline_requested_p'=> $viewline_p,
        'viewline_coords'     => $coords,
        'metrics'             => $metrics,
        'images'              => $images,
        'diagnostics'         => $diagnostics,
        'lon0'                => (float) $lon0,
        'kp_lines'            => $kp_lines_payload,
    ];

    return [
        'payload'  => $payload,
        'grid_raw' => $prob_grid,
    ];
}

function gaia_aurora_kp_bucket($kp)
{
    if ($kp === null) {
        return 'unknown';
    }
    $kp = (float) $kp;
    if ($kp <= 2.99) {
        return 'quiet';
    } elseif ($kp <= 3.49) {
        return 'unsettled';
    } elseif ($kp <= 4.49) {
        return 'active';
    } elseif ($kp <= 5.49) {
        return 'minor';
    } elseif ($kp <= 6.49) {
        return 'moderate';
    } elseif ($kp <= 7.49) {
        return 'strong';
    } elseif ($kp <= 8.49) {
        return 'severe';
    }
    return 'extreme';
}

function gaia_aurora_normalize_grid($grid)
{
    $rows = [];
    if (is_array($grid)) {
        foreach ($grid as $row) {
            if (is_array($row)) {
                $rows[] = array_map('floatval', array_values($row));
            }
        }
    }
    $height = count($rows);
    $width = $height > 0 ? count($rows[0]) : 0;
    return [
        'data'   => $rows,
        'width'  => $width,
        'height' => $height,
    ];
}

function gaia_isoline_southmost($grid, $pstar, $hemi)
{
    $coords = [];
    $rows = count($grid);
    if ($rows === 0) {
        return $coords;
    }
    $cols = count($grid[0]);
    if ($cols === 0) {
        return $coords;
    }
    $threshold = ($pstar <= 1) ? $pstar * 100 : $pstar;
    $row_start = min(90, $rows - 1);
    if ($row_start < 0) {
        return $coords;
    }

    if ($hemi === 'south') {
        $row_start = 90;
        if ($row_start >= $rows) {
            $row_start = $rows - 1;
        }
        $row_end = min($rows - 1, 180);
        if ($row_start > $row_end) {
            $row_start = $row_end;
        }
        $step = 1;
    } else {
        $row_end = 0;
        if ($row_start < $row_end) {
            $row_start = $row_end;
        }
        $step = -1;
    }

    for ($lon = 0; $lon < $cols; $lon++) {
        $hit = null;
        $prev_prob = null;
        $prev_lat = null;
        for ($r = $row_start; ($step < 0 ? $r >= $row_end : $r <= $row_end); $r += $step) {
            if (!isset($grid[$r][$lon])) {
                $prob = 0;
            } else {
                $prob = (float) $grid[$r][$lon];
            }
            $lat = 90 - $r;
            if ($prob >= $threshold) {
                if ($prev_prob !== null && $prob !== $prev_prob) {
                    $ratio = ($threshold - $prev_prob) / max(0.0001, $prob - $prev_prob);
                    $ratio = max(0, min(1, $ratio));
                    $lat = $prev_lat + ($lat - $prev_lat) * $ratio;
                }
                $hit = [
                    'lon' => $lon - 180,
                    'lat' => $lat,
                ];
                break;
            }
            $prev_prob = $prob;
            $prev_lat = $lat;
        }
        if ($hit !== null) {
            $coords[] = $hit;
        }
    }

    return $coords;
}

function gaia_line_smooth($coords, $window = 5)
{
    $count = count($coords);
    if ($count === 0 || $window <= 1) {
        return $coords;
    }
    $half = max(1, (int) floor($window / 2));
    $out = [];
    for ($i = 0; $i < $count; $i++) {
        if (!isset($coords[$i]['lon'], $coords[$i]['lat'])) {
            continue;
        }
        $sum = 0;
        $samples = 0;
        for ($j = max(0, $i - $half); $j <= min($count - 1, $i + $half); $j++) {
            if (!isset($coords[$j]['lat'])) {
                continue;
            }
            $sum += (float) $coords[$j]['lat'];
            $samples++;
        }
        $lat = $samples > 0 ? $sum / $samples : (float) $coords[$i]['lat'];
        $out[] = [
            'lon' => (float) $coords[$i]['lon'],
            'lat' => $lat,
        ];
    }
    return $out;
}

function gaia_aurora_round_coords($coords, $precision = 2)
{
    $out = [];
    foreach ($coords as $coord) {
        if (!isset($coord['lon'], $coord['lat'])) {
            continue;
        }
        $out[] = [
            'lon' => round((float) $coord['lon'], $precision),
            'lat' => round((float) $coord['lat'], $precision),
        ];
    }
    return $out;
}

function gaia_aurora_build_kp_lines($grid, $hemisphere, $levels)
{
    $out = [];
    if (!is_array($levels)) {
        return $out;
    }
    foreach ($levels as $idx => $level) {
        $p = gaia_aurora_normalize_probability($level, null);
        if ($p === null) {
            continue;
        }
        $coords_raw = gaia_isoline_southmost($grid, $p, $hemisphere);
        $coords = gaia_aurora_round_coords(gaia_line_smooth($coords_raw, GAIA_AURORA_SMOOTH_WINDOW));
        if (count($coords) < 2) {
            continue;
        }
        $out[] = [
            'p'      => $p,
            'coords' => $coords,
        ];
    }
    return $out;
}

function gaia_aurora_compute_metrics($coords, $hemisphere, $grid = null)
{
    $count = is_array($coords) ? count($coords) : 0;
    if ($count === 0) {
        return [
            'min_lat'        => null,
            'median_lat'     => null,
            'mean_prob'      => null,
            'mean_prob_line' => null,
            'count'          => 0,
            'hemisphere'     => $hemisphere,
        ];
    }

    $lats = [];
    foreach ($coords as $coord) {
        if (isset($coord['lat'])) {
            $lats[] = (float) $coord['lat'];
        }
    }
    if (!$lats) {
        return [
            'min_lat'        => null,
            'median_lat'     => null,
            'mean_prob'      => null,
            'mean_prob_line' => null,
            'count'          => 0,
            'hemisphere'     => $hemisphere,
        ];
    }
    sort($lats);
    $lat_count = count($lats);
    $min = $lats[0];
    $mid = (int) floor($lat_count / 2);
    if ($lat_count % 2 === 0) {
        $median = ($lats[$mid - 1] + $lats[$mid]) / 2;
    } else {
        $median = $lats[$mid];
    }

    $mean_prob = null;
    if (is_array($grid) && $grid) {
        $max_row = count($grid) - 1;
        $max_col = $max_row >= 0 ? count($grid[0]) - 1 : -1;
        $sum = 0;
        $samples = 0;
        foreach ($coords as $coord) {
            if (!isset($coord['lat'], $coord['lon'])) {
                continue;
            }
            $row = (int) round(90 - (float) $coord['lat']);
            $col = (int) round((float) $coord['lon'] + 180);
            if ($max_row >= 0) {
                $row = max(0, min($max_row, $row));
            }
            if ($max_col >= 0) {
                $col = max(0, min($max_col, $col));
            }
            if (isset($grid[$row][$col])) {
                $sum += (float) $grid[$row][$col];
                $samples++;
            }
        }
        if ($samples > 0) {
            $mean_prob = round($sum / $samples, 2);
        }
    }

    return [
        'min_lat'        => round($min, 2),
        'median_lat'     => round($median, 2),
        'mean_prob'      => $mean_prob,
        'mean_prob_line' => $mean_prob,
        'count'          => $lat_count,
        'hemisphere'     => $hemisphere,
    ];
}

function gaia_aurora_store_payload($hemisphere, $payload)
{
    set_transient('gaia_aurora_nowcast_' . $hemisphere, $payload, GAIA_AURORA_CACHE_TTL);
    update_option('gaia_aurora_last_' . $hemisphere, $payload, false);
}

function gaia_aurora_get_cached_payload($hemisphere)
{
    $cached = get_transient('gaia_aurora_nowcast_' . $hemisphere);
    if (is_array($cached)) {
        return $cached;
    }
    $stored = get_option('gaia_aurora_last_' . $hemisphere);
    return is_array($stored) ? $stored : null;
}

function gaia_aurora_persist_supabase($payload, $grid_raw, $kp_raw)
{
    $ts = $payload['ts'] ?? null;
    if (!$ts) {
        return;
    }
    $row = [
        'ts'             => $ts,
        'hemisphere'     => $payload['hemisphere'],
        'grid_width'     => $payload['grid']['w'],
        'grid_height'    => $payload['grid']['h'],
        'probabilities'  => $grid_raw,
        'kp'             => $payload['kp'],
        'kp_obs_time'    => $payload['kp_obs_time'],
        'viewline_p'     => $payload['viewline_p'],
        'viewline_coords'=> $payload['viewline_coords'],
        'source'         => 'SWPC_OVATION',
        'fetch_ms'       => $payload['diagnostics']['duration_ms'] ?? null,
    ];
    // Store the compact grid only when small enough; skip to keep payload manageable.
    $err = gaia_aurora_supabase_post('aurora_nowcast_samples', $row, ['on_conflict' => 'ts,hemisphere']);
    if ($err) {
        error_log('[gaia_aurora] supabase nowcast error: ' . $err);
    }

    if (!empty($payload['kp_obs_time']) && $payload['kp'] !== null) {
        $kp_row = [
            'kp_time' => $payload['kp_obs_time'],
            'kp'      => $payload['kp'],
            'raw'     => $kp_raw,
        ];
        $err = gaia_aurora_supabase_post('kp_obs', $kp_row, ['on_conflict' => 'kp_time']);
        if ($err) {
            error_log('[gaia_aurora] supabase kp error: ' . $err);
        }
    }
}

function gaia_aurora_write_media_json($payload, $hemisphere)
{
    if (!GAIA_AURORA_ENABLE_JSON_EXPORT) {
        return;
    }
    $dir = gaia_aurora_media_path('public/aurora/nowcast');
    if (!wp_mkdir_p($dir)) {
        error_log('[gaia_aurora] unable to create media dir ' . $dir);
        return;
    }
    $file = trailingslashit($dir) . 'latest_' . $hemisphere . '.json';
    file_put_contents($file, wp_json_encode($payload, JSON_UNESCAPED_SLASHES));
}

function gaia_aurora_write_daily_snapshot($north, $south)
{
    if (!GAIA_AURORA_ENABLE_JSON_EXPORT) {
        return;
    }
    $dir = gaia_aurora_media_path('public/aurora/nowcast');
    if (!wp_mkdir_p($dir)) {
        error_log('[gaia_aurora] unable to create media dir ' . $dir);
        return;
    }
    $day = substr($north['ts'] ?? gmdate('c'), 0, 10);
    $file = trailingslashit($dir) . 'aurora-nowcast-' . $day . '.json';
    if (!file_exists($file)) {
        $snapshot = [
            'north' => $north,
            'south' => $south,
            'diagnostics' => [
                'fetched_at' => gmdate('c'),
                'cache_hit'  => false,
            ],
        ];
        file_put_contents($file, wp_json_encode($snapshot, JSON_UNESCAPED_SLASHES));
    }
}

// -----------------------------------------------------------------------------
// Experimental viewline assets
// -----------------------------------------------------------------------------

function gaia_aurora_refresh_viewline()
{
    $tonight = gaia_aurora_fetch_viewline_asset('tonight', GAIA_AURORA_VIEWLINE_TONIGHT);
    $tomorrow = gaia_aurora_fetch_viewline_asset('tomorrow', GAIA_AURORA_VIEWLINE_TOMORROW);

    $row = [
        'ts'             => gmdate('Y-m-d'),
        'tonight_url'    => $tonight['url'] ?? GAIA_AURORA_VIEWLINE_TONIGHT,
        'tomorrow_url'   => $tomorrow['url'] ?? GAIA_AURORA_VIEWLINE_TOMORROW,
        'tonight_etag'   => $tonight['etag'] ?? null,
        'tomorrow_etag'  => $tomorrow['etag'] ?? null,
        'fetch_ms'       => max($tonight['duration_ms'] ?? 0, $tomorrow['duration_ms'] ?? 0),
        'updated_at'     => gmdate('c'),
    ];
    $err = gaia_aurora_supabase_post('aurora_viewline_forecast', $row, ['on_conflict' => 'ts']);
    if ($err) {
        error_log('[gaia_aurora] supabase viewline error: ' . $err);
    }
}

function gaia_aurora_fetch_viewline_asset($label, $url)
{
    $etag_key = 'gaia_aurora_viewline_etag_' . $label;
    $stored = get_option($etag_key);
    $resp = gaia_aurora_http_get($url, ['accept' => 'image/png', 'etag' => $stored]);

    $record = [
        'url'          => $url,
        'etag'         => $resp['etag'],
        'status'       => $resp['status'],
        'duration_ms'  => $resp['duration_ms'],
        'fetched_at'   => gmdate('c'),
        'cache_hit'    => ($resp['status'] === 304),
    ];

    if ($resp['status'] === 200 && $resp['etag']) {
        update_option($etag_key, $resp['etag'], false);
    }

    update_option('gaia_aurora_viewline_' . $label, $record, false);
    gaia_aurora_write_viewline_json($label, $record);
    return $record;
}

function gaia_aurora_write_viewline_json($label, $record)
{
    if (!GAIA_AURORA_ENABLE_JSON_EXPORT) {
        return;
    }
    $dir = gaia_aurora_media_path('public/aurora/viewline');
    if (!wp_mkdir_p($dir)) {
        error_log('[gaia_aurora] unable to create media dir ' . $dir);
        return;
    }
    $file = trailingslashit($dir) . $label . '.json';
    file_put_contents($file, wp_json_encode($record, JSON_UNESCAPED_SLASHES));
}

function gaia_aurora_read_viewline_json($label)
{
    $record = get_option('gaia_aurora_viewline_' . $label);
    if (is_array($record)) {
        return $record;
    }
    if (GAIA_AURORA_ENABLE_JSON_EXPORT) {
        $file = gaia_aurora_media_path('public/aurora/viewline/' . $label . '.json');
        if (file_exists($file)) {
            $decoded = json_decode(file_get_contents($file), true);
            if (is_array($decoded)) {
                return $decoded;
            }
        }
    }
    return [
        'url'        => $label === 'tonight' ? GAIA_AURORA_VIEWLINE_TONIGHT : GAIA_AURORA_VIEWLINE_TOMORROW,
        'fetched_at' => null,
        'etag'       => null,
    ];
}

// -----------------------------------------------------------------------------
// REST routes
// -----------------------------------------------------------------------------

function gaia_aurora_register_rest_routes()
{
    register_rest_route('gaia/v1', '/aurora/nowcast', [
        'methods'             => 'GET',
        'callback'            => 'gaia_aurora_rest_nowcast',
        'permission_callback' => '__return_true',
        'args'                => [
            'hemi' => [
                'type'              => 'string',
                'required'          => false,
                'validate_callback' => function ($value) {
                    $value = strtolower((string) $value);
                    return in_array($value, ['north', 'south'], true);
                },
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/aurora/viewline/(?P<label>tonight|tomorrow)', [
        'methods'             => 'GET',
        'callback'            => 'gaia_aurora_rest_viewline',
        'permission_callback' => '__return_true',
    ]);

    register_rest_route('gaia/v1', '/aurora/diagnostics', [
        'methods'             => 'GET',
        'callback'            => 'gaia_aurora_rest_diagnostics',
        'permission_callback' => '__return_true',
    ]);

    register_rest_route('gaia/v1', '/aurora/fetch-now', [
        'methods'             => 'POST',
        'callback'            => 'gaia_aurora_rest_fetch_now',
        'permission_callback' => '__return_true',
        'args'                => [
            'hemi' => [
                'type'              => 'string',
                'required'          => false,
                'validate_callback' => function ($value) {
                    $value = strtolower((string) $value);
                    return in_array($value, ['north', 'south', 'both'], true);
                },
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/aurora/cron-run', [
        'methods'             => 'POST',
        'callback'            => 'gaia_aurora_rest_cron_run',
        'permission_callback' => '__return_true',
    ]);

    // Diagnostic: summarize the raw OVATION payload shape for parser adaptation
    register_rest_route('gaia/v1', '/aurora/ovation-sample', [
        'methods'             => 'GET',
        'callback'            => 'gaia_aurora_rest_ovation_sample',
        'permission_callback' => '__return_true',
    ]);
}

function gaia_aurora_rest_nowcast($request)
{
    $hemi = strtolower($request->get_param('hemi') ?: 'north');
    if ($hemi !== 'south') {
        $hemi = 'north';
    }
    $payload = gaia_aurora_get_cached_payload($hemi);
    if (!$payload && GAIA_AURORA_ENABLE_JSON_EXPORT) {
        $file = gaia_aurora_media_path('public/aurora/nowcast/latest_' . $hemi . '.json');
        if (file_exists($file)) {
            $decoded = json_decode(file_get_contents($file), true);
            if (is_array($decoded)) {
                $decoded['diagnostics']['fallback'] = true;
                $payload = $decoded;
            }
        }
    }
    if (!$payload) {
        return new WP_REST_Response([
            'error' => 'no_data',
        ], 503);
    }
    return rest_ensure_response($payload);
}

function gaia_aurora_rest_viewline($request)
{
    $label = $request['label'];
    $record = gaia_aurora_read_viewline_json($label);
    return rest_ensure_response($record);
}

function gaia_aurora_rest_diagnostics()
{
    $diag = gaia_aurora_get_diagnostics();
    $diag['aurora'] = [
        'cache_snapshot_initial' => $diag['cache_snapshot_initial'] ?? [
            'north_ts' => null,
            'south_ts' => null,
        ],
        'cache_snapshot_final'   => $diag['cache_snapshot_final'] ?? [
            'north_ts' => null,
            'south_ts' => null,
        ],
        'cache_updated'          => $diag['cache_updated'] ?? false,
        'errors'                 => $diag['errors'] ?? [],
        'trace'                  => $diag['trace'] ?? [],
        'run_started_at'         => $diag['run_started_at'] ?? null,
    ];
    return rest_ensure_response($diag);
}

function gaia_aurora_rest_fetch_now(WP_REST_Request $request)
{
    $hemi = strtolower($request->get_param('hemi') ?: 'both');
    $started = microtime(true);

    // If a specific hemisphere is requested, we can reuse the main function and then filter the cache read.
    // Simpler: just run the full refresh; it computes both hemispheres in one pass.
    gaia_aurora_refresh_nowcast();

    $resp = [
        'ran'        => true,
        'duration_ms'=> (int) round((microtime(true) - $started) * 1000),
        'hemi'       => $hemi,
        'north'      => gaia_aurora_get_cached_payload('north'),
        'south'      => gaia_aurora_get_cached_payload('south'),
        'diagnostics'=> gaia_aurora_get_diagnostics(),
    ];
    return rest_ensure_response($resp);
}


function gaia_aurora_rest_cron_run(WP_REST_Request $request)
{
    $started = microtime(true);
    gaia_aurora_refresh_nowcast();
    gaia_aurora_refresh_viewline();
    $diag = gaia_aurora_get_diagnostics();
    return rest_ensure_response([
        'ran'         => true,
        'duration_ms' => (int) round((microtime(true) - $started) * 1000),
        'diagnostics' => $diag,
        'nowcast'     => [
            'north' => gaia_aurora_get_cached_payload('north'),
            'south' => gaia_aurora_get_cached_payload('south'),
        ],
        'viewline'    => [
            'tonight' => gaia_aurora_read_viewline_json('tonight'),
            'tomorrow'=> gaia_aurora_read_viewline_json('tomorrow'),
        ],
    ]);
}

/**
 * Diagnostic: fetch the raw OVATION payload and summarize its structure.
 */
function gaia_aurora_rest_ovation_sample(WP_REST_Request $request)
{
    $resp = gaia_aurora_http_get(GAIA_AURORA_NOWCAST_URL, ['timeout' => 10]);
    $out = [
        'status'  => $resp['status'],
        'ms'      => $resp['duration_ms'],
        'has_body'=> is_array($resp['body']),
        'keys'    => is_array($resp['body']) ? array_slice(array_keys($resp['body']), 0, 12) : null,
    ];

    if (is_array($resp['body'])) {
        // Try to expose common shapes without dumping huge payloads
        if (isset($resp['body']['coordinates']) && is_array($resp['body']['coordinates'])) {
            $coords = $resp['body']['coordinates'];
            $out['coordinates'] = [
                'type'   => gettype($coords),
                'length' => is_array($coords) ? count($coords) : null,
                'sample' => array_slice($coords, 0, 5),
            ];
        } elseif (isset($resp['body']['north']) && isset($resp['body']['south'])) {
            $out['north_rows'] = is_array($resp['body']['north']) ? count($resp['body']['north']) : null;
            $out['south_rows'] = is_array($resp['body']['south']) ? count($resp['body']['south']) : null;
        } elseif (isset($resp['body']['Data']) && is_array($resp['body']['Data'])) {
            $slice = $resp['body']['Data'][0] ?? null;
            if (is_array($slice)) {
                $out['Data_keys'] = array_slice(array_keys($slice), 0, 12);
                $out['North_rows'] = isset($slice['North']) && is_array($slice['North']) ? count($slice['North']) : null;
                $out['South_rows'] = isset($slice['South']) && is_array($slice['South']) ? count($slice['South']) : null;
            }
        } elseif (array_keys($resp['body']) === range(0, count($resp['body']) - 1)) {
            // Root is a list/array — include first element's keys
            $first = $resp['body'][0] ?? null;
            if (is_array($first)) {
                $out['root_array'] = [
                    'length' => count($resp['body']),
                    'first_keys' => array_keys($first),
                    'first_sample' => (is_array($first) ? array_slice($first, 0, 1) : $first),
                ];
                if (isset($first['coordinates']) && is_array($first['coordinates'])) {
                    $out['root_array_coordinates'] = [
                        'length' => count($first['coordinates']),
                        'sample' => array_slice($first['coordinates'], 0, 5),
                    ];
                }
            }
        }
    } else {
        $out['note'] = 'non-array body';
    }
    return rest_ensure_response($out);
}

