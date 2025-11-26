<?php
/**
 * Plugin Name: Gaia Eyes – Mini Kp Badge
 * Description: Adds a small live Kp indicator badge using the Gaia Eyes JSON feed. Theme-agnostic (header or body fallback).
 * Version: 1.1.0
 * Author: Gaia Eyes
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

require_once __DIR__ . '/gaiaeyes-api-helpers.php';

/**
 * Insert a small script in <head> that:
 * 1) Tries to append the badge inside common Neve header containers.
 * 2) Falls back to wp_body_open if header not found after retries.
 */
add_action( 'wp_head', function () {
	?>
	<script>
	(function(){
	  var SELECTORS = [
	    'header.header-main','header.site-header','header.header',
	    '.nv-header','.hfg_header','#header','.header-main-content'
	  ];
	  function findHeader(){
	    for (var i=0;i<SELECTORS.length;i++){
	      var h = document.querySelector(SELECTORS[i]);
	      if (h) return h;
	    }
	    return null;
	  }
	  function insert(){
	    var header = findHeader();
	    if (!header) return setTimeout(insert, 300);
	    header.classList.add('gaia-kp-host');

	    // Ensure a single badge bar container (right side)
	    var bar = document.getElementById('gaia-badges');
	    if (!bar){
	      bar = document.createElement('div');
	      bar.id = 'gaia-badges';
	      bar.style.cssText = 'display:flex;gap:8px;align-items:center;';
	      header.appendChild(bar);
	    }

	    // If a legacy KP badge exists elsewhere, move it into the bar
	    var legacyKp = document.getElementById('gaia-kp-badge');
	    if (legacyKp && legacyKp.parentElement !== bar){
	      bar.appendChild(legacyKp);
	    }
	    // If no KP badge yet, create one
	    if (!document.getElementById('gaia-kp-badge')){
	      var kp = document.createElement('div');
	      kp.id = 'gaia-kp-badge';
	      kp.textContent = 'Kp …';
	      kp.setAttribute('aria-live','polite');
	      kp.style.cssText = [
	        'display:inline-block',
	        'background:#111','color:#fff','border-radius:16px',
	        'padding:4px 10px','font-size:13px',
	        'font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif',
	        'box-shadow:0 0 6px rgba(0,0,0,.3)','transition:background .3s, box-shadow .3s'
	      ].join(';');
	      bar.appendChild(kp);
	    }

	    // Ensure a Schumann badge in the same bar
	    if (!document.getElementById('gaia-sch-badge')){
	      var sch = document.createElement('div');
	      sch.id = 'gaia-sch-badge';
	      sch.textContent = 'F1 …';
	      sch.setAttribute('aria-live','polite');
	      sch.style.cssText = [
	        'display:inline-block',
	        'background:#111','color:#fff','border-radius:16px',
	        'padding:4px 10px','font-size:13px',
	        'font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif',
	        'box-shadow:0 0 6px rgba(0,0,0,.3)','transition:background .3s, box-shadow .3s'
	      ].join(';');
	      bar.appendChild(sch);
	    }
	  }
	  if (document.readyState === 'loading'){
	    document.addEventListener('DOMContentLoaded', insert);
	  } else { insert(); }
	})();
	</script>
	<?php
}, 20);

/**
 * Output CSS + updater script in footer.
 * This version WAITS until #gaia-kp-badge exists, then updates it and refreshes every 10 min.
 */
add_action( 'wp_footer', function () {
	?>
	<style id="gaia-badges-css">
	.gaia-kp-host { position: relative; }
	/* Pin the badge bar to the right, vertically centered (desktop) */
	.gaia-kp-host #gaia-badges{
		position:absolute; right:12px; top:50%; transform:translateY(-50%);
		display:flex; gap:8px; align-items:center;
	}
	/* Storm pulse for KP>=5 */
	#gaia-kp-badge.gaia-pulse{ animation:gaiaPulse 2s ease-in-out infinite; }
	@keyframes gaiaPulse{
		0%{ box-shadow:0 0 0 0 rgba(255,200,0,.35) }
		70%{ box-shadow:0 0 0 10px rgba(255,200,0,0) }
		100%{ box-shadow:0 0 0 0 rgba(255,200,0,0) }
	}
	/* Mobile/tablet: drop into flow so it never overlaps the burger */
	@media (max-width: 992px){
		.gaia-kp-host #gaia-badges{ position: static; transform:none; margin:6px 12px 0 auto; }
	}
</style>
<script id="gaia-badges-js">
(function(){
    var BADGE_URL = "<?php echo esc_js(defined('GAIAEYES_API_BASE') ? rtrim(GAIAEYES_API_BASE, '/') . '/v1/badges/kp_schumann' : ''); ?>";

    function colorizeKp(kp){
        if (kp >= 7) return {bg:"#a40000", glow:"#ff4f4f", pulse:true};
        if (kp >= 5) return {bg:"#d98200", glow:"#ffc84f", pulse:true};
        if (kp >= 4) return {bg:"#0e6218", glow:"#34e07a", pulse:false};
        return {bg:"#222", glow:"#888", pulse:false};
    }
    function colorizeF1(f1){
        if (f1 == null) return {bg:"#222", glow:"#888"};
        if (f1 >= 9.0)  return {bg:"#3a235d", glow:"#b58cff"};   // elevated vs ~7.8–8.0
        if (f1 <= 7.2)  return {bg:"#003a52", glow:"#7fd1ff"};   // subdued vs baseline
        return {bg:"#222", glow:"#888"};
    }

    function updateBadges(kpEl, schEl){
        if (!BADGE_URL){
            kpEl.textContent = "Kp —";
            schEl.textContent = "F1 —";
            return;
        }
        return fetch(BADGE_URL + "?v=" + Date.now(), {cache:"no-store"})
            .then(function(r){
                if (!r.ok) throw new Error("badge http " + r.status);
                return r.json();
            })
            .then(function(j){
                var kp = j && j.kp && j.kp.value != null ? parseFloat(j.kp.value) : NaN;
                var f1 = j && j.schumann_f1 && j.schumann_f1.value != null ? parseFloat(j.schumann_f1.value) : null;

                if (!isNaN(kp)){
                    var kc = colorizeKp(kp);
                    kpEl.textContent = "Kp " + kp.toFixed(1);
                    kpEl.style.background = kc.bg;
                    kpEl.style.boxShadow  = "0 0 10px " + kc.glow;
                    if (kc.pulse){ kpEl.classList.add('gaia-pulse'); } else { kpEl.classList.remove('gaia-pulse'); }
                } else {
                    kpEl.textContent = "Kp —";
                }

                if (f1 != null){
                    var sc = colorizeF1(f1);
                    schEl.textContent = "F1 " + f1.toFixed(2) + " Hz";
                    schEl.style.background = sc.bg;
                    schEl.style.boxShadow  = "0 0 10px " + sc.glow;
                } else {
                    schEl.textContent = "F1 —";
                }
            })
            .catch(function(){
                kpEl.textContent = "Kp —";
                schEl.textContent = "F1 —";
            });
    }

    // Wait until both badges exist before first update (avoids "F1 …" stuck state)
    function waitAndKick(attempt){
        attempt = attempt || 0;
        var kp  = document.getElementById('gaia-kp-badge');
        var sch = document.getElementById('gaia-sch-badge');
        if (kp && sch){
            updateBadges(kp, sch);
            setInterval(function(){ updateBadges(kp, sch); }, 600000); // 10 min
            return;
        }
        if (attempt < 40){
            setTimeout(function(){ waitAndKick(attempt+1); }, 250);
        }
    }

    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', function(){ waitAndKick(0); });
    } else {
        waitAndKick(0);
    }
})();
</script>
	<?php
}, 99);