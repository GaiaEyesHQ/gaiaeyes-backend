<?php
/*
Plugin Name: Gaia Eyes - Privacy Policy
Description: Public /privacy page and shortcode for the Gaia Eyes privacy policy.
Version: 0.1
*/

if (!function_exists('gaiaeyes_privacy_policy_path')) {
    function gaiaeyes_privacy_policy_path() {
        return dirname(__DIR__, 2) . '/docs/legal/PRIVACY_POLICY.html';
    }
}

if (!function_exists('gaiaeyes_privacy_policy_fallback_html')) {
    function gaiaeyes_privacy_policy_fallback_html() {
        return <<<'HTML'
<div class="ge-privacy-policy-content">
  <section class="ge-privacy-section" id="overview">
    <p class="ge-privacy-eyebrow">Last updated</p>
    <h2>Overview</h2>
    <p>Gaia Eyes helps people notice patterns between body context, optional health signals, and environmental conditions. This Privacy Policy explains how Gaia Eyes handles data across the mobile app and website.</p>
    <p>Gaia Eyes is an observational context tool. It is not a medical device and does not diagnose, treat, cure, or prevent disease.</p>
  </section>

  <section class="ge-privacy-section" id="collect">
    <p class="ge-privacy-eyebrow">What we collect</p>
    <h2>Information we collect</h2>
    <p>Depending on how you use Gaia Eyes, we may collect account information, subscription metadata, symptom logs, notes, check-ins, support requests, optional health data you authorize, and location context such as ZIP code or approximate local conditions.</p>
    <ul>
      <li>Account details such as email address and profile preferences.</li>
      <li>Symptom logs, daily check-ins, notes, and in-app feedback.</li>
      <li>Optional Apple Health or wearable data you explicitly authorize.</li>
      <li>Approximate local context such as ZIP-based weather, air quality, allergens, and environmental conditions.</li>
      <li>Technical diagnostics and usage information needed to keep the app and website working.</li>
      <li>Subscription and billing metadata handled through platform billing and payment providers.</li>
    </ul>
  </section>

  <section class="ge-privacy-section" id="use">
    <p class="ge-privacy-eyebrow">How we use data</p>
    <h2>How Gaia Eyes uses information</h2>
    <p>We use information to provide current context, personal patterns, body summaries, support features, account access, troubleshooting, and subscription support.</p>
    <ul>
      <li>To build gauges, current outlook, drivers, patterns, and guide summaries.</li>
      <li>To personalize symptom follow-ups, support prompts, and account settings.</li>
      <li>To improve sync reliability, bug diagnosis, and product quality.</li>
      <li>To operate subscriptions, account security, and support workflows.</li>
    </ul>
  </section>

  <section class="ge-privacy-section" id="health">
    <p class="ge-privacy-eyebrow">Optional health data</p>
    <h2>Health and wearable data</h2>
    <p>If you choose to connect Health or supported wearables, Gaia Eyes may use data such as heart rate, sleep, HRV, SpO₂, respiratory rate, and related body signals to build your personal context.</p>
    <p>Health access is optional. You can revoke permissions at any time through Apple Health, device settings, or Gaia Eyes settings.</p>
  </section>

  <section class="ge-privacy-section" id="share">
    <p class="ge-privacy-eyebrow">How we share data</p>
    <h2>Service providers and sharing</h2>
    <p>We share data only as needed to operate Gaia Eyes and its infrastructure. That may include service providers for authentication, database/storage, billing, hosting, and environmental data delivery.</p>
    <ul>
      <li>Supabase for authentication, database, and storage.</li>
      <li>Stripe or platform billing providers for subscription support where applicable.</li>
      <li>Environmental and public data providers for local, space, and earth-system context.</li>
      <li>Hosting, logging, and reliability infrastructure used to keep Gaia Eyes available.</li>
    </ul>
    <p>We do not sell personal information.</p>
  </section>

  <section class="ge-privacy-section" id="choices">
    <p class="ge-privacy-eyebrow">Your choices</p>
    <h2>Your controls</h2>
    <p>You can control permissions, adjust settings, update symptom and notification preferences, and contact us about privacy or support questions.</p>
    <ul>
      <li>Disconnect optional health permissions at any time.</li>
      <li>Change timezone, notification timing, and symptom preferences in settings.</li>
      <li>Use support channels to request help with access, sync, or data questions.</li>
      <li>Delete the app or stop using the website at any time.</li>
    </ul>
  </section>

  <section class="ge-privacy-section" id="retention">
    <p class="ge-privacy-eyebrow">Retention and security</p>
    <h2>Retention and protection</h2>
    <p>We keep data only as long as reasonably needed to operate Gaia Eyes, support your account, meet legal obligations, and resolve reliability or billing issues. We use technical and organizational safeguards to protect stored data, but no system can guarantee absolute security.</p>
  </section>

  <section class="ge-privacy-section" id="contact">
    <p class="ge-privacy-eyebrow">Contact</p>
    <h2>Contact us</h2>
    <p>If you have privacy, support, or data questions, email <a href="mailto:help@gaiaeyes.com">help@gaiaeyes.com</a>.</p>
  </section>
</div>
HTML;
    }
}

if (!function_exists('gaiaeyes_privacy_policy_html')) {
    function gaiaeyes_privacy_policy_html() {
        static $cached = null;
        if ($cached !== null) {
            return $cached;
        }

        $path = gaiaeyes_privacy_policy_path();
        if (file_exists($path)) {
            $raw = file_get_contents($path);
            $cached = is_string($raw) && trim($raw) !== '' ? $raw : gaiaeyes_privacy_policy_fallback_html();
        } else {
            $cached = gaiaeyes_privacy_policy_fallback_html();
        }
        return $cached;
    }
}

if (!function_exists('gaiaeyes_privacy_url')) {
    function gaiaeyes_privacy_url($anchor = '') {
        $base = home_url('/privacy/');
        if (!$anchor) {
            return $base;
        }
        return $base . '#' . rawurlencode($anchor);
    }
}

if (!function_exists('gaiaeyes_is_privacy_request')) {
    function gaiaeyes_is_privacy_request() {
        $path = isset($_SERVER['REQUEST_URI']) ? (string) parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) : '';
        $segments = array_values(array_filter(explode('/', trim($path, '/'))));
        if (empty($segments)) {
            return false;
        }
        $last = end($segments);
        return in_array($last, ['privacy', 'privacy-policy'], true);
    }
}

if (!function_exists('gaiaeyes_render_privacy_policy')) {
    function gaiaeyes_render_privacy_policy() {
        $html = gaiaeyes_privacy_policy_html();
        if ($html === '') {
            return '<section class="ge-privacy-policy"><p>Privacy policy content is not available yet.</p></section>';
        }

        ob_start();
        ?>
        <section class="ge-privacy-policy">
            <style>
                .ge-privacy-policy { color: #eef5f2; }
                .ge-privacy-shell { display: grid; gap: 18px; }
                .ge-privacy-hero,
                .ge-privacy-nav,
                .ge-privacy-body {
                    background: linear-gradient(135deg, rgba(16, 40, 35, 0.96), rgba(9, 15, 13, 0.98));
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 22px;
                    padding: 22px;
                    box-shadow: 0 16px 36px rgba(0,0,0,0.18);
                }
                .ge-privacy-hero h1,
                .ge-privacy-policy-content h1,
                .ge-privacy-policy-content h2,
                .ge-privacy-policy-content h3 {
                    color: #ffffff;
                    margin-top: 0;
                }
                .ge-privacy-hero p,
                .ge-privacy-nav p,
                .ge-privacy-policy-content p,
                .ge-privacy-policy-content li {
                    color: rgba(255,255,255,0.84);
                }
                .ge-privacy-chip-row,
                .ge-privacy-actions,
                .ge-privacy-link-grid {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }
                .ge-privacy-chip,
                .ge-privacy-link {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    text-decoration: none;
                    border-radius: 999px;
                    padding: 10px 14px;
                    font-weight: 600;
                }
                .ge-privacy-chip {
                    background: rgba(255,255,255,0.08);
                    color: #ffffff;
                }
                .ge-privacy-link {
                    background: #2cc6a0;
                    color: #06211b;
                }
                .ge-privacy-link--quiet {
                    background: rgba(255,255,255,0.08);
                    color: #f3faf7;
                    border: 1px solid rgba(255,255,255,0.08);
                }
                .ge-privacy-link-grid a {
                    flex: 1 1 220px;
                    min-width: 220px;
                    padding: 18px;
                    text-decoration: none;
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 18px;
                    color: #ffffff;
                }
                .ge-privacy-link-grid strong {
                    display: block;
                    margin-bottom: 6px;
                    font-size: 1rem;
                }
                .ge-privacy-policy-content {
                    display: grid;
                    gap: 18px;
                }
                .ge-privacy-section + .ge-privacy-section {
                    padding-top: 14px;
                    border-top: 1px solid rgba(255,255,255,0.08);
                }
                .ge-privacy-eyebrow {
                    font-size: 0.72rem;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: rgba(255,255,255,0.5);
                    margin-bottom: 8px;
                }
                .ge-privacy-policy-content ul {
                    margin: 10px 0 0 18px;
                }
                .ge-privacy-policy-content a {
                    color: #9ee9d6;
                }
                @media (max-width: 700px) {
                    .ge-privacy-hero,
                    .ge-privacy-nav,
                    .ge-privacy-body {
                        padding: 18px;
                    }
                }
            </style>
            <?php $terms_url = function_exists('gaiaeyes_terms_url') ? gaiaeyes_terms_url() : home_url('/terms/'); ?>
            <div class="ge-privacy-shell">
                <header class="ge-privacy-hero">
                    <p class="ge-privacy-eyebrow">Legal</p>
                    <h1>Gaia Eyes Privacy Policy</h1>
                    <p>This page explains how Gaia Eyes handles account data, optional Health data, location context, symptom logs, support requests, and billing-related information across the app and website.</p>
                    <div class="ge-privacy-chip-row">
                        <span class="ge-privacy-chip">public privacy URL</span>
                        <span class="ge-privacy-chip">app + website</span>
                        <span class="ge-privacy-chip">optional Health data</span>
                        <span class="ge-privacy-chip">patterns, not diagnosis</span>
                    </div>
                    <div class="ge-privacy-actions">
                        <a class="ge-privacy-link" href="mailto:help@gaiaeyes.com?subject=Privacy%20Question">Contact Privacy Support</a>
                        <a class="ge-privacy-link ge-privacy-link--quiet" href="<?php echo esc_url(home_url('/support/')); ?>">Open Support Center</a>
                        <a class="ge-privacy-link ge-privacy-link--quiet" href="<?php echo esc_url($terms_url); ?>">Terms of Use</a>
                    </div>
                </header>

                <nav class="ge-privacy-nav" aria-label="Privacy quick links">
                    <p class="ge-privacy-eyebrow">Quick links</p>
                    <div class="ge-privacy-link-grid">
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('collect')); ?>"><strong>What we collect</strong><span>Account info, app inputs, optional Health data, location, diagnostics, and billing metadata.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('share')); ?>"><strong>How we share data</strong><span>Supabase, Stripe, Apple services, environmental data providers, and core infrastructure partners.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('choices')); ?>"><strong>Your choices</strong><span>Permissions, settings, support requests, and how to contact us about your data.</span></a>
                        <a href="<?php echo esc_url($terms_url); ?>"><strong>Terms of Use</strong><span>Read the public app and website terms alongside the Privacy Policy.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('contact')); ?>"><strong>Contact</strong><span>Use help@gaiaeyes.com for privacy, support, or data questions.</span></a>
                    </div>
                </nav>

                <section class="ge-privacy-body">
                    <?php echo wp_kses_post($html); ?>
                </section>
            </div>
        </section>
        <?php
        return ob_get_clean();
    }
}

add_shortcode('gaia_privacy_policy', function () {
    return gaiaeyes_render_privacy_policy();
});

add_action('template_redirect', function () {
    if (is_admin() || !gaiaeyes_is_privacy_request()) {
        return;
    }

    global $wp_query;
    if ($wp_query) {
        $wp_query->is_404 = false;
    }

    status_header(200);

    add_filter('document_title_parts', function ($parts) {
        if (is_array($parts)) {
            $parts['title'] = 'Privacy Policy';
        }
        return $parts;
    });

    get_header();
    echo '<main class="ge-privacy-page"><div class="ge-privacy-page__inner">';
    echo do_shortcode('[gaia_privacy_policy]');
    echo '</div></main>';
    get_footer();
    exit;
});
