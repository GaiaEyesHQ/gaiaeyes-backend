<?php
/**
 * Plugin Name: Gaia Eyes – Space Visuals
 * Description: Renders Solar/Aurora visual panels using gaiaeyes-media/data/space_live.json + images/space/.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) {
    exit;
}

function ge_fetch_json_cached($url, $cache_min) {
    $ttl = max(1, intval($cache_min)) * MINUTE_IN_SECONDS;
    $key = 'ge_json_' . md5($url);
    $cached = get_transient($key);
    if ($cached === false) {
        $response = wp_remote_get(esc_url_raw($url), [
            'timeout' => 8,
            'headers' => ['Accept' => 'application/json'],
        ]);
        if (!is_wp_error($response) && wp_remote_retrieve_response_code($response) === 200) {
            $cached = json_decode(wp_remote_retrieve_body($response), true);
            set_transient($key, $cached, $ttl);
        }
    }

    return is_array($cached) ? $cached : null;
}

add_shortcode('gaia_space_visuals', function ($atts) {
    $atts = shortcode_atts([
        'url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_live.json',
        'cache' => 10,
    ], $atts, 'gaia_space_visuals');

    $data = ge_fetch_json_cached($atts['url'], $atts['cache']);
    if (!$data) {
        return '<div class="ge-card">Space visuals unavailable.</div>';
    }

    $images = isset($data['images']) ? $data['images'] : [];

    ob_start();
    ?>
    <section class="ge-panel ge-space">
      <div class="ge-grid">
        <article class="ge-card"><h3>Solar disc (SUVI 131Å)</h3>
          <?php if (!empty($images['suvi_131_latest'])) : ?>
            <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['suvi_131_latest']); ?>" alt="GOES SUVI 131 latest" />
          <?php endif; ?>
        </article>
        <article class="ge-card"><h3>Auroral Ovals</h3><div class="ov-grid">
          <?php if (!empty($images['ovation_nh'])) : ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['ovation_nh']); ?>" alt="Aurora NH" /><figcaption>NH forecast</figcaption></figure><?php endif; ?>
          <?php if (!empty($images['ovation_sh'])) : ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['ovation_sh']); ?>" alt="Aurora SH" /><figcaption>SH forecast</figcaption></figure><?php endif; ?>
        </div></article>
        <article class="ge-card"><h3>Coronagraph / CMEs</h3><div class="ov-grid">
          <?php if (!empty($images['soho_c2'])) : ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['soho_c2']); ?>" alt="SOHO C2 latest" /><figcaption>SOHO C2</figcaption></figure><?php endif; ?>
          <?php if (!empty($images['goes_ccor1'])) : ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['goes_ccor1']); ?>" alt="GOES CCOR-1 latest" /><figcaption>GOES CCOR-1</figcaption></figure><?php endif; ?>
        </div></article>
        <article class="ge-card"><h3>Magnetometers</h3><div class="ov-grid">
          <?php foreach ([
            'mag_kiruna' => 'Kiruna',
            'mag_canmos' => 'CANMOS',
            'mag_hobart' => 'Hobart',
          ] as $key => $caption) :
            if (!empty($images[$key])) : ?>
              <figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images[$key]); ?>" alt="Magnetometer <?php echo esc_attr($caption); ?>" /><figcaption><?php echo esc_html($caption); ?></figcaption></figure>
            <?php endif;
          endforeach; ?>
        </div></article>
        <article class="ge-card"><h3>Sunspots / HMI</h3>
          <?php if (!empty($images['hmi_intensity'])) : ?>
            <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($images['hmi_intensity']); ?>" alt="HMI Intensitygram latest" />
          <?php endif; ?>
        </article>
      </div>
      <style>
        .ge-space .ge-grid { display:grid; gap:12px; }
        @media (min-width:900px) { .ge-space .ge-grid { grid-template-columns:repeat(2,1fr); } }
        .ge-space img { width:100%; height:auto; border-radius:8px; border:1px solid rgba(255,255,255,.08); }
        .ov-grid { display:grid; gap:8px; }
        @media (min-width:640px) { .ov-grid { grid-template-columns:repeat(2,1fr); } }
        figure { margin:0; }
        figcaption { text-align:center; font-size:.85rem; opacity:.85; margin-top:4px; }
      </style>
    </section>
    <?php
    return ob_get_clean();
});

add_shortcode('gaia_space_detail', function ($atts) {
    $atts = shortcode_atts([
        'cache' => 5,
        'url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_live.json',
    ], $atts, 'gaia_space_detail');

    return do_shortcode('[gaia_space_visuals url="' . esc_url($atts['url']) . '" cache="' . esc_attr($atts['cache']) . '"]');
});
