<?php
/**
 * Plugin Name: Gaia Eyes — Alert Auto-Clear (Radiation)
 * Description: Keeps the site-wide Solar Radiation Storm banner in sync with live GOES ≥10 MeV (hides when S0).
 */
if (!defined('ABSPATH')) exit;

add_action('wp_footer', function () {
    if (!defined('GAIAEYES_API_BASE')) return;
    $endpoint = rtrim(GAIAEYES_API_BASE, '/') . '/v1/space/visuals';
    ?>
<script>
(function(){
  const API = <?php echo json_encode($endpoint); ?>;
  const POLL_MS = 5 * 60 * 1000;       // refresh every 5 minutes
  const MAX_AGE_MIN = 60;              // ignore data older than 60 minutes

  function sScale(pfu){
    if (pfu >= 100000) return 5;
    if (pfu >= 10000)  return 4;
    if (pfu >= 1000)   return 3;
    if (pfu >= 100)    return 2;
    if (pfu >= 10)     return 1;
    return 0; // S0
  }

  function findRadiationBanner(){
    // Adjust selectors if your markup uses different classes/ids.
    return document.querySelector('[data-gaia-alert="radiation"], .gaia-alert--radiation');
  }

  async function tick(){
    try{
      const r = await fetch(API + '?v=' + Date.now(), {cache:'no-store'});
      if (!r.ok) throw new Error('http ' + r.status);
      const j = await r.json();
      const series = (j && j.series) || [];
      const protons = series.find(s => s.key === 'goes_protons');
      const last = protons && protons.samples && protons.samples[protons.samples.length - 1];
      const pfu  = last ? Number(last.value) : NaN;
      const ts   = last ? new Date(last.ts) : null;
      const fresh = ts ? ((Date.now() - ts.getTime()) / 60000) <= MAX_AGE_MIN : false;
      const S = (!isFinite(pfu) || !fresh) ? 0 : sScale(pfu);

      const banner = findRadiationBanner();
      if (!banner) return;

      if (S === 0){
        // Hide and prevent re-show via any cookie the banner code might set
        banner.remove();
        document.cookie = "gaia_radiation_ack=; Max-Age=0; path=/";
      } else {
        // (Optional) keep text fresh if your banner has these spans:
        const v = banner.querySelector('[data-gaia-pfu]');    // e.g. <span data-gaia-pfu></span>
        const s = banner.querySelector('[data-gaia-s]');      // e.g. <span data-gaia-s></span>
        if (v) v.textContent = Math.round(pfu) + ' pfu';
        if (s) s.textContent = 'S' + S;
      }
    } catch(e) {
      // fail-quietly: don’t flash the banner on error
    }
  }

  tick();
  setInterval(tick, POLL_MS);
})();
</script>
    <?php
}, 99);