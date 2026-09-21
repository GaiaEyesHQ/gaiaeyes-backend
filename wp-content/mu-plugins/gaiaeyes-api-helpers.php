<?php if (!defined('ABSPATH')) exit;

// Observation time is distinct from request/cache time. Never invent "now".
function gaiaeyes_observation_epoch($value) {
  if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/', $value)) return null;
  try {
    $date = new DateTimeImmutable($value, new DateTimeZone('UTC'));
    $errors = DateTimeImmutable::getLastErrors();
    return $errors && ($errors['warning_count'] || $errors['error_count']) ? null : $date->getTimestamp();
  } catch (Exception $e) {
    return null;
  }
}

function gaiaeyes_history_series($response) {
  $series = is_array($response) && !empty($response['ok']) ? ($response['data']['series24'] ?? []) : [];
  $out = ['kp'=>[], 'sw'=>[], 'bz'=>[]];
  foreach ($out as $key => $_) {
    $rows = $series[$key] ?? [];
    foreach ((is_array($rows) ? $rows : []) as $point) {
      if (!is_array($point) || !isset($point[0], $point[1]) || !is_numeric($point[1])) continue;
      $epoch = gaiaeyes_observation_epoch($point[0]);
      if ($epoch === null || !is_finite((float)$point[1])) continue;
      $out[$key][] = [gmdate('c', $epoch), (float)$point[1]];
    }
    usort($out[$key], function($a, $b) { return strcmp($a[0], $b[0]); });
  }
  return $out;
}

function gaiaeyes_data_status($timestamp, $has_data = true, $label = 'Data', $max_age = 3600, $day = null) {
  $epoch = gaiaeyes_observation_epoch($timestamp);
  $now = time();
  $state = 'unavailable';
  $text = 'Unavailable';
  $date_text = '';
  if ($has_data) {
    $state = 'unknown';
    $text = 'Time unavailable';
    if ($day !== null) {
      // A features-response day is not the publication day of its latest post.
      $valid_day = is_string($day) && preg_match('/^\d{4}-\d{2}-\d{2}$/', $day)
        && ($parsed_day = DateTimeImmutable::createFromFormat('!Y-m-d', $day)) && $parsed_day->format('Y-m-d') === $day;
      $today = (new DateTimeImmutable('now', new DateTimeZone('America/Chicago')))->format('Y-m-d');
      if ($valid_day) {
        $state = $day === $today ? 'current' : ($day < $today ? 'stale' : 'unknown');
        $text = $state === 'current' ? 'Current edition' : ($state === 'stale' ? 'Earlier edition — awaiting an update' : 'Edition date is ahead of today');
        $date_text = ' · Edition ' . esc_html($day) . ' (America/Chicago)';
      } else {
        $text = 'Publication day unavailable';
      }
    } elseif ($epoch !== null && $epoch <= $now + 300) {
      $state = $now - $epoch > $max_age ? 'stale' : 'current';
      $text = $state === 'stale' ? 'Stale snapshot' : 'Current snapshot';
    } elseif ($epoch !== null) {
      $text = 'Timestamp is ahead of the current time';
    }
  }
  if ($has_data && $epoch !== null) {
    $date_text .= ' · ' . ($day !== null ? 'Published' : 'As of') . ' <time datetime="' . esc_attr(gmdate('c', $epoch)) . '">' . esc_html(gmdate('Y-m-d H:i', $epoch)) . ' UTC</time>';
  }
  return '<p class="ge-data-status" data-state="' . esc_attr($state) . '" data-label="' . esc_attr($label) . '" data-has-data="' . ($has_data ? '1' : '0') . '" data-observed-at="' . esc_attr($epoch !== null ? gmdate('c', $epoch) : '') . '" data-max-age="' . intval($max_age) . '" data-edition="' . esc_attr($day !== null ? $day : '') . '" data-daily="' . ($day !== null ? '1' : '0') . '" style="font-size:.8rem;line-height:1.5;margin:6px 0;color:' . ($state === 'stale' ? '#ffd089' : 'inherit') . '"><strong>' . esc_html($label . ': ' . $text) . '</strong>' . $date_text . '</p>';
}

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
  function gaiaeyes_public_member_cta($context = '', $copy = '', $label_override = '', $eyebrow = 'Member context') {
    static $style_printed = false;

    $context = trim((string) $context);
    $copy = trim((string) $copy);
    $label_override = trim((string) $label_override);
    $eyebrow = trim((string) $eyebrow);
    if ($copy === '') {
      $copy = 'Members can connect public signals with personal gauges, symptoms, optional Apple Health context, patterns, drivers, and Outlook. Gaia Eyes looks for repeated timing and context; it does not diagnose or prove a signal caused a symptom.';
    }
    if ($eyebrow === '') {
      $eyebrow = 'Member context';
    }

    $label = $label_override !== '' ? $label_override : ($context ? $context . ' + your patterns' : 'Public signals + your patterns');

    ob_start(); ?>
    <aside class="gaia-public-cta" aria-label="Gaia Eyes member context">
      <div>
        <span class="gaia-public-cta__eyebrow"><?php echo esc_html($eyebrow); ?></span>
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

if (!function_exists('gaiaeyes_member_cta_shortcode')) {
  function gaiaeyes_member_cta_shortcode($atts = []) {
    $a = shortcode_atts([
      'eyebrow' => 'Gaia Eyes Plus',
      'title' => 'New Member Dashboard + App',
      'copy' => 'Gaia Eyes Plus includes My Dashboard gauges, personal drivers, Outlook, pattern tracking, symptoms and body context, local conditions with pollen and forecasts, and optional Apple Health context in the iPhone app. Use the same email for website and app access.',
    ], $atts, 'gaiaeyes_member_cta');

    return gaiaeyes_public_member_cta('', (string) $a['copy'], (string) $a['title'], (string) $a['eyebrow']);
  }
}

if (function_exists('add_shortcode')) {
  add_shortcode('gaiaeyes_member_cta', 'gaiaeyes_member_cta_shortcode');
  add_shortcode('gaiaeyes_member_banner', 'gaiaeyes_member_cta_shortcode');
}
