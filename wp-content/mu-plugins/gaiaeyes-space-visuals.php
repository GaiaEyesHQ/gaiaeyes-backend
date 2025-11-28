<?php
/**
 * Plugin Name: Gaia Eyes – Space Visuals (Enhanced UI)
 * Description: Visuals + spark charts (X-rays, protons, Bz, SW) + care notes + Kp legend using space_live.json.
 * Version: 1.2.0
 */
if (!defined('ABSPATH')) exit;

require_once __DIR__ . '/gaiaeyes-api-helpers.php';

if (!defined('GAIAEYES_SPACE_VISUALS_ENDPOINT')){
  $endpoint = getenv('GAIAEYES_SPACE_VISUALS_ENDPOINT');
  define('GAIAEYES_SPACE_VISUALS_ENDPOINT', $endpoint ? esc_url_raw($endpoint) : '');
}
if (!defined('GAIAEYES_SPACE_VISUALS_BEARER')){
  $bearer = getenv('GAIAEYES_SPACE_VISUALS_BEARER');
  define('GAIAEYES_SPACE_VISUALS_BEARER', $bearer ? trim($bearer) : '');
}
if (!defined('GAIAEYES_SPACE_VISUALS_DEV_USER')){
  $devu = getenv('GAIAEYES_API_DEV_USERID');
  define('GAIAEYES_SPACE_VISUALS_DEV_USER', $devu ? trim($devu) : '');
}

// Supabase media base constant
if (!defined('GAIA_MEDIA_BASE')){
  $mb = getenv('GAIA_MEDIA_BASE');
  define('GAIA_MEDIA_BASE', $mb ? esc_url_raw($mb) : '');
}

function ge_json_cached($url, $cache_min, $headers = array()){
  $ttl = max(1, intval($cache_min)) * MINUTE_IN_SECONDS;
  $sig = $url . '|' . md5(wp_json_encode($headers));
  $k = 'ge_json_' . md5($sig);
  $j = get_transient($k);
  if ($j===false){
    $req_headers = array_merge(array('Accept'=>'application/json'), (array)$headers);
    $r = wp_remote_get(esc_url_raw($url), ['timeout'=>10,'headers'=>$req_headers]);
    if (!is_wp_error($r) && wp_remote_retrieve_response_code($r)===200){
      $j = json_decode(wp_remote_retrieve_body($r), true);
      set_transient($k, $j, $ttl);
    }
  }
  return is_array($j)? $j : null;
}

function ge_visual_url($images, $key){
  return isset($images[$key]['url']) ? esc_url($images[$key]['url']) : '';
}

add_shortcode('gaia_space_detail', function($atts){
  $defaults = [
    'api' => defined('GAIAEYES_SPACE_VISUALS_ENDPOINT') ? GAIAEYES_SPACE_VISUALS_ENDPOINT : '',
    'url' => '',
    'cache' => 10,
  ];
  $a = shortcode_atts($defaults, $atts, 'gaia_space_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $api_payload = null;
  $legacy_payload = null;

  $api = isset($a['api']) ? trim($a['api']) : '';
  if ($api){
    $bearer = defined('GAIAEYES_SPACE_VISUALS_BEARER') && GAIAEYES_SPACE_VISUALS_BEARER
      ? GAIAEYES_SPACE_VISUALS_BEARER
      : (defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '');
    $dev_user = defined('GAIAEYES_SPACE_VISUALS_DEV_USER') && GAIAEYES_SPACE_VISUALS_DEV_USER
      ? GAIAEYES_SPACE_VISUALS_DEV_USER
      : (defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '');
    $api_payload = gaiaeyes_http_get_json_api_cached($api, 'ge_space_visuals', $ttl, $bearer, $dev_user);
    if (!is_array($api_payload) || empty($api_payload['ok']) || (empty($api_payload['items']) && empty($api_payload['images']))){
      $api_payload = null;
    }
  }

  if (!$api_payload && !empty($a['url'])){
    $legacy_payload = ge_json_cached($a['url'], $a['cache']);
  }

  $base = $api_payload['cdn_base'] ?? (defined('GAIA_MEDIA_BASE') ? GAIA_MEDIA_BASE : '');
  $base = $base ? rtrim($base, '/') . '/' : '';
  $images = [];
  $video = [];
  $structured_series = [];
  $legacy_series = [];
  $overlay_flags = [];
  $updated = '';

  $seen = [];
  $append_media = function($id, $path, $asset_type = 'image') use (&$images, &$video, &$seen) {
    $norm = strtolower(trim($id));
    if (!$norm || !$path || isset($seen[$norm])) return;
    $seen[$norm] = true;
    $entry = [
      'url' => $path,
      'asset_type' => $asset_type,
    ];
    $images[$norm] = $entry;
    if ($asset_type === 'video'){
      $video[$norm] = $entry;
    }
  };

  if ($api_payload){
    $updated = !empty($api_payload['generated_at']) ? esc_html($api_payload['generated_at']) : '';
    foreach (($api_payload['images'] ?? []) as $item){
      $id = $item['key'] ?? $item['id'] ?? '';
      $path = $item['url'] ?? $item['path'] ?? '';
      $atype = $item['asset_type'] ?? (preg_match('#\.(mp4|mov)(\?.*)?$#i', (string)$path) ? 'video' : 'image');
      if ($id && $path){
        $append_media($id, $path, $atype);
      }
    }
    foreach (($api_payload['items'] ?? []) as $it){
      $id = $it['id'] ?? $it['key'] ?? '';
      $path = $it['url'] ?? $it['path'] ?? '';
      $atype = $it['asset_type'] ?? (preg_match('#\.(mp4|mov)(\?.*)?$#i', (string)$path) ? 'video' : 'image');
      if ($id && $path){
        $append_media($id, $path, $atype);
      }
    }
    if (!isset($images['enlil']) && !isset($video['enlil'])){
      $append_media('enlil', 'nasa/enlil/latest.mp4', 'video');
    }
    foreach (($api_payload['series'] ?? []) as $entry){
      if (empty($entry['key'])) continue;
      $structured_series[$entry['key']] = [
        'samples' => $entry['samples'] ?? [],
        'meta' => $entry['meta'] ?? [],
      ];
    }
    $overlay_flags = $api_payload['feature_flags'] ?? [];
  } elseif ($legacy_payload){
    $updated = !empty($legacy_payload['timestamp_utc']) ? esc_html($legacy_payload['timestamp_utc']) : '';
    foreach (($legacy_payload['images'] ?? []) as $key=>$path){
      $append_media($key, $path, 'image');
    }
    foreach (($legacy_payload['video'] ?? []) as $key=>$path){
      $append_media($key, $path, 'video');
    }
    $legacy_series = $legacy_payload['series'] ?? ['xrs_7d'=>[],'protons_7d'=>[]];
  }

  if (!$api_payload && !$legacy_payload){
    $fallback = [
      'drap'        => 'drap/latest.png',
      'lasco_c2'    => 'nasa/lasco_c2/latest.jpg',
      'aia_304'     => 'nasa/aia_304/latest.jpg',
      'ovation_nh'  => 'aurora/viewline/tonight-north.png',
      'ovation_sh'  => 'aurora/viewline/tonight-south.png',
      'hmi_intensity'=> 'nasa/hmi_intensity/latest.jpg',
      'a_station'   => 'space/a_station/latest.png',
      'ccor1'       => 'nasa/ccor1/latest.jpg',
      'enlil'       => 'nasa/enlil/latest.mp4',
    ];
    foreach ($fallback as $k=>$rel){
      $atype = preg_match('#\.(mp4|mov)(\?.*)?$#i', $rel) ? 'video' : 'image';
      $append_media($k, $rel, $atype);
    }
  }

  $media_base = $base;

  if ($legacy_payload){
    $legacy_series = $legacy_payload['series'] ?? ['xrs_7d'=>[],'protons_7d'=>[]];
  } else {
    $legacy_series = ['xrs_7d'=>[],'protons_7d'=>[]];
  }

  $client_payload = [
    'series' => $structured_series,
    'legacySeries' => $legacy_series,
    'featureFlags' => $overlay_flags,
  ];

  $base = $media_base ? (rtrim($media_base, '/') . '/') : '';
  $img = [];
  foreach ($images as $key=>$entry){
    if (empty($entry['url'])) continue;
    $url = $entry['url'];
    $img[$key] = preg_match('#^https?://#', $url) ? $url : ($base . ltrim($url, '/'));
  }
  $vid_paths = [];
  foreach ($video as $key=>$entry){
    if (empty($entry['url'])) continue;
    $vurl = $entry['url'];
    $vid_paths[$key] = preg_match('#^https?://#', $vurl) ? $vurl : ($base . ltrim($vurl, '/'));
  }
  $vid = $vid_paths;

  ob_start(); ?>
  <?php
    $dbg_base = $media_base ?: '(none)';
    $dbg_imgc = count($images);
    $dbg_vidc = count($video);
    echo "\n<!-- ge-space-debug base={$dbg_base} images={$dbg_imgc} videos={$dbg_vidc} -->\n";
  ?>
  <section class="ge-panel ge-space">
    <div class="ge-headrow">
      <div class="ge-title">Space Dashboard</div>
      <?php if($updated): ?><div class="ge-updated">Updated <?php echo $updated; ?></div><?php endif; ?>
    </div>

    <div class="ge-grid">

      <!-- Solar disc -->
      <article class="ge-card">
        <h3>Solar disc (AIA 193/304 Å)</h3>
        <?php $solar_overlay = !empty($structured_series['goes_xray']['samples']); ?>
        <div class="visual-overlay<?php echo $solar_overlay ? '' : ' overlay-disabled'; ?>" data-overlay="solarOverlay" data-series-keys="<?php echo $solar_overlay ? 'goes_xray' : ''; ?>">
          <?php if(!empty($img['aia_primary'])): ?>
            <a href="<?php echo esc_attr($img['aia_primary']); ?>" target="_blank" rel="noopener">
              <img src="<?php echo esc_attr($img['aia_primary']); ?>" alt="SDO AIA latest" />
            </a>
          <?php elseif(!empty($img['aia_304'])): ?>
            <a href="<?php echo esc_attr($img['aia_304']); ?>" target="_blank" rel="noopener">
              <img src="<?php echo esc_attr($img['aia_304']); ?>" alt="SDO AIA 304Å latest" />
            </a>
          <?php elseif(!empty($img['hmi_intensity'])): ?>
            <a href="<?php echo esc_attr($img['hmi_intensity']); ?>" target="_blank" rel="noopener">
              <img src="<?php echo esc_attr($img['hmi_intensity']); ?>" alt="HMI Intensitygram latest" />
            </a>
          <?php else: ?>
            <div class="ge-note">Latest solar disc image unavailable.</div>
          <?php endif; ?>
          <?php if($solar_overlay): ?>
            <canvas id="solarOverlay" class="overlay-canvas" aria-hidden="true"></canvas>
            <button type="button" class="overlay-toggle" data-overlay-target="solarOverlay" aria-pressed="false">Toggle GOES X-ray overlay</button>
          <?php endif; ?>
        </div>

        <div class="spark-wrap">
          <div class="spark-head"><span id="sparkXrsVal">—</span></div>
          <div class="spark-box"><canvas id="sparkXrs" class="spark-canvas"></canvas></div>
          <div class="spark-cap">GOES X-ray (7d)</div>
        </div>
      </article>

      <!-- Aurora -->
      <article class="ge-card">
        <h3>Auroral Ovals</h3>
        <?php
          $aurora_keys = [];
          if (!empty($structured_series['aurora_power_north']['samples'])) $aurora_keys[] = 'aurora_power_north';
          if (!empty($structured_series['aurora_power_south']['samples'])) $aurora_keys[] = 'aurora_power_south';
        ?>
        <div class="visual-overlay<?php echo $aurora_keys ? '' : ' overlay-disabled'; ?>" data-overlay="auroraOverlay" data-series-keys="<?php echo esc_attr(implode(',', $aurora_keys)); ?>">
          <div class="ov-grid">
            <?php if(!empty($img['ovation_nh'])): ?>
              <figure>
                <a href="<?php echo esc_attr($img['ovation_nh']); ?>" target="_blank" rel="noopener">
                  <img src="<?php echo esc_attr($img['ovation_nh']); ?>" alt="Aurora NH" />
                </a>
                <figcaption>NH forecast</figcaption>
              </figure>
            <?php endif; ?>
            <?php if(!empty($img['ovation_sh'])): ?>
              <figure>
                <a href="<?php echo esc_attr($img['ovation_sh']); ?>" target="_blank" rel="noopener">
                  <img src="<?php echo esc_attr($img['ovation_sh']); ?>" alt="Aurora SH" />
                </a>
                <figcaption>SH forecast</figcaption>
              </figure>
            <?php endif; ?>
          </div>
          <?php if($aurora_keys): ?>
            <canvas id="auroraOverlay" class="overlay-canvas" aria-hidden="true"></canvas>
            <button type="button" class="overlay-toggle" data-overlay-target="auroraOverlay" aria-pressed="false">Toggle aurora power overlay</button>
          <?php endif; ?>
        </div>
        <div class="care-box">
          <h4>Care notes</h4>
          <ul>
            <li>High-lat GNSS caution during strong magnetometer spikes.</li>
            <li>Evening: manage light exposure if geomagnetic activity is elevated.</li>
            <li>Short daylight breaks may help nervous system stability.</li>
          </ul>
        </div>
      </article>

      <!-- Coronagraphs -->
      <article class="ge-card">
        <h3>Coronagraph / CMEs</h3>
        <div class="ov-grid">
          <?php if(!empty($img['soho_c2']) || !empty($img['lasco_c2'])): ?>
            <figure>
              <?php $c2 = !empty($img['soho_c2']) ? $img['soho_c2'] : $img['lasco_c2']; ?>
              <a href="<?php echo esc_attr($c2); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($c2); ?>" alt="SOHO/LASCO C2 latest" />
              </a>
              <figcaption>LASCO C2</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['lasco_c3'])): ?>
            <figure>
              <a href="<?php echo esc_attr($img['lasco_c3']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($img['lasco_c3']); ?>" alt="SOHO LASCO C3 latest" />
              </a>
              <figcaption>LASCO C3</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['ccor1_jpeg']) || !empty($img['ccor1'])): ?>
            <figure>
              <?php $ccor = !empty($img['ccor1_jpeg']) ? $img['ccor1_jpeg'] : $img['ccor1']; ?>
              <a href="<?php echo esc_attr($ccor); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($ccor); ?>" alt="GOES CCOR-1 latest" />
              </a>
              <figcaption>CCOR-1</figcaption>
            </figure>
          <?php endif; ?>
        </div>
        <?php if (!empty($vid['ccor1_mp4'])): ?>
          <video controls preload="metadata" controlslist="nodownload" style="width:100%;margin-top:8px;border-radius:8px;border:1px solid rgba(255,255,255,.08)">
            <source src="<?php echo esc_attr($vid['ccor1_mp4']); ?>" type="video/mp4" />
          </video>
        <?php endif; ?>
      </article>

      <!-- Geomagnetic -->
      <article class="ge-card">
        <h3>Geomagnetic Indices (Kp)</h3>
        <?php if(!empty($img['kp_station'])): ?>
          <a href="<?php echo esc_attr($img['kp_station']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo esc_attr($img['kp_station']); ?>" alt="Station K-index" />
          </a>
        <?php else: ?>
          <div class="ge-note">K-index plot unavailable.</div>
        <?php endif; ?>
        <div class="kp-legend">
          <div><span class="kp-box kp-g0"></span> G0 Kp 0–4 (quiet)</div>
          <div><span class="kp-box kp-g1"></span> G1 Kp 5 (minor)</div>
          <div><span class="kp-box kp-g2"></span> G2 Kp 6 (moderate)</div>
          <div><span class="kp-box kp-g3"></span> G3 Kp 7 (strong)</div>
          <div><span class="kp-box kp-g4"></span> G4 Kp 8 (severe)</div>
          <div><span class="kp-box kp-g5"></span> G5 Kp 9 (extreme)</div>
        </div>

        <div class="spark-wrap">
          <div class="spark-head"><span id="sparkProtonsVal">—</span></div>
          <div class="spark-box"><canvas id="sparkProtons" class="spark-canvas"></canvas></div>
          <div class="spark-cap">GOES Protons (7d)</div>
        </div>
        <div class="spark-wrap">
          <div class="spark-head"><span id="sparkBzVal">—</span></div>
          <div class="spark-box"><canvas id="sparkBz" class="spark-canvas"></canvas></div>
          <div class="spark-cap">IMF Bz (last 24h)</div>
        </div>
        <div class="spark-wrap">
          <div class="spark-head"><span id="sparkSwVal">—</span></div>
          <div class="spark-box"><canvas id="sparkSw" class="spark-canvas"></canvas></div>
          <div class="spark-cap">Solar wind speed (last 24h)</div>
        </div>
      </article>

      <!-- GEOSPACE -->
      <article class="ge-card">
        <h3>GEOSPACE Plots</h3>
        <div class="ov-grid">
          <?php foreach (['geospace_1d'=>'1 day','geospace_3h'=>'3 hours','geospace_7d'=>'7 days'] as $k=>$cap): if(!empty($img[$k])): ?>
            <figure>
              <a href="<?php echo esc_attr($img[$k]); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($img[$k]); ?>" alt="Geospace <?php echo esc_attr($cap); ?>" />
              </a>
              <figcaption><?php echo esc_html($cap); ?></figcaption>
            </figure>
          <?php endif; endforeach; ?>
        </div>
        <?php if (empty($img['geospace_1d']) && empty($img['geospace_3h']) && empty($img['geospace_7d'])): ?>
          <div class="ge-note">Geospace plots unavailable.</div>
        <?php endif; ?>
      </article>

      <!-- HF/DRAP & Indices -->
      <article class="ge-card">
        <h3>HF/DRAP & Indices</h3>
        <div class="ov-grid">
          <?php if(!empty($img['drap_global']) || !empty($img['drap'])): ?>
            <figure>
              <?php $drap = !empty($img['drap_global']) ? $img['drap_global'] : $img['drap']; ?>
              <a href="<?php echo esc_attr($drap); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($drap); ?>" alt="DRAP Global" />
              </a>
              <figcaption>DRAP global</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['a_station'])): ?>
            <figure>
              <a href="<?php echo esc_attr($img['a_station']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo esc_attr($img['a_station']); ?>" alt="Station A-index" />
              </a>
              <figcaption>Station A-index</figcaption>
            </figure>
          <?php endif; ?>
        </div>
      </article>

      <!-- Sunspots / HMI -->
      <article class="ge-card">
        <h3>Sunspots / HMI</h3>
        <?php if(!empty($img['hmi_intensity'])): ?>
          <a href="<?php echo esc_attr($img['hmi_intensity']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo esc_attr($img['hmi_intensity']); ?>" alt="HMI Intensitygram latest" />
          </a>
        <?php else: ?>
          <div class="ge-note">Sunspot image unavailable.</div>
        <?php endif; ?>
        <div class="cta-row"><a class="gaia-link" href="/aurora/#map">Aurora forecast →</a> <a class="gaia-link" href="/news/?category=solar_activity" style="margin-left:12px;">News →</a></div>
      </article>

      <!-- SWx Overview -->
      <article class="ge-card">
        <h3>SWx Overview</h3>
        <?php if(!empty($img['swx_overview_small'])): ?>
          <a href="<?php echo esc_attr($img['swx_overview_small']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo esc_attr($img['swx_overview_small']); ?>" alt="Space Weather Overview" />
          </a>
        <?php else: ?>
          <div class="ge-note">SWx overview unavailable.</div>
        <?php endif; ?>
      </article>

    </div>

    <style>
      .ge-headrow{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;gap:8px;flex-wrap:wrap}
      .ge-title{font-size:1.15rem;font-weight:700}
      .ge-updated{opacity:.85;font-size:.9rem}
      .ge-space .ge-grid{ display:grid; gap:12px }
      @media(min-width:900px){ .ge-space .ge-grid{ grid-template-columns:repeat(2,1fr) } }
      .ge-space img{ width:100%; height:auto; border-radius:8px; border:1px solid rgba(255,255,255,.08) }
      .ov-grid{ display:grid; gap:8px } @media(min-width:640px){ .ov-grid{ grid-template-columns:repeat(2,1fr) } }
      figure{ margin:0 } figcaption{ text-align:center; font-size:.85rem; opacity:.85; margin-top:4px }
      .care-box{ margin-top:8px } .care-box h4{ margin:.25rem 0 } .care-box ul{ margin:0; padding-left:18px; line-height:1.4 }
      .spark-wrap{ margin-top:8px }
      .spark-cap{ font-size:.85rem; opacity:.85; margin-top:4px }
      .cta-row{ margin-top:8px }
      .gaia-link{ color:inherit; text-decoration:none; border-bottom:1px dotted rgba(255,255,255,.25) }
      .gaia-link:hover{ border-bottom-color: rgba(255,255,255,.6) }
      .ge-note{ opacity:.85; font-size:.9rem; margin-top:6px }
      .kp-legend{ display:grid; grid-template-columns:repeat(2,1fr); gap:6px; margin:8px 0 }
      .kp-box{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:6px; vertical-align:-2px }
      .kp-g0{ background:#3a9a5d } .kp-g1{ background:#b3e67a } .kp-g2{ background:#ffd166 } .kp-g3{ background:#ff9f1c } .kp-g4{ background:#ff6b6b } .kp-g5{ background:#a40000 }

      /* Spark charts: fixed height; add head row for latest value */
      .spark-box{ position:relative; width:100%; height:120px; min-height:120px; }
      .spark-canvas{ display:block; width:100% !important; height:100% !important; }
      .spark-head{ font-size:.9rem; opacity:.9; margin-bottom:6px; display:flex; justify-content:flex-end; }
      .visual-overlay{ position:relative; }
      .visual-overlay .overlay-canvas{ position:absolute; inset:0; width:100% !important; height:100% !important; pointer-events:none; opacity:0; transition:opacity .3s ease; }
      .visual-overlay.overlay-active .overlay-canvas{ opacity:.85; }
      .visual-overlay .overlay-toggle{ position:absolute; top:8px; right:8px; background:rgba(0,0,0,.6); color:#fff; border:none; border-radius:999px; padding:4px 12px; font-size:.8rem; cursor:pointer; }
      .visual-overlay.overlay-disabled .overlay-toggle{ display:none; }
      .visual-overlay .overlay-toggle:focus{ outline:2px solid rgba(255,255,255,.6); outline-offset:2px; }
      .visual-overlay + .spark-wrap { margin-top: 8px; clear: both; }
      /* Cap very tall media on mobile/desktop (kept from previous fix) */
      @media(max-width:640px){
        .ge-space img,
        .ge-space video{ max-height:360px; object-fit:contain; }
      }
      @media(min-width:641px){
        .ge-space img,
        .ge-space video{ max-height:560px; object-fit:contain; }
      }
    </style>

    <!-- Chart.js + date adapter for time-series sparks -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
    <script>
      (function(){
        const visualsPayload = <?php echo wp_json_encode($client_payload); ?> || {};
        const structuredSeries = visualsPayload.series || {};
        const legacySeries = visualsPayload.legacySeries || {};
        const overlayCharts = {};

        function whenSparkReady(cb){
          if (window.GaiaSpark && window.GaiaSpark.renderSpark) {
            cb(window.GaiaSpark);
            return;
          }
          const handler = () => {
            window.removeEventListener('gaiaSparkReady', handler);
            if (window.GaiaSpark && window.GaiaSpark.renderSpark) {
              cb(window.GaiaSpark);
            }
          };
          window.addEventListener('gaiaSparkReady', handler, { once:true });
        }

        function renderSpark(id, data, options){
          whenSparkReady((spark) => {
            spark.renderSpark(id, data, options);
          });
        }

        function latestPoint(arr){ if(!arr || !arr.length) return null; return arr[arr.length-1]; }
        function fmtXray(value){
          const v = Number(value||0);
          if (!isFinite(v) || v<=0) return '—';
          const logv = Math.log10(v);
          const cls = (logv>=-4)?'X':(logv>=-5)?'M':(logv>=-6)?'C':(logv>=-7)?'B':'A';
          const scale = {'A':1e-8,'B':1e-7,'C':1e-6,'M':1e-5,'X':1e-4}[cls];
          const mag = (v/scale).toFixed(1);
          return `${mag}${cls} (${v.toExponential(1)} W/m²)`;
        }

        function toSeriesXrs(rows){
          if (!Array.isArray(rows) || rows.length === 0) return [];
          if (rows.length && typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
            const out = [];
            rows.forEach(r=>{
              const t = r.time_tag || r.time || r.timestamp || null;
              const c1 = parseFloat(r.xray_flux_1 || r.short || r['flux_short'] || 0);
              const c2 = parseFloat(r.xray_flux_2 || r.long  || r['flux_long']  || 0);
              const v  = Math.max(isFinite(c1)?c1:0, isFinite(c2)?c2:0);
              if (t) {
                const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
                out.push({x:new Date(ts), y:v});
              }
            });
            return out;
          }
          let start = 0;
          if (Array.isArray(rows[0]) && rows[0].length && typeof rows[0][0] === 'string') {
            const maybeHeader = rows[0].join(',').toLowerCase();
            if (maybeHeader.includes('time') || maybeHeader.includes('short') || maybeHeader.includes('long')) start = 1;
          }
          const out = [];
          for (let i = start; i < rows.length; i++) {
            const r = rows[i]; if (!Array.isArray(r)) continue;
            const t = r[0];
            const c1 = parseFloat(r[1]);
            const c2 = parseFloat(r[2]);
            const v  = Math.max(isFinite(c1)?c1:0, isFinite(c2)?c2:0);
            if (t) {
              const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
              out.push({x:new Date(ts), y:v});
            }
          }
          return out;
        }

        function structuredSamples(key){
          const entry = structuredSeries[key];
          if (!entry || !Array.isArray(entry.samples)) return [];
          return entry.samples.map((pt)=>{
            if (!pt || !pt.ts) return null;
            const dt = new Date(pt.ts);
            if (Number.isNaN(dt.getTime())) return null;
            return { x: dt, y: Number(pt.value||0), raw: pt };
          }).filter(Boolean);
        }

        function setVal(id, text){ const el=document.getElementById(id); if(el) el.textContent=text; }

        function ensureOverlay(canvasId, keys){
          if (overlayCharts[canvasId]) return overlayCharts[canvasId];
          const ctx = document.getElementById(canvasId);
          if (!ctx) return null;
          const datasets = [];
          keys.forEach((key)=>{
            let samples = structuredSamples(key);
            if (!samples.length && key === 'goes_xray'){
              samples = toSeriesXrs(legacySeries.xrs_7d || []);
            } else if (!samples.length && key === 'goes_protons'){
              const out=[];
              (legacySeries.protons_7d || []).forEach(r=>{ const t=r.time_tag||r.time||null; const v=parseFloat(r.integral_protons_10MeV||r.flux||0); if(t&&isFinite(v)) out.push({x:new Date(t), y:v}); });
              samples = out;
            }
            if (!samples.length) return;
            const meta = (structuredSeries[key] && structuredSeries[key].meta) || {};
            const color = meta.color || '#7fc8ff';
            datasets.push({
              label: meta.label || key,
              data: samples,
              parsing: false,
              borderColor: color,
              borderWidth: 2,
              pointRadius: 0,
              tension: 0.25,
              fill: false,
            });
          });
          if (!datasets.length) return null;
          overlayCharts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'nearest', intersect: false },
              plugins: { legend: { display: true, labels:{ color:'#eee' } } },
              scales: {
                x: { type: 'time', ticks:{ color:'#ddd' }, grid:{ color:'rgba(255,255,255,.2)' } },
                y: { ticks:{ color:'#ddd' }, grid:{ color:'rgba(255,255,255,.15)' } }
              }
            }
          });
          return overlayCharts[canvasId];
        }

        document.querySelectorAll('[data-overlay]').forEach((wrapper)=>{
          const canvasId = wrapper.getAttribute('data-overlay');
          const keys = (wrapper.getAttribute('data-series-keys') || '').split(',').map(k=>k.trim()).filter(Boolean);
          if (!canvasId || !keys.length) return;
          const btn = wrapper.querySelector('[data-overlay-toggle]');
          if (btn){
            btn.addEventListener('click', () => {
              const active = wrapper.classList.toggle('overlay-active');
              btn.setAttribute('aria-pressed', active ? 'true' : 'false');
              if (active){ ensureOverlay(canvasId, keys); }
            });
          } else {
            ensureOverlay(canvasId, keys);
            wrapper.classList.add('overlay-active');
          }
        });

        (async function(){
          let arr = structuredSamples('goes_xray');
          if (!arr.length){
            try {
              let xrsRaw = legacySeries.xrs_7d || [];
              if (!Array.isArray(xrsRaw) || xrsRaw.length === 0) {
                const live = await fetch('https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json', {cache:'no-store'});
                if (live.ok) xrsRaw = await live.json();
              }
              arr = toSeriesXrs(xrsRaw);
            } catch(e){}
          }
          if (arr.length > 1000) arr = arr.slice(-1000);
          renderSpark('sparkXrs', arr, { xLabel:'UTC time', yLabel:'GOES X-ray flux', units:'W/m²', yMin:0, color:'#7fc8ff' });
          const lp = (arr.length ? arr[arr.length-1] : null);
          if (lp) {
            const sample = lp.raw;
            const txt = sample && sample.class ? `${sample.class} (${lp.y.toExponential(1)} W/m²)` : fmtXray(lp.y);
            setVal('sparkXrsVal', txt);
          } else {
            setVal('sparkXrsVal', '—');
          }
        })();

        (async function(){
          function toSeriesProtons(rows){
            if (!Array.isArray(rows)) return [];
            const out = [];
            // object form
            if (rows.length && typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
              rows.forEach(r=>{
                const t = r.time_tag || r.time || r.timestamp || null;
                const v = parseFloat(r.integral_protons_10MeV || r.flux || r.value || 0);
                if (!t || !isFinite(v)) return;
                const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
                out.push({ x: new Date(ts), y: v });
              });
              return out;
            }
            // 2D array form (skip header)
            let start = 0;
            if (Array.isArray(rows[0]) && rows[0].length && typeof rows[0][0] === 'string') start = 1;
            for (let i=start;i<rows.length;i++){
              const r = rows[i];
              if (!Array.isArray(r)) continue;
              const t = r[0];
              const v = parseFloat(r[1] ?? r[2] ?? 0);
              if (!t || !isFinite(v)) continue;
              const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
              out.push({ x: new Date(ts), y: v });
            }
            return out;
          }

          let arr = structuredSamples('goes_protons');
          if (!arr.length && Array.isArray(legacySeries.protons_7d) && legacySeries.protons_7d.length){
            arr = toSeriesProtons(legacySeries.protons_7d);
          }
          if (!arr.length){
            try {
              // Live SWPC fallback (primary integral protons 7-day)
              const live = await fetch('https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json', {cache:'no-store'});
              if (live.ok) {
                const json = await live.json();
                arr = toSeriesProtons(json);
              }
            } catch(e){}
          }
          const sliced = arr.length > 1000 ? arr.slice(-1000) : arr;
          renderSpark('sparkProtons', sliced, { xLabel:'UTC time', yLabel:'Proton flux', units:'pfu', yMin:0, color:'#ffd089' });
          const lp = latestPoint(sliced);
          setVal('sparkProtonsVal', lp ? (lp.y.toFixed(0)+' pfu') : '—');
        })();

        Promise.all([
          fetch('https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json',{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
          fetch('https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json',{cache:'no-store'}).then(r=>r.json()).catch(()=>null)
        ]).then(([mag,plasma])=>{
          try{
            const mRows = Array.isArray(mag)? mag.slice(1):[];
            const bz = [];
            mRows.forEach(r=>{
              const t = r[0], v = parseFloat(r[3]);
              if (!t || !isFinite(v)) return;
              const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
              bz.push({ x: new Date(ts), y: v });
            });
            renderSpark('sparkBz', bz, { xLabel:'UTC time', yLabel:'IMF Bz', units:'nT', zeroLine:true, color:'#a7d3ff' });
            const lp = latestPoint(bz); setVal('sparkBzVal', lp ? (lp.y.toFixed(1)+' nT') : '—');
          }catch(e){}
          try{
            const pRows = Array.isArray(plasma)? plasma.slice(1):[];
            const sw = [];
            pRows.forEach(r=>{
              const t = r[0], v = parseFloat(r[2]);
              if (!t || !isFinite(v)) return;
              const ts = (typeof t === 'string' && !t.endsWith('Z')) ? (t + 'Z') : t;
              sw.push({ x: new Date(ts), y: v });
            });
            renderSpark('sparkSw', sw, { xLabel:'UTC time', yLabel:'Solar wind speed', units:'km/s', yMin:0, color:'#ffd089' });
            const lp = latestPoint(sw); setVal('sparkSwVal', lp ? (lp.y.toFixed(0)+' km/s') : '—');
          }catch(e){}
        });
      })();
    </script>
  </section>
  <?php return ob_get_clean();
});
