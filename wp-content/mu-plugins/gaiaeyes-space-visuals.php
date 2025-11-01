<?php
/**
 * Plugin Name: Gaia Eyes – Space Visuals (Enhanced)
 * Description: Visuals + spark charts (X-rays, protons) + care notes using space_live.json.
 * Version: 1.1.0
 */
if (!defined('ABSPATH')) exit;

function ge_json_cached($url, $cache_min){
  $ttl = max(1, intval($cache_min)) * MINUTE_IN_SECONDS;
  $k = 'ge_json_' . md5($url);
  $j = get_transient($k);
  if ($j===false){
    $r = wp_remote_get(esc_url_raw($url), ['timeout'=>8,'headers'=>['Accept'=>'application/json']]);
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
  $img = $j['images'] ?? []; $ser = $j['series'] ?? ['xrs_7d'=>[],'protons_7d'=>[]];
  $missing = $j['missing'] ?? [];
  ob_start(); ?>
  <section class="ge-panel ge-space">
    <div class="ge-grid">
      <article class="ge-card"><h3>Solar disc (AIA 193/304 Å)</h3>
        <?php if(!empty($img['aia_primary'])): ?>
          <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['aia_primary']); ?>" alt="SDO AIA latest" />
        <?php elseif(!empty($img['suvi_131_latest'])): ?>
          <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['suvi_131_latest']); ?>" alt="GOES SUVI latest" />
        <?php else: ?>
          <div class="ge-note">Latest solar disc image unavailable.</div>
        <?php endif; ?>
        <div class="spark-wrap">
          <canvas id="sparkXrs" height="60"></canvas>
          <div class="spark-cap">GOES X-ray (7d)</div>
        </div>
      </article>

      <article class="ge-card"><h3>Auroral Ovals</h3><div class="ov-grid">
        <?php if(!empty($img['ovation_nh'])): ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['ovation_nh']); ?>" alt="Aurora NH" /><figcaption>NH forecast</figcaption></figure><?php endif; ?>
        <?php if(!empty($img['ovation_sh'])): ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['ovation_sh']); ?>" alt="Aurora SH" /><figcaption>SH forecast</figcaption></figure><?php endif; ?>
      </div>
        <div class="care-box">
          <h4>Care notes</h4>
          <ul>
            <li>High-lat GNSS caution during strong magnetometer spikes.</li>
            <li>Evening: manage light exposure if geomagnetic activity boosted.</li>
            <li>Short daylight breaks may help nervous system stability.</li>
          </ul>
        </div>
      </article>

      <article class="ge-card"><h3>Coronagraph / CMEs</h3><div class="ov-grid">
        <?php if(!empty($img['soho_c2'])): ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['soho_c2']); ?>" alt="SOHO C2 latest" /><figcaption>SOHO C2</figcaption></figure><?php endif; ?>
        <?php if(!empty($img['lasco_c3'])): ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['lasco_c3']); ?>" alt="SOHO LASCO C3 latest" /><figcaption>LASCO C3</figcaption></figure><?php endif; ?>
      </div></article>

      <article class="ge-card"><h3>Geomagnetic Indices (Kp)</h3>
        <?php if(!empty($img['kp_plot'])): ?>
          <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['kp_plot']); ?>" alt="Planetary K-index plot" />
        <?php else: ?>
          <div class="ge-note">K-index plot unavailable.</div>
        <?php endif; ?>
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

      <article class="ge-card"><h3>Sunspots / HMI</h3>
        <?php if(!empty($img['hmi_intensity'])): ?><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['hmi_intensity']); ?>" alt="HMI Intensitygram latest" /><?php endif; ?>
        <div class="cta-row"><a class="gaia-link" href="/aurora/#map">Aurora forecast →</a> <a class="gaia-link" href="/news/?category=solar_activity" style="margin-left:12px;">News →</a></div>
      </article>
    </div>
    <style>
      .ge-space .ge-grid{ display:grid; gap:12px }
      @media(min-width:900px){ .ge-space .ge-grid{ grid-template-columns:repeat(2,1fr) } }
      .ge-space img{ width:100%; height:auto; border-radius:8px; border:1px solid rgba(255,255,255,.08) }
      .ov-grid{ display:grid; gap:8px } @media(min-width:640px){ .ov-grid{ grid-template-columns:repeat(2,1fr) } }
      .care-box{ margin-top:8px } .care-box h4{ margin:.25rem 0 } .care-box ul{ margin:0; padding-left:18px; line-height:1.4 }
      .spark-wrap{ margin-top:8px } .spark-cap{ font-size:.85rem; opacity:.85; margin-top:2px }
      .cta-row{ margin-top:8px }
      .gaia-link{ color:inherit; text-decoration:none; border-bottom:1px dotted rgba(255,255,255,.25) }
      .gaia-link:hover{ border-bottom-color: rgba(255,255,255,.6) }
      .ge-note{ opacity:.85; font-size:.9rem; margin-top:6px }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
      (function(){
        const ser = <?php echo wp_json_encode($ser); ?> || {};
        function toSeriesXrs(rows){
          // rows are array of objects; map to [time,value] (use highest flux of two channels)
          const out = [];
          (rows||[]).forEach(r => {
            const t = r.time_tag || r.time || r.timestamp || null;
            const c1 = parseFloat(r.xray_flux_1 || r.short || 0);
            const c2 = parseFloat(r.xray_flux_2 || r.long || 0);
            const v = Math.max(isFinite(c1)?c1:0, isFinite(c2)?c2:0);
            if (t) out.push({x:new Date(t), y:v});
          });
          return out.slice(-240);
        }
        function toSeriesProtons(rows){
          const out = [];
          (rows||[]).forEach(r => {
            const t = r.time_tag || r.time || null;
            const v = parseFloat(r.integral_protons_10MeV || r.flux || 0);
            if (t) out.push({x:new Date(t), y:isFinite(v)?v:0});
          });
          return out.slice(-240);
        }
        function drawSpark(id, data, color){
          const el = document.getElementById(id); if(!el) return;
          const ctx = el.getContext('2d');
          new Chart(ctx, {
            type:'line',
            data:{ datasets:[{ data:data, borderColor:color, borderWidth:1.5, tension:.2, pointRadius:0 }]},
            options:{ parsing:false, responsive:true, maintainAspectRatio:false, animation:false,
              scales:{ x:{ type:'time', time:{ unit:'day' }, display:false }, y:{ display:false } },
              plugins:{ legend:{display:false}, tooltip:{enabled:false} }
            }
          });
        }
        try{
          drawSpark('sparkXrs', toSeriesXrs(ser.xrs_7d), '#7fc8ff');
          drawSpark('sparkProtons', toSeriesProtons(ser.protons_7d), '#ffd089');
        }catch(e){}

        // Fetch SWPC 1-day JSON for Bz and plasma speed and render sparks
        function fetchJson(url){ return fetch(url, {cache:'no-store'}).then(r=>r.json()); }
        function toSeriesBz(rows){
          // mag-1-day.json rows: [time_tag, bx, by, bz, bt, lat, lon]
          const out=[]; (rows||[]).slice(-300).forEach(r=>{ try{
            const t = r[0]; const bz = parseFloat(r[3]);
            if (t && isFinite(bz)) out.push({x:new Date(t), y:bz});
          }catch(e){} }); return out;
        }
        function toSeriesSw(rows){
          // plasma-1-day.json rows: [time_tag, density, speed, temperature]
          const out=[]; (rows||[]).slice(-300).forEach(r=>{ try{
            const t = r[0]; const spd = parseFloat(r[2]);
            if (t && isFinite(spd)) out.push({x:new Date(t), y:spd});
          }catch(e){} }); return out;
        }
        Promise.all([
          fetchJson('https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json').catch(()=>null),
          fetchJson('https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json').catch(()=>null)
        ]).then(([mag,plasma])=>{
          try{
            const magRows = Array.isArray(mag)? mag.slice(1) : [];
            const plaRows = Array.isArray(plasma)? plasma.slice(1) : [];
            drawSpark('sparkBz', toSeriesBz(magRows), '#a7d3ff');
            drawSpark('sparkSw', toSeriesSw(plaRows), '#ffd089');
          }catch(e){}
        });
      })();
    </script>
  </section>
  <?php return ob_get_clean();
});
