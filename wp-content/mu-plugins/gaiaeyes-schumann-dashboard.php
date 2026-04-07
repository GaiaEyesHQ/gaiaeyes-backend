<?php
/**
 * Plugin Name: Gaia Eyes - Schumann Dashboard
 * Description: Public Schumann dashboard block + shortcode (gauge, heatmap, pulse line).
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

require_once __DIR__ . '/gaiaeyes-api-helpers.php';

if (!defined('GAIAEYES_SCHUMANN_LATEST_TTL')) {
    define('GAIAEYES_SCHUMANN_LATEST_TTL', 60);
}
if (!defined('GAIAEYES_SCHUMANN_SERIES_TTL')) {
    define('GAIAEYES_SCHUMANN_SERIES_TTL', 300);
}
if (!defined('GAIAEYES_SCHUMANN_HEATMAP_TTL')) {
    define('GAIAEYES_SCHUMANN_HEATMAP_TTL', 300);
}
if (!defined('GAIAEYES_SCHUMANN_APP_LINK')) {
    define('GAIAEYES_SCHUMANN_APP_LINK', 'gaiaeyes://open?screen=schumann');
}
if (!defined('GAIAEYES_SCHUMANN_DETAIL_TTL')) {
    define('GAIAEYES_SCHUMANN_DETAIL_TTL', 300);
}
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

if (!function_exists('gaiaeyes_schumann_dashboard_api_base')) {
    function gaiaeyes_schumann_dashboard_api_base() {
        static $resolved = null;
        if ($resolved !== null) {
            return $resolved;
        }

        $api_base = '';
        if (defined('GAIAEYES_API_BASE')) {
            $api_base = (string) GAIAEYES_API_BASE;
        }
        if ($api_base === '') {
            $env = getenv('GAIAEYES_API_BASE');
            if (is_string($env)) {
                $api_base = $env;
            }
        }

        $api_base = trim($api_base);
        $resolved = $api_base !== '' ? rtrim(esc_url_raw($api_base), '/') : '';
        return $resolved;
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_ttl')) {
    function gaiaeyes_schumann_dashboard_ttl($kind) {
        switch ($kind) {
            case 'latest':
                return max(5, (int) apply_filters('gaiaeyes_schumann_latest_ttl', GAIAEYES_SCHUMANN_LATEST_TTL));
            case 'series':
                return max(5, (int) apply_filters('gaiaeyes_schumann_series_ttl', GAIAEYES_SCHUMANN_SERIES_TTL));
            case 'heatmap':
                return max(5, (int) apply_filters('gaiaeyes_schumann_heatmap_ttl', GAIAEYES_SCHUMANN_HEATMAP_TTL));
            default:
                return 60;
        }
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_fetch_json')) {
    function gaiaeyes_schumann_dashboard_fetch_json($path, $cache_key, $ttl) {
        $base = gaiaeyes_schumann_dashboard_api_base();
        if ($base === '') {
            return null;
        }

        $url = $base . $path;
        $bearer = defined('GAIAEYES_API_BEARER') ? trim((string) GAIAEYES_API_BEARER) : trim((string) getenv('GAIAEYES_API_BEARER'));
        $dev_user = defined('GAIAEYES_API_DEV_USERID') ? trim((string) GAIAEYES_API_DEV_USERID) : trim((string) getenv('GAIAEYES_API_DEV_USERID'));

        if (function_exists('gaiaeyes_http_get_json_api_cached')) {
            return gaiaeyes_http_get_json_api_cached($url, $cache_key, $ttl, $bearer, $dev_user);
        }

        $cached = get_transient($cache_key);
        if ($cached !== false) {
            return $cached;
        }

        $headers = [
            'Accept' => 'application/json',
            'User-Agent' => 'GaiaEyesWP/1.0',
        ];
        if ($bearer !== '') {
            $headers['Authorization'] = 'Bearer ' . $bearer;
        }
        if ($dev_user !== '') {
            $headers['X-Dev-UserId'] = $dev_user;
        }

        $resp = wp_remote_get(
            add_query_arg(['v' => floor(time() / 60)], $url),
            ['timeout' => 10, 'headers' => $headers]
        );

        if (is_wp_error($resp)) {
            return null;
        }

        $status = (int) wp_remote_retrieve_response_code($resp);
        if ($status < 200 || $status >= 300) {
            return null;
        }

        $decoded = json_decode((string) wp_remote_retrieve_body($resp), true);
        if (!is_array($decoded)) {
            return null;
        }

        set_transient($cache_key, $decoded, $ttl);
        return $decoded;
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_clear_cache')) {
    function gaiaeyes_schumann_dashboard_clear_cache() {
        delete_transient('ge_sch_dash_latest');
        delete_transient('ge_sch_dash_series');
        delete_transient('ge_sch_dash_heatmap');
        delete_transient('ge_sch_dash_tomsk_latest');
        delete_transient('ge_sch_detail_payload');
        delete_transient('ge_sch_detail_combined');
        delete_transient('ge_sch_detail_latest_json');
    }
}

if (!function_exists('gaiaeyes_schumann_remote_json_fallback')) {
    function gaiaeyes_schumann_remote_json_fallback($primary, $mirror, $cache_key, $ttl) {
        $cached = get_transient($cache_key);
        if ($cached !== false) {
            return $cached;
        }

        $versioned = ['v' => floor(time() / 600)];
        $resp = wp_remote_get(add_query_arg($versioned, esc_url_raw($primary)), [
            'timeout' => 10,
            'headers' => ['Accept' => 'application/json'],
        ]);
        if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
            $resp = wp_remote_get(add_query_arg($versioned, esc_url_raw($mirror)), [
                'timeout' => 10,
                'headers' => ['Accept' => 'application/json'],
            ]);
        }
        if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
            return null;
        }
        $decoded = json_decode((string) wp_remote_retrieve_body($resp), true);
        if (!is_array($decoded)) {
            return null;
        }
        set_transient($cache_key, $decoded, $ttl);
        return $decoded;
    }
}

if (!function_exists('gaiaeyes_schumann_detail_payload')) {
    function gaiaeyes_schumann_detail_payload($force_refresh = false) {
        if ($force_refresh) {
            gaiaeyes_schumann_dashboard_clear_cache();
        }

        $cache_key = 'ge_sch_detail_payload';
        if (!$force_refresh) {
            $cached = get_transient($cache_key);
            if ($cached !== false) {
                return $cached;
            }
        }

        $latest_api = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/latest',
            'ge_sch_dash_latest',
            gaiaeyes_schumann_dashboard_ttl('latest')
        );
        $latest_json = gaiaeyes_schumann_remote_json_fallback(
            GAIAEYES_SCH_LATEST_URL,
            GAIAEYES_SCH_LATEST_MIRROR,
            'ge_sch_detail_latest_json',
            GAIAEYES_SCHUMANN_DETAIL_TTL
        );
        $combined = gaiaeyes_schumann_remote_json_fallback(
            GAIAEYES_SCH_COMBINED_URL,
            GAIAEYES_SCH_COMBINED_MIRROR,
            'ge_sch_detail_combined',
            GAIAEYES_SCHUMANN_DETAIL_TTL
        );
        $tomsk_latest = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/tomsk_params/latest?station_id=tomsk',
            'ge_sch_dash_tomsk_latest',
            gaiaeyes_schumann_dashboard_ttl('latest')
        );

        $payload = [
            'ok' => true,
            'fetched_at' => gmdate('c'),
            'latest' => is_array($latest_api) && !empty($latest_api['ok']) ? $latest_api : $latest_json,
            'latest_api' => $latest_api,
            'latest_json' => $latest_json,
            'combined' => $combined,
            'tomsk_latest' => $tomsk_latest,
            'series_url' => gaiaeyes_schumann_dashboard_api_base()
                ? gaiaeyes_schumann_dashboard_api_base() . '/v1/earth/schumann/series?hours=24&station=cumiana'
                : 'https://gaiaeyes-backend.onrender.com/v1/earth/schumann/series?hours=24&station=cumiana',
        ];

        set_transient($cache_key, $payload, GAIAEYES_SCHUMANN_DETAIL_TTL);
        return $payload;
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_payload')) {
    function gaiaeyes_schumann_dashboard_payload($force_refresh = false) {
        if ($force_refresh) {
            gaiaeyes_schumann_dashboard_clear_cache();
        }

        $latest = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/latest',
            'ge_sch_dash_latest',
            gaiaeyes_schumann_dashboard_ttl('latest')
        );

        $series = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/series_primary?limit=192',
            'ge_sch_dash_series',
            gaiaeyes_schumann_dashboard_ttl('series')
        );

        $heatmap = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/heatmap_48h',
            'ge_sch_dash_heatmap',
            gaiaeyes_schumann_dashboard_ttl('heatmap')
        );

        $tomsk_latest = gaiaeyes_schumann_dashboard_fetch_json(
            '/v1/earth/schumann/tomsk_params/latest?station_id=tomsk',
            'ge_sch_dash_tomsk_latest',
            gaiaeyes_schumann_dashboard_ttl('latest')
        );

        return [
            'ok' => true,
            'fetched_at' => gmdate('c'),
            'api_base' => gaiaeyes_schumann_dashboard_api_base(),
            'latest' => $latest,
            'series' => $series,
            'heatmap' => $heatmap,
            'tomsk_latest' => $tomsk_latest,
            'status' => [
                'latest_ok' => is_array($latest) && !empty($latest['ok']),
                'series_ok' => is_array($series) && !empty($series['ok']),
                'heatmap_ok' => is_array($heatmap) && !empty($heatmap['ok']),
                'tomsk_latest_ok' => is_array($tomsk_latest) && !empty($tomsk_latest['ok']),
            ],
        ];
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_tomsk_series_proxy')) {
    function gaiaeyes_schumann_dashboard_tomsk_series_proxy(WP_REST_Request $request) {
        $hours = max(1, min(168, intval($request->get_param('hours') ?: 48)));
        $station_id = sanitize_key((string) ($request->get_param('station_id') ?: 'tomsk'));
        if ($station_id === '') {
            $station_id = 'tomsk';
        }

        $path = '/v1/earth/schumann/tomsk_params/series?hours=' . rawurlencode((string) $hours)
            . '&station_id=' . rawurlencode($station_id);
        $cache_key = 'ge_sch_dash_tomsk_series_' . md5($station_id . ':' . $hours);

        $payload = gaiaeyes_schumann_dashboard_fetch_json(
            $path,
            $cache_key,
            gaiaeyes_schumann_dashboard_ttl('series')
        );

        if (!is_array($payload)) {
            return new WP_REST_Response([
                'ok' => false,
                'error' => 'Tomsk series unavailable',
                'station_id' => $station_id,
                'count' => 0,
                'points' => [],
            ], 200);
        }

        return new WP_REST_Response($payload, 200);
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_enqueue_assets')) {
    function gaiaeyes_schumann_dashboard_enqueue_assets() {
        static $did_enqueue = false;
        if ($did_enqueue) {
            return;
        }

        $style_path = __DIR__ . '/gaiaeyes-schumann-dashboard.css';
        $script_path = __DIR__ . '/gaiaeyes-schumann-dashboard.js';

        wp_register_style(
            'gaiaeyes-schumann-dashboard',
            plugins_url('gaiaeyes-schumann-dashboard.css', __FILE__),
            [],
            file_exists($style_path) ? filemtime($style_path) : null
        );

        wp_register_script(
            'gaiaeyes-schumann-dashboard',
            plugins_url('gaiaeyes-schumann-dashboard.js', __FILE__),
            [],
            file_exists($script_path) ? filemtime($script_path) : null,
            true
        );

        wp_localize_script('gaiaeyes-schumann-dashboard', 'GAIAEYES_SCHUMANN_DASHBOARD_CFG', [
            'restUrl' => esc_url_raw(rest_url('gaia/v1/schumann/dashboard')),
            'tomskSeriesRestUrl' => esc_url_raw(rest_url('gaia/v1/schumann/tomsk-series')),
            'appLink' => esc_url_raw((string) apply_filters('gaiaeyes_schumann_app_link', GAIAEYES_SCHUMANN_APP_LINK)),
            'proEnabled' => (bool) apply_filters('gaiaeyes_schumann_pro_enabled', false),
        ]);

        wp_enqueue_style('gaiaeyes-schumann-dashboard');
        wp_enqueue_script('gaiaeyes-schumann-dashboard');

        $did_enqueue = true;
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_render')) {
    function gaiaeyes_schumann_dashboard_render($atts = []) {
        $a = shortcode_atts([
            'app_link' => '',
        ], $atts, 'gaiaeyes_schumann_dashboard');

        $component_id = 'ge-schumann-dashboard-' . wp_generate_uuid4();
        $app_link = trim((string) $a['app_link']);
        if ($app_link === '') {
            $app_link = (string) apply_filters('gaiaeyes_schumann_app_link', GAIAEYES_SCHUMANN_APP_LINK);
        }

        gaiaeyes_schumann_dashboard_enqueue_assets();

        $client_cfg = [
            'appLink' => $app_link,
            'proEnabled' => (bool) apply_filters('gaiaeyes_schumann_pro_enabled', false),
        ];

        ob_start();
        ?>
        <section
            id="<?php echo esc_attr($component_id); ?>"
            class="ge-schumann-dashboard"
            data-gaiaeyes-schumann-dashboard="1"
            data-config="<?php echo esc_attr(wp_json_encode($client_cfg)); ?>"
        >
            <div class="ge-sch-loading" aria-live="polite">Loading Schumann dashboard...</div>
        </section>
        <?php
        return ob_get_clean();
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_shortcode')) {
    function gaiaeyes_schumann_dashboard_shortcode($atts = []) {
        return gaiaeyes_schumann_dashboard_render($atts);
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_block_render')) {
    function gaiaeyes_schumann_dashboard_block_render($attributes = []) {
        return gaiaeyes_schumann_dashboard_render(is_array($attributes) ? $attributes : []);
    }
}

if (!function_exists('gaiaeyes_schumann_dashboard_rest_proxy')) {
    function gaiaeyes_schumann_dashboard_rest_proxy(WP_REST_Request $request) {
        $refresh = $request->get_param('refresh');
        $force_refresh = !empty($refresh) && $refresh !== '0' && $refresh !== 0 && $refresh !== false;

        $payload = gaiaeyes_schumann_dashboard_payload($force_refresh);
        if (empty($payload['api_base'])) {
            return new WP_REST_Response([
                'ok' => false,
                'error' => 'GAIAEYES_API_BASE is not configured',
                'latest' => null,
                'series' => null,
                'heatmap' => null,
            ], 500);
        }

        return new WP_REST_Response($payload, 200);
    }
}

add_action('rest_api_init', function () {
    register_rest_route('gaia/v1', '/schumann/dashboard', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => 'gaiaeyes_schumann_dashboard_rest_proxy',
        'args' => [
            'refresh' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/schumann/tomsk-series', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => 'gaiaeyes_schumann_dashboard_tomsk_series_proxy',
        'args' => [
            'hours' => [
                'required' => false,
                'sanitize_callback' => 'absint',
            ],
            'station_id' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_key',
            ],
        ],
    ]);

    register_rest_route('gaia/v1', '/schumann/detail', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $request) {
            $refresh = $request->get_param('refresh');
            $force_refresh = !empty($refresh) && $refresh !== '0' && $refresh !== 0 && $refresh !== false;
            return new WP_REST_Response(gaiaeyes_schumann_detail_payload($force_refresh), 200);
        },
        'args' => [
            'refresh' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);
});

add_action('init', function () {
    if (!shortcode_exists('gaiaeyes_schumann_dashboard')) {
        add_shortcode('gaiaeyes_schumann_dashboard', 'gaiaeyes_schumann_dashboard_shortcode');
    }

    if (function_exists('register_block_type')) {
        $block_script_path = __DIR__ . '/gaiaeyes-schumann-dashboard-block.js';
        wp_register_script(
            'gaiaeyes-schumann-dashboard-block',
            plugins_url('gaiaeyes-schumann-dashboard-block.js', __FILE__),
            ['wp-blocks', 'wp-element', 'wp-i18n'],
            file_exists($block_script_path) ? filemtime($block_script_path) : null,
            true
        );

        register_block_type('gaiaeyes/schumann-dashboard', [
            'api_version' => 2,
            'editor_script' => 'gaiaeyes-schumann-dashboard-block',
            'render_callback' => 'gaiaeyes_schumann_dashboard_block_render',
        ]);
    }
});
