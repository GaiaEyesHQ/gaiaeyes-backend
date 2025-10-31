<?php
/**
 * Plugin Name: Gaia Eyes – News
 * Description: Shows latest space/aurora headlines from gaiaeyes-media/data/news_latest.json.
 */
if (!defined('ABSPATH')) {
  exit;
}

function ge_news_cached($url, $cache_min) {
  $ttl = max(1, intval($cache_min)) * MINUTE_IN_SECONDS;
  $cache_key = 'ge_news_' . md5($url);
  $payload = get_transient($cache_key);
  if ($payload === false) {
    $response = wp_remote_get(esc_url_raw($url), [
      'timeout' => 8,
      'headers' => ['Accept' => 'application/json'],
    ]);
    if (!is_wp_error($response) && wp_remote_retrieve_response_code($response) === 200) {
      $payload = json_decode(wp_remote_retrieve_body($response), true);
      if (is_array($payload)) {
        set_transient($cache_key, $payload, $ttl);
      }
    }
  }
  return is_array($payload) ? $payload : null;
}

add_shortcode('gaia_news', function ($atts) {
  $atts = shortcode_atts([
    'url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/news_latest.json',
    'cache' => 30,
    'limit' => 12,
  ], $atts, 'gaia_news');

  $json = ge_news_cached($atts['url'], $atts['cache']);
  if (!$json || empty($json['items']) || !is_array($json['items'])) {
    return '<div class="ge-card">No news.</div>';
  }

  $limit = max(1, intval($atts['limit']));
  $items = array_slice($json['items'], 0, $limit);
  ob_start();
  ?>
  <section class="ge-panel ge-news">
    <div class="ge-grid">
      <?php foreach ($items as $item): ?>
        <article class="ge-card">
          <h3><a class="gaia-link" href="<?php echo esc_url($item['link'] ?? '#'); ?>" target="_blank" rel="noopener"><?php echo esc_html($item['title'] ?? ''); ?></a></h3>
          <?php if (!empty($item['source']) || !empty($item['published_at'])): ?>
            <div class="ge-meta"><?php echo esc_html(trim(($item['source'] ?? '') . (!empty($item['published_at']) ? ' • ' . $item['published_at'] : ''))); ?></div>
          <?php endif; ?>
        </article>
      <?php endforeach; ?>
    </div>
    <style>
      .ge-news .ge-grid { display: grid; gap: 12px; }
      @media (min-width: 900px) { .ge-news .ge-grid { grid-template-columns: repeat(3, 1fr); } }
      .ge-news .ge-meta { opacity: .8; font-size: .9rem; margin-top: 4px; }
      .gaia-link { color: inherit; text-decoration: none; border-bottom: 1px dotted rgba(255, 255, 255, .25); }
      .gaia-link:hover { border-bottom-color: rgba(255, 255, 255, .6); }
    </style>
  </section>
  <?php
  return ob_get_clean();
});
