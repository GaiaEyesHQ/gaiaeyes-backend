<?php
/**
 * Plugin Name: Gaia Eyes – Aurora Detail Renderer
 * Description: Renders the Aurora detail experience via a theme partial while preserving the legacy shortcode.
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
 // In the context section, update base_map_url paths:
        $context['base_map_url'] = [
            'north' => home_url('/gaiaeyes-media/public/aurora/nowcast/northern-hemisphere.jpg'),
            'south' => home_url('/gaiaeyes-media/public/aurora/nowcast/southern-hemisphere.jpg'),
        ];
        // Feature toggles for the template/JS
        $context['enable_kp_lines_toggle'] = true;   // show KP Lines button
        $context['enable_push_alerts']     = true;   // show Push Alerts button (wire later)

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
