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

        return [
            'ok' => true,
            'fetched_at' => gmdate('c'),
            'api_base' => gaiaeyes_schumann_dashboard_api_base(),
            'latest' => $latest,
            'series' => $series,
            'heatmap' => $heatmap,
            'status' => [
                'latest_ok' => is_array($latest) && !empty($latest['ok']),
                'series_ok' => is_array($series) && !empty($series['ok']),
                'heatmap_ok' => is_array($heatmap) && !empty($heatmap['ok']),
            ],
        ];
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
            'mode' => 'scientific',
            'show_details' => '',
            'app_link' => '',
        ], $atts, 'gaiaeyes_schumann_dashboard');

        $mode = strtolower(trim((string) $a['mode'])) === 'mystical' ? 'mystical' : 'scientific';
        $show_details = trim((string) $a['show_details']);
        $show_details_bool = $show_details === '' ? null : in_array(strtolower($show_details), ['1', 'true', 'yes', 'on'], true);

        $component_id = 'ge-schumann-dashboard-' . wp_generate_uuid4();
        $app_link = trim((string) $a['app_link']);
        if ($app_link === '') {
            $app_link = (string) apply_filters('gaiaeyes_schumann_app_link', GAIAEYES_SCHUMANN_APP_LINK);
        }

        gaiaeyes_schumann_dashboard_enqueue_assets();

        $client_cfg = [
            'mode' => $mode,
            'showDetails' => $show_details_bool,
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
