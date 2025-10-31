<?php
/**
 * Plugin Name: Gaia Eyes – Earthquakes Detail
 * Description: Scientific Earthquakes detail page using quakes_latest.json (USGS-derived) with recent events, stats, and health context.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) exit;

// Defaults (GitHub Pages + jsDelivr mirror)
if (!defined('GAIAEYES_QUAKES_URL')) {
  define('GAIAEYES_QUAKES_URL', 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/quakes_latest.json');
}
if (!defined('GAIAEYES_QUAKES_MIRROR')) {
  define('GAIAEYES_QUAKES_MIRROR', 'https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main/data/quakes_latest.json');
}

function gaiaeyes_quakes_fetch($primary, $mirror, $cache_key, $ttl){
  $cached = get_transient($cache_key);
  if ($cached !== false) return $cached;
  $v = array('v' => floor(time()/600));
  $resp = wp_remote_get(add_query_arg($v, esc_url_raw($primary)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
    $resp = wp_remote_get(add_query_arg($v, esc_url_raw($mirror)), ['timeout'=>10,'headers'=>['Accept'=>'application/json']]);
  }
  if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return null;
  $data = json_decode(wp_remote_retrieve_body($resp), true);
  if (!is_array($data)) return null;
  set_transient($cache_key, $data, $ttl);
  return $data;
}

/**
 * Shortcode: [gaia_quakes_detail quakes_url="" cache="10" max="10"]
 */
function gaiaeyes_quakes_detail_shortcode($atts){
  $a = shortcode_atts([
    'quakes_url'  => GAIAEYES_QUAKES_URL,
    'history_url' => 'https://gaiaeyeshq.github.io/gaiaeyes-media/data/quakes_history.json',
    'cache'       => 10,
    'max'         => 10,
  ], $atts, 'gaia_quakes_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;
  $d = gaiaeyes_quakes_fetch($a['quakes_url'], GAIAEYES_QUAKES_MIRROR, 'ge_quakes_latest', $ttl);
  $hist = gaiaeyes_quakes_fetch(
    $a['history_url'],
    str_replace('github.io','cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main',$a['history_url']),
    'ge_quakes_history',
    $ttl
  );

  $ts = is_array($d) && !empty($d['timestamp_utc']) ? $d['timestamp_utc'] : '';
  $events = is_array($d) && !empty($d['events']) && is_array($d['events']) ? $d['events'] : [];
  $total = is_array($d) && isset($d['total']) ? intval($d['total']) : null;
  $total24 = is_array($d) && isset($d['total_24h']) ? intval($d['total_24h']) : null;

  // Robust "all magnitudes" total detection
  $tot_all = null; $tot24_all = null;
  if (isset($d['total_all'])) { $tot_all = intval($d['total_all']); }
  elseif (isset($d['counts']) && isset($d['counts']['all'])) { $tot_all = intval($d['counts']['all']); }
  elseif (isset($d['stats']) && isset($d['stats']['total_all'])) { $tot_all = intval($d['stats']['total_all']); }
  elseif ($total !== null) { $tot_all = $total; }

  if (isset($d['total_24h_all'])) { $tot24_all = intval($d['total_24h_all']); }
  elseif (isset($d['counts']) && (isset($d['counts']['24h']) || isset($d['counts']['last_24h']))) { $tot24_all = isset($d['counts']['24h']) ? intval($d['counts']['24h']) : intval($d['counts']['last_24h']); }
  elseif (isset($d['stats']) && isset($d['stats']['total_24h_all'])) { $tot24_all = intval($d['stats']['total_24h_all']); }
  elseif ($total24 !== null) { $tot24_all = $total24; }

  // Prefer all-magnitudes buckets from the day feed if available; fallback to M5+ events distribution
  $buckets = ['<2.5'=>0,'2.5–3.9'=>0,'4.0–4.9'=>0,'5.0–5.9'=>0,'6.0–6.9'=>0,'≥7.0'=>0];
  if (is_array($d) && !empty($d['buckets_day']) && is_array($d['buckets_day'])) {
    foreach (['<2.5','2.5–3.9','4.0–4.9','5.0–5.9','6.0–6.9','≥7.0'] as $key){
      if (isset($d['buckets_day'][$key])) $buckets[$key] = intval($d['buckets_day'][$key]);
    }
  } else if ($events){
    // fallback using listed (M5+) events
    $buckets = ['<4.0'=>0,'4.0–4.9'=>0,'5.0–5.9'=>0,'6.0–6.9'=>0,'≥7.0'=>0];
    foreach($events as $ev){
      $m = isset($ev['mag']) ? floatval($ev['mag']) : null;
      if ($m===null) continue;
      if ($m < 4.0) $buckets['<4.0']++;
      elseif ($m < 5.0) $buckets['4.0–4.9']++;
      elseif ($m < 6.0) $buckets['5.0–5.9']++;
      elseif ($m < 7.0) $buckets['6.0–6.9']++;
      else $buckets['≥7.0']++;
    }
  }

  // Monthly summary (last 6 months) from quakes_history.json (if present)
  $monthly_rows = [];
  if (is_array($hist) && !empty($hist['monthly']) && is_array($hist['monthly'])) {
    $months = $hist['monthly'];
    // keep last 6 entries
    $tail = array_slice($months, -6);
    foreach ($tail as $row) {
      $mon = $row['month'] ?? '';
      $m5  = isset($row['m5p']) ? intval($row['m5p']) : (isset($row['m5p_daily']) ? intval($row['m5p_daily']) : null);
      $all = isset($row['all']) ? intval($row['all']) : null;
      $monthly_rows[] = [ 'month' => $mon, 'm5p' => $m5, 'all' => $all ];
    }
  }

  $max_items = max(1, intval($a['max']));

  ob_start(); ?>
  <section class="ge-quakes ge-panel">
    <header class="ge-head">
      <h2>Earthquakes – Scientific Detail</h2>
      <div class="ge-meta">Updated <?php echo esc_html( $ts ?: '—' ); ?></div>
    </header>
    <article class="ge-card ge-topstats">
      <h3 id="stats">Global Stats (all magnitudes) <a class="anchor-link" href="#stats" aria-label="Link to Global Stats">🔗</a></h3>
      <div class="ge-meta-row">
        <span><strong>Total (all mags):</strong> <?php echo ($tot_all!==null)? intval($tot_all) : '—'; ?></span>
        <span><strong>Last 24h (all mags):</strong> <?php echo ($tot24_all!==null)? intval($tot24_all) : '—'; ?></span>
      </div>
      <div class="ge-note">Distribution shown for all magnitudes (USGS day feed). The Recent Events list defaults to M5.0+.</div>
      <div class="bucket-grid">
        <?php foreach ($buckets as $label=>$count): ?>
          <div class="bucket-item"><span class="b-lab"><?php echo esc_html($label); ?></span><span class="b-val"><?php echo intval($count); ?></span></div>
        <?php endforeach; ?>
      </div>
      <div class="ge-cta">
        <a class="gaia-link btn-compare" href="/compare/?a=m5p_daily&b=m5p_daily&range=90">Compare with Space Weather →</a>
      </div>
    </article>

    <div class="ge-grid">
      <article class="ge-card">
        <h3 id="recent">Recent Events (M5.0+) <a class="anchor-link" href="#recent" aria-label="Link to Recent Events">🔗</a></h3>
        <div class="ge-note">Note: This list shows magnitude 5.0 and above. Global stats above include all magnitudes.</div>
        <div class="ge-filters" id="geEqFilters">
          <div class="flt-group">
            <span class="flt-label">Show:</span>
            <label><input type="radio" name="eqShow" value="m5" checked> M5+</label>
            <label><input type="radio" name="eqShow" value="all"> All (sample)</label>
          </div>
          <div class="flt-group">
            <span class="flt-label">Sort:</span>
            <label><input type="radio" name="eqSort" value="latest" checked> Latest</label>
            <label><input type="radio" name="eqSort" value="mag"> Magnitude</label>
          </div>
        </div>
        <div id="geEqListWrap">
          <ul class="ev-list" id="geEqList"></ul>
          <noscript>
            <?php if (!$events): ?>
              <div class="ge-empty">No recent events found.</div>
            <?php else: ?>
              <ul class="ev-list">
              <?php 
                $i = 0;
                foreach ($events as $ev){
                  if ($i++ >= $max_items) break;
                  $mag = isset($ev['mag']) ? number_format((float)$ev['mag'], 1) : '—';
                  $place = isset($ev['place']) ? $ev['place'] : '—';
                  $time = isset($ev['time_utc']) ? $ev['time_utc'] : '';
                  $url  = isset($ev['url']) ? $ev['url'] : '';
                  $depth = isset($ev['depth_km']) ? $ev['depth_km'] : null;
                  $sevClass = '';
                  $mval = isset($ev['mag']) ? floatval($ev['mag']) : 0;
                  if ($mval >= 7.0) $sevClass = 'sev-high';
                  elseif ($mval >= 6.0) $sevClass = 'sev-medium';
                  elseif ($mval >= 5.0) $sevClass = 'sev-low';
              ?>
              <li class="ev <?php echo esc_attr($sevClass); ?>">
                <span class="ev-mag">M<?php echo esc_html($mag); ?></span>
                <span class="ev-place"><?php echo esc_html($place); ?></span>
                <span class="ev-time"><?php echo esc_html($time); ?></span>
                <?php if ($depth!==null): ?><span class="ev-depth"><?php echo esc_html(number_format((float)$depth,1)); ?> km</span><?php endif; ?>
                <?php if ($url): ?><a class="ev-link" href="<?php echo esc_url($url); ?>" target="_blank" rel="noopener">USGS</a><?php endif; ?>
              </li>
              <?php } ?>
              </ul>
            <?php endif; ?>
          </noscript>
        </div>
        <div class="ge-more" id="geEqMoreCtl">
          <button type="button" class="btn-more" id="eqMoreBtn">Show more</button>
          <button type="button" class="btn-more" id="eqAllBtn">Show all</button>
        </div>

        <script>
          (function(){
            const listM5 = <?php echo wp_json_encode($events); ?> || [];
            const listAll = <?php echo wp_json_encode( isset($d['events_all_sample']) ? $d['events_all_sample'] : [] ); ?> || [];
            const maxItems = <?php echo (int)$max_items; ?>;
            let pageSize = maxItems; // default page size
            let shown = maxItems;     // how many items currently shown
            const ul = document.getElementById('geEqList');
            const wrap = document.getElementById('geEqListWrap');
            const filters = document.getElementById('geEqFilters');

            function fmt(n, dp){ try { return (n==null? '—' : Number(n).toFixed(dp)); } catch(e){ return '—'; } }
            function fmtAgo(date){
              if (!(date instanceof Date) || isNaN(date)) return '';
              const diffMs = Date.now() - date.getTime();
              const ahead = diffMs < 0;
              const minutes = Math.round(Math.abs(diffMs) / 60000);
              if (minutes < 60) {
                return `${minutes} min ${ahead ? 'ahead' : 'ago'}`;
              }
              const hours = Math.round(minutes / 60);
              if (hours < 48) {
                return `${hours} hr${hours !== 1 ? 's' : ''} ${ahead ? 'ahead' : 'ago'}`;
              }
              const days = Math.round(hours / 24);
              return `${days} day${days !== 1 ? 's' : ''} ${ahead ? 'ahead' : 'ago'}`;
            }

            function fmtIsoShort(iso){
              if (!iso) return '';
              const d = new Date(iso);
              if (isNaN(d)) return iso;
              const pad = (n) => String(n).padStart(2, '0');
              const pretty = `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}Z`;
              const rel = fmtAgo(d);
              return { pretty, rel };
            }

            function render(items){
              ul.innerHTML = '';
              if (!items || !items.length){ ul.innerHTML = '<li class="ge-empty">No recent events found.</li>'; return; }
              items.slice(0, shown).forEach(ev => {
                const mag = (ev.mag!=null) ? `M${fmt(ev.mag,1)}` : 'M—';
                const place = ev.place || '—';
                const iso = ev.time_utc || '';
                const t = fmtIsoShort(iso);
                const prettyTime = t && typeof t === 'object' ? t.pretty : (t || iso || '—');
                const relTime = t && typeof t === 'object' ? t.rel : '';
                const depth = (ev.depth_km!=null) ? `${fmt(ev.depth_km,1)} km` : '';
                const url = ev.url || '';
                let sev = '';
                const mval = (typeof ev.mag==='number')? ev.mag : (parseFloat(ev.mag)||0);
                if (mval >= 7) sev='sev-high'; else if (mval >= 6) sev='sev-medium'; else if (mval >= 5) sev='sev-low';
                const li = document.createElement('li'); li.className = `ev ${sev}`;
                li.innerHTML = `
                  <span class="ev-mag">${mag}</span>
                  <span class="ev-place">${place}</span>
                  <span class="ev-time">${prettyTime}${relTime ? `<br><small>${relTime}</small>` : ''}</span>
                  ${depth? `<span class="ev-depth">${depth}</span>` : ''}
                  ${url? `<a class="ev-link" href="${url}" target="_blank" rel="noopener">USGS</a>` : ''}
                `;
                ul.appendChild(li);
              });
            }

            function sortLatest(a,b){
              const ta = Date.parse(a.time_utc||'');
              const tb = Date.parse(b.time_utc||'');
              return (isNaN(tb)?0:tb) - (isNaN(ta)?0:ta);
            }
            function sortMag(a,b){
              const ma = (typeof a.mag==='number')? a.mag : parseFloat(a.mag)||0;
              const mb = (typeof b.mag==='number')? b.mag : parseFloat(b.mag)||0;
              return mb - ma;
            }

            function currentList(){
              const show = (filters.querySelector('input[name="eqShow"]:checked')||{}).value || 'm5';
              return show==='all'? listAll.slice() : listM5.slice();
            }

            const moreCtl = document.getElementById('geEqMoreCtl');
            const btnMore = document.getElementById('eqMoreBtn');
            const btnAll  = document.getElementById('eqAllBtn');
            function updateButtons(items){
              if (!items || items.length <= shown) { moreCtl.style.display = 'none'; }
              else { moreCtl.style.display = 'flex'; }
            }
            function applyAndButtons(){
              const items = currentList();
              const sort = (filters.querySelector('input[name="eqSort"]:checked')||{}).value || 'latest';
              items.sort(sort==='mag'? sortMag : sortLatest);
              render(items);
              updateButtons(items);
            }
            btnMore.addEventListener('click', function(){ shown += pageSize; applyAndButtons(); });
            btnAll.addEventListener('click', function(){ shown = 1000; applyAndButtons(); });
            // replace original apply binding
            filters.removeEventListener && filters.removeEventListener('change', apply);
            filters.addEventListener('change', function(){ shown = pageSize; applyAndButtons(); });
            // initial draw
            applyAndButtons();
          })();
        </script>
      </article>

      <?php if (!empty($monthly_rows)) : ?>
      <article class="ge-card">
        <h3 id="monthly">Monthly & YoY <a class="anchor-link" href="#monthly" aria-label="Link to Monthly & YoY">🔗</a></h3>
        <div class="ge-note">Last 6 months (global). M5+ counts shown; totals where available.</div>
        <table class="ge-table">
          <thead><tr><th>Month</th><th>M5+</th><th>All</th></tr></thead>
          <tbody>
            <?php foreach ($monthly_rows as $r): ?>
              <tr><td><?php echo esc_html($r['month']); ?></td><td><?php echo esc_html( $r['m5p']!==null ? $r['m5p'] : '—'); ?></td><td><?php echo esc_html( $r['all']!==null ? $r['all'] : '—'); ?></td></tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </article>
      <?php endif; ?>
      </article>

      <article class="ge-card">
        <h3 id="health">Health context <a class="anchor-link" href="#health" aria-label="Link to Health Context">🔗</a></h3>
        <ul class="ge-list">
          <li>Rapid pressure and ground-motion changes can challenge the vestibular system; if sensitive, pace activities on high-activity days.</li>
          <li>Hydration and short daylight breaks may help stabilize autonomic tone.</li>
          <li>During global seismic clusters, keep evenings calm and light exposure lower to support sleep continuity.</li>
        </ul>
      </article>

      <article class="ge-card">
        <h3 id="about">About Earthquakes <a class="anchor-link" href="#about" aria-label="Link to About Earthquakes">🔗</a></h3>
        <p>Magnitude (M) is a logarithmic scale; each full step represents ~32× energy release. While most quakes are small, regional clustering and larger magnitudes can affect infrastructure and, indirectly, stress levels and daily routines. This page reflects a distilled feed of recent events to provide situational awareness alongside solar and Schumann metrics.</p>
      </article>
      <div class="ge-cta" style="margin-top:10px;">
        <a class="gaia-link btn-compare" href="/compare/?a=m5p_daily&b=kp_daily_max&range=90">Compare with Space Weather →</a>
        <span style="margin-left:10px;"><a class="gaia-link" href="/space-dashboard/#kp">Space Dashboard →</a></span>
        <span style="margin-left:10px;"><a class="gaia-link" href="/health-context/">Health context →</a></span>
      </div>
    </div>

    <style>
      .ge-panel{background:#0f121a;color:#e9eef7;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px}
      .ge-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
      .ge-head h2{margin:0;font-size:1.15rem}
      .ge-meta{opacity:.8;font-size:.9rem}
      .ge-grid{display:grid;gap:12px}
      @media(min-width:900px){.ge-grid{grid-template-columns:1fr}}
      .ge-card{background:#151a24;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:12px}
      .ge-list{margin:0;padding-left:18px;line-height:1.45}
      .ev-list{margin:0;padding-left:0;list-style:none}
      .ev{display:grid;grid-template-columns:92px 1fr auto auto auto;gap:8px;align-items:center;border-bottom:1px dashed rgba(255,255,255,.08);padding:6px 0}
      .ev-mag{font-weight:700}
      .ev-place{opacity:.9}
      .ev-time{opacity:.75;font-size:.9rem}
      .ev-depth{opacity:.75;font-size:.9rem}
      .ev-link{color:#bcd5ff;text-decoration:none;border-bottom:1px dashed #4b6aa1}
      .bucket-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:8px}
      .bucket-item{background:#1b2233;border:1px solid #344a72;border-radius:10px;padding:8px;text-align:center}
      .b-lab{display:block;font-size:.85rem;opacity:.85}
      .b-val{display:block;font-size:1.05rem;font-weight:700}
      .anchor-link{opacity:0;margin-left:8px;font-size:.9rem;color:inherit;text-decoration:none;border-bottom:1px dotted rgba(255,255,255,.25);transition:opacity .2s ease}
      .ge-card h3:hover .anchor-link{opacity:1}
      .anchor-link:hover{border-bottom-color:rgba(255,255,255,.6)}
      .sev-low .ev-mag{color:#ffd089}
      .sev-medium .ev-mag{color:#ffb347}
      .sev-high .ev-mag{color:#ff6b6b}
      .ge-note{opacity:.8;font-size:.9rem;margin:.25rem 0 .5rem 0}
      .ge-filters{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:.35rem 0 .5rem}
      .flt-group{display:flex;gap:8px;align-items:center}
      .flt-label{opacity:.85}
      .ge-topstats{margin-bottom:12px}
      .ge-meta-row{display:flex;gap:14px;flex-wrap:wrap;margin:.25rem 0 .5rem 0}
      .ge-cta{margin-top:8px}
      .btn-compare{display:inline-block;background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:8px;padding:6px 10px;text-decoration:none}
      .btn-compare:hover{border-color:#4b6aa1}
      .ge-more{display:flex;gap:8px;margin:.5rem 0}
      .btn-more{background:#1b2233;color:#cfe3ff;border:1px solid #344a72;border-radius:8px;padding:6px 10px;cursor:pointer}
      .btn-more:hover{border-color:#4b6aa1}
      .ge-table{width:100%;border-collapse:collapse;margin-top:6px}
      .ge-table th,.ge-table td{border:1px solid rgba(255,255,255,.08);padding:6px 8px;text-align:left}
      .ge-table th{background:#1b2233}
      @media(max-width: 640px){
        .ev{
          grid-template-columns: 84px 1fr;
          grid-template-areas:
            "mag time"
            "place place"
            "depth link";
          align-items: start;
        }
        .ev-mag{ grid-area: mag; }
        .ev-time{ grid-area: time; text-align: right; font-size: .9rem; opacity: .85; }
        .ev-place{ grid-area: place; white-space: normal; line-height: 1.3; overflow-wrap: anywhere; }
        .ev-depth{ grid-area: depth; font-size: .9rem; opacity: .8; }
        .ev-link{ grid-area: link; justify-self: end; }
      }
      .ev-time small{ opacity: .8; }
    </style>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_quakes_detail','gaiaeyes_quakes_detail_shortcode');
