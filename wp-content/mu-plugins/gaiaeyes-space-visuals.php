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
  ob_start(); ?>
  <section class="ge-panel ge-space">
    <div class="ge-grid">
      <article class="ge-card"><h3>Solar disc (SUVI 131Å)</h3>
        <?php if(!empty($img['suvi_131_latest'])): ?>
          <img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['suvi_131_latest']); ?>" alt="GOES SUVI 131 latest" />
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
        <?php if(!empty($img['goes_ccor1'])): ?><figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img['goes_ccor1']); ?>" alt="GOES CCOR-1 latest" /><figcaption>GOES CCOR-1</figcaption></figure><?php endif; ?>
      </div></article>

      <article class="ge-card"><h3>Magnetometers</h3><div class="ov-grid">
        <?php foreach (['mag_kiruna'=>'Kiruna','mag_canmos'=>'CANMOS','mag_hobart'=>'Hobart'] as $k=>$cap): if(!empty($img[$k])): ?>
          <figure><img src="https://gaiaeyeshq.github.io/gaiaeyes-media/<?php echo esc_attr($img[$k]); ?>" alt="Magnetometer <?php echo esc_attr($cap); ?>" /><figcaption><?php echo esc_html($cap); ?></figcaption></figure>
        <?php endif; endforeach; ?>
      </div>
        <div class="spark-wrap">
          <canvas id="sparkProtons" height="60"></canvas>
          <div class="spark-cap">GOES Protons (7d)</div>
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
      })();
    </script>
  </section>
  <?php return ob_get_clean();
});
