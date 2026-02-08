// Tiny helper to animate arc gauges via stroke-dasharray
(function(){
  function initGauge(el){
    const min = parseFloat(el.getAttribute('data-min') || '0');
    const max = parseFloat(el.getAttribute('data-max') || '100');
    const val = parseFloat(el.getAttribute('data-value') || '0');
    const svg = el.querySelector('svg');
    const track = svg.querySelector('.track');
    const fill  = svg.querySelector('.fill');

    // Circle geometry
    const R = parseFloat(svg.getAttribute('data-r') || '80');
    const C = 2 * Math.PI * R;

    const clamped = Math.max(min, Math.min(max, val));
    const pct = (clamped - min) / (max - min);
    const arcLen = C * pct;

    track.style.strokeDasharray = C + ' ' + C;
    track.style.strokeDashoffset = 0;

    fill.style.strokeDasharray = arcLen + ' ' + (C - arcLen);
    fill.style.strokeDashoffset = 0;

    // Update numeric center
    const v = el.querySelector('.center .v');
    if (v){ v.textContent = (clamped % 1 === 0) ? clamped.toFixed(0) : clamped.toFixed(2); }
  }

  function boot(){
    document.querySelectorAll('.ge-arc').forEach(initGauge);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
})();