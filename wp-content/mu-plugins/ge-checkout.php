<?php
/*
Plugin Name: Gaia Eyes - Checkout
Description: Shortcode [ge_checkout plan="plus_monthly" label="Subscribe"] requires Supabase sign-in then calls backend to create Stripe Checkout.
Version: 0.1
*/

add_shortcode('ge_checkout', function ($atts) {
    // Accept both legacy "plan" usage and explicit Stripe price IDs for monthly/yearly
    $a = shortcode_atts([
        'plan'           => '', // optional logical plan key (e.g., "plus" or "pro")
        'monthly'        => '', // Stripe price_... for monthly
        'yearly'         => '', // Stripe price_... for yearly
        'label'          => 'Subscribe', // legacy single-button label
        'label_monthly'  => 'Subscribe — Monthly',
        'label_yearly'   => 'Subscribe — Yearly',
    ], $atts, 'ge_checkout');

    ob_start();
    ?>
    <div class="ge-checkout" <?php if (!empty($a['plan'])) { ?>data-plan="<?php echo esc_attr($a['plan']); ?>"<?php } ?>>
        <div class="ge-checkout-buttons">
            <?php if (!empty($a['monthly']) || !empty($a['yearly'])): ?>
                <?php if (!empty($a['monthly'])): ?>
                    <button class="ge-checkout-btn"
                            data-price-id="<?php echo esc_attr($a['monthly']); ?>"
                            data-term="monthly">
                        <?php echo esc_html($a['label_monthly']); ?>
                    </button>
                <?php endif; ?>
                <?php if (!empty($a['yearly'])): ?>
                    <button class="ge-checkout-btn"
                            data-price-id="<?php echo esc_attr($a['yearly']); ?>"
                            data-term="yearly">
                        <?php echo esc_html($a['label_yearly']); ?>
                    </button>
                <?php endif; ?>
            <?php else: ?>
                <!-- Legacy single-button path using a logical plan key -->
                <button class="ge-checkout-btn"
                        data-plan="<?php echo esc_attr($a['plan'] ?: 'plus_monthly'); ?>">
                    <?php echo esc_html($a['label']); ?>
                </button>
            <?php endif; ?>
        </div>
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

// Fallback: ensure shortcodes are parsed in page content and widgets.
// Some themes/templates remove the default 'the_content' shortcode filter.
add_filter('the_content', 'do_shortcode', 11);
add_filter('widget_text', 'do_shortcode', 11);
