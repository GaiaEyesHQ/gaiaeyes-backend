<?php
/*
Plugin Name: Gaia Eyes - Checkout
Description: Shortcode [ge_checkout plan="plus_monthly" label="Subscribe"] requires Supabase password sign-in then calls backend to create Stripe Checkout.
Version: 0.1
*/

add_shortcode('ge_checkout', function ($atts) {
    // Accept plan keys (preferred) and optional monthly/yearly overrides
    $a = shortcode_atts([
        'plan'           => '', // "plus" or full plan key like "plus_monthly"
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
        'plus_monthly', 'plus_yearly',
    ];
    $monthly_plan = '';
    $yearly_plan = '';
    $single_plan = '';

    if ($a['plan'] === 'plus') {
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
        <div class="ge-checkout-help">
            <a href="<?php echo esc_url(home_url('/app/')); ?>">Get the app</a>
            <a href="<?php echo esc_url(home_url('/support/#need-help-with-billing')); ?>">Billing help</a>
            <a href="<?php echo esc_url(home_url('/support/#restore-purchases')); ?>">Restore access</a>
            <a href="<?php echo esc_url(home_url('/support/#free-vs-plus')); ?>">Free vs Plus</a>
        </div>
    </div>
    <?php
    return ob_get_clean();
});

add_shortcode('ge_checkout_plans', function ($atts) {
    $a = shortcode_atts([
        'title' => 'Gaia Eyes Plus',
        'subtitle' => 'One Plus subscription unlocks member access on the website and in the iPhone app when you use the same Gaia Eyes email.',
        'app_url' => home_url('/app/'),
        'billing_note' => 'Two payment options: subscribe here with Stripe for web checkout, or subscribe in the iOS app through Apple payments on your phone.',
        'plus_label' => 'Plus',
        'plus_badge' => 'Most popular',
        'plus_desc' => 'Personalized gauges, drivers, Outlook, pattern history, local conditions, allergens, forecasts, and optional Apple Health context in the app.',
        'plus_price_monthly' => '$4.99 / month',
        'plus_price_yearly' => '$49.99 / year',
        'plus_features' => 'Website and iPhone app member access with the same email|My Dashboard gauges and daily context|Personal drivers and Outlook|Patterns, symptoms, and body-context history|Local conditions, pollen, allergens, AQI, pressure, and 7-day forecast context|Optional Apple Health context in the iPhone app',
        'plus_label_monthly' => 'Get Plus (Monthly)',
        'plus_label_yearly' => 'Get Plus (Yearly)',
    ], $atts, 'ge_checkout_plans');

    $plus_features = array_filter(array_map('trim', explode('|', (string) $a['plus_features'])));

    ob_start();
    ?>
    <section class="ge-plans">
        <header class="ge-plans-header">
            <h2 class="ge-plans-title"><?php echo esc_html($a['title']); ?></h2>
            <p class="ge-plans-subtitle"><?php echo esc_html($a['subtitle']); ?></p>
            <div class="ge-plans-channel-note">
                <span><?php echo esc_html($a['billing_note']); ?></span>
                <a href="<?php echo esc_url($a['app_url']); ?>">Get the iPhone app</a>
            </div>
        </header>
        <div class="ge-plan-grid">
            <article class="ge-plan-card ge-plan-card--plus">
                <div class="ge-plan-top">
                    <span class="ge-plan-badge"><?php echo esc_html($a['plus_badge']); ?></span>
                    <h3 class="ge-plan-name"><?php echo esc_html($a['plus_label']); ?></h3>
                    <p class="ge-plan-desc"><?php echo esc_html($a['plus_desc']); ?></p>
                </div>
                <div class="ge-plan-prices">
                    <div class="ge-plan-price"><?php echo esc_html($a['plus_price_monthly']); ?></div>
                    <div class="ge-plan-price ge-plan-price--muted"><?php echo esc_html($a['plus_price_yearly']); ?></div>
                </div>
                <?php if (!empty($plus_features)): ?>
                    <ul class="ge-plan-features">
                        <?php foreach ($plus_features as $feat): ?>
                            <li><?php echo esc_html($feat); ?></li>
                        <?php endforeach; ?>
                    </ul>
                <?php endif; ?>
                <div class="ge-checkout ge-checkout--card">
                    <div class="ge-checkout-buttons">
                        <button class="ge-checkout-btn ge-checkout-btn--monthly"
                                data-plan="plus_monthly"
                                data-label="<?php echo esc_attr($a['plus_label_monthly']); ?>">
                            <?php echo esc_html($a['plus_label_monthly']); ?>
                        </button>
                        <button class="ge-checkout-btn ge-checkout-btn--yearly"
                                data-plan="plus_yearly"
                                data-label="<?php echo esc_attr($a['plus_label_yearly']); ?>">
                            <?php echo esc_html($a['plus_label_yearly']); ?>
                        </button>
                    </div>
                    <div class="ge-checkout-msg" aria-live="polite"></div>
                </div>
            </article>
        </div>
        <div class="ge-plans-support">
            <span>Need billing help before checkout?</span>
            <a href="<?php echo esc_url($a['app_url']); ?>">Get the app</a>
            <a href="<?php echo esc_url(home_url('/support/#need-help-with-billing')); ?>">Billing help</a>
            <a href="<?php echo esc_url(home_url('/support/#restore-purchases')); ?>">Restore access</a>
            <a href="<?php echo esc_url(home_url('/support/#what-gaia-eyes-does')); ?>">Understanding Gaia Eyes</a>
        </div>
    </section>
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

    wp_register_style('ge-checkout', false);
    wp_enqueue_style('ge-checkout');
    wp_add_inline_style('ge-checkout', '
        .ge-plans { padding: 12px 0; }
        .ge-plans-header { text-align: center; margin-bottom: 24px; }
        .ge-plans-title { font-size: 32px; margin: 0 0 8px; }
        .ge-plans-subtitle { margin: 0; color: #4d5c57; }
        .ge-plans-channel-note { margin: 14px auto 0; max-width: 760px; display: flex; gap: 10px; justify-content: center; align-items: center; flex-wrap: wrap; padding: 12px 14px; border-radius: 12px; background: #eef7f4; color: #31423d; font-size: 13px; line-height: 1.45; }
        .ge-plans-channel-note a { color: #0f6f5c; font-weight: 700; text-decoration: none; white-space: nowrap; }
        .ge-plans-channel-note a:hover { text-decoration: underline; }
        .ge-plan-grid { display: grid; gap: 20px; grid-template-columns: minmax(240px, 520px); justify-content: center; }
        .ge-plan-card { background: #0f1a17; color: #f2f7f4; border-radius: 16px; padding: 20px; box-shadow: 0 16px 40px rgba(0,0,0,0.2); }
        .ge-plan-top { margin-bottom: 12px; }
        .ge-plan-badge { display: inline-block; font-size: 12px; letter-spacing: 0.4px; text-transform: uppercase; padding: 4px 8px; border-radius: 999px; background: #2cc6a0; color: #0a1411; }
        .ge-plan-name { margin: 10px 0 6px; font-size: 22px; }
        .ge-plan-desc { margin: 0 0 12px; color: #c9d6d1; }
        .ge-plan-prices { margin: 12px 0; }
        .ge-plan-price { font-size: 18px; font-weight: 600; }
        .ge-plan-price--muted { font-size: 14px; color: #9fb0aa; }
        .ge-plan-features { margin: 12px 0 16px; padding-left: 18px; color: #d9e4e0; }
        .ge-plan-features li { margin-bottom: 6px; }
        .ge-checkout--card .ge-checkout-buttons { display: flex; flex-direction: column; gap: 8px; }
        .ge-checkout-btn { border: none; border-radius: 999px; padding: 12px 18px; font-weight: 600; background: #2cc6a0; color: #0a1411; cursor: pointer; }
        .ge-checkout-btn--yearly { background: #1d2f2a; color: #e7f2ee; border: 1px solid rgba(255,255,255,0.15); }
        .ge-checkout-msg { margin-top: 8px; color: #f6c85f; font-size: 13px; min-height: 18px; }
        .ge-checkout-auth { margin-top: 12px; display: grid; gap: 10px; padding: 12px; border-radius: 16px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); }
        .ge-checkout-auth label { display: grid; gap: 5px; font-size: 12px; color: #c9d6d1; }
        .ge-checkout-auth input[type="email"], .ge-checkout-auth input[type="password"] { width: 100%; box-sizing: border-box; border: 1px solid rgba(255,255,255,0.16); border-radius: 10px; padding: 10px 12px; color: #f5fffb; background: rgba(0,0,0,0.22); }
        .ge-checkout-auth__check { grid-template-columns: auto 1fr; align-items: center; }
        .ge-checkout-auth__actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .ge-checkout-auth__actions button { border: 0; border-radius: 999px; padding: 9px 14px; font-weight: 700; cursor: pointer; }
        .ge-checkout-auth__actions button[type="submit"] { background: #2cc6a0; color: #0a1411; }
        .ge-checkout-auth__actions button[type="button"] { background: rgba(255,255,255,0.10); color: #e7f2ee; }
        .ge-checkout-help, .ge-plans-support { margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; font-size: 13px; color: #c9d6d1; }
        .ge-checkout-help a, .ge-plans-support a { color: #9ee9d6; text-decoration: none; }
        .ge-checkout-help a:hover, .ge-plans-support a:hover { text-decoration: underline; }
        @media (max-width: 640px) { .ge-plans-title { font-size: 26px; } }
    ');

    $supabase_url = defined('SUPABASE_URL') ? SUPABASE_URL : getenv('SUPABASE_URL');
    $supabase_anon = defined('SUPABASE_ANON_KEY') ? SUPABASE_ANON_KEY : getenv('SUPABASE_ANON_KEY');
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');

    wp_localize_script('ge-checkout', 'GE_CHECKOUT_CFG', [
        'supabaseUrl' => $supabase_url ? rtrim($supabase_url, '/') : '',
        'supabaseAnon' => $supabase_anon ? trim($supabase_anon) : '',
        'backendBase' => $backend_base ? rtrim($backend_base, '/') : '',
    ]);
});
