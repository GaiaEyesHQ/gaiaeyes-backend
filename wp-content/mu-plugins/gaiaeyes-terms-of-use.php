<?php
/*
Plugin Name: Gaia Eyes - Terms of Use
Description: Public /terms page and shortcode for the Gaia Eyes Terms of Use / EULA.
Version: 0.1
*/

if (!function_exists('gaiaeyes_terms_of_use_path')) {
    function gaiaeyes_terms_of_use_path() {
        return dirname(__DIR__, 2) . '/docs/legal/TERMS_OF_USE.html';
    }
}

if (!function_exists('gaiaeyes_terms_of_use_fallback_html')) {
    function gaiaeyes_terms_of_use_fallback_html() {
        return <<<'HTML'
<div class="ge-terms-content">
  <section class="ge-terms-section" id="overview">
    <p class="ge-terms-eyebrow">Terms of Use</p>
    <h2>Overview</h2>
    <p>These Terms of Use apply to the Gaia Eyes mobile app, website, support center, and related services.</p>
    <p>Gaia Eyes is a pattern and context tool. It is not a medical device and does not provide medical advice, diagnosis, or treatment.</p>
  </section>

  <section class="ge-terms-section" id="subscriptions">
    <p class="ge-terms-eyebrow">Billing</p>
    <h2>Subscriptions and account access</h2>
    <p>Paid access, renewals, and cancellation may also be governed by Apple or other platform billing rules where applicable.</p>
    <p>Deleting a Gaia Eyes account does not automatically cancel an App Store subscription.</p>
  </section>

  <section class="ge-terms-section" id="acceptable-use">
    <p class="ge-terms-eyebrow">Use of the service</p>
    <h2>Acceptable use</h2>
    <p>You may not misuse Gaia Eyes, attempt unauthorized access, interfere with service operation, or use the service in violation of law or these terms.</p>
  </section>

  <section class="ge-terms-section" id="medical">
    <p class="ge-terms-eyebrow">Medical limits</p>
    <h2>No medical advice</h2>
    <p>Gaia Eyes is observational and informational. Seek professional care for urgent or medically important concerns.</p>
  </section>

  <section class="ge-terms-section" id="contact">
    <p class="ge-terms-eyebrow">Contact</p>
    <h2>Questions</h2>
    <p>If you have questions about these Terms of Use, contact <a href="mailto:help@gaiaeyes.com">help@gaiaeyes.com</a>.</p>
  </section>
</div>
HTML;
    }
}

if (!function_exists('gaiaeyes_terms_of_use_html')) {
    function gaiaeyes_terms_of_use_html() {
        static $cached = null;
        if ($cached !== null) {
            return $cached;
        }

        $path = gaiaeyes_terms_of_use_path();
        if (file_exists($path)) {
            $raw = file_get_contents($path);
            $cached = is_string($raw) && trim($raw) !== '' ? $raw : gaiaeyes_terms_of_use_fallback_html();
        } else {
            $cached = gaiaeyes_terms_of_use_fallback_html();
        }
        return $cached;
    }
}

if (!function_exists('gaiaeyes_terms_url')) {
    function gaiaeyes_terms_url($anchor = '') {
        $base = home_url('/terms/');
        if (!$anchor) {
            return $base;
        }
        return $base . '#' . rawurlencode($anchor);
    }
}

if (!function_exists('gaiaeyes_is_terms_request')) {
    function gaiaeyes_is_terms_request() {
        $path = isset($_SERVER['REQUEST_URI']) ? (string) parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) : '';
        $segments = array_values(array_filter(explode('/', trim($path, '/'))));
        if (empty($segments)) {
            return false;
        }
        $last = end($segments);
        return in_array($last, ['terms', 'terms-of-use', 'eula'], true);
    }
}

if (!function_exists('gaiaeyes_render_terms_of_use')) {
    function gaiaeyes_render_terms_of_use() {
        $html = gaiaeyes_terms_of_use_html();
        if ($html === '') {
            return '<section class="ge-terms-of-use"><p>Terms of Use content is not available yet.</p></section>';
        }

        $privacy_url = home_url('/privacy/');
        $support_url = home_url('/support/');

        ob_start();
        ?>
        <section class="ge-terms-of-use">
            <style>
                .ge-terms-of-use { color: #eef5f2; }
                .ge-terms-shell { display: grid; gap: 18px; }
                .ge-terms-hero,
                .ge-terms-nav,
                .ge-terms-body {
                    background: linear-gradient(135deg, rgba(16, 40, 35, 0.96), rgba(9, 15, 13, 0.98));
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 22px;
                    padding: 22px;
                    box-shadow: 0 16px 36px rgba(0,0,0,0.18);
                }
                .ge-terms-hero h1,
                .ge-terms-content h1,
                .ge-terms-content h2,
                .ge-terms-content h3 {
                    color: #ffffff;
                    margin-top: 0;
                }
                .ge-terms-hero p,
                .ge-terms-nav p,
                .ge-terms-content p,
                .ge-terms-content li {
                    color: rgba(255,255,255,0.84);
                }
                .ge-terms-chip-row,
                .ge-terms-actions,
                .ge-terms-link-grid {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }
                .ge-terms-chip,
                .ge-terms-link {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    text-decoration: none;
                    border-radius: 999px;
                    padding: 10px 14px;
                    font-weight: 600;
                }
                .ge-terms-chip {
                    background: rgba(255,255,255,0.08);
                    color: #ffffff;
                }
                .ge-terms-link {
                    background: #2cc6a0;
                    color: #06211b;
                }
                .ge-terms-link--quiet {
                    background: rgba(255,255,255,0.08);
                    color: #f3faf7;
                    border: 1px solid rgba(255,255,255,0.08);
                }
                .ge-terms-link-grid a {
                    flex: 1 1 220px;
                    min-width: 220px;
                    padding: 18px;
                    text-decoration: none;
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 18px;
                    color: #ffffff;
                }
                .ge-terms-link-grid strong {
                    display: block;
                    margin-bottom: 6px;
                    font-size: 1rem;
                }
                .ge-terms-content {
                    display: grid;
                    gap: 18px;
                }
                .ge-terms-section + .ge-terms-section {
                    padding-top: 14px;
                    border-top: 1px solid rgba(255,255,255,0.08);
                }
                .ge-terms-eyebrow {
                    font-size: 0.72rem;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: rgba(255,255,255,0.5);
                    margin-bottom: 8px;
                }
                .ge-terms-content ul {
                    margin: 10px 0 0 18px;
                }
                .ge-terms-content a {
                    color: #9ee9d6;
                }
                @media (max-width: 700px) {
                    .ge-terms-hero,
                    .ge-terms-nav,
                    .ge-terms-body {
                        padding: 18px;
                    }
                }
            </style>
            <div class="ge-terms-shell">
                <header class="ge-terms-hero">
                    <p class="ge-terms-eyebrow">Legal</p>
                    <h1>Gaia Eyes Terms of Use</h1>
                    <p>This public page covers Gaia Eyes account use, subscriptions, acceptable use, app-store billing boundaries, disclaimers, and other core terms for the app and website.</p>
                    <div class="ge-terms-chip-row">
                        <span class="ge-terms-chip">public terms URL</span>
                        <span class="ge-terms-chip">app + website</span>
                        <span class="ge-terms-chip">patterns, not diagnosis</span>
                        <span class="ge-terms-chip">App Store billing note</span>
                    </div>
                    <div class="ge-terms-actions">
                        <a class="ge-terms-link" href="<?php echo esc_url($support_url); ?>">Open Support Center</a>
                        <a class="ge-terms-link ge-terms-link--quiet" href="<?php echo esc_url($privacy_url); ?>">Privacy Policy</a>
                        <a class="ge-terms-link ge-terms-link--quiet" href="mailto:help@gaiaeyes.com?subject=Terms%20Question">Contact Support</a>
                    </div>
                </header>

                <nav class="ge-terms-nav" aria-label="Terms quick links">
                    <p class="ge-terms-eyebrow">Quick links</p>
                    <div class="ge-terms-link-grid">
                        <a href="<?php echo esc_url(gaiaeyes_terms_url('subscriptions')); ?>"><strong>Subscriptions</strong><span>Billing, renewals, and the App Store cancellation boundary.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_terms_url('medical')); ?>"><strong>No medical advice</strong><span>Gaia Eyes is observational and informational, not a clinical tool.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_terms_url('termination')); ?>"><strong>Account deletion</strong><span>How account deletion and retained records are handled.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_terms_url('contact')); ?>"><strong>Contact</strong><span>Use help@gaiaeyes.com for support or legal questions.</span></a>
                    </div>
                </nav>

                <section class="ge-terms-body">
                    <?php echo wp_kses_post($html); ?>
                </section>
            </div>
        </section>
        <?php
        return ob_get_clean();
    }
}

add_shortcode('gaia_terms_of_use', function () {
    return gaiaeyes_render_terms_of_use();
});

add_action('template_redirect', function () {
    if (is_admin() || !gaiaeyes_is_terms_request()) {
        return;
    }

    global $wp_query;
    if ($wp_query) {
        $wp_query->is_404 = false;
    }

    status_header(200);

    add_filter('document_title_parts', function ($parts) {
        if (is_array($parts)) {
            $parts['title'] = 'Terms of Use';
        }
        return $parts;
    });

    get_header();
    echo '<main class="ge-terms-page"><div class="ge-terms-page__inner">';
    echo do_shortcode('[gaia_terms_of_use]');
    echo '</div></main>';
    get_footer();
    exit;
});
