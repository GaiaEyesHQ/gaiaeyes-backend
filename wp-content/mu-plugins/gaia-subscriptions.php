<?php
/**
 * Plugin Name: GaiaEyes Subscriptions (Shortcodes)
 * Description: Adds [ge_pricing_table] shortcode that renders Stripe’s pricing table.
 */

add_action('init', function () {
    add_shortcode('ge_pricing_table', function ($atts) {
        $a = shortcode_atts([
            'pricing_table_id' => '',
            'publishable_key'  => '',
        ], $atts, 'ge_pricing_table');

        if (!$a['pricing_table_id'] || !$a['publishable_key']) {
            return '<!-- ge_pricing_table: missing pricing_table_id or publishable_key -->';
        }

        // Load Stripe’s pricing table script (footer)
        wp_enqueue_script(
            'stripe-pricing-table',
            'https://js.stripe.com/v3/pricing-table.js',
            [],
            null,
            true
        );

        // Optionally pass logged-in user context for Stripe (helps our webhook mapping)
        $extra = '';
        if (is_user_logged_in()) {
            $user = wp_get_current_user();
            // Use WP user id + email. (If you later have your Supabase user id in a cookie/meta, swap it in here.)
            $extra .= ' client-reference-id="' . esc_attr('wp-' . $user->ID) . '"';
            $extra .= ' customer-email="' . esc_attr($user->user_email) . '"';
        }

        $html  = '<div class="ge-pricing-table">';
        $html .= '<stripe-pricing-table';
        $html .= ' pricing-table-id="' . esc_attr($a['pricing_table_id']) . '"';
        $html .= ' publishable-key="' . esc_attr($a['publishable_key']) . '"';
        $html .= $extra;
        $html .= '></stripe-pricing-table>';
        $html .= '</div>';

        return $html;
    });
});