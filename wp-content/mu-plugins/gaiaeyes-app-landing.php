<?php
/*
Plugin Name: Gaia Eyes - App Landing
Description: Launch landing page shortcode for the Gaia Eyes iOS app.
Version: 0.1
*/

if (!defined('ABSPATH')) {
    exit;
}

function gaiaeyes_app_landing_truthy($value) {
    return in_array(strtolower(trim((string) $value)), ['1', 'true', 'yes', 'on'], true);
}

add_shortcode('gaiaeyes_app_landing', function ($atts) {
    $a = shortcode_atts([
        'app_url' => 'https://apps.apple.com/us/app/gaia-eyes/id6761451455?uo=4',
        'support_url' => home_url('/support/'),
        'privacy_url' => home_url('/privacy-policy/'),
        'terms_url' => home_url('/terms/'),
        'show_public_code' => '0',
        'public_code' => 'GAIAEARLY',
        'public_code_label' => '1 month of Plus free',
    ], $atts, 'gaiaeyes_app_landing');

    $show_public_code = gaiaeyes_app_landing_truthy($a['show_public_code']);

    ob_start();
    ?>
    <section class="gea-app-page">
        <style>
            .gea-app-page {
                --gea-bg: #06110f;
                --gea-card: rgba(9, 20, 18, 0.78);
                --gea-card-strong: rgba(13, 27, 25, 0.96);
                --gea-line: rgba(91, 233, 212, 0.32);
                --gea-text: #f4fbf8;
                --gea-muted: #aebbb7;
                --gea-cyan: #55e0e9;
                --gea-green: #5ee3a5;
                --gea-gold: #f6c96f;
                --gea-pink: #f08aa8;
                color: var(--gea-text);
                background:
                    radial-gradient(circle at 14% 10%, rgba(85, 224, 233, 0.24), transparent 26rem),
                    radial-gradient(circle at 86% 22%, rgba(246, 201, 111, 0.16), transparent 26rem),
                    linear-gradient(145deg, #020706 0%, var(--gea-bg) 52%, #081615 100%);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 28px;
                overflow: hidden;
                box-shadow: 0 30px 90px rgba(0, 0, 0, 0.35);
                font-family: inherit;
            }
            .gea-app-page * { box-sizing: border-box; }
            .gea-app-hero {
                position: relative;
                padding: clamp(42px, 8vw, 88px) clamp(20px, 5vw, 72px);
                min-height: 560px;
                display: grid;
                grid-template-columns: minmax(0, 1.05fr) minmax(280px, 0.95fr);
                gap: clamp(28px, 5vw, 72px);
                align-items: center;
            }
            .gea-app-hero::before {
                content: "";
                position: absolute;
                inset: 0;
                background:
                    linear-gradient(100deg, rgba(255, 255, 255, 0.06), transparent 18%),
                    radial-gradient(circle at 42% 40%, rgba(255, 255, 255, 0.08), transparent 18rem);
                pointer-events: none;
            }
            .gea-app-copy,
            .gea-app-phone { position: relative; z-index: 1; }
            .gea-app-kicker {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                padding: 8px 12px;
                border: 1px solid var(--gea-line);
                border-radius: 999px;
                color: var(--gea-cyan);
                background: rgba(85, 224, 233, 0.08);
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            .gea-app-title {
                margin: 22px 0 16px;
                max-width: 820px;
                font-size: clamp(44px, 8vw, 92px);
                line-height: 0.96;
                letter-spacing: -0.06em;
                color: var(--gea-text);
            }
            .gea-app-title span {
                display: block;
                color: var(--gea-green);
                text-shadow: 0 0 34px rgba(94, 227, 165, 0.25);
            }
            .gea-app-subtitle {
                max-width: 680px;
                margin: 0 0 26px;
                color: #c8d6d1;
                font-size: clamp(18px, 2.2vw, 25px);
                line-height: 1.45;
            }
            .gea-app-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin: 0 0 24px;
            }
            .gea-app-button {
                display: inline-flex;
                justify-content: center;
                align-items: center;
                min-height: 52px;
                padding: 14px 20px;
                border-radius: 999px;
                font-weight: 900;
                text-decoration: none;
                transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
            }
            .gea-app-button:hover,
            .gea-app-button:focus {
                transform: translateY(-1px);
                text-decoration: none;
            }
            .gea-app-button-primary {
                color: #031311;
                background: linear-gradient(135deg, var(--gea-cyan), var(--gea-green));
                box-shadow: 0 18px 40px rgba(85, 224, 233, 0.22);
            }
            .gea-app-button-secondary {
                color: var(--gea-text);
                border: 1px solid rgba(255, 255, 255, 0.18);
                background: rgba(255, 255, 255, 0.06);
            }
            .gea-app-note {
                margin: 0;
                color: var(--gea-muted);
                font-size: 14px;
            }
            .gea-app-phone {
                justify-self: center;
                width: min(100%, 420px);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 46px;
                padding: 18px;
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.03)),
                    rgba(1, 5, 5, 0.74);
                box-shadow: 0 28px 70px rgba(0, 0, 0, 0.42);
            }
            .gea-app-screen {
                border-radius: 32px;
                min-height: 620px;
                padding: 28px 22px;
                background:
                    radial-gradient(circle at 50% 16%, rgba(85, 224, 233, 0.18), transparent 16rem),
                    linear-gradient(180deg, #050807, #08110f);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            .gea-app-signalbar {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
                margin-bottom: 18px;
            }
            .gea-app-pill {
                padding: 8px 10px;
                border-radius: 999px;
                text-align: center;
                color: #dbe8ff;
                background: rgba(71, 128, 255, 0.16);
                border: 1px solid rgba(95, 145, 255, 0.36);
                font-weight: 800;
                font-size: 13px;
            }
            .gea-app-pill:nth-child(3) {
                color: #ffe0b2;
                background: rgba(246, 201, 111, 0.16);
                border-color: rgba(246, 201, 111, 0.38);
            }
            .gea-app-gauge-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
            }
            .gea-app-gauge,
            .gea-app-driver {
                min-height: 124px;
                padding: 16px;
                border-radius: 22px;
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.09);
            }
            .gea-app-gauge small,
            .gea-app-driver small {
                display: block;
                margin-bottom: 10px;
                color: #9ea9a6;
                font-weight: 800;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .gea-app-gauge strong {
                display: block;
                font-size: 34px;
                line-height: 1;
                margin-bottom: 12px;
            }
            .gea-app-meter {
                width: 100%;
                height: 8px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.12);
                overflow: hidden;
            }
            .gea-app-meter span {
                display: block;
                height: 100%;
                border-radius: inherit;
                background: linear-gradient(90deg, var(--gea-green), var(--gea-gold));
            }
            .gea-app-driver {
                grid-column: 1 / -1;
                min-height: 0;
                margin-top: 12px;
                border-color: rgba(94, 227, 165, 0.22);
                background: rgba(94, 227, 165, 0.07);
            }
            .gea-app-driver-tags {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
            .gea-app-driver-tags span {
                padding: 7px 10px;
                border-radius: 999px;
                color: #e8fff6;
                background: rgba(94, 227, 165, 0.13);
                border: 1px solid rgba(94, 227, 165, 0.22);
                font-size: 13px;
                font-weight: 800;
            }
            .gea-app-section {
                padding: clamp(34px, 5vw, 64px) clamp(20px, 5vw, 72px);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
            .gea-app-section h2 {
                margin: 0 0 12px;
                color: var(--gea-text);
                font-size: clamp(30px, 4.4vw, 54px);
                letter-spacing: -0.04em;
            }
            .gea-app-section-lede {
                max-width: 780px;
                margin: 0 0 26px;
                color: #c6d3cf;
                font-size: 18px;
                line-height: 1.6;
            }
            .gea-app-feature-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 14px;
            }
            .gea-app-feature {
                min-height: 240px;
                padding: 22px;
                border-radius: 26px;
                background: var(--gea-card);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            .gea-app-feature b {
                display: block;
                margin-bottom: 10px;
                color: var(--gea-cyan);
                font-size: 20px;
            }
            .gea-app-feature p {
                margin: 0;
                color: #c0cbc8;
                line-height: 1.55;
            }
            .gea-app-plus {
                display: grid;
                grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
                gap: 18px;
                align-items: stretch;
            }
            .gea-app-plus-card,
            .gea-app-offer-card {
                padding: 26px;
                border-radius: 28px;
                background: var(--gea-card-strong);
                border: 1px solid var(--gea-line);
            }
            .gea-app-plus-price {
                margin: 0 0 16px;
                color: var(--gea-gold);
                font-size: 30px;
                font-weight: 900;
            }
            .gea-app-list {
                display: grid;
                gap: 10px;
                margin: 0;
                padding: 0;
                list-style: none;
            }
            .gea-app-list li {
                position: relative;
                padding-left: 24px;
                color: #d3ded9;
            }
            .gea-app-list li::before {
                content: "";
                position: absolute;
                left: 0;
                top: 0.68em;
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: var(--gea-green);
                box-shadow: 0 0 18px rgba(94, 227, 165, 0.56);
            }
            .gea-app-code {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                margin: 14px 0;
                padding: 12px 14px;
                border-radius: 16px;
                color: #071411;
                background: linear-gradient(135deg, var(--gea-gold), var(--gea-green));
                font-size: 18px;
                font-weight: 950;
                letter-spacing: 0.08em;
            }
            .gea-app-footer {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                padding: 28px clamp(20px, 5vw, 72px);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                color: var(--gea-muted);
                background: rgba(0, 0, 0, 0.18);
            }
            .gea-app-footer a {
                color: var(--gea-cyan);
                text-decoration: none;
                font-weight: 800;
            }
            .gea-app-footer a:hover,
            .gea-app-footer a:focus { text-decoration: underline; }
            @media (max-width: 980px) {
                .gea-app-hero,
                .gea-app-plus { grid-template-columns: 1fr; }
                .gea-app-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .gea-app-phone { width: min(100%, 380px); }
                .gea-app-screen { min-height: 560px; }
            }
            @media (max-width: 620px) {
                .gea-app-page { border-radius: 18px; }
                .gea-app-hero { min-height: 0; padding-top: 34px; }
                .gea-app-actions,
                .gea-app-footer { align-items: stretch; flex-direction: column; }
                .gea-app-button { width: 100%; }
                .gea-app-feature-grid,
                .gea-app-gauge-grid { grid-template-columns: 1fr; }
                .gea-app-signalbar { grid-template-columns: repeat(2, 1fr); }
                .gea-app-phone { display: none; }
            }
        </style>

        <div class="gea-app-hero">
            <div class="gea-app-copy">
                <div class="gea-app-kicker">Now live on iPhone</div>
                <h1 class="gea-app-title">Your body reacts to more than you think. <span>Gaia Eyes helps you see why.</span></h1>
                <p class="gea-app-subtitle">
                    Gaia Eyes compares your symptoms, optional Apple Health trends, local conditions, and
                    space-weather signals so you can see what keeps repeating without turning it into medical advice.
                </p>
                <div class="gea-app-actions">
                    <a class="gea-app-button gea-app-button-primary" href="<?php echo esc_url($a['app_url']); ?>" target="_blank" rel="noopener">
                        Download free on the App Store
                    </a>
                    <a class="gea-app-button gea-app-button-secondary" href="#gaiaeyes-plus">
                        See what Plus unlocks
                    </a>
                </div>
                <p class="gea-app-note">
                    HealthKit is optional. Gaia Eyes still shows public environmental context if you skip Apple Health access.
                </p>
            </div>
            <div class="gea-app-phone" aria-hidden="true">
                <div class="gea-app-screen">
                    <div class="gea-app-signalbar">
                        <span class="gea-app-pill">Kp 1.7</span>
                        <span class="gea-app-pill">SW 456</span>
                        <span class="gea-app-pill">SR 7.8</span>
                        <span class="gea-app-pill">hPa 1010</span>
                    </div>
                    <div class="gea-app-gauge-grid">
                        <div class="gea-app-gauge">
                            <small>Pain</small>
                            <strong>34</strong>
                            <div class="gea-app-meter"><span style="width:34%"></span></div>
                        </div>
                        <div class="gea-app-gauge">
                            <small>Focus</small>
                            <strong>47</strong>
                            <div class="gea-app-meter"><span style="width:47%"></span></div>
                        </div>
                        <div class="gea-app-gauge">
                            <small>Energy</small>
                            <strong>71</strong>
                            <div class="gea-app-meter"><span style="width:71%"></span></div>
                        </div>
                        <div class="gea-app-gauge">
                            <small>Sleep</small>
                            <strong>50</strong>
                            <div class="gea-app-meter"><span style="width:50%"></span></div>
                        </div>
                        <div class="gea-app-driver">
                            <small>Active influences</small>
                            <div class="gea-app-driver-tags">
                                <span>Pressure</span>
                                <span>Allergens</span>
                                <span>Schumann</span>
                                <span>Sleep</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="gea-app-section">
            <h2>One daily view for body + environment.</h2>
            <p class="gea-app-section-lede">
                Gaia Eyes is built for people who track how they feel and want better context around the day:
                weather shifts, allergens, AQI, pressure, space weather, sleep, symptoms, and repeating patterns.
            </p>
            <div class="gea-app-feature-grid">
                <article class="gea-app-feature">
                    <b>Mission Control</b>
                    <p>Daily gauges for pain, focus, heart, recovery load, energy, sleep, mood, and health status.</p>
                </article>
                <article class="gea-app-feature">
                    <b>Active influences</b>
                    <p>See which local, space, earth-resonance, and body-context signals are active right now.</p>
                </article>
                <article class="gea-app-feature">
                    <b>Patterns over time</b>
                    <p>Log symptoms and compare timing so repeated links can be reviewed instead of guessed.</p>
                </article>
                <article class="gea-app-feature">
                    <b>Shareable insights</b>
                    <p>Turn your discoveries into social cards that explain the signal without overclaiming.</p>
                </article>
            </div>
        </div>

        <div class="gea-app-section" id="gaiaeyes-plus">
            <div class="gea-app-plus">
                <article class="gea-app-plus-card">
                    <h2>Plus unlocks the deeper read.</h2>
                    <p class="gea-app-plus-price">$4.99 / month</p>
                    <ul class="gea-app-list">
                        <li>Personalized drivers and daily outlooks.</li>
                        <li>Optional Apple Health context for sleep, heart, HRV, SpO2, and steps.</li>
                        <li>Pattern history, body-context cards, and share previews.</li>
                        <li>Expanded guide content and subscription-gated surfaces.</li>
                    </ul>
                </article>
                <article class="gea-app-offer-card">
                    <h2>Have an offer code?</h2>
                    <p class="gea-app-section-lede">
                        Redeem the code with your Apple ID, then open Gaia Eyes and restore purchases if access
                        does not appear immediately.
                    </p>
                    <?php if ($show_public_code): ?>
                        <div class="gea-app-code"><?php echo esc_html($a['public_code']); ?></div>
                        <p class="gea-app-note"><?php echo esc_html($a['public_code_label']); ?> while launch codes remain available.</p>
                    <?php else: ?>
                        <p class="gea-app-note">
                            Founder and team codes are meant for direct sharing, so they are not shown publicly on this page.
                        </p>
                    <?php endif; ?>
                    <div class="gea-app-actions" style="margin-top:18px;">
                        <a class="gea-app-button gea-app-button-primary" href="<?php echo esc_url($a['app_url']); ?>" target="_blank" rel="noopener">
                            Open Gaia Eyes in the App Store
                        </a>
                        <a class="gea-app-button gea-app-button-secondary" href="<?php echo esc_url($a['support_url']); ?>">
                            Redemption help
                        </a>
                    </div>
                </article>
            </div>
        </div>

        <footer class="gea-app-footer">
            <span>Gaia Eyes is wellness context, not medical diagnosis or treatment.</span>
            <span>
                <a href="<?php echo esc_url($a['privacy_url']); ?>">Privacy</a>
                &nbsp;·&nbsp;
                <a href="<?php echo esc_url($a['terms_url']); ?>">Terms</a>
                &nbsp;·&nbsp;
                <a href="<?php echo esc_url($a['support_url']); ?>">Support</a>
            </span>
        </footer>
    </section>
    <?php
    return ob_get_clean();
});
