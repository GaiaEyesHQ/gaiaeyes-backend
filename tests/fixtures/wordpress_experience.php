<?php
// Offline WordPress adapter: render actual shortcode/template code, never HTTP.
$repo = dirname(__DIR__, 2);
$scenario = $argv[1] ?? 'current';
$view = $argv[2] ?? 'home';
if ($scenario === 'api-response') {
  $features_response = json_decode(file_get_contents($argv[3]), true, 512, JSON_THROW_ON_ERROR);
}
define('ABSPATH', $repo . '/');
define('MINUTE_IN_SECONDS', 60);
define('GAIAEYES_API_BASE', 'https://fixture.invalid');
define('GAIAEYES_API_BEARER', 'fixture-server-secret');
define('GAIAEYES_SPACE_VISUALS_ENDPOINT', GAIAEYES_API_BASE . '/v1/space/visuals');
define('GAIA_MEDIA_BASE', '/assets/');
$shortcodes = $actions = $scripts = $transients = $requests = [];
function add_shortcode($name, $callback) { $GLOBALS['shortcodes'][$name] = $callback; }
function add_action($hook, $callback, $priority = 10) { $GLOBALS['actions'][$hook][$priority][] = $callback; }
function shortcode_atts($defaults, $atts, $tag = '') { return array_merge($defaults, $atts); }
function esc_html($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function esc_attr($s) { return esc_html($s); }
function esc_js($s) { return addslashes((string)$s); }
function esc_url($s) { return esc_attr($s); }
function esc_url_raw($s) { return $s; }
function sanitize_text_field($s) { return strip_tags($s); }
function wp_json_encode($v) { return json_encode($v); }
function wp_parse_args($a, $b) { return array_merge($b, $a); }
function wp_unique_id() { static $n = 0; return ++$n; }
function trailingslashit($s) { return rtrim($s,'/') . '/'; }
function number_format_i18n($n, $d = 0) { return number_format($n,$d); }
function is_admin() { return false; }
function home_url($path) { return $path; }
function rest_url($path) { return '/wp-json/' . $path; }
function add_query_arg($args, $url) { return $url . (strpos($url,'?') === false ? '?' : '&') . http_build_query($args); }
function get_transient($key) { return $GLOBALS['transients'][$key] ?? false; }
function set_transient($key, $value, $ttl) { $GLOBALS['transients'][$key] = $value; }
function is_wp_error($r) { return false; }
function wp_remote_retrieve_response_code($r) { return $r['code']; }
function wp_remote_retrieve_body($r) { return json_encode($r['data']); }
function wp_enqueue_script($name, $src, $deps, $version, $footer) {
  $GLOBALS['scripts'][$name] = compact('src','deps','version','footer');
}
function fixture_time($offset = 0) {
  $age = $GLOBALS['scenario'] === 'stale' ? 18000 : 120;
  return gmdate('c', time() - $age + $offset);
}
function fixture_series() {
  if (in_array($GLOBALS['scenario'], ['missing','no-history'])) return ['kp'=>[], 'sw'=>[], 'bz'=>[]];
  $series = ['kp'=>[], 'sw'=>[], 'bz'=>[]];
  for ($i=0; $i<24; $i++) {
    $time = fixture_time(($i-23)*3600);
    $series['kp'][] = [$time, 2.0];
    $series['sw'][] = [$time, 340 + $i];
    $series['bz'][] = [$time, ($i % 6)-3];
  }
  $series['bz'][23][1] = 0; // A real zero must survive.
  if ($GLOBALS['scenario'] === 'partial') $series['bz'] = [[fixture_time(),null], [fixture_time(),false], ['bad date',5]];
  return $series;
}
function wp_remote_get($url, $args) {
  $GLOBALS['requests'][] = ['url'=>$url, 'headers'=>$args['headers'] ?? []];
  $path = parse_url($url, PHP_URL_PATH);
  $missing = $GLOBALS['scenario'] === 'missing';
  if ($missing) return ['code'=>503, 'data'=>null];
  $data = null;
  if ($path === '/v1/space/history') $data = ['ok'=>true,'data'=>['series24'=>fixture_series()]];
  elseif ($path === '/v1/space/xray/history') $data = ['ok'=>true,'data'=>['series'=>['long'=>[[fixture_time(-3600),1e-6],[fixture_time(),2e-6]]]]];
  elseif ($path === '/v1/space/visuals') $data = [
    'ok'=>true, 'generated_at'=>fixture_time(), 'cdn_base'=>'/assets/',
    'images'=>[['key'=>'test','url'=>'/assets/placeholder.svg']],
    'series'=>[['key'=>'goes_protons','samples'=>[['ts'=>fixture_time(),'value'=>2,'energy'=>'>=10 MeV']]]],
  ];
  elseif ($path === '/v1/features/today') {
    if ($GLOBALS['scenario'] === 'api-response') return ['code'=>200, 'data'=>$GLOBALS['features_response']];
    $features = ['kp'=>0.7,'sw_speed_kms'=>324,'bz_nt'=>0.3,'day'=>gmdate('Y-m-d')];
    if ($GLOBALS['scenario'] === 'api-day-missing') $features += ['post_title'=>'Synthetic edition','post_caption'=>'A useful check-in.'];
    if ($GLOBALS['scenario'] === 'no-features') return ['code'=>503,'data'=>null];
    $data = ['ok'=>true, 'data'=>$features];
  }
  elseif ($path === '/v1/space/forecast/outlook') $data = ['headline'=>'Synthetic forecast','confidence'=>'Limited'];
  elseif (strpos($path,'earthscope') !== false) {
    $day = new DateTimeImmutable('now', new DateTimeZone('America/Chicago'));
    if ($GLOBALS['scenario'] === 'stale') $day = $day->modify('-1 day');
    $data = ['day'=>$day->format('Y-m-d'), 'timestamp_utc'=>$day->setTime(9,30)->setTimezone(new DateTimeZone('UTC'))->format('c'),
      'title'=>'Synthetic edition', 'caption'=>'Notice how you feel and record what matters to you.',
      'affects'=>'Compare your own observations with the environmental context.', 'playbook'=>'Keep your usual supportive routines.'];
    if ($GLOBALS['scenario'] === 'unknown') unset($data['day'],$data['timestamp_utc']);
  }
  elseif (strpos($path,'space_weather') !== false) $data = ['timestamp_utc'=>fixture_time(-1200),'now'=>['kp'=>0.7,'solar_wind_kms'=>324,'bz_nt'=>0.3]];
  else $data = [];
  return ['code'=>200, 'data'=>$data];
}
require $repo . '/wp-content/mu-plugins/gaiaeyes-api-helpers.php';
require $repo . '/wp-content/mu-plugins/gaiaeyes-spark-helper.php';
require $repo . '/wp-content/mu-plugins/gaiaeyes-space-weather-detail.php';
require $repo . '/wp-content/mu-plugins/gaiaeyes-space-visuals.php';
$theme = file_get_contents($repo . '/wp-content/themes/neve/functions.php');
$start = strpos($theme, "if ( ! function_exists( 'gaia_space_weather_bar' ) )");
$end = strpos($theme, '// [gaia_pulse', $start);
if ($start === false || $end === false) throw new Exception('Theme fixture extraction boundary missing');
eval(substr($theme, $start, $end-$start));

ob_start();
if ($view === 'home') {
  echo gaia_earthscope_banner(['client_refresh'=>'false']);
  echo gaia_space_weather_bar([]);
} elseif ($view === 'earthscope') {
  echo gaia_earthscope_banner(['client_refresh'=>'false', 'allow_legacy_fallback'=>'false']);
} elseif ($view === 'space' || $view === 'space-reverse') {
  if ($view === 'space-reverse') echo $shortcodes['gaia_space_detail']([]);
  echo gaia_space_weather_detail_shortcode([]);
  if ($view === 'space') echo $shortcodes['gaia_space_detail']([]);
} elseif ($view === 'aurora-theme' || $view === 'aurora-fallback') {
  $args = ['rest_base'=>'/fixtures/aurora'];
  echo '<a href="#photo-tips">How to Capture Auroras</a>';
  include $repo . ($view === 'aurora-theme' ? '/wp-content/themes/neve/partials/gaiaeyes-aurora-detail.php' : '/wp-content/mu-plugins/templates/gaiaeyes-aurora-detail.php');
}
$html = ob_get_clean();
// Model WordPress's dependency ordering/deduplication at footer priority 20.
$emitted = [];
$emit = function($handle) use (&$emit, &$emitted) {
  if (isset($emitted[$handle])) return;
  $script = $GLOBALS['scripts'][$handle];
  foreach ($script['deps'] as $dependency) $emit($dependency);
  $emitted[$handle] = true;
  echo '<script data-handle="' . esc_attr($handle) . '" src="/assets/' . esc_attr($handle) . '.js"></script>';
};
ob_start();
foreach ($scripts as $handle=>$_) $emit($handle);
$hooks = $actions['wp_footer'] ?? [];
ksort($hooks);
foreach ($hooks as $priority=>$callbacks) foreach ($callbacks as $callback) $callback();
$footer = ob_get_clean();
if ($view === 'contract') {
  echo json_encode(['series'=>gaiaeyes_history_series(['ok'=>true,'data'=>['series24'=>['bz'=>[[fixture_time(),0],[fixture_time(),null],[fixture_time(),false],['now',5]]]]]),
    'invalid_time'=>gaiaeyes_data_status('now',true), 'future_time'=>gaiaeyes_data_status(gmdate('c',time()+86400),true)]);
} else {
  echo json_encode(['html'=>$html,'footer'=>$footer,'scripts'=>$scripts,'requests'=>$requests]);
}
