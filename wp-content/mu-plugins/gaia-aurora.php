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
    define('GAIA_AURORA_NOWCAST_URL', 'https://services.swpc.noaa.gov/json/ovation_aurora_latest.json');
}
if (!defined('GAIA_AURORA_KP_URL')) {
    define('GAIA_AURORA_KP_URL', 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json');
}
if (!defined('GAIA_AURORA_IMAGE_NORTH')) {
    define('GAIA_AURORA_IMAGE_NORTH', 'https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg');
}
if (!defined('GAIA_AURORA_IMAGE_SOUTH')) {
    define('GAIA_AURORA_IMAGE_SOUTH', 'https://services.swpc.noaa.gov/images/animations/ovation/south/latest.jpg');
}
if (!defined('GAIA_AURORA_VIEWLINE_TONIGHT')) {
    define('GAIA_AURORA_VIEWLINE_TONIGHT', 'https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tonights_static_viewline_forecast.png');
}
if (!defined('GAIA_AURORA_VIEWLINE_TOMORROW')) {
    define('GAIA_AURORA_VIEWLINE_TOMORROW', 'https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/tomorrow_nights_static_viewline_forecast.png');
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

/**
 * Resolve an environment variable with sensible fallbacks.
 */
function gaia_aurora_env($key, $default = null)
{
    $val = getenv($key);
    if ($val === false || $val === '') {
        return $default;
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
function gaia_aurora_supabase_post($path, $payload, $params = [])
{
    $rest = gaia_aurora_env('SUPABASE_REST_URL');
    $key  = gaia_aurora_env('SUPABASE_SERVICE_KEY') ?: gaia_aurora_env('SUPABASE_ANON_KEY');
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
            'Content-Type' => 'application/json',
            'Accept'       => 'application/json',
            'apikey'       => $key,
            'Authorization'=> 'Bearer ' . $key,
            'Prefer'       => 'resolution=merge-duplicates',
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
    $viewline_p = GAIA_AURORA_VIEWLINE_P;

    $north_bundle = gaia_aurora_build_payload('north', $ts, $grid_data['north'], $viewline_p, $kp_info, $grid_resp, $grid_data['meta']);
    $south_bundle = gaia_aurora_build_payload('south', $ts, $grid_data['south'], $viewline_p, $kp_info, $grid_resp, $grid_data['meta']);

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
        // Flattened coordinates – reconstruct into grids.
        $out = gaia_aurora_reconstruct_from_coordinates($body['coordinates']);
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
        $hemi = strtolower((string) ($entry['hemisphere'] ?? ''));
        $lat = isset($entry['latitude']) ? (float) $entry['latitude'] : (isset($entry['magnetic_latitude']) ? (float) $entry['magnetic_latitude'] : null);
        $lon = isset($entry['longitude']) ? (float) $entry['longitude'] : (isset($entry['magnetic_longitude']) ? (float) $entry['magnetic_longitude'] : null);
        $prob = isset($entry['probability']) ? (float) $entry['probability'] : (isset($entry['oval_prob']) ? (float) $entry['oval_prob'] : null);
        if ($lat === null || $lon === null || $prob === null) {
            continue;
        }
        $lon_index = (int) round(($lon + 180) % 360);
        $lat_index = (int) round(90 - $lat);
        if ($hemi === 'north') {
            if (!isset($north[$lat_index])) {
                $north[$lat_index] = [];
            }
            $north[$lat_index][$lon_index] = $prob;
        } elseif ($hemi === 'south') {
            if (!isset($south[$lat_index])) {
                $south[$lat_index] = [];
            }
            $south[$lat_index][$lon_index] = $prob;
        }
        if (!$timestamp && !empty($entry['time'])) {
            $timestamp = (string) $entry['time'];
        }
    }
    ksort($north);
    ksort($south);
    foreach ($north as &$row) {
        ksort($row);
        $row = array_values($row);
    }
    foreach ($south as &$row) {
        ksort($row);
        $row = array_values($row);
    }
    return [
        'north'     => array_values($north),
        'south'     => array_values($south),
        'timestamp' => $timestamp,
        'meta'      => [],
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
function gaia_aurora_build_payload($hemisphere, $ts, $grid, $viewline_p, $kp_info, $grid_resp, $meta)
{
    $grid = gaia_aurora_normalize_grid($grid);
    $width = $grid['width'];
    $height = $grid['height'];
    $prob_grid = $grid['data'];

    $coords = gaia_aurora_derive_viewline($prob_grid, $hemisphere, $viewline_p);
    $metrics = gaia_aurora_compute_metrics($coords, $prob_grid, $hemisphere);

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
        'ts'             => $ts,
        'hemisphere'     => $hemisphere,
        'kp'             => $kp,
        'kp_obs_time'    => $kp_time,
        'kp_bucket'      => gaia_aurora_kp_bucket($kp),
        'grid'           => [
            'w'       => $width,
            'h'       => $height,
            'src'     => 'swpc_ovation',
            'sample'  => 'omitted',
        ],
        'viewline_p'     => $viewline_p,
        'viewline_coords'=> $coords,
        'metrics'        => $metrics,
        'images'         => $images,
        'diagnostics'    => $diagnostics,
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

function gaia_aurora_derive_viewline($grid, $hemisphere, $p_threshold)
{
    $coords = [];
    $height = count($grid);
    if ($height === 0) {
        return $coords;
    }
    $width = count($grid[0]);
    if ($width === 0) {
        return $coords;
    }
    $equator_index = (int) floor(($height - 1) / 2);
    $lon_step = 360 / max(1, $width);

    for ($col = 0; $col < $width; $col++) {
        $lon = -180 + $col * $lon_step;
        $prob_column = [];
        for ($row = 0; $row < $height; $row++) {
            $prob_column[$row] = $grid[$row][$col] ?? 0;
        }
        if ($hemisphere === 'north') {
            $lat = gaia_aurora_scan_latitude($prob_column, $equator_index, 0, -1, $p_threshold, $height);
        } else {
            $lat = gaia_aurora_scan_latitude($prob_column, $equator_index, $height - 1, 1, $p_threshold, $height);
        }
        if ($lat !== null) {
            $coords[] = ['lon' => round($lon, 2), 'lat' => round($lat, 2)];
        }
    }

    return gaia_aurora_smooth_coords($coords, GAIA_AURORA_SMOOTH_WINDOW);
}

function gaia_aurora_scan_latitude($prob_column, $start, $end, $step, $threshold, $height)
{
    $prev_prob = null;
    $prev_lat = null;
    for ($row = $start; ($step < 0 ? $row >= $end : $row <= $end); $row += $step) {
        $prob = $prob_column[$row] ?? 0;
        $lat = 90 - $row;
        if ($prev_prob !== null && $prob >= $threshold && $prev_prob < $threshold) {
            $ratio = ($threshold - $prev_prob) / max(0.0001, $prob - $prev_prob);
            $lat = $prev_lat + ($lat - $prev_lat) * (1 - $ratio);
            return $lat;
        }
        if ($prob >= $threshold) {
            return $lat;
        }
        $prev_prob = $prob;
        $prev_lat = $lat;
    }
    return null;
}

function gaia_aurora_smooth_coords($coords, $window)
{
    $count = count($coords);
    if ($count === 0 || $window <= 1) {
        return $coords;
    }
    $half = (int) floor($window / 2);
    $smoothed = [];
    for ($i = 0; $i < $count; $i++) {
        $sum = 0;
        $weight = 0;
        for ($j = max(0, $i - $half); $j <= min($count - 1, $i + $half); $j++) {
            $sum += $coords[$j]['lat'];
            $weight++;
        }
        if ($weight > 0) {
            $lat = round($sum / $weight, 2);
        } else {
            $lat = $coords[$i]['lat'];
        }
        $smoothed[] = ['lon' => $coords[$i]['lon'], 'lat' => $lat];
    }
    return $smoothed;
}

function gaia_aurora_compute_metrics($coords, $grid, $hemisphere)
{
    if (!$coords) {
        return [];
    }
    $lats = array_column($coords, 'lat');
    sort($lats);
    $min = $lats[0];
    $mid_index = (int) floor(count($lats) / 2);
    $median = $lats[$mid_index];

    $mean_prob = null;
    $sum = 0;
    $samples = 0;
    foreach ($coords as $coord) {
        $row = (int) round(90 - $coord['lat']);
        $col = (int) round(($coord['lon'] + 180));
        if (isset($grid[$row][$col])) {
            $sum += (float) $grid[$row][$col];
            $samples++;
        }
    }
    if ($samples > 0) {
        $mean_prob = round($sum / $samples, 2);
    }

    return [
        'min_lat'        => round($min, 2),
        'median_lat'     => round($median, 2),
        'mean_prob_line' => $mean_prob,
        'count'          => count($coords),
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
    $err = gaia_aurora_supabase_post('marts.aurora_nowcast_samples', $row, ['on_conflict' => 'ts,hemisphere']);
    if ($err) {
        error_log('[gaia_aurora] supabase nowcast error: ' . $err);
    }

    if (!empty($payload['kp_obs_time']) && $payload['kp'] !== null) {
        $kp_row = [
            'kp_time' => $payload['kp_obs_time'],
            'kp'      => $payload['kp'],
            'raw'     => $kp_raw,
        ];
        $err = gaia_aurora_supabase_post('marts.kp_obs', $kp_row, ['on_conflict' => 'kp_time']);
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
    $err = gaia_aurora_supabase_post('marts.aurora_viewline_forecast', $row, ['on_conflict' => 'ts']);
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

