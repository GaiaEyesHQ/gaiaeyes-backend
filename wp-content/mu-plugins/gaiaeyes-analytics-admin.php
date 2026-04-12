<?php
/*
Plugin Name: Gaia Eyes Analytics Admin
Description: Internal WordPress Tools report for Gaia Eyes app analytics.
Version: 0.1.0
*/

if (!defined('ABSPATH')) {
    exit;
}

if (!function_exists('gaiaeyes_analytics_backend_base')) {
function gaiaeyes_analytics_backend_base() {
    $backend_base = defined('GAIAEYES_API_BASE') ? GAIAEYES_API_BASE : getenv('GAIAEYES_API_BASE');
    return $backend_base ? rtrim((string) $backend_base, '/') : '';
}
}

if (!function_exists('gaiaeyes_analytics_admin_bearer')) {
function gaiaeyes_analytics_admin_bearer() {
    $candidates = [
        defined('GAIAEYES_API_ADMIN_BEARER') ? GAIAEYES_API_ADMIN_BEARER : getenv('GAIAEYES_API_ADMIN_BEARER'),
        defined('GAIAEYES_ADMIN_BEARER') ? GAIAEYES_ADMIN_BEARER : getenv('GAIAEYES_ADMIN_BEARER'),
        getenv('ADMIN_TOKEN'),
        defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : getenv('GAIAEYES_API_BEARER'),
    ];
    foreach ($candidates as $candidate) {
        if (is_string($candidate) && trim($candidate) !== '') {
            return trim($candidate);
        }
    }
    return '';
}
}

if (!function_exists('gaiaeyes_analytics_report_range')) {
function gaiaeyes_analytics_report_range() {
    $preset = isset($_GET['gaia_range']) ? sanitize_key((string) wp_unslash($_GET['gaia_range'])) : '7d';
    $now = current_time('timestamp');
    $today = wp_date('Y-m-d', $now);

    switch ($preset) {
        case 'today':
            return [$today, $today, 'Today'];
        case 'yesterday':
            $day = wp_date('Y-m-d', $now - DAY_IN_SECONDS);
            return [$day, $day, 'Yesterday'];
        case '30d':
            return [wp_date('Y-m-d', $now - (29 * DAY_IN_SECONDS)), $today, 'Last 30 days'];
        case 'custom':
            $from = isset($_GET['from']) ? sanitize_text_field((string) wp_unslash($_GET['from'])) : $today;
            $to = isset($_GET['to']) ? sanitize_text_field((string) wp_unslash($_GET['to'])) : $today;
            if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $from)) {
                $from = $today;
            }
            if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $to)) {
                $to = $today;
            }
            return [$from, $to, 'Custom range'];
        case '7d':
        default:
            return [wp_date('Y-m-d', $now - (6 * DAY_IN_SECONDS)), $today, 'Last 7 days'];
    }
}
}

if (!function_exists('gaiaeyes_analytics_fetch_summary')) {
function gaiaeyes_analytics_fetch_summary($from, $to) {
    $backend_base = gaiaeyes_analytics_backend_base();
    $bearer = gaiaeyes_analytics_admin_bearer();

    if ($backend_base === '') {
        return new WP_Error('gaiaeyes_analytics_backend_missing', 'GAIAEYES_API_BASE is not configured.');
    }
    if ($bearer === '') {
        return new WP_Error('gaiaeyes_analytics_bearer_missing', 'GAIAEYES_API_ADMIN_BEARER, GAIAEYES_ADMIN_BEARER, ADMIN_TOKEN, or GAIAEYES_API_BEARER is not configured.');
    }

    $tz = wp_timezone_string();
    if (!$tz) {
        $tz = 'America/Chicago';
    }
    $url = add_query_arg(
        [
            'from' => $from,
            'to' => $to,
            'tz' => $tz,
        ],
        $backend_base . '/v1/admin/analytics/summary'
    );

    $resp = wp_remote_get($url, [
        'timeout' => 25,
        'headers' => [
            'Accept' => 'application/json',
            'Authorization' => 'Bearer ' . $bearer,
        ],
    ]);
    if (is_wp_error($resp)) {
        return $resp;
    }

    $status = (int) wp_remote_retrieve_response_code($resp);
    $body = (string) wp_remote_retrieve_body($resp);
    $decoded = json_decode($body, true);
    if (!is_array($decoded)) {
        return new WP_Error('gaiaeyes_analytics_invalid_json', 'Analytics endpoint returned invalid JSON.');
    }
    if ($status < 200 || $status >= 300 || empty($decoded['ok'])) {
        $message = isset($decoded['error']) && is_string($decoded['error']) ? $decoded['error'] : 'Analytics fetch failed.';
        return new WP_Error('gaiaeyes_analytics_fetch_failed', $message);
    }
    return $decoded;
}
}

if (!function_exists('gaiaeyes_analytics_count')) {
function gaiaeyes_analytics_count($value) {
    return number_format_i18n((int) ($value ?? 0));
}
}

if (!function_exists('gaiaeyes_analytics_event_count')) {
function gaiaeyes_analytics_event_count($rows, $event_name) {
    if (!is_array($rows)) {
        return 0;
    }
    foreach ($rows as $row) {
        if (isset($row['event_name']) && (string) $row['event_name'] === $event_name) {
            return (int) ($row['events'] ?? 0);
        }
    }
    return 0;
}
}

if (!function_exists('gaiaeyes_analytics_render_metric')) {
function gaiaeyes_analytics_render_metric($label, $value, $detail = '') {
    ?>
    <div class="gaia-analytics-card">
        <strong><?php echo esc_html($label); ?></strong>
        <span><?php echo esc_html(gaiaeyes_analytics_count($value)); ?></span>
        <?php if ($detail !== ''): ?>
            <small><?php echo esc_html($detail); ?></small>
        <?php endif; ?>
    </div>
    <?php
}
}

if (!function_exists('gaiaeyes_analytics_render_table')) {
function gaiaeyes_analytics_render_table($title, $rows, $empty_message = 'No events in this range.') {
    ?>
    <section class="gaia-analytics-panel">
        <h2><?php echo esc_html($title); ?></h2>
        <?php if (empty($rows) || !is_array($rows)): ?>
            <p class="gaia-analytics-muted"><?php echo esc_html($empty_message); ?></p>
        <?php else: ?>
            <table class="widefat striped">
                <thead>
                    <tr>
                        <th>Event</th>
                        <th>Events</th>
                        <th>Users</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row): ?>
                        <tr>
                            <td><code><?php echo esc_html((string) ($row['event_name'] ?? '')); ?></code></td>
                            <td><?php echo esc_html(gaiaeyes_analytics_count($row['events'] ?? 0)); ?></td>
                            <td><?php echo esc_html(gaiaeyes_analytics_count($row['users'] ?? 0)); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </section>
    <?php
}
}

if (!function_exists('gaiaeyes_analytics_render_daily_table')) {
function gaiaeyes_analytics_render_daily_table($rows) {
    ?>
    <section class="gaia-analytics-panel">
        <h2>Daily Trend</h2>
        <?php if (empty($rows) || !is_array($rows)): ?>
            <p class="gaia-analytics-muted">No daily analytics rows in this range.</p>
        <?php else: ?>
            <table class="widefat striped">
                <thead>
                    <tr>
                        <th>Day</th>
                        <th>Events</th>
                        <th>Users</th>
                        <th>Sessions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row): ?>
                        <tr>
                            <td><?php echo esc_html((string) ($row['day'] ?? '')); ?></td>
                            <td><?php echo esc_html(gaiaeyes_analytics_count($row['events'] ?? 0)); ?></td>
                            <td><?php echo esc_html(gaiaeyes_analytics_count($row['users'] ?? 0)); ?></td>
                            <td><?php echo esc_html(gaiaeyes_analytics_count($row['sessions'] ?? 0)); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </section>
    <?php
}
}

if (!function_exists('gaiaeyes_analytics_render_admin_page')) {
function gaiaeyes_analytics_render_admin_page() {
    if (!current_user_can('manage_options')) {
        wp_die('You do not have permission to view this page.');
    }

    [$from, $to, $label] = gaiaeyes_analytics_report_range();
    $summary = gaiaeyes_analytics_fetch_summary($from, $to);
    $selected_range = isset($_GET['gaia_range']) ? sanitize_key((string) wp_unslash($_GET['gaia_range'])) : '7d';
    $totals = is_array($summary) ? ($summary['totals'] ?? []) : [];
    $current = is_array($summary) ? ($summary['current'] ?? []) : [];
    $lifetime = is_array($summary) ? ($summary['lifetime'] ?? []) : [];
    $onboarding = is_array($summary) ? ($summary['onboarding'] ?? []) : [];
    $health_sync = is_array($summary) ? ($summary['health_sync'] ?? []) : [];
    $engagement = is_array($summary) ? ($summary['engagement'] ?? []) : [];
    $feature_adoption = is_array($summary) ? ($summary['feature_adoption'] ?? []) : [];
    ?>
    <div class="wrap">
        <h1>Gaia Analytics</h1>
        <p>Internal app analytics from the backend event store. Counts are aggregate and intentionally avoid raw health details.</p>

        <style>
            .gaia-analytics-form{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin:16px 0;padding:14px;background:#fff;border:1px solid #dcdcde;border-radius:12px}
            .gaia-analytics-form label{display:flex;flex-direction:column;gap:4px;font-weight:600}
            .gaia-analytics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}
            .gaia-analytics-card{background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:14px}
            .gaia-analytics-card strong{display:block;color:#50575e;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
            .gaia-analytics-card span{display:block;font-size:28px;font-weight:700;margin-top:6px;color:#1d2327}
            .gaia-analytics-card small{display:block;margin-top:4px;color:#646970}
            .gaia-analytics-panels{display:grid;grid-template-columns:1fr;gap:16px;max-width:1200px}
            @media (min-width:1100px){.gaia-analytics-panels{grid-template-columns:1fr 1fr}}
            .gaia-analytics-panel{background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:16px}
            .gaia-analytics-panel h2{margin-top:0}
            .gaia-analytics-muted{color:#646970}
            .gaia-analytics-error{padding:16px;background:#fff1f0;border:1px solid #f0c0bb;border-radius:12px;color:#8a2424}
        </style>

        <form class="gaia-analytics-form" method="get" action="">
            <input type="hidden" name="page" value="gaia-analytics">
            <label>
                Range
                <select name="gaia_range">
                    <option value="today" <?php selected($selected_range, 'today'); ?>>Today</option>
                    <option value="yesterday" <?php selected($selected_range, 'yesterday'); ?>>Yesterday</option>
                    <option value="7d" <?php selected($selected_range, '7d'); ?>>Last 7 days</option>
                    <option value="30d" <?php selected($selected_range, '30d'); ?>>Last 30 days</option>
                    <option value="custom" <?php selected($selected_range, 'custom'); ?>>Custom</option>
                </select>
            </label>
            <label>
                From
                <input type="date" name="from" value="<?php echo esc_attr($from); ?>">
            </label>
            <label>
                To
                <input type="date" name="to" value="<?php echo esc_attr($to); ?>">
            </label>
            <?php submit_button('Refresh', 'primary', '', false); ?>
        </form>

        <?php if (is_wp_error($summary)): ?>
            <div class="gaia-analytics-error">
                <strong>Could not load analytics.</strong>
                <p><?php echo esc_html($summary->get_error_message()); ?></p>
            </div>
        <?php else: ?>
            <h2><?php echo esc_html($label); ?>: <?php echo esc_html($from); ?> to <?php echo esc_html($to); ?></h2>
            <div class="gaia-analytics-grid">
                <?php gaiaeyes_analytics_render_metric('Current 24h events', $current['events'] ?? 0, 'Rolling window'); ?>
                <?php gaiaeyes_analytics_render_metric('Current 24h users', $current['users'] ?? 0); ?>
                <?php gaiaeyes_analytics_render_metric('Events', $totals['events'] ?? 0); ?>
                <?php gaiaeyes_analytics_render_metric('Users', $totals['users'] ?? 0); ?>
                <?php gaiaeyes_analytics_render_metric('Sessions', $totals['sessions'] ?? 0); ?>
                <?php gaiaeyes_analytics_render_metric('All-time events', $lifetime['events'] ?? 0, !empty($lifetime['last_event_at']) ? 'Last event: ' . (string) $lifetime['last_event_at'] : 'No stored events yet'); ?>
                <?php gaiaeyes_analytics_render_metric('Onboarding completed', gaiaeyes_analytics_event_count($onboarding, 'onboarding_completed')); ?>
                <?php gaiaeyes_analytics_render_metric('Health sync completed', gaiaeyes_analytics_event_count($health_sync, 'health_backfill_completed')); ?>
                <?php gaiaeyes_analytics_render_metric('Daily check-ins', gaiaeyes_analytics_event_count($engagement, 'daily_checkin_completed')); ?>
                <?php gaiaeyes_analytics_render_metric('Lunar enabled', gaiaeyes_analytics_event_count($feature_adoption, 'lunar_tracking_enabled')); ?>
                <?php gaiaeyes_analytics_render_metric('Notifications enabled', gaiaeyes_analytics_event_count($feature_adoption, 'notifications_enabled')); ?>
            </div>

            <div class="gaia-analytics-panels">
                <?php gaiaeyes_analytics_render_daily_table($summary['daily'] ?? []); ?>
                <?php gaiaeyes_analytics_render_table('Top Events', $summary['top_events'] ?? []); ?>
                <?php gaiaeyes_analytics_render_table('Onboarding Funnel', $onboarding); ?>
                <?php gaiaeyes_analytics_render_table('Health Sync', $health_sync); ?>
                <?php gaiaeyes_analytics_render_table('Engagement', $engagement); ?>
                <?php gaiaeyes_analytics_render_table('Feature Adoption', $feature_adoption); ?>
                <?php gaiaeyes_analytics_render_table('Errors and Drop-off', $summary['errors'] ?? []); ?>
            </div>
        <?php endif; ?>
    </div>
    <?php
}
}

add_action('admin_menu', function () {
    add_management_page(
        'Gaia Analytics',
        'Gaia Analytics',
        'manage_options',
        'gaia-analytics',
        'gaiaeyes_analytics_render_admin_page'
    );
});
