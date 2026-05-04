<?php if (!defined('ABSPATH')) exit;

if (!function_exists('gaiaeyes_http_get_json_api_cached')){
  function gaiaeyes_http_get_json_api_cached($url, $cache_key, $ttl, $bearer = '', $dev_user = ''){
    $cached = get_transient($cache_key);
    if ($cached !== false) return $cached;
    $headers = ['Accept'=>'application/json','User-Agent'=>'GaiaEyesWP/1.0'];
    if ($bearer)   $headers['Authorization'] = 'Bearer ' . $bearer;
    if ($dev_user) $headers['X-Dev-UserId']  = $dev_user;
    $resp = wp_remote_get(add_query_arg(['v'=>floor(time()/600)], $url), ['timeout'=>10,'headers'=>$headers]);
    $code = is_wp_error($resp) ? 0 : intval(wp_remote_retrieve_response_code($resp));
    if ($code < 200 || $code >= 300) return null;
    $data = json_decode(wp_remote_retrieve_body($resp), true);
    if (!is_array($data)) return null;
    set_transient($cache_key, $data, $ttl);
    return $data;
  }
}

if (!function_exists('gaiaeyes_public_member_cta')) {
  function gaiaeyes_public_member_cta($context = '', $copy = '') {
    static $style_printed = false;

    $context = trim((string) $context);
    $copy = trim((string) $copy);
    if ($copy === '') {
      $copy = 'Members can connect public signals with personal gauges, symptoms, optional Apple Health context, patterns, drivers, and Outlook. Gaia Eyes looks for repeated timing and context; it does not diagnose or prove a signal caused a symptom.';
    }

    $label = $context ? $context . ' + your patterns' : 'Public signals + your patterns';

    ob_start(); ?>
    <aside class="gaia-public-cta" aria-label="Gaia Eyes member context">
      <div>
        <span class="gaia-public-cta__eyebrow">Member context</span>
        <strong><?php echo esc_html($label); ?></strong>
        <p><?php echo esc_html($copy); ?></p>
      </div>
      <div class="gaia-public-cta__actions">
        <a class="gaia-public-cta__primary" href="<?php echo esc_url(home_url('/app/')); ?>">Get the app</a>
        <a class="gaia-public-cta__secondary" href="<?php echo esc_url(home_url('/subscribe/')); ?>">See Plus</a>
        <a class="gaia-public-cta__secondary" href="<?php echo esc_url(home_url('/my-dashboard/')); ?>">My Dashboard</a>
      </div>
    </aside>
    <?php if (!$style_printed) : $style_printed = true; ?>
      <style>
        .gaia-public-cta{margin:14px 0 0;padding:14px;border-radius:12px;background:rgba(43,140,255,.10);border:1px solid rgba(156,192,255,.22);color:#e8edf7;display:flex;gap:14px;justify-content:space-between;align-items:center;flex-wrap:wrap}
        .gaia-public-cta__eyebrow{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9cc0ff;font-weight:800;margin-bottom:4px}
        .gaia-public-cta strong{display:block;font-size:16px;line-height:1.25}
        .gaia-public-cta p{margin:6px 0 0;max-width:760px;color:rgba(232,237,247,.82);line-height:1.45;font-size:14px}
        .gaia-public-cta__actions{display:flex;gap:8px;flex-wrap:wrap}
        .gaia-public-cta__actions a{display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:0 12px;border-radius:999px;font-size:13px;font-weight:800;text-decoration:none}
        .gaia-public-cta__primary{background:#2b8cff;color:#fff}
        .gaia-public-cta__secondary{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e8edf7}
      </style>
    <?php endif; ?>
    <?php
    return ob_get_clean();
  }
}
