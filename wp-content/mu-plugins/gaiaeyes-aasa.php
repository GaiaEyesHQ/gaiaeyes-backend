<?php
/**
 * Plugin Name: Gaia Eyes — AASA (Apple App Site Association)
 * Description: Serves the AASA JSON for iOS Universal Links at /apple-app-site-association and /.well-known/apple-app-site-association.
 * Version: 1.0
 */

if (!defined('ABSPATH')) exit;

add_action('init', function () {
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);

    // Serve AASA at both canonical endpoints (no .json extension)
    if ($path === '/apple-app-site-association' || $path === '/.well-known/apple-app-site-association') {
        // Set these in wp-config.php (recommended):
        //   define('GAIA_IOS_TEAM_ID', 'ABCDE12345');
        //   define('GAIA_IOS_BUNDLE_ID', 'com.gaiaexporter');
        $team   = defined('GAIA_IOS_TEAM_ID')   ? GAIA_IOS_TEAM_ID   : 'YOUR_TEAM_ID';
        $bundle = defined('GAIA_IOS_BUNDLE_ID') ? GAIA_IOS_BUNDLE_ID : 'com.gaiaexporter';

        // Paths the app will claim (add more if you need)
        $paths = apply_filters('gaia_aasa_paths', [
            '/app-login/*',
        ]);

        $payload = [
            'applinks' => [
                'apps'    => [],
                'details' => [
                    [
                        'appID' => $team . '.' . $bundle,
                        'paths' => array_values($paths),
                    ],
                ],
            ],
        ];

        // Send correct headers; avoid WP wrappers so no extra output leaks
        nocache_headers();
        header('Content-Type: application/json');
        echo wp_json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        exit;
    }
});