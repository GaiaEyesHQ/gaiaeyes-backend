<?php
/**
 * Plugin Name: Gaia Eyes – Space Visuals (Enhanced UI)
 * Description: Visuals + spark charts (X-rays, protons, Bz, SW) + care notes + Kp legend using space_live.json.
 * Version: 1.2.0
 */
if (!defined('ABSPATH')) exit;

function ge_json_cached($url, $cache_min){
  $ttl = max(1, intval($cache_min)) * MINUTE_IN_SECONDS;
  $k = 'ge_json_' . md5($url);
  $j = get_transient($k);
  if ($j===false){
    $r = wp_remote_get(esc_url_raw($url), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
    if (!is_wp_error($r) && wp_remote_retrieve_response_code($r)===200){
      $j = json_decode(wp_remote_retrieve_body($r), true);
      set_transient($k, $j, $ttl);
    }
  }
  return is_array($j)? $j : null;
}

add_shortcode('gaia_space_detail', function($atts){
  $a = shortcode_atts(['url'=>'https://gaiaeyeshq.github.io/gaiaeyes-media/data/space_live.json','cache'=>5], $atts, 'gaia_space_detail');
  $j = ge_json_cached($a['url'], $a['cache']);
  if (!$j) return '<div class="ge-card">Space dashboard unavailable.</div>';
  $img = $j['images'] ?? [];
  $ser = $j['series'] ?? ['xrs_7d'=>[],'protons_7d'=>[]];
  $vid = $j['video'] ?? [];
  $missing = $j['missing'] ?? [];
  $updated = !empty($j['timestamp_utc']) ? esc_html($j['timestamp_utc']) : '';

  // helper for clickable image
  $base = 'https://gaiaeyeshq.github.io/gaiaeyes-media/';

  ob_start(); ?>
  <section class="ge-panel ge-space">
    <div class="ge-headrow">
      <div class="ge-title">Space Dashboard</div>
      <?php if($updated): ?><div class="ge-updated">Updated <?php echo $updated; ?></div><?php endif; ?>
    </div>

    <div class="ge-grid">

      <!-- Solar disc -->
      <article class="ge-card">
        <h3>Solar disc (AIA 193/304 Å)</h3>
        <?php if(!empty($img['aia_primary'])): ?>
          <a href="<?php echo $base . esc_attr($img['aia_primary']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo $base . esc_attr($img['aia_primary']); ?>" alt="SDO AIA latest" />
          </a>
        <?php elseif(!empty($img['hmi_intensity'])): ?>
          <a href="<?php echo $base . esc_attr($img['hmi_intensity']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo $base . esc_attr($img['hmi_intensity']); ?>" alt="HMI Intensitygram latest" />
          </a>
        <?php else: ?>
          <div class="ge-note">Latest solar disc image unavailable.</div>
        <?php endif; ?>

        <div class="spark-wrap">
          <canvas id="sparkXrs" height="60"></canvas>
          <div class="spark-cap">GOES X-ray (7d)</div>
        </div>
      </article>

      <!-- Aurora -->
      <article class="ge-card">
        <h3>Auroral Ovals</h3>
        <div class="ov-grid">
          <?php if(!empty($img['ovation_nh'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['ovation_nh']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['ovation_nh']); ?>" alt="Aurora NH" />
              </a>
              <figcaption>NH forecast</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['ovation_sh'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['ovation_sh']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['ovation_sh']); ?>" alt="Aurora SH" />
              </a>
              <figcaption>SH forecast</figcaption>
            </figure>
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
          <?php if(!empty($img['soho_c2'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['soho_c2']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['soho_c2']); ?>" alt="SOHO C2 latest" />
              </a>
              <figcaption>SOHO C2</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['lasco_c3'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['lasco_c3']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['lasco_c3']); ?>" alt="SOHO LASCO C3 latest" />
              </a>
              <figcaption>LASCO C3</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['ccor1_jpeg'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['ccor1_jpeg']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['ccor1_jpeg']); ?>" alt="GOES CCOR-1 latest" />
              </a>
              <figcaption>CCOR-1</figcaption>
            </figure>
          <?php endif; ?>
        </div>
        <?php if (!empty($vid['ccor1_mp4'])): ?>
          <video controls preload="metadata" controlslist="nodownload" style="width:100%;margin-top:8px;border-radius:8px;border:1px solid rgba(255,255,255,.08)">
            <source src="<?php echo $base . esc_attr($vid['ccor1_mp4']); ?>" type="video/mp4" />
          </video>
        <?php endif; ?>
      </article>

      <!-- Geomagnetic -->
      <article class="ge-card">
        <h3>Geomagnetic Indices (Kp)</h3>
        <?php if(!empty($img['kp_station'])): ?>
          <a href="<?php echo $base . esc_attr($img['kp_station']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo $base . esc_attr($img['kp_station']); ?>" alt="Station K-index" />
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
          <canvas id="sparkProtons" height="60"></canvas>
          <div class="spark-cap">GOES Protons (7d)</div>
        </div>
        <div class="spark-wrap">
          <canvas id="sparkBz" height="60"></canvas>
          <div class="spark-cap">IMF Bz (last 24h)</div>
        </div>
        <div class="spark-wrap">
          <canvas id="sparkSw" height="60"></canvas>
          <div class="spark-cap">Solar wind speed (last 24h)</div>
        </div>
      </article>

      <!-- GEOSPACE -->
      <article class="ge-card">
        <h3>GEOSPACE Plots</h3>
        <div class="ov-grid">
          <?php foreach (['geospace_1d'=>'1 day','geospace_3h'=>'3 hours','geospace_7d'=>'7 days'] as $k=>$cap): if(!empty($img[$k])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img[$k]); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img[$k]); ?>" alt="Geospace <?php echo esc_attr($cap); ?>" />
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
          <?php if(!empty($img['drap_global'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['drap_global']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['drap_global']); ?>" alt="DRAP Global" />
              </a>
              <figcaption>DRAP global</figcaption>
            </figure>
          <?php endif; ?>
          <?php if(!empty($img['a_station'])): ?>
            <figure>
              <a href="<?php echo $base . esc_attr($img['a_station']); ?>" target="_blank" rel="noopener">
                <img src="<?php echo $base . esc_attr($img['a_station']); ?>" alt="Station A-index" />
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
          <a href="<?php echo $base . esc_attr($img['hmi_intensity']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo $base . esc_attr($img['hmi_intensity']); ?>" alt="HMI Intensitygram latest" />
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
          <a href="<?php echo $base . esc_attr($img['swx_overview_small']); ?>" target="_blank" rel="noopener">
            <img src="<?php echo $base . esc_attr($img['swx_overview_small']); ?>" alt="Space Weather Overview" />
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
      .spark-wrap{ margin-top:8px } .spark-cap{ font-size:.85rem; opacity:.85; margin-top:2px }
      .cta-row{ margin-top:8px }
      .gaia-link{ color:inherit; text-decoration:none; border-bottom:1px dotted rgba(255,255,255,.25) }
      .gaia-link:hover{ border-bottom-color: rgba(255,255,255,.6) }
      .ge-note{ opacity:.85; font-size:.9rem; margin-top:6px }
      .kp-legend{ display:grid; grid-template-columns:repeat(2,1fr); gap:6px; margin:8px 0 }
      .kp-box{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:6px; vertical-align:-2px }
      .kp-g0{ background:#3a9a5d } .kp-g1{ background:#b3e67a } .kp-g2{ background:#ffd166 } .kp-g3{ background:#ff9f1c } .kp-g4{ background:#ff6b6b } .kp-g5{ background:#a40000 }
    </style>

    <!-- Chart.js + date adapter for time-series sparks -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
    <script>
      (function(){
        const ser = <?php echo wp_json_encode($ser); ?> || {};
        function drawSpark(id, data, color){
          const el = document.getElementById(id); if(!el) return;
          const ctx = el.getContext('2d');
          new Chart(ctx, {
            type:'line',
            data:{ datasets:[{ data:data, borderColor:color, borderWidth:1.6, tension:.2, pointRadius:0 }]},
            options:{ parsing:false, responsive:true, maintainAspectRatio:false, animation:false,
              scales:{ x:{ type:'time', time:{ unit:'hour' }, display:false }, y:{ display:false } },
              plugins:{ legend:{display:false}, tooltip:{enabled:false} }
            }
          });
        }
        function toSeriesXrs(rows){
          const out=[]; (rows||[]).forEach(r=>{
            const t = r.time_tag || r.time || r.timestamp || null;
            const c1 = parseFloat(r.xray_flux_1 || r.short || 0);
            const c2 = parseFloat(r.xray_flux_2 || r.long  || 0);
            const v  = Math.max(isFinite(c1)?c1:0, isFinite(c2)?c2:0);
            if (t) out.push({x:new Date(t), y:v});
          }); return out.slice(-240);
        }
        function fetchJson(url){ return fetch(url, {cache:'no-store'}).then(r=>r.json()).catch(()=>null); }
        function toSeriesBz(rows){
          const out=[]; (rows||[]).slice(1).slice(-300).forEach(r=>{
            try{ const t=r[0]; const bz=parseFloat(r[3]); if(t&&isFinite(bz)) out.push({x:new Date(t), y:bz}); }catch(e){}
          }); return out;
        }
        function toSeriesSw(rows){
          const out=[]; (rows||[]).slice(1).slice(-300).forEach(r=>{
            try{ const t=r[0]; const spd=parseFloat(r[2]); if(t&&isFinite(spd)) out.push({x:new Date(t), y:spd}); }catch(e){}
          }); return out;
        }
        // Sparks: XRS from JSON, Protons from JSON, Bz/Speed from SWPC 1-day
        try{ drawSpark('sparkXrs', toSeriesXrs(ser.xrs_7d), '#7fc8ff'); }catch(e){}
        try{ // Protons (7d)
          const p = ser.protons_7d || [];
          const out=[]; (p||[]).forEach(r=>{ const t=r.time_tag||r.time||null; const v=parseFloat(r.integral_protons_10MeV||r.flux||0); if(t&&isFinite(v)) out.push({x:new Date(t), y:v}); });
          drawSpark('sparkProtons', out.slice(-240), '#ffd089');
        }catch(e){}
        Promise.all([
          fetchJson('https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json'),
          fetchJson('https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json')
        ]).then(([mag,plasma])=>{
          try{ drawSpark('sparkBz', toSeriesBz(mag||[]), '#a7d3ff'); }catch(e){}
          try{ drawSpark('sparkSw', toSeriesSw(plasma||[]), '#ffd089'); }catch(e){}
        });
      })();
    </script>
  </section>
  <?php return ob_get_clean();
});
