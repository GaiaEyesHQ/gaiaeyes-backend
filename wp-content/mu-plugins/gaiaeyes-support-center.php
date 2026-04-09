<?php
/*
Plugin Name: Gaia Eyes - Support Center
Description: Public /support page and shortcode powered by the shared Help Center JSON.
Version: 0.1
*/

if (!function_exists('gaiaeyes_help_center_json_path')) {
    function gaiaeyes_help_center_json_path() {
        return dirname(__DIR__, 2) . '/gaiaeyes-ios/ios/GaiaExporter/Resources/HelpCenterContent.json';
    }
}

if (!function_exists('gaiaeyes_help_center_data')) {
    function gaiaeyes_help_center_data() {
        static $cached = null;
        if ($cached !== null) {
            return $cached;
        }

        $path = gaiaeyes_help_center_json_path();
        if (!file_exists($path)) {
            $cached = [];
            return $cached;
        }

        $raw = file_get_contents($path);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        $cached = is_array($decoded) ? $decoded : [];
        return $cached;
    }
}

if (!function_exists('gaiaeyes_support_url')) {
    function gaiaeyes_support_url($anchor = '') {
        $base = home_url('/support/');
        if (!$anchor) {
            return $base;
        }
        return $base . '#' . rawurlencode($anchor);
    }
}

if (!function_exists('gaiaeyes_support_link_href')) {
    function gaiaeyes_support_link_href($link) {
        $kind = isset($link['kind']) ? strtolower((string) $link['kind']) : '';
        $target = isset($link['target']) ? (string) $link['target'] : '';
        if ($kind === 'article' || $kind === 'category') {
            return gaiaeyes_support_url($target);
        }
        return $target;
    }
}

if (!function_exists('gaiaeyes_support_articles_by_category')) {
    function gaiaeyes_support_articles_by_category($articles) {
        $grouped = [];
        foreach ((array) $articles as $article) {
            $category = isset($article['category']) ? (string) $article['category'] : '';
            if ($category === '') {
                continue;
            }
            if (!isset($grouped[$category])) {
                $grouped[$category] = [];
            }
            $grouped[$category][] = $article;
        }
        return $grouped;
    }
}

if (!function_exists('gaiaeyes_support_lower')) {
    function gaiaeyes_support_lower($value) {
        $value = (string) $value;
        if (function_exists('mb_strtolower')) {
            return mb_strtolower($value);
        }
        return strtolower($value);
    }
}

if (!function_exists('gaiaeyes_support_article_search_blob')) {
    function gaiaeyes_support_article_search_blob($article) {
        $parts = [];
        $parts[] = (string) ($article['title'] ?? '');
        $parts[] = (string) ($article['summary'] ?? '');
        $parts[] = (string) ($article['category'] ?? '');
        foreach ((array) ($article['keywords'] ?? []) as $keyword) {
            $parts[] = (string) $keyword;
        }
        foreach ((array) ($article['body_sections'] ?? []) as $section) {
            $parts[] = (string) ($section['title'] ?? '');
            foreach ((array) ($section['paragraphs'] ?? []) as $paragraph) {
                $parts[] = (string) $paragraph;
            }
            foreach ((array) ($section['bullets'] ?? []) as $bullet) {
                $parts[] = (string) $bullet;
            }
        }
        return gaiaeyes_support_lower(implode("\n", $parts));
    }
}

if (!function_exists('gaiaeyes_support_filter_articles')) {
    function gaiaeyes_support_filter_articles($articles, $query) {
        $query = trim((string) $query);
        if ($query === '') {
            return array_values((array) $articles);
        }

        $needles = array_values(array_filter(array_map('trim', preg_split('/\s+/', gaiaeyes_support_lower($query)))));
        if (empty($needles)) {
            return array_values((array) $articles);
        }

        $matches = [];
        foreach ((array) $articles as $article) {
            $blob = gaiaeyes_support_article_search_blob($article);
            $hit = true;
            foreach ($needles as $needle) {
                if ($needle === '') {
                    continue;
                }
                if (strpos($blob, $needle) === false) {
                    $hit = false;
                    break;
                }
            }
            if ($hit) {
                $matches[] = $article;
            }
        }
        return $matches;
    }
}

if (!function_exists('gaiaeyes_support_articles_by_ids')) {
    function gaiaeyes_support_articles_by_ids($articles, $ids) {
        $map = [];
        foreach ((array) $articles as $article) {
            $id = isset($article['id']) ? (string) $article['id'] : '';
            if ($id !== '' && !isset($map[$id])) {
                $map[$id] = $article;
            }
        }

        $selected = [];
        foreach ((array) $ids as $id) {
            $id = (string) $id;
            if ($id !== '' && isset($map[$id])) {
                $selected[] = $map[$id];
            }
        }
        return $selected;
    }
}

if (!function_exists('gaiaeyes_support_popular_article_ids')) {
    function gaiaeyes_support_popular_article_ids() {
        return [
            'what-gaia-eyes-does',
            'how-background-health-sync-works',
            'why-signals-update-at-different-speeds',
            'restore-purchases',
            'need-help-with-billing',
            'what-health-data-is-used-for',
            'report-a-bug',
            'no-diagnosis-no-medical-advice',
        ];
    }
}

if (!function_exists('gaiaeyes_render_support_center')) {
    function gaiaeyes_render_support_center() {
        $data = gaiaeyes_help_center_data();
        if (empty($data)) {
            return '<section class="ge-support-center"><p>Support content is not available yet.</p></section>';
        }

        $metadata = isset($data['metadata']) && is_array($data['metadata']) ? $data['metadata'] : [];
        $categories = isset($data['categories']) && is_array($data['categories']) ? $data['categories'] : [];
        $articles = isset($data['articles']) && is_array($data['articles']) ? $data['articles'] : [];
        $search_query = isset($_GET['q']) ? trim(sanitize_text_field(wp_unslash((string) $_GET['q']))) : '';
        $filtered_articles = gaiaeyes_support_filter_articles($articles, $search_query);
        $articles_by_category = gaiaeyes_support_articles_by_category($filtered_articles);
        $visible_categories = array_values(array_filter($categories, function ($category) use ($articles_by_category) {
            $category_id = isset($category['id']) ? (string) $category['id'] : '';
            return $category_id !== '' && !empty($articles_by_category[$category_id]);
        }));
        $popular_articles = gaiaeyes_support_articles_by_ids($articles, gaiaeyes_support_popular_article_ids());
        $support_email = isset($metadata['support_email']) ? (string) $metadata['support_email'] : '';
        $updated_at = isset($metadata['updated_at']) ? (string) $metadata['updated_at'] : '';
        $article_count = count($articles);
        $filtered_count = count($filtered_articles);

        ob_start();
        ?>
        <section class="ge-support-center">
            <style>
                .ge-support-center { color: #eef5f2; }
                .ge-support-shell { display: grid; gap: 18px; }
                .ge-support-hero,
                .ge-support-category,
                .ge-support-article,
                .ge-support-contact {
                    background: linear-gradient(135deg, rgba(16, 40, 35, 0.96), rgba(9, 15, 13, 0.98));
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 22px;
                    padding: 22px;
                    box-shadow: 0 16px 36px rgba(0,0,0,0.18);
                }
                .ge-support-hero h1,
                .ge-support-category h2,
                .ge-support-article h3,
                .ge-support-contact h2 {
                    color: #ffffff;
                    margin-top: 0;
                }
                .ge-support-hero p,
                .ge-support-category p,
                .ge-support-article p,
                .ge-support-contact p,
                .ge-support-article li {
                    color: rgba(255,255,255,0.82);
                }
                .ge-support-chip-row,
                .ge-support-actions,
                .ge-support-category-grid {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }
                .ge-support-search {
                    margin-top: 18px;
                    display: grid;
                    gap: 10px;
                    padding: 16px;
                    border-radius: 18px;
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.08);
                }
                .ge-support-search__row {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    align-items: center;
                }
                .ge-support-search label {
                    font-weight: 700;
                    color: #ffffff;
                }
                .ge-support-search input {
                    flex: 1 1 280px;
                    min-width: 220px;
                    border-radius: 14px;
                    border: 1px solid rgba(255,255,255,0.12);
                    background: rgba(7,13,24,0.65);
                    color: #ffffff;
                    padding: 12px 14px;
                    font-size: 0.98rem;
                }
                .ge-support-search button {
                    border: 0;
                    border-radius: 14px;
                    padding: 12px 16px;
                    background: #2cc6a0;
                    color: #06211b;
                    font-weight: 700;
                    cursor: pointer;
                }
                .ge-support-search small {
                    color: rgba(255,255,255,0.62);
                }
                .ge-support-chip,
                .ge-support-link {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    text-decoration: none;
                    border-radius: 999px;
                    padding: 10px 14px;
                    font-weight: 600;
                }
                .ge-support-chip {
                    background: rgba(255,255,255,0.08);
                    color: #ffffff;
                }
                .ge-support-link {
                    background: #2cc6a0;
                    color: #06211b;
                }
                .ge-support-link--quiet {
                    background: rgba(255,255,255,0.08);
                    color: #f3faf7;
                    border: 1px solid rgba(255,255,255,0.08);
                }
                .ge-support-category-grid a {
                    flex: 1 1 240px;
                    min-width: 220px;
                    padding: 18px;
                    text-decoration: none;
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 18px;
                    color: #ffffff;
                }
                .ge-support-category-grid strong {
                    display: block;
                    margin-bottom: 6px;
                    font-size: 1rem;
                }
                .ge-support-stack { display: grid; gap: 16px; }
                .ge-support-article + .ge-support-article { margin-top: 14px; }
                .ge-support-article__eyebrow {
                    font-size: 0.72rem;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: rgba(255,255,255,0.5);
                    margin-bottom: 8px;
                }
                .ge-support-article__summary {
                    font-size: 1rem;
                    margin-bottom: 16px;
                }
                .ge-support-section + .ge-support-section {
                    margin-top: 14px;
                    padding-top: 14px;
                    border-top: 1px solid rgba(255,255,255,0.08);
                }
                .ge-support-section h4 {
                    margin: 0 0 8px;
                    color: #ffffff;
                }
                .ge-support-section ul {
                    margin: 10px 0 0 18px;
                }
                .ge-support-actions {
                    margin-top: 14px;
                }
                .ge-support-overview-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 12px;
                }
                .ge-support-overview-card {
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 18px;
                    padding: 18px;
                    color: #ffffff;
                    text-decoration: none;
                }
                .ge-support-overview-card strong {
                    display: block;
                    margin-bottom: 8px;
                    font-size: 1rem;
                }
                .ge-support-overview-card span {
                    color: rgba(255,255,255,0.72);
                }
                .ge-support-anchor {
                    scroll-margin-top: 120px;
                }
                @media (max-width: 700px) {
                    .ge-support-hero,
                    .ge-support-category,
                    .ge-support-article,
                    .ge-support-contact {
                        padding: 18px;
                    }
                }
            </style>

            <div class="ge-support-shell">
                <header class="ge-support-hero">
                    <p class="ge-support-article__eyebrow">Support</p>
                    <h1>Gaia Eyes Help Center</h1>
                    <p>Clear answers for Health sync, permissions, billing, privacy, and the basics of how Gaia Eyes works. This page is public, requires no login, and is the right support link to share for app review or customer handoff.</p>
                    <div class="ge-support-chip-row">
                        <span class="ge-support-chip">public support link</span>
                        <span class="ge-support-chip"><?php echo esc_html($article_count); ?> help articles</span>
                        <?php if ($updated_at !== ''): ?>
                            <span class="ge-support-chip">updated <?php echo esc_html($updated_at); ?></span>
                        <?php endif; ?>
                        <span class="ge-support-chip">patterns, not certainties</span>
                        <span class="ge-support-chip">optional Health data</span>
                        <span class="ge-support-chip">user stays in control</span>
                        <span class="ge-support-chip">no diagnosis / no medical advice</span>
                    </div>
                    <div class="ge-support-actions">
                        <?php if ($support_email !== ''): ?>
                            <a class="ge-support-link" href="<?php echo esc_url('mailto:' . $support_email . '?subject=Gaia%20Eyes%20Support'); ?>">Email Support</a>
                        <?php endif; ?>
                        <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(gaiaeyes_support_url('report-a-bug')); ?>">Report a bug</a>
                        <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(gaiaeyes_support_url('health-sync-help')); ?>">Health sync help</a>
                        <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(gaiaeyes_support_url('need-help-with-billing')); ?>">Billing help</a>
                        <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(gaiaeyes_support_url('what-health-data-is-used-for')); ?>">Privacy and Health data</a>
                        <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(home_url('/privacy/')); ?>">Privacy Policy</a>
                    </div>
                    <form class="ge-support-search" method="get" action="<?php echo esc_url(gaiaeyes_support_url()); ?>">
                        <label for="ge-support-search-input">Search the help center</label>
                        <div class="ge-support-search__row">
                            <input
                                id="ge-support-search-input"
                                type="search"
                                name="q"
                                value="<?php echo esc_attr($search_query); ?>"
                                placeholder="Try: sleep sync, restore purchases, billing, privacy"
                            />
                            <button type="submit">Search</button>
                            <?php if ($search_query !== ''): ?>
                                <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url(gaiaeyes_support_url()); ?>">Clear</a>
                            <?php endif; ?>
                        </div>
                        <small>Search across titles, summaries, keywords, and article content.</small>
                    </form>
                </header>

                <section class="ge-support-contact">
                    <h2>Quick contact</h2>
                    <p>If you need a direct handoff right now, use one of the launch-ready email subjects below.</p>
                    <div class="ge-support-actions">
                        <?php if ($support_email !== ''): ?>
                            <a class="ge-support-link" href="<?php echo esc_url('mailto:' . $support_email . '?subject=Bug%20Report'); ?>">Bug Report</a>
                            <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url('mailto:' . $support_email . '?subject=Billing%20Help'); ?>">Billing Help</a>
                            <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url('mailto:' . $support_email . '?subject=Health%20Sync%20Help'); ?>">Health Sync Help</a>
                            <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url('mailto:' . $support_email . '?subject=General%20Feedback'); ?>">General Feedback</a>
                        <?php endif; ?>
                    </div>
                </section>

                <?php if (!empty($popular_articles)): ?>
                    <section class="ge-support-category">
                        <p class="ge-support-article__eyebrow">Popular help</p>
                        <h2>Start with the most common questions</h2>
                        <p>These cover the main app-review and launch-support topics: what Gaia Eyes does, Health sync, billing, privacy, and direct contact.</p>
                        <div class="ge-support-overview-grid">
                            <?php foreach ($popular_articles as $article): ?>
                                <a class="ge-support-overview-card" href="<?php echo esc_url(gaiaeyes_support_url((string) ($article['id'] ?? ''))); ?>">
                                    <strong><?php echo esc_html((string) ($article['title'] ?? 'Support article')); ?></strong>
                                    <span><?php echo esc_html((string) ($article['summary'] ?? '')); ?></span>
                                </a>
                            <?php endforeach; ?>
                        </div>
                    </section>
                <?php endif; ?>

                <?php if ($search_query !== ''): ?>
                    <section class="ge-support-category">
                        <p class="ge-support-article__eyebrow">Search results</p>
                        <h2><?php echo esc_html($filtered_count . ' matching article' . ($filtered_count === 1 ? '' : 's')); ?></h2>
                        <p>
                            Results for
                            <strong><?php echo esc_html($search_query); ?></strong>.
                            <?php if ($filtered_count === 0): ?>
                                Try broader terms like sync, billing, sleep, privacy, or symptoms.
                            <?php endif; ?>
                        </p>
                    </section>
                <?php endif; ?>

                <nav class="ge-support-category-grid" aria-label="Support categories">
                    <?php foreach ($visible_categories as $category): ?>
                        <?php
                        $category_id = isset($category['id']) ? (string) $category['id'] : '';
                        if ($category_id === '') {
                            continue;
                        }
                        ?>
                        <a href="<?php echo esc_url(gaiaeyes_support_url($category_id)); ?>">
                            <strong><?php echo esc_html((string) ($category['title'] ?? 'Support')); ?></strong>
                            <span><?php echo esc_html((string) ($category['summary'] ?? '')); ?></span>
                        </a>
                    <?php endforeach; ?>
                </nav>

                <?php foreach ($visible_categories as $category): ?>
                    <?php
                    $category_id = isset($category['id']) ? (string) $category['id'] : '';
                    if ($category_id === '') {
                        continue;
                    }
                    $category_articles = isset($articles_by_category[$category_id]) ? $articles_by_category[$category_id] : [];
                    if (empty($category_articles)) {
                        continue;
                    }
                    ?>
                    <section id="<?php echo esc_attr($category_id); ?>" class="ge-support-category ge-support-anchor">
                        <p class="ge-support-article__eyebrow"><?php echo esc_html((string) ($category['title'] ?? 'Support')); ?></p>
                        <h2><?php echo esc_html((string) ($category['title'] ?? 'Support')); ?></h2>
                        <p><?php echo esc_html((string) ($category['summary'] ?? '')); ?></p>

                        <div class="ge-support-stack">
                            <?php foreach ($category_articles as $article): ?>
                                <?php $article_id = isset($article['id']) ? (string) $article['id'] : ''; ?>
                                <article id="<?php echo esc_attr($article_id); ?>" class="ge-support-article ge-support-anchor">
                                    <p class="ge-support-article__eyebrow"><?php echo esc_html((string) ($category['title'] ?? 'Support')); ?></p>
                                    <h3><?php echo esc_html((string) ($article['title'] ?? 'Untitled')); ?></h3>
                                    <p class="ge-support-article__summary"><?php echo esc_html((string) ($article['summary'] ?? '')); ?></p>

                                    <?php foreach ((array) ($article['body_sections'] ?? []) as $section): ?>
                                        <div class="ge-support-section">
                                            <h4><?php echo esc_html((string) ($section['title'] ?? '')); ?></h4>
                                            <?php foreach ((array) ($section['paragraphs'] ?? []) as $paragraph): ?>
                                                <p><?php echo esc_html((string) $paragraph); ?></p>
                                            <?php endforeach; ?>
                                            <?php $bullets = (array) ($section['bullets'] ?? []); ?>
                                            <?php if (!empty($bullets)): ?>
                                                <ul>
                                                    <?php foreach ($bullets as $bullet): ?>
                                                        <li><?php echo esc_html((string) $bullet); ?></li>
                                                    <?php endforeach; ?>
                                                </ul>
                                            <?php endif; ?>
                                        </div>
                                    <?php endforeach; ?>

                                    <?php $links = (array) ($article['links'] ?? []); ?>
                                    <?php if (!empty($links)): ?>
                                        <div class="ge-support-actions">
                                            <?php foreach ($links as $link): ?>
                                                <?php
                                                $href = gaiaeyes_support_link_href($link);
                                                if ($href === '') {
                                                    continue;
                                                }
                                                ?>
                                                <a class="ge-support-link ge-support-link--quiet" href="<?php echo esc_url($href); ?>">
                                                    <?php echo esc_html((string) ($link['label'] ?? 'Open')); ?>
                                                </a>
                                            <?php endforeach; ?>
                                        </div>
                                    <?php endif; ?>
                                </article>
                            <?php endforeach; ?>
                        </div>
                    </section>
                <?php endforeach; ?>
            </div>
        </section>
        <?php
        return ob_get_clean();
    }
}

add_shortcode('gaia_support_center', function () {
    return gaiaeyes_render_support_center();
});

if (!function_exists('gaiaeyes_is_support_request')) {
    function gaiaeyes_is_support_request() {
        $path = isset($_SERVER['REQUEST_URI']) ? (string) parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) : '';
        $segments = array_values(array_filter(explode('/', trim($path, '/'))));
        if (empty($segments)) {
            return false;
        }
        return end($segments) === 'support';
    }
}

add_action('template_redirect', function () {
    if (is_admin() || !gaiaeyes_is_support_request()) {
        return;
    }

    global $wp_query;
    if ($wp_query) {
        $wp_query->is_404 = false;
    }

    status_header(200);

    add_filter('document_title_parts', function ($parts) {
        if (is_array($parts)) {
            $parts['title'] = 'Support';
        }
        return $parts;
    });

    get_header();
    echo '<main class="ge-support-page"><div class="ge-support-page__inner">';
    echo do_shortcode('[gaia_support_center]');
    echo '</div></main>';
    get_footer();
    exit;
});

add_action('wp_footer', function () {
    if (is_admin() || gaiaeyes_is_support_request()) {
        return;
    }
    ?>
    <div class="ge-support-footer-link" style="text-align:center;padding:0 0 18px;font-size:13px;">
        <a href="<?php echo esc_url(gaiaeyes_support_url()); ?>" style="color:#2cc6a0;text-decoration:none;font-weight:600;">Support</a>
    </div>
    <?php
}, 99);
