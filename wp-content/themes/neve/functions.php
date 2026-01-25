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
        'detail' => '/space-dashboard/',
        'cache'      => 5, // minutes
        'series_embed' => 'false',
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

    // Prefer API-based flares summary when available
    $api_base   = defined('GAIAEYES_API_BASE') ? rtrim(GAIAEYES_API_BASE, '/') : '';
    $api_bearer = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
    $api_dev    = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';
    $flares_api = null;
    if ( $api_base && function_exists('gaiaeyes_http_get_json_api_cached') ) {
      $flares_api = gaiaeyes_http_get_json_api_cached(
        $api_base . '/v1/space/flares',
        'ge_sw_flr_bar',
        $cache_secs,
        $api_bearer,
        $api_dev
      );
    }

    // Try to fetch 24h space-weather history for Kp/SW/Bz from the API
    $sw_history = null;
    if ( $api_base && function_exists('gaiaeyes_http_get_json_api_cached') ) {
      $sw_history = gaiaeyes_http_get_json_api_cached(
        $api_base . '/v1/space/history?hours=24',
        'ge_sw_history_bar',
        $cache_secs,
        $api_bearer,
        $api_dev
      );
    }

    // Pull Space Visuals bundle (images + series) to expose series for overlays/charts
    $space_visuals = null;
    if ( $api_base && function_exists('gaiaeyes_http_get_json_api_cached') ) {
      $sv_endpoint = defined('GAIAEYES_SPACE_VISUALS_ENDPOINT') ? GAIAEYES_SPACE_VISUALS_ENDPOINT : ($api_base . '/v1/space/visuals');
      $space_visuals = gaiaeyes_http_get_json_api_cached(
        $sv_endpoint,
        'ge_space_visuals_bundle',
        $cache_secs,
        $api_bearer,
        $api_dev
      );
    }

    // Decide whether to embed series JSON for front‑end overlays/charts
    $embed_series   = ( isset($atts['series_embed']) && ( $atts['series_embed'] === true || strtolower((string)$atts['series_embed']) === 'true' ) );
    $sv_series_json = '';
    $sv_config_json = '';
    if ( $embed_series && is_array($space_visuals) ) {
      $series = $space_visuals['series'] ?? [];
      if ( is_array($series) ) {
        // Keep a compact subset most useful for overlays; extend as needed
        $keep   = ['goes_protons','goes_electrons','goes_xray'];
        $bundle = array_intersect_key( $series, array_flip($keep) );
        if ( ! empty($bundle) ) {
          $sv_series_json = wp_json_encode( $bundle );
        }
      }
      $cdn_base = $space_visuals['cdn_base'] ?? ( defined('GAIA_MEDIA_BASE') ? GAIA_MEDIA_BASE : '' );
      if ( $cdn_base ) {
        $sv_config_json = wp_json_encode( ['cdn_base' => $cdn_base] );
      }
    }

    // If neither JSON nor API provide anything, bail out
    $series24 = null;
    if ( is_array( $sw_history )
         && ! empty( $sw_history['ok'] )
         && ! empty( $sw_history['data']['series24'] )
         && is_array( $sw_history['data']['series24'] ) ) {
      $series24 = $sw_history['data']['series24'];
    }

    if ( ( ! is_array( $data ) || empty( $data['now'] ) ) && ! $series24 ) {
      return '<section class="gaia-sw"><div class="gaia-sw__card">Space Weather: unavailable</div></section>';
    }

    // Helpers to derive "now" and 24h max from [ts,val] series
    $extract_last = function( $series ) {
      if ( ! is_array( $series ) || ! $series ) {
        return null;
      }
      $last = end( $series );
      if ( is_array( $last ) ) {
        if ( isset( $last[1] ) && is_numeric( $last[1] ) ) {
          return (float) $last[1];
        }
        if ( isset( $last[0] ) && is_numeric( $last[0] ) ) {
          return (float) $last[0];
        }
        return null;
      }
      return is_numeric( $last ) ? (float) $last : null;
    };
    $extract_max = function( $series ) {
      if ( ! is_array( $series ) || ! $series ) {
        return null;
      }
      $max = null;
      foreach ( $series as $entry ) {
        $val = $entry;
        if ( is_array( $entry ) ) {
          $val = isset( $entry[1] ) ? $entry[1] : ( $entry[0] ?? null );
        }
        if ( ! is_numeric( $val ) ) {
          continue;
        }
        $val = (float) $val;
        if ( $max === null || $val > $max ) {
          $max = $val;
        }
      }
      return $max;
    };

    $kp_now_val = null;
    $sw_now_val = null;
    $bz_now_val = null;
    $kp_max24_val = null;
    $sw_max24_val = null;

    if ( $series24 ) {
      if ( isset( $series24['kp'] ) ) {
        $kp_now_val   = $extract_last( $series24['kp'] );
        $kp_max24_val = $extract_max( $series24['kp'] );
      }
      if ( isset( $series24['sw'] ) ) {
        $sw_now_val   = $extract_last( $series24['sw'] );
        $sw_max24_val = $extract_max( $series24['sw'] );
      }
      if ( isset( $series24['bz'] ) ) {
        $bz_now_val = $extract_last( $series24['bz'] );
      }
    }

    // Fallback to JSON "now" values when API history did not provide them
    if ( is_array( $data ) && ! empty( $data['now'] ) ) {
      if ( $kp_now_val === null && isset( $data['now']['kp'] ) && is_numeric( $data['now']['kp'] ) ) {
        $kp_now_val = (float) $data['now']['kp'];
      }
      if ( $sw_now_val === null && isset( $data['now']['solar_wind_kms'] ) && is_numeric( $data['now']['solar_wind_kms'] ) ) {
        $sw_now_val = (float) $data['now']['solar_wind_kms'];
      }
      if ( $bz_now_val === null && isset( $data['now']['bz_nt'] ) && is_numeric( $data['now']['bz_nt'] ) ) {
        $bz_now_val = (float) $data['now']['bz_nt'];
      }
    }

    // Fallback to JSON 24h maxima if API history did not provide them
    if ( is_array( $data ) && isset( $data['last_24h'] ) && is_array( $data['last_24h'] ) ) {
      if ( $kp_max24_val === null && isset( $data['last_24h']['kp_max'] ) && is_numeric( $data['last_24h']['kp_max'] ) ) {
        $kp_max24_val = (float) $data['last_24h']['kp_max'];
      }
      if ( $sw_max24_val === null && isset( $data['last_24h']['solar_wind_max_kms'] ) && is_numeric( $data['last_24h']['solar_wind_max_kms'] ) ) {
        $sw_max24_val = (float) $data['last_24h']['solar_wind_max_kms'];
      }
    }

    $ts = ! empty( $data['timestamp_utc'] ) ? strtotime( $data['timestamp_utc'] ) : time();

    $kp  = $kp_now_val !== null ? number_format( $kp_now_val, 1 ) : '—';
    $sw  = $sw_now_val !== null ? intval( $sw_now_val ) : '—';
    $bzv = $bz_now_val !== null ? $bz_now_val : null;
    $bz  = ( $bzv !== null ) ? number_format( $bzv, 1 ) : '—';
    $bzpol = ( $bzv !== null && $bzv < 0 ) ? 'southward' : 'northward';

    $kp_max24 = $kp_max24_val !== null ? number_format( $kp_max24_val, 1 ) : null;
    $sw_max24 = $sw_max24_val !== null ? intval( $sw_max24_val ) : null;

    $headline   = $data['next_72h']['headline'] ?? '';
    $confidence = $data['next_72h']['confidence'] ?? '';
    $alerts_txt = (!empty($data['alerts']) && is_array($data['alerts'])) ? implode(', ', $data['alerts']) : 'None';

    // Pull new flare/CME stats
    $flares      = is_array($fc) ? ($fc['flares'] ?? []) : [];
    $cmes        = is_array($fc) ? ($fc['cmes']   ?? []) : [];

    // Default flare stats from legacy JSON (for now)
    $flr_total   = $flares['total_24h'] ?? null;
    $flr_bands   = is_array($flares['bands_24h'] ?? null) ? $flares['bands_24h'] : [];
    $flr_max     = $flares['max_24h'] ?? null;

    // Override flare stats from /v1/space/flares API when available
    if ( is_array($flares_api) && !empty($flares_api['ok']) && !empty($flares_api['data']) && is_array($flares_api['data']) ) {
      $fd = $flares_api['data'];
      if ( array_key_exists('max_24h', $fd) ) {
        $flr_max = $fd['max_24h'];
      }
      if ( array_key_exists('total_24h', $fd) ) {
        $flr_total = $fd['total_24h'];
      }
      if ( !empty($fd['bands_24h']) && is_array($fd['bands_24h']) ) {
        $flr_bands = $fd['bands_24h'];
      }
    }

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
      <?php if ( ! empty($sv_series_json) ): ?>
        <script type="application/json" id="gaia-space-series"><?php echo $sv_series_json; ?></script>
      <?php endif; ?>
      <?php if ( ! empty($sv_config_json) ): ?>
        <script type="application/json" id="gaia-space-config"><?php echo $sv_config_json; ?></script>
      <?php endif; ?>
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
        'space_detail'    => '/space-dashboard/',
        'schumann_detail' => '/schumann/',
        'aurora_detail'   => '/aurora/',
        'quakes_detail'   => '/earthquakes/',
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
    $aurora_detail = trailingslashit( $atts['aurora_detail'] );
    $quakes_detail = trailingslashit( $atts['quakes_detail'] );

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
      // Quakes pill from daily JSON or pass-through earthscope_json
      $quakes_pill = '';
      if (!empty($d['quakes']) && is_array($d['quakes'])) {
        $q24 = $d['quakes']['total_24h'] ?? null;
        if ($q24) { $quakes_pill = 'Quakes: ' . intval($q24) . ' in 24h'; }
      } else if (!empty($m['earthscope_json']) && is_array($m['earthscope_json'])) {
        $q = $m['earthscope_json']['quakes'] ?? [];
        if (!empty($q['total_24h'])) { $quakes_pill = 'Quakes: ' . intval($q['total_24h']) . ' in 24h'; }
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
    // Ensure $quakes_pill is always defined
    if (!isset($quakes_pill)) $quakes_pill = '';

    ob_start(); ?>
    <section class="gaia-es">
      <div class="gaia-es__head">
        <div class="gaia-es__head-left">
          <h3 class="gaia-es__title">EarthScope</h3>
          <?php if ( $title ): ?>
            <span class="gaia-es__badge"><?php echo esc_html($title); ?></span>
          <?php endif; ?>
          <?php if ( $aurora_chip ): ?>
            <span class="gaia-es__badge gaia-es__badge--aurora"><a class="gaia-link" href="<?php echo esc_url( $aurora_detail . '#map' ); ?>"><?php echo esc_html($aurora_chip); ?></a></span>
          <?php endif; ?>
          <?php if ( $sch_pill ): ?>
            <span class="gaia-es__badge gaia-es__badge--sch"><a class="gaia-link" href="<?php echo esc_url( $sch_detail . '#combined' ); ?>"><?php echo esc_html($sch_pill); ?></a></span>
          <?php endif; ?>
          <?php if ( !empty($quakes_pill) ): ?>
            <span class="gaia-es__badge gaia-es__badge--quakes"><a class="gaia-link" href="<?php echo esc_url( $quakes_detail . '#recent' ); ?>"><?php echo esc_html($quakes_pill); ?></a></span>
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
        .gaia-es__badge--quakes{background:#2a1f1f;color:#ffd6d6;border:1px solid #6e3a3a}
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
    'cache' => 5,
    'space_detail' => '/space-dashboard/',
    'aurora_detail' => '/aurora/',
    'quakes_detail' => '/earthquakes/'
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
  // Trailing slash variables for detail links
  $space_detail = trailingslashit( $a['space_detail'] );
  $aurora_detail = trailingslashit( $a['aurora_detail'] );
  $quakes_detail = trailingslashit( $a['quakes_detail'] );
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
        $internal = '';
        switch ($type) {
          case 'cme':
            $internal = $space_detail . '#cmes';
            break;
          case 'flare':
            $internal = $space_detail . '#flares';
            break;
          case 'aurora':
            $internal = $aurora_detail . '#map';
            break;
          case 'quake':
            $internal = $quakes_detail . '#recent';
            break;
          case 'tips':
            $internal = $aurora_detail . '#photo-tips';
            break;
          default:
            $internal = '';
        }
      ?>
      <article class="pulse-card pulse-<?php echo $type; ?> sev-<?php echo $sev; ?>">
        <header class="pulse-head">
        <?php if ($internal): ?>
          <h4 class="pulse-title"><a class="gaia-link" href="<?php echo esc_url($internal); ?>"><?php echo $title; ?></a></h4>
        <?php else: ?>
          <h4 class="pulse-title"><?php echo $title; ?></h4>
        <?php endif; ?>
          <span class="chip sev"><?php echo strtoupper($sev); ?></span>
        </header>
        <?php if ($tw): ?><div class="pulse-when"><?php echo $tw; ?></div><?php endif; ?>
        <p class="pulse-summary"><?php echo $sum; ?></p>
        <?php if ($url): ?>
          <a class="pulse-link" href="<?php echo $url; ?>">Read more</a>
        <?php elseif ($internal): ?>
          <a class="pulse-link" href="<?php echo esc_url($internal); ?>">Read more</a>
        <?php endif; ?>
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
      .gaia-link{color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25)}
      .gaia-link:hover{border-bottom-color:rgba(255,255,255,.6)}
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

add_shortcode('gaia_alert_banner', function($atts){
  $a = shortcode_atts([
    'sw_url'     => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_weather.json',
    'quakes_url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/quakes_latest.json',
    'cache'      => 5,
  ], $atts, 'gaia_alert_banner');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $get = function($url,$key) use($ttl){
    $k='ge_alert_'.$key.'_'.md5($url);
    $c=get_transient($k); if($c!==false)return $c;
    $r=wp_remote_get(esc_url_raw($url),['timeout'=>8,'headers'=>['Accept'=>'application/json']]);
    if(!is_wp_error($r)&&wp_remote_retrieve_response_code($r)===200){
      $j=json_decode(wp_remote_retrieve_body($r),true);
      if(is_array($j)){set_transient($k,$j,$ttl);return $j;}
    }
    return null;
  };
  $sw=$get($a['sw_url'],'sw');
  $qk=$get($a['quakes_url'],'qk');
  $banner_sw='';$banner_qk='';$banner_rad='';
  // --- Radiation (proton storm) banner from Space Visuals bundle ---
  $api_base   = defined('GAIAEYES_API_BASE') ? rtrim(GAIAEYES_API_BASE, '/') : '';
  $api_bearer = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
  $api_dev    = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';
  $vis = null;
  if ($api_base && function_exists('gaiaeyes_http_get_json_api_cached')) {
    $sv_endpoint = defined('GAIAEYES_SPACE_VISUALS_ENDPOINT') ? GAIAEYES_SPACE_VISUALS_ENDPOINT : ($api_base . '/v1/space/visuals');
    $vis = gaiaeyes_http_get_json_api_cached($sv_endpoint, 'ge_alert_vis', $ttl, $api_bearer, $api_dev);
  } else if ($api_base) {
    $endpoint = $api_base . '/v1/space/visuals';
    $r = wp_remote_get( esc_url_raw($endpoint), ['timeout'=>8,'headers'=>['Accept'=>'application/json']] );
    if (!is_wp_error($r) && wp_remote_retrieve_response_code($r)===200){
      $vis = json_decode(wp_remote_retrieve_body($r), true);
    }
  }
  if ( is_array( $vis ) ) {
    // Determine current S-scale strictly from GOES ≥10 MeV proton channel.
    $pfu10   = null;
    $last_ts = null;
    $series  = $vis['series'] ?? [];
    if ( is_array( $series ) ) {
      foreach ( $series as $s ) {
        if ( ( $s['key'] ?? '' ) === 'goes_protons' && ! empty( $s['samples'] ) && is_array( $s['samples'] ) ) {
          for ( $i = count( $s['samples'] ) - 1; $i >= 0; $i-- ) {
            $row = $s['samples'][ $i ];
            if ( ( $row['energy'] ?? '' ) === '>=10 MeV' && is_numeric( $row['value'] ?? null ) ) {
              $pfu10   = (float) $row['value'];
              $last_ts = isset( $row['ts'] ) ? strtotime( (string) $row['ts'] ) : null;
              break;
            }
          }
          break;
        }
      }
    }

    // Only show a banner when S-scale is ≥ S1. Do not rely on feature flags.
    if ( $pfu10 !== null ) {
      // Optionally require recent data (≤ 12h); if timestamp missing, assume recent.
      $is_recent = $last_ts ? ( ( time() - $last_ts ) <= 12 * HOUR_IN_SECONDS ) : true;

      if ( $is_recent ) {
        $level = '';
        if ( $pfu10 >= 100000 ) { $level = 'S5'; }
        elseif ( $pfu10 >= 10000 ) { $level = 'S4'; }
        elseif ( $pfu10 >= 1000 )  { $level = 'S3'; }
        elseif ( $pfu10 >= 100 )   { $level = 'S2'; }
        elseif ( $pfu10 >= 10 )    { $level = 'S1'; }

        if ( $level !== '' ) {
          $banner_rad = "Solar radiation storm: {$level} (" . number_format( $pfu10, 0 ) . " pfu at ≥10 MeV)";
        } else {
          // Explicitly keep it empty when below S1 so stale banners won’t persist.
          $banner_rad = '';
        }
      }
    }
  }
  if ( is_array( $sw ) ) {
    $kp = $sw['now']['kp'] ?? null; $g = '';
    if ( is_numeric( $kp ) ) {
      $k = floatval( $kp );
      if ( $k >= 9 ) { $g = 'G5'; }
      elseif ( $k >= 8 ) { $g = 'G4'; }
      elseif ( $k >= 7 ) { $g = 'G3'; }
      elseif ( $k >= 6 ) { $g = 'G2'; }
      elseif ( $k >= 5 ) { $g = 'G1'; }
      if ( $g ) {
        $banner_sw = "Geomagnetic activity: {$g} storm (Kp " . number_format( $k, 1 ) . ")";
      } elseif ( $k >= 4.0 ) {
        // New: alert for Kp ≥ 4 as "Active geomagnetic conditions"
        $banner_sw = "Active geomagnetic conditions (Kp " . number_format( $k, 1 ) . ")";
      }
    }
  }
  if(is_array($qk)){
    $events=$qk['events']??[];$m6=0;
    foreach($events as $ev){$mag=isset($ev['mag'])?floatval($ev['mag']):0;if($mag>=6.0)$m6++;}
    if($m6>0)$banner_qk="Significant seismic activity: {$m6} event(s) M6.0+ in the last 72h";
  }
  if(!$banner_sw&&!$banner_qk&&!$banner_rad)return '';
  ob_start(); ?>
  <div class="ge-alerts" id="geAlertsWrap">
    <?php if($banner_rad): ?><div class="ge-alert ge-alert--rad" data-key="rad"><strong><?php echo esc_html($banner_rad); ?></strong><a class="ge-alert__link" href="/space-dashboard/#protons">Details →</a><button type="button" class="ge-alert__close" aria-label="Dismiss">×</button></div><?php endif; ?>
    <?php if($banner_sw): ?><div class="ge-alert ge-alert--kp" data-key="kp"><strong><?php echo esc_html($banner_sw); ?></strong><a class="ge-alert__link" href="/space-dashboard/#kp">Details →</a><button type="button" class="ge-alert__close" aria-label="Dismiss">×</button></div><?php endif; ?>
    <?php if($banner_qk): ?><div class="ge-alert ge-alert--eq" data-key="eq"><strong><?php echo esc_html($banner_qk); ?></strong><a class="ge-alert__link" href="/earthquakes/#recent">Details →</a><button type="button" class="ge-alert__close" aria-label="Dismiss">×</button></div><?php endif; ?>
  </div>
  <style>
    .ge-alerts{margin:8px 0;display:grid;gap:8px}
    .ge-alert{display:flex;gap:10px;align-items:center;justify-content:space-between;background:#221c1c;color:#ffd6d6;border:1px solid #6e3a3a;border-radius:10px;padding:8px 10px}
    .ge-alert--kp{background:#1b2a22;color:#aef2c0;border-color:#2d624a}
    .ge-alert--rad{background:#2f2613;color:#ffe0a3;border-color:#7a5a1a}
    .ge-alert__link{color:#bcd5ff;text-decoration:none;border-bottom:1px dashed #4b6aa1}
    .ge-alert__close{background:transparent;border:0;color:inherit;font-size:20px;cursor:pointer}
  </style>
  <script>
    (function(){
      const wrap=document.getElementById('geAlertsWrap');if(!wrap)return;
      const DAY=86400000;
      wrap.querySelectorAll('.ge-alert').forEach(function(b){
        const key='gaiaAlertDismiss_'+b.getAttribute('data-key');
        const prev=localStorage.getItem(key);
        if(prev&&Date.now()-parseInt(prev,10)<DAY){b.remove();return;}
        b.querySelector('.ge-alert__close').addEventListener('click',function(){
          localStorage.setItem(key,String(Date.now()));
          b.remove();
        });
      });
      if(!wrap.querySelector('.ge-alert'))wrap.remove();
    })();
  </script>
  <?php return ob_get_clean();
});


if (!function_exists('gaia_render_alert_banner')) {
  function gaia_render_alert_banner() {
    if (is_admin()) return;
    echo do_shortcode('[gaia_alert_banner]');
  }
}
// Site‑wide banner injection near top of body
add_action('wp_body_open', 'gaia_render_alert_banner');
