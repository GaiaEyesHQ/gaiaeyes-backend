<?php
/**
 * Neve functions.php file
 *
 * Author:          Andrei Baicus <andrei@themeisle.com>
 * Created on:      17/08/2018
 *
 * @package Neve
 */

define( 'NEVE_VERSION', '4.1.4' );
define( 'NEVE_INC_DIR', trailingslashit( get_template_directory() ) . 'inc/' );
define( 'NEVE_ASSETS_URL', trailingslashit( get_template_directory_uri() ) . 'assets/' );
define( 'NEVE_MAIN_DIR', get_template_directory() . '/' );
define( 'NEVE_BASENAME', basename( NEVE_MAIN_DIR ) );
define( 'NEVE_PLUGINS_DIR', plugin_dir_path( dirname( __DIR__ ) ) . 'plugins/' );

if ( ! defined( 'NEVE_DEBUG' ) ) {
	define( 'NEVE_DEBUG', false );
}
define( 'NEVE_NEW_DYNAMIC_STYLE', true );
/**
 * Buffer which holds errors during theme inititalization.
 *
 * @var WP_Error $_neve_bootstrap_errors
 */
global $_neve_bootstrap_errors;

$_neve_bootstrap_errors = new WP_Error();

if ( version_compare( PHP_VERSION, '7.0' ) < 0 ) {
	$_neve_bootstrap_errors->add(
		'minimum_php_version',
		sprintf(
			/* translators: %s message to upgrade PHP to the latest version */
			__( "Hey, we've noticed that you're running an outdated version of PHP which is no longer supported. Make sure your site is fast and secure, by %1\$s. Neve's minimal requirement is PHP%2\$s.", 'neve' ),
			sprintf(
				/* translators: %s message to upgrade PHP to the latest version */
				'<a href="https://wordpress.org/support/upgrade-php/">%s</a>',
				__( 'upgrading PHP to the latest version', 'neve' )
			),
			'7.0'
		)
	);
}
/**
 * A list of files to check for existence before bootstrapping.
 *
 * @var non-falsy-string[] Files to check for existence.
 */
$_files_to_check = defined( 'NEVE_IGNORE_SOURCE_CHECK' ) ? [] : [
	NEVE_MAIN_DIR . 'vendor/autoload.php',
	NEVE_MAIN_DIR . 'style-main-new.css',
	NEVE_MAIN_DIR . 'assets/js/build/modern/frontend.js',
	NEVE_MAIN_DIR . 'assets/apps/dashboard/build/dashboard.js',
	NEVE_MAIN_DIR . 'assets/apps/customizer-controls/build/controls.js',
];
foreach ( $_files_to_check as $_file_to_check ) {
	if ( ! is_file( $_file_to_check ) ) {
		$_neve_bootstrap_errors->add(
			'build_missing',
			sprintf(
				/* translators: %s: commands to run the theme */
				__( 'You appear to be running the Neve theme from source code. Please finish installation by running %s.', 'neve' ), // phpcs:ignore WordPress.Security.EscapeOutput
				'<code>composer install --no-dev &amp;&amp; yarn install --frozen-lockfile &amp;&amp; yarn run build</code>'
			)
		);
		break;
	}
}
/**
 * Adds notice bootstraping errors.
 *
 * @internal
 * @global WP_Error $_neve_bootstrap_errors
 */
function _neve_bootstrap_errors() {
	global $_neve_bootstrap_errors;
	printf( '<div class="notice notice-error"><p>%1$s</p></div>', $_neve_bootstrap_errors->get_error_message() ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
}

if ( $_neve_bootstrap_errors->has_errors() ) {
	/**
	 * Add notice for PHP upgrade.
	 */
	add_filter( 'template_include', '__return_null', 99 );
	switch_theme( WP_DEFAULT_THEME );
	unset( $_GET['activated'] ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	add_action( 'admin_notices', '_neve_bootstrap_errors' );

	return;
}

/**
 * Themeisle SDK filter.
 *
 * @param array $products products array.
 *
 * @return array
 */
function neve_filter_sdk( $products ) {
	$products[] = get_template_directory() . '/style.css';

	return $products;
}

add_filter( 'themeisle_sdk_products', 'neve_filter_sdk' );
add_filter(
	'themeisle_sdk_compatibilities/' . NEVE_BASENAME,
	function ( $compatibilities ) {

		$compatibilities['NevePro'] = [
			'basefile'  => defined( 'NEVE_PRO_BASEFILE' ) ? NEVE_PRO_BASEFILE : '',
			'required'  => '2.9',
			'tested_up' => '3.1',
		];

		return $compatibilities;
	}
);
require_once 'globals/migrations.php';
require_once 'globals/utilities.php';
require_once 'globals/hooks.php';
require_once 'globals/sanitize-functions.php';
require_once get_template_directory() . '/start.php';

/**
 * If the new widget editor is available,
 * we re-assign the widgets to hfg_footer
 */
if ( neve_is_new_widget_editor() ) {
	/**
	 * Re-assign the widgets to hfg_footer
	 *
	 * @param array  $section_args The section arguments.
	 * @param string $section_id The section ID.
	 * @param string $sidebar_id The sidebar ID.
	 *
	 * @return mixed
	 */
	function neve_customizer_custom_widget_areas( $section_args, $section_id, $sidebar_id ) {
		if ( strpos( $section_id, 'widgets-footer' ) ) {
			$section_args['panel'] = 'hfg_footer';
		}

		return $section_args;
	}

	add_filter( 'customizer_widgets_section_args', 'neve_customizer_custom_widget_areas', 10, 3 );
}

require_once get_template_directory() . '/header-footer-grid/loader.php';

add_filter(
	'neve_welcome_metadata',
	function() {
		return [
			'is_enabled' => ! defined( 'NEVE_PRO_VERSION' ),
			'pro_name'   => 'Neve Pro Addon',
			'logo'       => get_template_directory_uri() . '/assets/img/dashboard/logo.svg',
			'cta_link'   => tsdk_translate_link( tsdk_utmify( 'https://themeisle.com/themes/neve/upgrade/?discount=LOYALUSER582&dvalue=50', 'neve-welcome', 'notice' ), 'query' ),
		];
	}
);

add_filter( 'themeisle_sdk_enable_telemetry', '__return_true' );

/**
 * ----------------------------------------------------------------
 * Gaia Eyes: Space Weather Bar shortcode
 * Usage: [gaia_space_weather_bar]
 * ----------------------------------------------------------------
 */
if ( ! function_exists( 'gaia_space_weather_bar' ) ) {
  function gaia_space_weather_bar( $atts ) {
    $atts = shortcode_atts(
      [
        'url'        => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_weather.json',
        'flares_url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/flares_cmes.json',
        'detail' => '/space-weather/',
        'cache'      => 5, // minutes
      ],
      $atts,
      'gaia_space_weather_bar'
    );

    $cache_secs = max( 1, intval( $atts['cache'] ) ) * MINUTE_IN_SECONDS;

    $fetch_json = function( $url, $key ) use ( $cache_secs ) {
      $cache_key = 'gaia_sw_' . $key . '_' . md5( $url );
      $json = get_transient( $cache_key );
      if ( false === $json ) {
        $resp = wp_remote_get( esc_url_raw( $url ), [ 'timeout' => 8, 'headers' => [ 'Accept'=>'application/json' ] ] );
        if ( ! is_wp_error( $resp ) && 200 === wp_remote_retrieve_response_code( $resp ) ) {
          $json = wp_remote_retrieve_body( $resp );
          set_transient( $cache_key, $json, $cache_secs );
        }
      }
      return $json ? json_decode( $json, true ) : null;
    };

    $data  = $fetch_json( $atts['url'], 'wx' );
    $fc    = $fetch_json( $atts['flares_url'], 'flr' );
    $detail = trailingslashit( $atts['detail'] );

    if ( ! is_array( $data ) || empty( $data['now'] ) ) {
      return '<section class="gaia-sw"><div class="gaia-sw__card">Space Weather: unavailable</div></section>';
    }

    $ts   = ! empty( $data['timestamp_utc'] ) ? strtotime( $data['timestamp_utc'] ) : time();
    $kp   = isset( $data['now']['kp'] ) ? number_format( floatval( $data['now']['kp'] ), 1 ) : '—';
    $sw   = isset( $data['now']['solar_wind_kms'] ) ? intval( $data['now']['solar_wind_kms'] ) : '—';
    $bzv  = isset( $data['now']['bz_nt'] ) ? floatval( $data['now']['bz_nt'] ) : null;
    $bz   = ( null !== $bzv ) ? number_format( $bzv, 1 ) : '—';
    $bzpol= ( null !== $bzv && $bzv < 0 ) ? 'southward' : 'northward';

    // NEW: last 24h maxima
    $kp_max24 = isset( $data['last_24h']['kp_max'] ) ? number_format( floatval( $data['last_24h']['kp_max'] ), 1 ) : null;
    $sw_max24 = isset( $data['last_24h']['solar_wind_max_kms'] ) ? intval( $data['last_24h']['solar_wind_max_kms'] ) : null;

    $headline   = $data['next_72h']['headline'] ?? '';
    $confidence = $data['next_72h']['confidence'] ?? '';
    $alerts_txt = (!empty($data['alerts']) && is_array($data['alerts'])) ? implode(', ', $data['alerts']) : 'None';

    // Pull new flare/CME stats
    $flares      = is_array($fc) ? ($fc['flares'] ?? []) : [];
    $cmes        = is_array($fc) ? ($fc['cmes']   ?? []) : [];
    $flr_total   = $flares['total_24h'] ?? null;
    $flr_bands   = is_array($flares['bands_24h'] ?? null) ? $flares['bands_24h'] : [];
    $flr_max     = $flares['max_24h'] ?? null;

    $cme_stats   = is_array($cmes['stats'] ?? null) ? $cmes['stats'] : [];
    $cme_total   = $cme_stats['total_72h'] ?? null;
    $cme_ed_cnt  = $cme_stats['earth_directed_count'] ?? null;
    $cme_vmax    = $cme_stats['max_speed_kms'] ?? null;

    // Build chips under Next 72h
    $chips = [];
    if ( $flr_max || $flr_total ) {
      $chip = 'Flares (24h): ';
      if ( $flr_max )   $chip .= esc_html($flr_max) . ' peak';
      if ( $flr_total ) $chip .= ($flr_max ? ' • ' : '') . esc_html($flr_total) . ' total';
      $chips[] = '<span class="gaia-chip" data-type="flare"><a class="gaia-link" href="' . esc_url( $detail . '#flares' ) . '">' . $chip . '</a></span>';
    }
    if ( $cme_total || $cme_vmax || $cme_ed_cnt ) {
      $chip = 'CMEs: ';
      $parts = [];
      if ( $cme_total ) $parts[] = esc_html($cme_total) . ' total';
      if ( $cme_ed_cnt ) $parts[] = esc_html($cme_ed_cnt) . ' earth-directed';
      if ( $cme_vmax )  $parts[] = 'max ' . esc_html($cme_vmax) . ' km/s';
      $chip .= implode(' • ', $parts);
      $chips[] = '<span class="gaia-chip" data-type="cme" data-level="' . ( stripos($headline,'Fast')!==false ? 'fast' : (stripos($headline,'Moderate')!==false ? 'moderate' : '') ) . '"><a class="gaia-link" href="' . esc_url( $detail . '#cmes' ) . '">' . $chip . '</a></span>';
    }

    // Optional flare band mini-line (A/B/C/M/X with non-zero counts)
    $flr_band_line = '';
    if ( $flr_bands ) {
      $nz = array_filter($flr_bands, fn($v)=>intval($v)>0 );
      if ( !empty($nz) ) {
        $parts = [];
        foreach (['X','M','C','B','A'] as $b) {
          if ( !empty($flr_bands[$b]) ) $parts[] = $b.':'.intval($flr_bands[$b]);
        }
        if ( $parts ) $flr_band_line = implode(' ', $parts);
      }
    }

    ob_start(); ?>
    <section class="gaia-sw">
      <header class="gaia-sw__head">
        <h3 class="gaia-sw__title"><a href="<?php echo esc_url( $detail ); ?>" class="gaia-link">Space Weather Bar</a></h3>
        <time datetime="<?php echo esc_attr( gmdate( 'c', $ts ) ); ?>">
          Updated <?php echo esc_html( gmdate( 'D, d M Y H:i', $ts ) ); ?> UTC
        </time>
      </header>

      <div class="gaia-sw__row">
        <div class="gaia-sw__card">
          <div class="gaia-sw__label">Now (UTC)</div>
          <div>Kp: <strong><a href="<?php echo esc_url( $detail . '#kp' ); ?>" class="gaia-link"><?php echo esc_html( $kp ); ?></a></strong><?php if ($kp_max24 !== null): ?> <span class="gaia-sw__sub">(24h max <?php echo esc_html($kp_max24); ?>)</span><?php endif; ?></div>
          <div>Solar wind: <strong><a href="<?php echo esc_url( $detail . '#solar-wind' ); ?>" class="gaia-link"><?php echo esc_html( $sw ); ?></a></strong> km/s<?php if ($sw_max24 !== null): ?> <span class="gaia-sw__sub">(24h max <?php echo esc_html($sw_max24); ?>)</span><?php endif; ?></div>
          <div>Bz: <strong><a href="<?php echo esc_url( $detail . '#bz' ); ?>" class="gaia-link"><?php echo esc_html( $bz ); ?></a> nT</strong> (<?php echo esc_html( $bzpol ); ?>)</div>
        </div>

        <div class="gaia-sw__card">
          <div class="gaia-sw__label">Next 72h</div>
          <div>
            <a href="<?php echo esc_url( $detail . '#aurora' ); ?>" class="gaia-link"><?php echo esc_html( $headline ); ?></a>
            <?php if ( ! empty( $confidence ) ) : ?>
              &bull; <?php echo esc_html( $confidence ); ?>
            <?php endif; ?>
          </div>
          <div class="gaia-sw__alerts">Alerts: <?php echo esc_html( $alerts_txt ); ?></div>
          <?php if ( $chips ) : ?>
            <div class="gaia-sw__chips"><?php echo implode('', $chips); ?></div>
          <?php endif; ?>
          <?php if ( $flr_band_line ) : ?>
            <div class="gaia-sw__bands">Bands: <?php echo esc_html($flr_band_line); ?></div>
          <?php endif; ?>
        </div>

        <div class="gaia-sw__card">
          <div class="gaia-sw__label">Impacts</div>
          <ul class="gaia-sw__list">
            <li><strong>GPS:</strong> <?php echo esc_html( $data['impacts']['gps'] ?? '—' ); ?></li>
            <li><strong>Comms:</strong> <?php echo esc_html( $data['impacts']['comms'] ?? '—' ); ?></li>
            <li><strong>Grids:</strong> <?php echo esc_html( $data['impacts']['grids'] ?? '—' ); ?></li>
            <li><strong>Aurora:</strong> <?php echo esc_html( $data['impacts']['aurora'] ?? '—' ); ?></li>
          </ul>
        </div>
      </div>

      <style>
        .gaia-sw{border-radius:16px;padding:16px;background:#111;color:#eee}
        .gaia-sw__head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
        .gaia-sw__title{margin:0;font-size:1.05rem}
        .gaia-sw__row{display:grid;gap:12px}
        @media(min-width:768px){.gaia-sw__row{grid-template-columns:repeat(3,1fr)}}
        .gaia-sw__card{background:#1c1c1c;border-radius:12px;padding:12px}
        .gaia-sw__label{font-size:.9rem;opacity:.75;margin-bottom:6px}
        .gaia-sw__alerts{font-size:.85rem;opacity:.9;margin-top:6px}
        .gaia-sw__list{margin:0;padding-left:18px;line-height:1.35}
        .gaia-sw__chips{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
        .gaia-chip{display:inline-block;background:#22304a;border:1px solid #35537c;color:#bbd7ff;border-radius:999px;padding:2px 8px;font-size:.72rem;line-height:1}
        .gaia-sw__sub{font-size:.8rem;opacity:.75;margin-left:6px}
        .gaia-sw__bands{font-size:.78rem;opacity:.85;margin-top:6px}
        .gaia-chip[data-type="cme"][data-level="fast"]{background:#3f2d12;border-color:#8a5a1a;color:#ffd089}
        .gaia-chip[data-type="cme"][data-level="moderate"]{background:#2c3515;border-color:#516b1f;color:#d2f59a}
        .gaia-chip[data-type="flare"]{background:#2a2438;border-color:#5d4c8f;color:#d9c6ff}
        .gaia-link{color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25)}
        .gaia-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      </style>
    </section>
    <?php
    return ob_get_clean();
  }
  add_shortcode( 'gaia_space_weather_bar', 'gaia_space_weather_bar' );
}
if ( ! function_exists( 'gaia_earthscope_banner' ) ) {
  function gaia_earthscope_banner( $atts ) {
    $atts = shortcode_atts(
      [
        'daily_url'       => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/earthscope_daily.json',
        'url'             => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/earthscope.json',
        'space_detail'    => '/space-weather/',
        'schumann_detail' => '/schumann/',
        'cache'           => 5,
        'mode'            => 'mystical',
      ],
      $atts,
      'gaia_earthscope_banner'
    );
    $cache_secs = max(1, intval($atts['cache'])) * MINUTE_IN_SECONDS;

    $fetch_json = function( $url, $key ) use ( $cache_secs ) {
      $k = 'gaia_es_card_' . $key . '_' . md5( $url );
      $json = get_transient( $k );
      if ( false === $json ) {
        $r = wp_remote_get( esc_url_raw( $url ), [ 'timeout'=>8, 'headers'=>['Accept'=>'application/json'] ] );
        if ( ! is_wp_error( $r ) && 200 === wp_remote_retrieve_response_code( $r ) ) {
          $json = wp_remote_retrieve_body( $r );
          set_transient( $k, $json, $cache_secs );
        }
      }
      return $json ? json_decode( $json, true ) : null;
    };

    // Trailing slash variables for detail links
    $space_detail = trailingslashit( $atts['space_detail'] );
    $sch_detail   = trailingslashit( $atts['schumann_detail'] );

    // Prefer daily (new schema), fallback to legacy
    $d = $fetch_json( $atts['daily_url'], 'daily' );
    $is_daily = is_array($d) && ( isset($d['caption']) || isset($d['sections']) );
    if ( ! $is_daily ) {
      $d = $fetch_json( $atts['url'], 'legacy' );
      if ( ! is_array($d) ) return '<section class="gaia-es">EarthScope: unavailable</section>';
    }

    // Normalize fields
    $title = '';
    $caption = ''; $affects = ''; $playbook = '';
    $sch_f1 = null; $sch_delta = null;
    $aurora_chip = '';

    if ( $is_daily ) {
      $title   = isset($d['title']) ? trim( (string)$d['title'] ) : '';
      $sec     = is_array($d['sections'] ?? null) ? $d['sections'] : [];
      $caption = (string) ( $sec['caption'] ?? $d['caption'] ?? '' );
      $affects = (string) ( $sec['affects'] ?? $d['affects'] ?? '' );
      $playbook= (string) ( $sec['playbook'] ?? $d['playbook'] ?? '' );

      $m = is_array($d['metrics'] ?? null) ? $d['metrics'] : [];
      $sch_f1   = isset($m['schumann_value_hz']) ? floatval($m['schumann_value_hz']) : null;
      $sch_delta= is_array($m['deltas'] ?? null) ? ($m['deltas']['schumann'] ?? null) : null;

      $space = is_array($m['space_json'] ?? null) ? $m['space_json'] : [];
      if ( ! empty($space['aurora_headline']) ) {
        $aurora_chip = 'Aurora: ' . sanitize_text_field($space['aurora_headline']);
        if ( ! empty($space['aurora_window']) ) {
          $aurora_chip .= ' • ' . sanitize_text_field($space['aurora_window']);
        }
      }
    } else {
      // legacy compact fallback
      $mode = strtolower($atts['mode']) === 'scientific' ? 'sci' : 'mystical';
      $lines = $d[$mode] ?? [];
      $caption = is_array($lines) && $lines ? implode(' ', array_slice($lines, 0, 1)) : '';
      $affects = ''; $playbook = '';
    }

    // Best-effort sections fallback
    if ( empty($caption) && isset($d['sections']['caption']) ) $caption = (string) $d['sections']['caption'];
    if ( empty($affects) && isset($d['sections']['affects']) ) $affects = (string) $d['sections']['affects'];
    if ( empty($playbook) && isset($d['sections']['playbook']) ) $playbook = (string) $d['sections']['playbook'];

    // Build Schumann pill text
    $sch_pill = '';
    if ( $sch_f1 ) {
      $sch_pill = 'Schumann: ' . number_format($sch_f1, 2) . ' Hz';
      if ( $sch_delta !== null ) {
        $sch_pill .= ' • Δ≈' . number_format(floatval($sch_delta), 2) . ' Hz';
      }
    }

    ob_start(); ?>
    <section class="gaia-es">
      <div class="gaia-es__head">
        <div class="gaia-es__head-left">
          <h3 class="gaia-es__title">EarthScope</h3>
          <?php if ( $title ): ?>
            <span class="gaia-es__badge"><?php echo esc_html($title); ?></span>
          <?php endif; ?>
          <?php if ( $aurora_chip ): ?>
            <span class="gaia-es__badge gaia-es__badge--aurora"><a class="gaia-link" href="<?php echo esc_url( $space_detail . '#aurora' ); ?>"><?php echo esc_html($aurora_chip); ?></a></span>
          <?php endif; ?>
          <?php if ( $sch_pill ): ?>
            <span class="gaia-es__badge gaia-es__badge--sch"><a class="gaia-link" href="<?php echo esc_url( $sch_detail . '#combined' ); ?>"><?php echo esc_html($sch_pill); ?></a></span>
          <?php endif; ?>
        </div>
      </div>

      <div class="gaia-es__grid">
        <!-- Card 1: How it may feel (caption) -->
        <div class="gaia-es__card">
          <div class="gaia-es__label">Summary</div>
          <div class="gaia-es__caption"><?php echo nl2br( esc_html( $caption ) ); ?></div>
        </div>

        <!-- Card 2: Care notes -->
        <div class="gaia-es__card">
          <div class="gaia-es__label">How to cope</div>
          <div class="gaia-es__body"><?php echo nl2br( esc_html( $playbook ) ); ?></div>
        </div>

        <!-- Card 3: Health notes (previously Schumann card) -->
        <div class="gaia-es__card">
          <div class="gaia-es__label">Health notes</div>
          <div class="gaia-es__body"><?php echo nl2br( esc_html( $affects ) ); ?></div>
        </div>
      </div>

      <style>
        .gaia-es{border-radius:14px;padding:14px;background:#101015;color:#eee}
        .gaia-es__head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px;flex-wrap:wrap}
        .gaia-es__title{margin:0;font-size:1.05rem}
        .gaia-es__badge{display:inline-block;margin-left:8px;padding:4px 8px;border-radius:999px;background:#1c2130;color:#cfe3ff;font-size:.75rem;border:1px solid #374a6a}
        .gaia-es__badge--aurora{background:#1b2a22;color:#9af1bb;border-color:#2d624a}
        .gaia-es__badge--sch{background:#20283b;color:#bcd5ff;border:1px solid #344a72}
        .gaia-es__grid{display:grid;gap:12px}
        @media(min-width:768px){.gaia-es__grid{grid-template-columns:repeat(3,1fr)}}
        .gaia-es__card{background:#151827;border-radius:12px;padding:12px;border:1px solid rgba(255,255,255,.06)}
        .gaia-es__label{font-size:.9rem;opacity:.8;margin-bottom:6px}
        .gaia-es__caption{white-space:pre-wrap;line-height:1.4}
        .gaia-es__body{white-space:pre-wrap;line-height:1.4}
        .gaia-link{color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25)}
        .gaia-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      </style>
    </section>
    <?php
    return ob_get_clean();
  }
  add_shortcode('gaia_earthscope_banner','gaia_earthscope_banner');
}

// [gaia_pulse url="https://gaiaeyeshq.github.io/gaiaeyes-media/data/pulse.json" cache="5"]
add_shortcode('gaia_pulse', function($atts){
  $a = shortcode_atts([
    'url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/pulse.json',
    'cache' => 5
  ], $atts, 'gaia_pulse');

  $key = 'gaia_pulse_' . md5($a['url']);
  $json = get_transient($key);
  if ($json === false) {
    $r = wp_remote_get( esc_url_raw($a['url']), ['timeout'=>8, 'headers'=>['Accept'=>'application/json']] );
    if (!is_wp_error($r) && wp_remote_retrieve_response_code($r)===200){
      $json = wp_remote_retrieve_body($r);
      set_transient($key, $json, max(1,intval($a['cache']))*MINUTE_IN_SECONDS);
    }
  }
  if (empty($json)) return '<section class="gaia-pulse">Pulse: unavailable</section>';
  $d = json_decode($json, true);
  if (!is_array($d)) return '<section class="gaia-pulse">Pulse: bad data</section>';
  $cards = $d['cards'] ?? [];

  ob_start(); ?>
  <section class="gaia-pulse">
    <div class="pulse-grid">
      <?php foreach ($cards as $c): 
        $sev = esc_attr($c['severity'] ?? 'info');
        $type= esc_attr($c['type'] ?? 'info');
        $title = esc_html($c['title'] ?? 'Update');
        $sum = esc_html($c['summary'] ?? '');
        $tw  = esc_html($c['time_window'] ?? '');
        $url = !empty($c['details_url']) ? esc_url($c['details_url']) : '';
      ?>
      <article class="pulse-card pulse-<?php echo $type; ?> sev-<?php echo $sev; ?>">
        <header class="pulse-head">
          <h4 class="pulse-title"><?php echo $title; ?></h4>
          <span class="chip sev"><?php echo strtoupper($sev); ?></span>
        </header>
        <?php if ($tw): ?><div class="pulse-when"><?php echo $tw; ?></div><?php endif; ?>
        <p class="pulse-summary"><?php echo $sum; ?></p>
        <?php if ($url): ?><a class="pulse-link" href="<?php echo $url; ?>">Read more</a><?php endif; ?>
      </article>
      <?php endforeach; ?>
    </div>
    <style>
      .gaia-pulse{background:#0f121a;color:#e9eef7;border-radius:14px;padding:14px}
      .pulse-grid{display:grid;gap:12px}
      @media(min-width:768px){.pulse-grid{grid-template-columns:repeat(2,1fr)}}
      .pulse-card{background:#151a24;border-radius:12px;padding:12px;border:1px solid rgba(255,255,255,0.05)}
      .pulse-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
      .pulse-title{margin:0;font-size:1rem}
      .chip.sev{font-size:.7rem;border-radius:999px;padding:2px 8px;background:#222;color:#ddd;border:1px solid #333}
      .sev-low .chip.sev{background:#1f2a1f;color:#b7f3c6;border-color:#2d4d35}
      .sev-medium .chip.sev{background:#3f2d12;color:#ffd089;border-color:#8a5a1a}
      .sev-high .chip.sev{background:#5a1a1a;color:#ffd2d2;border-color:#8e2a2a}
      .pulse-when{font-size:.85rem;opacity:.85;margin:4px 0}
      .pulse-summary{margin:.35rem 0 .5rem 0;line-height:1.35}
      .pulse-link{color:#bcd5ff;text-decoration:none;border-bottom:1px dashed #4b6aa1}
      .pulse-cme{border-left:3px solid #4b6aa1}
      .pulse-flare{border-left:3px solid #7e57c2}
      .pulse-aurora{border-left:3px solid #34e07a}
      .pulse-severe{border-left:3px solid #ffb347}
      .pulse-quake{border-left:3px solid #ff6b6b}
      .pulse-tips{border-left:3px solid #9bd0ff}
	  .pulse-cme{border-left:3px solid #4b6aa1}
	  @media (max-width:480px){
 	    .pulse-title{font-size:.95rem}
  	    .pulse-summary{font-size:.92rem}
	  }
    </style>
  </section>
  <?php return ob_get_clean();
});
// [gaia_pulse_detail url="https://gaiaeyeshq.github.io/gaiaeyes-media/data/pulse.json" type="cme" index="0"]
add_shortcode('gaia_pulse_detail', function($atts){
  $a = shortcode_atts([
    'url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/pulse.json',
    'type' => '', 'index' => ''
  ], $atts, 'gaia_pulse_detail');
  $r = wp_remote_get( esc_url_raw($a['url']), ['timeout'=>8,'headers'=>['Accept'=>'application/json']] );
  if (is_wp_error($r) || wp_remote_retrieve_response_code($r)!==200) return '<section class="gaia-pulse">Pulse: unavailable</section>';
  $d = json_decode(wp_remote_retrieve_body($r), true);
  $cards = $d['cards'] ?? [];
  $sel = null;

  if ($a['type']){
    foreach($cards as $c){ if (($c['type'] ?? '') === $a['type']) { $sel = $c; break; } }
  }
  if (!$sel && strlen($a['index'])){
    $i = intval($a['index']); if ($i>=0 && $i<count($cards)) $sel = $cards[$i];
  }
  if (!$sel) return '<section class="gaia-pulse">No matching card.</section>';

  ob_start(); ?>
  <article class="pulse-detail">
    <header><h2><?php echo esc_html($sel['title'] ?? 'Update'); ?></h2>
      <span class="chip sev"><?php echo esc_html(strtoupper($sel['severity'] ?? 'info')); ?></span>
    </header>
    <?php if (!empty($sel['time_window'])): ?><div class="when"><?php echo esc_html($sel['time_window']); ?></div><?php endif; ?>
    <?php if (!empty($sel['summary'])): ?><p class="sum"><?php echo esc_html($sel['summary']); ?></p><?php endif; ?>
    <?php if (!empty($sel['data'])): ?><pre class="data"><?php echo esc_html(json_encode($sel['data'], JSON_PRETTY_PRINT)); ?></pre><?php endif; ?>
    <?php if (!empty($sel['details_url'])): ?><p><a href="<?php echo esc_url($sel['details_url']); ?>">Source</a></p><?php endif; ?>
    <style>
      .pulse-detail{background:#0f121a;color:#e9eef7;border-radius:14px;padding:16px}
      .pulse-detail header{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
      .pulse-detail h2{margin:0}
      .chip.sev{font-size:.75rem;border-radius:999px;padding:2px 8px;background:#222;color:#ddd;border:1px solid #333}
      .when{opacity:.85;margin:6px 0}
      .sum{line-height:1.45}
      .data{background:#0b0f16;border:1px solid rgba(255,255,255,0.08);padding:10px;border-radius:8px;overflow:auto}
    </style>
  </article>
  <?php return ob_get_clean();
});