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

if (!function_exists('gaiaeyes_privacy_policy_html')) {
    function gaiaeyes_privacy_policy_html() {
        static $cached = null;
        if ($cached !== null) {
            return $cached;
        }

        $path = gaiaeyes_privacy_policy_path();
        if (!file_exists($path)) {
            $cached = '';
            return $cached;
        }

        $raw = file_get_contents($path);
        $cached = is_string($raw) ? $raw : '';
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
                    </div>
                </header>

                <nav class="ge-privacy-nav" aria-label="Privacy quick links">
                    <p class="ge-privacy-eyebrow">Quick links</p>
                    <div class="ge-privacy-link-grid">
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('collect')); ?>"><strong>What we collect</strong><span>Account info, app inputs, optional Health data, location, diagnostics, and billing metadata.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('share')); ?>"><strong>How we share data</strong><span>Supabase, Stripe, Apple services, environmental data providers, and core infrastructure partners.</span></a>
                        <a href="<?php echo esc_url(gaiaeyes_privacy_url('choices')); ?>"><strong>Your choices</strong><span>Permissions, settings, support requests, and how to contact us about your data.</span></a>
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
