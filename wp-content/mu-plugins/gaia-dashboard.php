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
        .gaia-dashboard__gauges{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:12px 0;align-items:stretch}
        @media(min-width:900px){.gaia-dashboard__gauges{grid-template-columns:repeat(3,minmax(0,1fr));}}
        @media(min-width:1200px){.gaia-dashboard__gauges{grid-template-columns:repeat(4,minmax(0,1fr));}}
        .gaia-dashboard__gauge{padding:12px;border-radius:14px;background:#151c28;display:flex;flex-direction:column;gap:10px;min-height:150px}
        .gaia-dashboard__gauge--clickable{cursor:pointer;transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease;border:1px solid rgba(255,255,255,.16)}
        .gaia-dashboard__gauge--clickable:hover{transform:translateY(-1px);box-shadow:0 0 16px rgba(162,186,223,.22);border-color:rgba(162,186,223,.42)}
        .gaia-dashboard__gauge-label{font-size:12px;color:#9da9c1}
        .gaia-dashboard__gauge-meter{position:relative;display:grid;place-items:center;margin-top:2px}
        .gaia-dashboard__gauge-arc{width:104px;height:104px;display:block}
        @media(min-width:1200px){.gaia-dashboard__gauge-arc{width:110px;height:110px}}
        .gaia-dashboard__gauge-ring{fill:none;stroke:rgba(255,255,255,.12);stroke-width:9}
        .gaia-dashboard__gauge-value-arc{fill:none;stroke-width:9;stroke-linecap:round}
        .gaia-dashboard__gauge-center{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;pointer-events:none}
        .gaia-dashboard__gauge-value{font-size:26px;font-weight:750;line-height:1;display:flex;gap:4px;align-items:baseline}
        .gaia-dashboard__gauge-delta{font-size:12px;font-weight:600;color:#8f9db7}
        .gaia-dashboard__gauge-delta--strong{color:#d8b176}
        .gaia-dashboard__gauge-zone{font-size:12px;line-height:1.2;opacity:.95}
        .gaia-dashboard__gauge-zone-key{font-size:11px;color:#9da9c1;text-align:center;margin-top:2px}
        .gaia-dashboard__gauge-dot{fill:#fff;stroke:#1a2434;stroke-width:1.6}
        .gaia-dashboard__tap-hint{font-size:10px;color:#c6d3ea;letter-spacing:.02em}
        .gaia-dashboard__gauge-legend{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 10px}
        .gaia-dashboard__legend-item{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:#9da9c1}
        .gaia-dashboard__legend-dot{width:8px;height:8px;border-radius:50%}
        .gaia-dashboard__alerts{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
        .gaia-dashboard__pill{padding:5px 10px;border-radius:999px;font-size:12px;background:#223246;color:#a9c8ff}
        .gaia-dashboard__pill--watch{background:#3a2d19;color:#ffd58f}
        .gaia-dashboard__pill--high{background:#3b1e23;color:#ffadb8}
        .gaia-dashboard__drivers{margin-top:12px;padding:12px;border-radius:12px;background:#131b28}
        .gaia-dashboard__drivers h4{margin:0 0 10px;font-size:17px}
        .gaia-dashboard__drivers-list{display:flex;flex-direction:column;gap:9px}
        .gaia-dashboard__driver-row{padding:10px;border-radius:12px;background:#172130;border:1px solid rgba(255,255,255,.08)}
        .gaia-dashboard__driver-row--clickable{cursor:pointer;transition:box-shadow .15s ease,border-color .15s ease}
        .gaia-dashboard__driver-row--clickable:hover{box-shadow:0 0 14px rgba(163,188,225,.18);border-color:rgba(163,188,225,.36)}
        .gaia-dashboard__driver-head{display:flex;align-items:baseline;gap:8px;justify-content:space-between}
        .gaia-dashboard__driver-label{font-size:14px;font-weight:650}
        .gaia-dashboard__driver-state{font-size:12px}
        .gaia-dashboard__driver-value{font-size:12px;color:#9da9c1}
        .gaia-dashboard__driver-bar-track{margin-top:8px;height:9px;border-radius:999px;background:rgba(255,255,255,.09);overflow:hidden}
        .gaia-dashboard__driver-bar-fill{height:100%;border-radius:999px}
        .gaia-dashboard__earthscope{margin-top:12px;padding:12px;border-radius:12px;background:#151c28}
        .gaia-dashboard__earthscope h4{margin:0 0 8px;font-size:18px}
        .gaia-dashboard__earthscope-summary{font-size:14px;line-height:1.5;margin:0 0 10px;color:#e8edf7}
        .gaia-dashboard__earthscope-link{display:inline-flex;align-items:center;font-size:13px;color:#9cc0ff;text-decoration:underline;background:none;border:0;padding:0;cursor:pointer}
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
        .gaia-dashboard__modal{position:fixed;inset:0;z-index:99999;display:none}
        .gaia-dashboard__modal.is-open{display:block}
        .gaia-dashboard__modal-backdrop{position:absolute;inset:0;background:rgba(2,6,12,.72)}
        .gaia-dashboard__modal-card{position:relative;max-width:620px;margin:9vh auto;background:#101826;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:18px;max-height:82vh;overflow:auto;color:#e8edf7}
        .gaia-dashboard__modal-title{margin:0 0 10px;font-size:22px}
        .gaia-dashboard__modal-group{margin-top:12px}
        .gaia-dashboard__modal-group h5{margin:0 0 7px;font-size:15px}
        .gaia-dashboard__modal-group ul{margin:0;padding-left:18px}
        .gaia-dashboard__modal-group li{margin:0 0 6px;line-height:1.45}
        .gaia-dashboard__modal-actions{display:flex;justify-content:space-between;gap:10px;margin-top:16px;flex-wrap:wrap}
        body.gaia-modal-open{overflow:hidden}
    ');
});

add_action('wp_head', function () {
    ?>
    <script id="gaia-auth-hash-guard">
    (function () {
      try {
        var h = window.location.hash || "";
        if (!h || h.length < 2) return;
        var frag = h.slice(1);
        if (frag.indexOf("access_token=") === -1 && frag.indexOf("refresh_token=") === -1) return;
        try { sessionStorage.setItem("gaia_auth_fragment", frag); } catch (e) {}
        if (window.history && window.history.replaceState) {
          window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
        }
      } catch (e) {}
    })();
    </script>
    <?php
}, 1);

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
    $debug = $request->get_param('debug');

    $query_args = ['day' => $day];
    if ($debug !== null && $debug !== '' && $debug !== '0' && $debug !== 0 && $debug !== false) {
        $query_args['debug'] = '1';
    }

    $url = add_query_arg($query_args, $backend_base . '/v1/dashboard');

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
            'debug' => [
                'required' => false,
                'sanitize_callback' => 'sanitize_text_field',
            ],
        ],
    ]);
});
