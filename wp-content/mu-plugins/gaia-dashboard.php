<?php
/*
Plugin Name: Gaia Dashboard Shortcode
Description: Renders the member dashboard from /v1/dashboard via Supabase session auth.
Version: 0.1.0
*/

if (!defined('ABSPATH')) {
    exit;
}

add_action('wp_enqueue_scripts', function () {
    wp_register_script(
        'gaia-dashboard',
        plugins_url('gaia-dashboard.js', __FILE__),
        ['supabase-js'],
        filemtime(__DIR__ . '/gaia-dashboard.js'),
        true
    );

    $supabase_url = defined('SUPABASE_URL') ? SUPABASE_URL : getenv('SUPABASE_URL');
    $supabase_anon = defined('SUPABASE_ANON_KEY') ? SUPABASE_ANON_KEY : getenv('SUPABASE_ANON_KEY');
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');
    $media_base = defined('MEDIA_BASE_URL') ? MEDIA_BASE_URL : getenv('MEDIA_BASE_URL');
    if (!$media_base && $supabase_url) {
        $media_base = rtrim($supabase_url, '/') . '/storage/v1/object/public/space-visuals';
    }
    $request_uri = isset($_SERVER['REQUEST_URI']) ? wp_unslash($_SERVER['REQUEST_URI']) : '/';
    $redirect_url = esc_url_raw(home_url($request_uri));

    wp_localize_script('gaia-dashboard', 'GAIA_DASHBOARD_CFG', [
        'supabaseUrl' => $supabase_url ? rtrim($supabase_url, '/') : '',
        'supabaseAnon' => $supabase_anon ? trim($supabase_anon) : '',
        'backendBase' => $backend_base ? rtrim($backend_base, '/') : '',
        'dashboardProxy' => esc_url_raw(rest_url('gaia/v1/dashboard')),
        'mediaBase' => $media_base ? rtrim($media_base, '/') : '',
        'redirectUrl' => $redirect_url,
    ]);

    wp_register_style('gaia-dashboard', false);
    wp_add_inline_style('gaia-dashboard', '
        .gaia-dashboard{border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:16px;background:#0f131a;color:#e8edf7}
        .gaia-dashboard__muted{color:#9da9c1;font-size:13px}
        .gaia-dashboard__status{color:#9da9c1}
        .gaia-dashboard__head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
        .gaia-dashboard__title{font-size:22px;font-weight:700;line-height:1.2;margin:0}
        .gaia-dashboard__mode{font-size:12px;padding:3px 8px;border-radius:999px;background:#1f2a3a;color:#9cc0ff}
        .gaia-dashboard__gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:10px 0}
        .gaia-dashboard__gauge{padding:10px;border-radius:10px;background:#151c28}
        .gaia-dashboard__gauge-label{font-size:12px;color:#9da9c1}
        .gaia-dashboard__gauge-value{font-size:24px;font-weight:700}
        .gaia-dashboard__alerts{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
        .gaia-dashboard__pill{padding:5px 10px;border-radius:999px;font-size:12px;background:#223246;color:#a9c8ff}
        .gaia-dashboard__pill--watch{background:#3a2d19;color:#ffd58f}
        .gaia-dashboard__pill--high{background:#3b1e23;color:#ffadb8}
        .gaia-dashboard__earthscope{margin-top:12px;padding:12px;border-radius:12px;background:#151c28}
        .gaia-dashboard__earthscope h4{margin:0 0 8px;font-size:18px}
        .gaia-dashboard__es-grid{display:grid;grid-template-columns:1fr;gap:10px}
        @media(min-width:900px){.gaia-dashboard__es-grid{grid-template-columns:1fr 1fr}}
        .gaia-dashboard__es-block{position:relative;overflow:hidden;border-radius:12px;min-height:150px;background:#0f1a2b;background-size:cover;background-position:center}
        .gaia-dashboard__es-overlay{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.32),rgba(0,0,0,.72))}
        .gaia-dashboard__es-content{position:relative;z-index:1;padding:12px;color:#fff}
        .gaia-dashboard__es-title{margin:0 0 8px;font-size:15px;line-height:1.25}
        .gaia-dashboard__es-body{margin:0;white-space:pre-line;line-height:1.45;font-size:14px}
        .gaia-dashboard__signin{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        .gaia-dashboard__btn{border:0;border-radius:999px;padding:8px 14px;background:#2b8cff;color:#fff;font-weight:600;cursor:pointer}
        .gaia-dashboard__btn--ghost{background:#1f2a3a;color:#d7e6ff}
    ');
});

if (!function_exists('gaia_dashboard_shortcode_render')) {
function gaia_dashboard_shortcode_render($atts = []) {
    $a = shortcode_atts([
        'title' => 'Mission Control',
    ], $atts, 'gaia_dashboard');

    wp_enqueue_script('supabase-js', 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2', [], null, true);
    wp_enqueue_script('gaia-dashboard');
    wp_enqueue_style('gaia-dashboard');

    ob_start();
    ?>
    <section class="gaia-dashboard" data-gaia-dashboard data-title="<?php echo esc_attr($a['title']); ?>">
        <div class="gaia-dashboard__status">Loading dashboard...</div>
    </section>
    <?php
    return ob_get_clean();
}
}

add_action('init', function () {
    if (!shortcode_exists('gaia_dashboard')) {
        add_shortcode('gaia_dashboard', 'gaia_dashboard_shortcode_render');
    }
});

add_filter('the_content', function ($content) {
    if (strpos($content, '[gaia_dashboard') === false) {
        return $content;
    }
    return do_shortcode($content);
}, 20);

if (!function_exists('gaia_dashboard_proxy_backend')) {
function gaia_dashboard_proxy_backend(WP_REST_Request $request) {
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');
    $backend_base = $backend_base ? rtrim((string) $backend_base, '/') : '';
    if (!$backend_base) {
        return new WP_REST_Response(['ok' => false, 'error' => 'GAIAEYES_API_BASE is not configured'], 500);
    }

    $day = sanitize_text_field((string) ($request->get_param('day') ?: ''));
    if (!$day) {
        $day = gmdate('Y-m-d');
    }

    $url = add_query_arg(['day' => $day], $backend_base . '/v1/dashboard');

    $auth = (string) $request->get_header('authorization');
    if (!$auth && isset($_SERVER['HTTP_AUTHORIZATION'])) {
        $auth = (string) wp_unslash($_SERVER['HTTP_AUTHORIZATION']);
    }

    $headers = ['Accept' => 'application/json'];
    if ($auth !== '') {
        $headers['Authorization'] = $auth;
    }

    $resp = wp_remote_get($url, [
        'timeout' => 20,
        'headers' => $headers,
    ]);

    if (is_wp_error($resp)) {
        return new WP_REST_Response([
            'ok' => false,
            'error' => 'dashboard proxy fetch failed',
            'detail' => $resp->get_error_message(),
        ], 502);
    }

    $status = (int) wp_remote_retrieve_response_code($resp);
    $body = (string) wp_remote_retrieve_body($resp);
    $decoded = json_decode($body, true);

    if (!is_array($decoded)) {
        return new WP_REST_Response([
            'ok' => false,
            'error' => 'dashboard proxy invalid JSON',
            'status' => $status,
        ], 502);
    }

    return new WP_REST_Response($decoded, $status > 0 ? $status : 200);
}
}

add_action('rest_api_init', function () {
    register_rest_route('gaia/v1', '/dashboard', [
        'methods' => WP_REST_Server::READABLE,
        'permission_callback' => '__return_true',
        'callback' => 'gaia_dashboard_proxy_backend',
        'args' => [
            'day' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);
});
