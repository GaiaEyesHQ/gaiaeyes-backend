<?php
/*
Plugin Name: Gaia Eyes - Checkout
Description: Shortcode [ge_checkout plan="plus_monthly" label="Subscribe"] requires Supabase sign-in then calls backend to create Stripe Checkout.
Version: 0.1
*/

add_shortcode('ge_checkout', function ($atts) {
    $a = shortcode_atts([
        'plan' => 'plus_monthly',
        'label' => 'Subscribe with Gaia Eyes',
    ], $atts, 'ge_checkout');

    ob_start(); ?>
    <div class="ge-checkout">
        <button class="ge-checkout-btn" data-plan="<?php echo esc_attr($a['plan']); ?>">
            <?php echo esc_html($a['label']); ?>
        </button>
        <div class="ge-checkout-msg" aria-live="polite" style="margin-top:8px;"></div>
    </div>
    <?php
    return ob_get_clean();
});

add_action('wp_enqueue_scripts', function () {
    wp_enqueue_script('supabase-js', 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2', [], null, true);
    wp_enqueue_script(
        'ge-checkout',
        plugins_url('ge-checkout.js', __FILE__),
        ['supabase-js'],
        filemtime(__DIR__ . '/ge-checkout.js'),
        true
    );

    $supabase_url = defined('SUPABASE_URL') ? SUPABASE_URL : getenv('SUPABASE_URL');
    $supabase_anon = defined('SUPABASE_ANON_KEY') ? SUPABASE_ANON_KEY : getenv('SUPABASE_ANON_KEY');
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');

    wp_localize_script('ge-checkout', 'GE_CHECKOUT_CFG', [
        'supabaseUrl' => $supabase_url ? rtrim($supabase_url, '/') : '',
        'supabaseAnon' => $supabase_anon ? trim($supabase_anon) : '',
        'backendBase' => $backend_base ? rtrim($backend_base, '/') : '',
    ]);
});
