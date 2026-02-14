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
    $request_uri = isset($_SERVER['REQUEST_URI']) ? wp_unslash($_SERVER['REQUEST_URI']) : '/';
    $redirect_url = esc_url_raw(home_url($request_uri));

    wp_localize_script('gaia-dashboard', 'GAIA_DASHBOARD_CFG', [
        'supabaseUrl' => $supabase_url ? rtrim($supabase_url, '/') : '',
        'supabaseAnon' => $supabase_anon ? trim($supabase_anon) : '',
        'backendBase' => $backend_base ? rtrim($backend_base, '/') : '',
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
        .gaia-dashboard__markdown h2,.gaia-dashboard__markdown h3{margin:12px 0 6px;font-size:16px}
        .gaia-dashboard__markdown p{margin:8px 0}
        .gaia-dashboard__markdown ul{margin:8px 0;padding-left:18px}
        .gaia-dashboard__signin{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        .gaia-dashboard__btn{border:0;border-radius:999px;padding:8px 14px;background:#2b8cff;color:#fff;font-weight:600;cursor:pointer}
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
