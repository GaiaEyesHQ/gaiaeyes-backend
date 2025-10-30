<?php
/**
 * Plugin Name: Gaia Eyes – Earthquakes Detail
 * Description: Scientific Earthquakes detail page using quakes_latest.json (USGS-derived) with recent events, stats, and health context.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) exit;

// Defaults (GitHub Pages + jsDelivr mirror)
if (!defined('GAIAEYES_QUAKES_URL')) {
  define('GAIAEYES_QUAKES_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/quakes_latest.json');
}
if (!defined('GAIAEYES_QUAKES_MIRROR')) {
  define('GAIAEYES_QUAKES_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/quakes_latest.json');
}

function gaiaeyes_quakes_fetch($primary, $mirror, $cache_key, $ttl){
  $cached = get_transient($cache_key);
  if ($cached !== false) return $cached;
  $v = array('v' => floor(time()/600));
  $resp = wp_remote_get(add_query_arg($v, esc_url_raw($primary)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
    $resp = wp_remote_get(add_query_arg($v, esc_url_raw($mirror)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  }
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;
  $data = json_decode(wp_remote_retrieve_body($resp), true);
  if (!is_array($data)) return null;
  set_transient($cache_key, $data, $ttl);
  return $data;
}

/**
 * Shortcode: [gaia_quakes_detail quakes_url="" cache="10" max="10"]
 */
function gaiaeyes_quakes_detail_shortcode($atts){
  $a = shortcode_atts([
    'quakes_url' => GAIAEYES_QUAKES_URL,
    'cache'      => 10,
    'max'        => 10,
  ], $atts, 'gaia_quakes_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $d = gaiaeyes_quakes_fetch($a['quakes_url'], GAIAEYES_QUAKES_MIRROR, 'ge_quakes_latest', $ttl);

  $ts = is_array($d) && !empty($d['timestamp_utc']) ? $d['timestamp_utc'] : '';
  $events = is_array($d) && !empty($d['events']) && is_array($d['events']) ? $d['events'] : [];
  $total = is_array($d) && isset($d['total']) ? intval($d['total']) : null;
  $total24 = is_array($d) && isset($d['total_24h']) ? intval($d['total_24h']) : null;

  // Build simple magnitude buckets from events if present
  $buckets = ['<4.0'=>0,'4.0–4.9'=>0,'5.0–5.9'=>0,'6.0–6.9'=>0,'≥7.0'=>0];
  if ($events){
    foreach($events as $ev){
      $m = isset($ev['mag']) ? floatval($ev['mag']) : null;
      if ($m===null) continue;
      if ($m < 4.0) $buckets['<4.0']++;
      elseif ($m < 5.0) $buckets['4.0–4.9']++;
      elseif ($m < 6.0) $buckets['5.0–5.9']++;
      elseif ($m < 7.0) $buckets['6.0–6.9']++;
      else $buckets['≥7.0']++;
    }
  }

  $max_items = max(1, intval($a['max']));

  ob_start(); ?>
  <section class="ge-quakes ge-panel">
    <header class="ge-head">
      <h2>Earthquakes – Scientific Detail</h2>
      <div class="ge-meta">Updated <?php echo esc_html( $ts ?: '—' ); ?></div>
    </header>
    <div class="ge-ticker" role="region" aria-label="Global earthquake stats">
      <span class="tk tk-total"><strong>Total (feed):</strong> <?php echo ($total!==null)? intval($total) : '—'; ?></span>
      <span class="tk tk-24h"><strong>Last 24h:</strong> <?php echo ($total24!==null)? intval($total24) : '—'; ?></span>
    </div>

    <div class="ge-grid">
      <article class="ge-card">
        <h3 id="recent">Recent Events (M5.0+) <a class="anchor-link" href="#recent" aria-label="Link to Recent Events">🔗</a></h3>
        <div class="ge-note">Note: This list shows magnitude 5.0 and above. The ticker totals include all magnitudes.</div>
        <?php if (!$events): ?>
          <div class="ge-empty">No recent events found.</div>
        <?php else: ?>
          <ul class="ev-list">
            <?php 
              $i = 0;
              foreach ($events as $ev){
                if ($i++ >= $max_items) break;
                $mag = isset($ev['mag']) ? number_format((float)$ev['mag'], 1) : '—';
                $place = isset($ev['place']) ? $ev['place'] : '—';
                $time = isset($ev['time_utc']) ? $ev['time_utc'] : '';
                $url  = isset($ev['url']) ? $ev['url'] : '';
                $depth = isset($ev['depth_km']) ? $ev['depth_km'] : null;
                $sevClass = '';
                $mval = isset($ev['mag']) ? floatval($ev['mag']) : 0;
                if ($mval >= 7.0) $sevClass = 'sev-high';
                elseif ($mval >= 6.0) $sevClass = 'sev-medium';
                elseif ($mval >= 5.0) $sevClass = 'sev-low';
            ?>
            <li class="ev <?php echo esc_attr($sevClass); ?>">
              <span class="ev-mag">M<?php echo esc_html($mag); ?></span>
              <span class="ev-place"><?php echo esc_html($place); ?></span>
              <span class="ev-time"><?php echo esc_html($time); ?></span>
              <?php if ($depth!==null): ?><span class="ev-depth"><?php echo esc_html(number_format((float)$depth,1)); ?> km</span><?php endif; ?>
              <?php if ($url): ?><a class="ev-link" href="<?php echo esc_url($url); ?>" target="_blank" rel="noopener">USGS</a><?php endif; ?>
            </li>
            <?php } ?>
          </ul>
        <?php endif; ?>
      </article>

      <article class="ge-card">
        <h3 id="stats">Global Stats <a class="anchor-link" href="#stats" aria-label="Link to Global Stats">🔗</a></h3>
        <ul class="ge-list">
          <li><strong>Total (feed):</strong> <?php echo ($total!==null)? intval($total) : '—'; ?></li>
          <li><strong>Last 24h:</strong> <?php echo ($total24!==null)? intval($total24) : '—'; ?></li>
        </ul>
        <div class="bucket-grid">
          <?php foreach ($buckets as $label=>$count): ?>
            <div class="bucket-item"><span class="b-lab"><?php echo esc_html($label); ?></span><span class="b-val"><?php echo intval($count); ?></span></div>
          <?php endforeach; ?>
        </div>
      </article>

      <article class="ge-card">
        <h3 id="health">Health context <a class="anchor-link" href="#health" aria-label="Link to Health Context">🔗</a></h3>
        <ul class="ge-list">
          <li>Rapid pressure and ground-motion changes can challenge the vestibular system; if sensitive, pace activities on high-activity days.</li>
          <li>Hydration and short daylight breaks may help stabilize autonomic tone.</li>
          <li>During global seismic clusters, keep evenings calm and light exposure lower to support sleep continuity.</li>
        </ul>
      </article>

      <article class="ge-card">
        <h3 id="about">About Earthquakes <a class="anchor-link" href="#about" aria-label="Link to About Earthquakes">🔗</a></h3>
        <p>Magnitude (M) is a logarithmic scale; each full step represents ~32× energy release. While most quakes are small, regional clustering and larger magnitudes can affect infrastructure and, indirectly, stress levels and daily routines. This page reflects a distilled feed of recent events to provide situational awareness alongside solar and Schumann metrics.</p>
      </article>
    </div>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-head h2{margin:0;font-size:1.15rem}
      .ge-meta{opacity:.8;font-size:.9rem}
      .ge-grid{display:grid;gap:12px}
      @media(min-width:900px){.ge-grid{grid-template-columns:repeat(2,1fr)}}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px}
      .ge-list{margin:0;padding-left:18px;line-height:1.45}
      .ev-list{margin:0;padding-left:0;list-style:none}
      .ev{display:grid;grid-template-columns:92px 1fr auto auto auto;gap:8px;align-items:center;border-bottom:1px dashed rgba(255,255,255,.08);padding:6px 0}
      .ev-mag{font-weight:700}
      .ev-place{opacity:.9}
      .ev-time{opacity:.75;font-size:.9rem}
      .ev-depth{opacity:.75;font-size:.9rem}
      .ev-link{color:#bcd5ff;text-decoration:none;border-bottom:1px dashed #4b6aa1}
      .bucket-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:8px}
      .bucket-item{background:#1b2233;border:1px solid #344a72;border-radius:10px;padding:8px;text-align:center}
      .b-lab{display:block;font-size:.85rem;opacity:.85}
      .b-val{display:block;font-size:1.05rem;font-weight:700}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      .sev-low .ev-mag{color:#ffd089}
      .sev-medium .ev-mag{color:#ffb347}
      .sev-high .ev-mag{color:#ff6b6b}
      .ge-ticker{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:8px 10px;margin-bottom:10px}
      .ge-ticker .tk{display:inline-block;font-size:.92rem}
      .ge-note{opacity:.8;font-size:.9rem;margin:.25rem 0 .5rem 0}
    </style>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_quakes_detail','gaiaeyes_quakes_detail_shortcode');
