<?php
/**
 * Plugin Name: Gaia Eyes – Dashboard UI (Gauges & Pills)
 * Description: Spaceship-style gauges and status pills. Shortcodes: [ge_gauge] and [ge_panel] for quick layouts.
 * Version: 0.1.0
 */

if (!defined('ABSPATH')) exit;

define('GE_DASH_VER', '0.1.0');
define('GE_DASH_DIR', __DIR__ . '/gaia-dashboard-ui');
define('GE_DASH_URL', plugins_url('gaia-dashboard-ui', __FILE__));

add_action('wp_enqueue_scripts', function(){
    global $post;
    $needs = true;
    if (function_exists('has_shortcode') && isset($post->post_content)) {
        $needs = has_shortcode($post->post_content, 'ge_gauge') || has_shortcode($post->post_content, 'ge_panel');
    }
    if ($needs) {
        wp_enqueue_style('ge-dashboard-css', GE_DASH_URL . '/gaia_dashboard.css', [], GE_DASH_VER);
        wp_enqueue_script('ge-gauges-js', GE_DASH_URL . '/gaia_gauges.js', [], GE_DASH_VER, true);
    }
});

/**
 * [ge_gauge] – Single arc gauge
 * attrs:
 *   label: text
 *   value: number
 *   min,max: numbers
 *   unit: text
 *   theme: kp|bz|pfu|schumann|default
 *   severity: ok|warn|alert (optional glow)
 */
add_shortcode('ge_gauge', function($atts=[]){
    $a = shortcode_atts([
        'label' => 'Metric',
        'value' => '0',
        'min'   => '0',
        'max'   => '100',
        'unit'  => '',
        'theme' => 'default',
        'severity' => ''
    ], $atts, 'ge_gauge');

    $value = floatval($a['value']);
    $min   = floatval($a['min']);
    $max   = floatval($a['max']);
    $unit  = sanitize_text_field($a['unit']);
    $label = sanitize_text_field($a['label']);
    $theme = preg_replace('/[^a-z0-9_-]/i','', $a['theme']);
    $sev   = preg_replace('/[^a-z0-9_-]/i','', $a['severity']);

    ob_start(); ?>
    <div class="ge-card">
      <div class="ge-row">
        <div class="ge-label"><?php echo esc_html($label); ?></div>
        <?php if ($sev): ?>
          <span class="ge-pill" data-severity="<?php echo esc_attr($sev); ?>"><?php echo strtoupper(esc_html($sev)); ?></span>
        <?php endif; ?>
      </div>
      <div class="ge-arc" data-theme="<?php echo esc_attr($theme); ?>" data-min="<?php echo esc_attr($min); ?>" data-max="<?php echo esc_attr($max); ?>" data-value="<?php echo esc_attr($value); ?>">
        <svg viewBox="0 0 200 200" data-r="80" aria-hidden="true">
          <circle class="track" cx="100" cy="100" r="80" />
          <circle class="fill"  cx="100" cy="100" r="80" />
        </svg>
        <div class="center">
          <div class="v"><?php echo esc_html($value); ?></div>
          <?php if ($unit): ?><div class="u"><?php echo esc_html($unit); ?></div><?php endif; ?>
          <div class="l"><?php echo esc_html($label); ?></div>
        </div>
      </div>
    </div>
    <?php return ob_get_clean();
});

/**
 * [ge_panel] – Wrap gauges into a responsive grid
 * Usage:
 * [ge_panel]
 *   [ge_gauge ...] [ge_gauge ...]
 * [/ge_panel]
 */
add_shortcode('ge_panel', function($atts=[], $content=''){
    $inner = do_shortcode($content);
    return '<section class="ge-panel">'.$inner.'</section>';
});
