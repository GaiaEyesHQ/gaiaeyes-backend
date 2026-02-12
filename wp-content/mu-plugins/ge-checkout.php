<?php
/*
Plugin Name: Gaia Eyes - Checkout
Description: Shortcode [ge_checkout plan="plus_monthly" label="Subscribe"] requires Supabase sign-in then calls backend to create Stripe Checkout.
Version: 0.1
*/

add_shortcode('ge_checkout', function ($atts) {
    // Accept plan keys (preferred) and optional monthly/yearly overrides
    $a = shortcode_atts([
        'plan'           => '', // "plus", "pro", or full plan key like "plus_monthly"
        'monthly'        => '', // optional plan key override (e.g., "plus_monthly")
        'yearly'         => '', // optional plan key override (e.g., "plus_yearly")
        'label'          => 'Subscribe', // legacy single-button label
        'label_monthly'  => 'Subscribe - Monthly',
        'label_yearly'   => 'Subscribe - Yearly',
    ], $atts, 'ge_checkout');

    // Normalize attrs (trim whitespace and enforce label fallbacks)
    $a['plan'] = isset($a['plan']) && is_string($a['plan']) ? trim(strtolower($a['plan'])) : '';
    $a['monthly'] = isset($a['monthly']) && is_string($a['monthly']) ? trim(strtolower($a['monthly'])) : '';
    $a['yearly']  = isset($a['yearly'])  && is_string($a['yearly'])  ? trim(strtolower($a['yearly']))  : '';
    if (empty($a['label_monthly'])) { $a['label_monthly'] = 'Subscribe - Monthly'; }
    if (empty($a['label_yearly']))  { $a['label_yearly']  = 'Subscribe - Yearly'; }

    $allowed = [
        'plus_monthly', 'plus_yearly', 'pro_monthly', 'pro_yearly',
    ];
    $monthly_plan = '';
    $yearly_plan = '';
    $single_plan = '';

    if (in_array($a['plan'], ['plus', 'pro'], true)) {
        $monthly_plan = $a['plan'] . '_monthly';
        $yearly_plan = $a['plan'] . '_yearly';
    } elseif (in_array($a['plan'], $allowed, true)) {
        $single_plan = $a['plan'];
    }

    if (in_array($a['monthly'], $allowed, true)) {
        $monthly_plan = $a['monthly'];
    }
    if (in_array($a['yearly'], $allowed, true)) {
        $yearly_plan = $a['yearly'];
    }

    ob_start();
    ?>
    <div class="ge-checkout">
        <div class="ge-checkout-buttons">
            <?php if (!empty($monthly_plan) || !empty($yearly_plan)): ?>
                <?php if (!empty($monthly_plan)): ?>
                    <button class="ge-checkout-btn ge-checkout-btn--monthly"
                            data-plan="<?php echo esc_attr($monthly_plan); ?>"
                            data-label="<?php echo esc_attr($a['label_monthly']); ?>">
                        <?php echo esc_html($a['label_monthly']); ?>
                    </button>
                <?php endif; ?>
                <?php if (!empty($yearly_plan)): ?>
                    <button class="ge-checkout-btn ge-checkout-btn--yearly"
                            data-plan="<?php echo esc_attr($yearly_plan); ?>"
                            data-label="<?php echo esc_attr($a['label_yearly']); ?>">
                        <?php echo esc_html($a['label_yearly']); ?>
                    </button>
                <?php endif; ?>
            <?php else: ?>
                <!-- Legacy single-button path using a logical plan key -->
                <button class="ge-checkout-btn"
                        data-plan="<?php echo esc_attr($single_plan ?: 'plus_monthly'); ?>">
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
