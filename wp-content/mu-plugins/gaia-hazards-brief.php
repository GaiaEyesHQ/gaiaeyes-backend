<?php
/**
 * Plugin Name: Gaia Eyes – Hazards Brief
 * Description: Shows a compact Global Hazards brief on the homepage, sourced from latest.json. Also provides [gaia_hazards_brief] shortcode.
 * Author: Gaia Eyes
 * Version: 0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Shortcode: [gaia_hazards_brief url="https://.../public/hazards/latest.json" cache="5"]
 * - Fetches hazards/latest.json (48h snapshot created by the bot)
 * - Renders a concise summary and links to the latest “Hazards Digest” post
 */
function gaia_hazards_brief_shortcode( $atts = [] ) {
    $atts = shortcode_atts(
        [
            'url'   => 'https://gaiaeyeshq.github.io/gaiaeyes-media/public/hazards/latest.json',
            'cache' => 5, // minutes.
        ],
        $atts,
        'gaia_hazards_brief'
    );

    $ttl = max( 1, intval( $atts['cache'] ) ) * MINUTE_IN_SECONDS;

    $get_json = function ( $url ) use ( $ttl ) {
        $key    = 'gaia_hazards_latest_' . md5( $url );
        $cached = get_transient( $key );
        if ( false !== $cached ) {
            return $cached;
        }

        $response = wp_remote_get(
            esc_url_raw( $url ),
            [
                'timeout' => 10,
                'headers' => [ 'Accept' => 'application/json' ],
            ]
        );

        if ( is_wp_error( $response ) || 200 !== wp_remote_retrieve_response_code( $response ) ) {
            return null;
        }

        $body = json_decode( wp_remote_retrieve_body( $response ), true );
        if ( is_array( $body ) ) {
            set_transient( $key, $body, $ttl );
            return $body;
        }

        return null;
    };

    $data = $get_json( $atts['url'] );
    if ( ! is_array( $data ) ) {
        return '<section class="gaia-hazards-brief"><div class="ghb-card">Global Hazards: unavailable</div></section>';
    }

    $items = isset( $data['items'] ) && is_array( $data['items'] ) ? $data['items'] : [];
    $gen   = isset( $data['generated_at'] ) ? $data['generated_at'] : '';

    $severity_counts = [
        'red'    => 0,
        'orange' => 0,
        'yellow' => 0,
        'info'   => 0,
    ];
    $type_counts     = [
        'quake'   => 0,
        'cyclone' => 0,
        'ash'     => 0,
        'other'   => 0,
    ];
    $top              = [];

    foreach ( $items as $item ) {
        $severity = isset( $item['severity'] ) ? strtolower( (string) $item['severity'] ) : 'info';
        if ( isset( $severity_counts[ $severity ] ) ) {
            $severity_counts[ $severity ]++;
        }

        $type = isset( $item['type'] ) ? strtolower( (string) $item['type'] ) : 'other';
        if ( isset( $type_counts[ $type ] ) ) {
            $type_counts[ $type ]++;
        }

        $top[] = [
            'sev'   => $severity,
            'type'  => $type,
            'title' => isset( $item['title'] ) ? (string) $item['title'] : '',
            'ts'    => isset( $item['ts'] ) ? (string) $item['ts'] : '',
        ];
    }

    usort(
        $top,
        function ( $a, $b ) {
            $rank = [ 'red' => 3, 'orange' => 2, 'yellow' => 1, 'info' => 0 ];
            $ra   = isset( $rank[ $a['sev'] ] ) ? $rank[ $a['sev'] ] : 0;
            $rb   = isset( $rank[ $b['sev'] ] ) ? $rank[ $b['sev'] ] : 0;

            if ( $ra === $rb ) {
                return strcmp( $b['ts'], $a['ts'] );
            }

            return $rb - $ra;
        }
    );

    $top = array_slice( $top, 0, 5 );

    $digest_link = '';
    $digest_cat  = get_category_by_slug( 'hazards-digest' );
    if ( $digest_cat && isset( $digest_cat->term_id ) ) {
        $digest_posts = get_posts(
            [
                'numberposts' => 1,
                'category'    => $digest_cat->term_id,
                'post_status' => 'publish',
                'orderby'     => 'date',
                'order'       => 'DESC',
            ]
        );

        if ( $digest_posts ) {
            $digest_link = get_permalink( $digest_posts[0] );
        }
    }

    ob_start();
    ?>
    <section class="gaia-hazards-brief">
        <header class="ghb-head">
            <h3 class="ghb-title">Global Hazards Brief</h3>
            <?php if ( $gen ) : ?>
                <time class="ghb-time" datetime="<?php echo esc_attr( $gen ); ?>">
                    Updated <?php echo esc_html( gmdate( 'D, d M Y H:i', strtotime( $gen ) ) ); ?> UTC
                </time>
            <?php endif; ?>
        </header>

        <div class="ghb-row">
            <div class="ghb-card">
                <div class="ghb-label">Severity (48h)</div>
                <ul class="ghb-stats">
                    <li class="sev sev-red">RED: <strong><?php echo intval( $severity_counts['red'] ); ?></strong></li>
                    <li class="sev sev-orange">ORANGE: <strong><?php echo intval( $severity_counts['orange'] ); ?></strong></li>
                    <li class="sev sev-yellow">YELLOW: <strong><?php echo intval( $severity_counts['yellow'] ); ?></strong></li>
                    <li class="sev sev-info">INFO: <strong><?php echo intval( $severity_counts['info'] ); ?></strong></li>
                </ul>
            </div>

            <div class="ghb-card">
                <div class="ghb-label">By Type (48h)</div>
                <ul class="ghb-stats">
                    <li>Earthquakes: <strong><?php echo intval( $type_counts['quake'] ); ?></strong></li>
                    <li>Cyclones/Severe: <strong><?php echo intval( $type_counts['cyclone'] ); ?></strong></li>
                    <li>Volcano/Ash: <strong><?php echo intval( $type_counts['ash'] ); ?></strong></li>
                    <li>Other: <strong><?php echo intval( $type_counts['other'] ); ?></strong></li>
                </ul>
            </div>

            <div class="ghb-card">
                <div class="ghb-label">Recent Highlights</div>
                <ul class="ghb-top">
                    <?php foreach ( $top as $highlight ) :
                        $sev_label  = strtoupper( $highlight['sev'] );
                        $headline   = $highlight['title'] ? $highlight['title'] : ucfirst( $highlight['type'] ) . ' update';
                        $time_label = $highlight['ts'] ? gmdate( 'd M H:i', strtotime( $highlight['ts'] ) ) . 'Z' : '';
                        ?>
                        <li class="sev-<?php echo esc_attr( $highlight['sev'] ); ?>">
                            <span class="badge"><?php echo esc_html( $sev_label ); ?></span>
                            <span class="txt"><?php echo esc_html( $headline ); ?></span>
                            <?php if ( $time_label ) : ?>
                                <span class="when"><?php echo esc_html( $time_label ); ?></span>
                            <?php endif; ?>
                        </li>
                    <?php endforeach; ?>
                </ul>

                <?php if ( $digest_link ) : ?>
                    <div class="ghb-more"><a class="ghb-link" href="<?php echo esc_url( $digest_link ); ?>">Full details → Hazards Digest</a></div>
                <?php endif; ?>
            </div>
        </div>

        <style>
            .gaia-hazards-brief { border-radius: 14px; padding: 14px; background: #101015; color: #eee; }
            .ghb-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
            .ghb-title { margin: 0; font-size: 1.05rem; }
            .ghb-time { opacity: .8; font-size: .9rem; }
            .ghb-row { display: grid; gap: 12px; }
            @media (min-width: 768px) { .ghb-row { grid-template-columns: repeat(3, 1fr); } }
            .ghb-card { background: #151827; border: 1px solid rgba(255,255,255,.06); border-radius: 12px; padding: 12px; }
            .ghb-label { font-size: .9rem; opacity: .85; margin-bottom: 6px; }
            .ghb-stats { margin: 0; padding-left: 18px; line-height: 1.4; }
            .ghb-top { margin: 0; padding-left: 0; list-style: none; }
            .ghb-top li { display: flex; gap: 8px; align-items: center; margin: 6px 0; }
            .badge { font-size: .72rem; border-radius: 999px; padding: 2px 8px; background: #222; color: #ddd; border: 1px solid #333; }
            .sev-red .badge { background: #5a1a1a; color: #ffd2d2; border-color: #8e2a2a; }
            .sev-orange .badge { background: #3f2d12; color: #ffd089; border-color: #8a5a1a; }
            .sev-yellow .badge { background: #2c3515; color: #d2f59a; border-color: #516b1f; }
            .sev-info .badge { background: #22304a; color: #bbd7ff; border-color: #35537c; }
            .when { opacity: .75; font-size: .82rem; margin-left: auto; }
            .ghb-more { margin-top: 8px; }
            .ghb-link { color: #bcd5ff; text-decoration: none; border-bottom: 1px dashed #4b6aa1; }
            .ghb-link:hover { border-bottom-color: #bcd5ff; }
        </style>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode( 'gaia_hazards_brief', 'gaia_hazards_brief_shortcode' );

/**
 * Auto-inject hazards brief on the homepage unless already present or in admin.
 */
add_filter(
    'the_content',
    function ( $content ) {
        if ( is_admin() || ! in_the_loop() || ! is_main_query() ) {
            return $content;
        }

        if ( ! function_exists( 'is_front_page' ) || ! is_front_page() ) {
            return $content;
        }

        if ( function_exists( 'has_shortcode' ) && has_shortcode( $content, 'gaia_hazards_brief' ) ) {
            return $content;
        }

        return do_shortcode( '[gaia_hazards_brief]' ) . $content;
    }
);
