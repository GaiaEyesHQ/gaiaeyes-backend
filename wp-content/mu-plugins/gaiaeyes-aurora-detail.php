<?php
/**
 * Plugin Name: Gaia Eyes – Aurora Detail Renderer
 * Description: Renders the Aurora detail experience via a theme partial while preserving the legacy shortcode.
 * Feature Flag: define('GAIA_AURORA_SHOW_KP_LINES', true) to enable KP-lines overlay UI.
 * Version: 2.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

if (!function_exists('gaia_aurora_render_detail')) {
    /**
     * Locate and render the aurora detail partial.
     *
     * @param array $atts Shortcode-style attributes.
     * @return string
     */
    function gaia_aurora_render_detail($atts = [])
    {
        $defaults = [
            'initial_hemisphere' => 'north',
            'refresh_interval'   => 300,
            'rest_base'          => '/wp-json/gaia/v1/aurora',
        ];

        // Back-compat: map the legacy `which` attribute to the initial hemisphere toggle.
        if (isset($atts['which'])) {
            $w = strtolower((string) $atts['which']);
            if ($w === 'sh' || $w === 'south') {
                $atts['initial_hemisphere'] = 'south';
            } elseif ($w === 'nh' || $w === 'north') {
                $atts['initial_hemisphere'] = 'north';
            }
        }

        $context = shortcode_atts($defaults, $atts, 'gaia_aurora_detail');
        // Provide base map images for each hemisphere (served from your media repo)
        //$context['base_map_url'] = [
          //  'north' => home_url('/gaiaeyes-media/public/aurora/nowcast/northern-hemisphere.jpg'),
          //  'south' => home_url('/gaiaeyes-media/public/aurora/nowcast/southern-hemisphere.jpg'),
        //];
        // Feature toggles for the template/JS
        // KP-lines overlay is parked behind a feature flag by default.
        // Enable globally by defining GAIA_AURORA_SHOW_KP_LINES=true in wp-config.php,
        // or per-instance with the shortcode attribute kp_lines="true|false".
        $kp_lines_enabled = defined('GAIA_AURORA_SHOW_KP_LINES') ? (bool) GAIA_AURORA_SHOW_KP_LINES : false;
        if (isset($atts['kp_lines'])) {
            $v = strtolower(trim((string)$atts['kp_lines']));
            $kp_lines_enabled = in_array($v, ['1','true','yes','on'], true) ? true :
                                (in_array($v, ['0','false','no','off'], true) ? false : $kp_lines_enabled);
        }
        /**
         * Filter: gaia_aurora_kp_lines_enabled
         * Allow themes/plugins to override whether the KP-lines overlay UI is shown.
         *
         * @param bool  $enabled Current enabled state.
         * @param array $context Current render context.
         * @param array $atts    Raw shortcode attributes.
         */
        $kp_lines_enabled = apply_filters('gaia_aurora_kp_lines_enabled', $kp_lines_enabled, $context, $atts);
        $context['enable_kp_lines_toggle'] = $kp_lines_enabled; // controls KP Lines button visibility
        // Inline CSS guard to force-hide KP-lines UI/overlay when disabled (applies to theme partial and MU fallback)
        $inline_kp_hide = '';
        if (!$kp_lines_enabled) {
            $inline_kp_hide = '<style>
            .ga-aurora [data-role="kp-lines-toggle"],
            .ga-aurora .ga-kp-lines,
            .ga-aurora .ga-aurora__legend--kplines,
            .ga-aurora .ga-aurora__panel--kplines,
            .ga-aurora svg,
            .ga-aurora .ga-aurora__map,
            .ga-aurora .ga-aurora__canvas { display: none !important; }
            </style>';
        }
        $context['enable_push_alerts']     = true;              // show Push Alerts button (wire later)

        $template = locate_template('partials/gaiaeyes-aurora-detail.php');
        $fallback = WP_CONTENT_DIR . '/mu-plugins/templates/gaiaeyes-aurora-detail.php';

        if (!$template) {
            if (file_exists($fallback)) {
                $template = $fallback;
            } else {
                return '<div class="gaia-aurora__error">Aurora detail template missing.</div>';
            }
        }

        $context = apply_filters('gaia_aurora_detail_context', $context, $atts);

        ob_start();
        // Output the inline CSS guard (if KP-lines is disabled) before the template markup.
        if (!empty($inline_kp_hide)) {
            echo $inline_kp_hide;
        }
        if (function_exists('load_template')) {
            load_template($template, false, $context);
        } else {
            // Fallback for very old WordPress versions.
            $gaia_aurora_context = $context; // phpcs:ignore WordPress.NamingConventions.PrefixAllGlobals
            include $template;
        }
        return ob_get_clean();
    }
}

if (!function_exists('gaiaeyes_aurora_detail_shortcode')) {
    /**
     * Legacy shortcode wrapper.
     *
     * @param array $atts
     * @return string
     */
    function gaiaeyes_aurora_detail_shortcode($atts = [])
    {
        return gaia_aurora_render_detail($atts);
    }
}

add_shortcode('gaia_aurora_detail', 'gaiaeyes_aurora_detail_shortcode');
