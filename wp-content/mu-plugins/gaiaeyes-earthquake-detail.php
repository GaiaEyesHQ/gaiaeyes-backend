<?php
/**
 * Plugin Name: Gaia Eyes – Earthquakes Detail
 * Description: Scientific Earthquakes detail page using quakes_latest.json (USGS-derived) with recent events, stats, and health context.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) exit;

// Defaults (GitHub Pages + jsDelivr mirror)
require_once __DIR__ . '/gaiaeyes-api-helpers.php';


/**
 * Shortcode: [gaia_quakes_detail quakes_url="" cache="10" max="10"]
 */
function gaiaeyes_quakes_detail_shortcode($atts){
  $a = shortcode_atts([
    'cache' => 10,
    'max'   => 10,
  ], $atts, 'gaia_quakes_detail');

  $ttl = max(1, intval($a['cache'])) * MINUTE_IN_SECONDS;

  $api_base = defined('GAIAEYES_API_BASE') ? rtrim(GAIAEYES_API_BASE, '/') : '';
  $bearer   = defined('GAIAEYES_API_BEARER') ? GAIAEYES_API_BEARER : '';
  $dev_user = defined('GAIAEYES_API_DEV_USERID') ? GAIAEYES_API_DEV_USERID : '';

  $latest_payload = $api_base
    ? gaiaeyes_http_get_json_api_cached($api_base . '/v1/quakes/latest', 'ge_quakes_latest', $ttl, $bearer, $dev_user)
    : null;
  $history_payload = $api_base
    ? gaiaeyes_http_get_json_api_cached($api_base . '/v1/quakes/history', 'ge_quakes_history', $ttl, $bearer, $dev_user)
    : null;

  $d = (is_array($latest_payload) && !empty($latest_payload['ok']) && !empty($latest_payload['item']) && is_array($latest_payload['item']))
    ? $latest_payload['item']
    : null;
  $hist_items = (is_array($history_payload) && !empty($history_payload['ok']) && !empty($history_payload['items']) && is_array($history_payload['items']))
    ? $history_payload['items']
    : [];

  $ts = is_array($d) && !empty($d['day']) ? $d['day'] : '';

  // Fetch recent event-level data from /v1/quakes/events for the "Recent Events" list.
  $events_payload = $api_base
    ? gaiaeyes_http_get_json_api_cached(
        $api_base . '/v1/quakes/events?min_mag=0&hours=24&limit=500',
        'ge_quakes_events',
        $ttl,
        $bearer,
        $dev_user
      )
    : null;

  $events = (is_array($events_payload)
    && !empty($events_payload['ok'])
    && !empty($events_payload['items'])
    && is_array($events_payload['items']))
    ? $events_payload['items']
    : [];

  $tot_all = is_array($d) && isset($d['all_quakes']) ? intval($d['all_quakes']) : null;

  // Buckets approximated from the daily aggregates by magnitude class
  $buckets = [
    'M4.0–4.9' => (is_array($d) && isset($d['m4p'])) ? intval($d['m4p']) : 0,
    'M5.0–5.9' => (is_array($d) && isset($d['m5p'])) ? intval($d['m5p']) : 0,
    'M6.0–6.9' => (is_array($d) && isset($d['m6p'])) ? intval($d['m6p']) : 0,
    'M7.0+'    => (is_array($d) && isset($d['m7p'])) ? intval($d['m7p']) : 0,
  ];

  // Determine view mode for Monthly & YoY: either "last6" (default) or a specific year (YYYY).
  $selected_year = isset($_GET['quakes_year']) ? preg_replace('/[^0-9]/', '', (string) $_GET['quakes_year']) : '';
  if ($selected_year === '' || strlen($selected_year) !== 4) {
    $selected_year = 'last6';
  }
  $view_last6 = ($selected_year === 'last6');
  $year_list = [];

  // Monthly summary (last 6 months or selected year) + YoY/MoM delta for M5+ from /v1/quakes/history endpoint
  $monthly_rows = [];
  if (!empty($hist_items) && is_array($hist_items)) {
    $months = $hist_items;
    // Build index of month (YYYY-MM) -> values for YoY/MoM lookup and collect available years
    $mon_idx = [];
    foreach ($months as $row) {
      $rawMonth = $row['month'] ?? '';
      if ($rawMonth === '') continue;
      $year = substr($rawMonth, 0, 4);
      if ($year !== '' && ctype_digit($year)) {
        $year_list[$year] = true;
      }
      $mk = substr($rawMonth, 0, 7); // normalize to "YYYY-MM"
      $mon_idx[$mk] = [
        'm5p' => isset($row['m5p']) ? intval($row['m5p']) : null,
        'all' => isset($row['all_quakes']) ? intval($row['all_quakes']) : null,
      ];
    }
    // Normalize year_list to a sorted array of years (newest first)
    $year_list = array_keys($year_list);
    rsort($year_list);

    // Choose subset of months for display
    if ($view_last6) {
      // Last 6 (most recent) entries and display oldest→newest
      $subset = array_slice($months, 0, 6);
      $subset = array_reverse($subset);
    } else {
      // All months in the selected year, oldest→newest
      $subset = [];
      foreach ($months as $row) {
        $rawMonth = $row['month'] ?? '';
        if ($rawMonth === '') continue;
        $year = substr($rawMonth, 0, 4);
        if ($year === $selected_year) {
          $subset[] = $row;
        }
      }
      $subset = array_reverse($subset);
    }

    foreach ($subset as $row) {
      $rawMonth = $row['month'] ?? '';
      $mon = $rawMonth !== '' ? substr($rawMonth, 0, 7) : '';
      $m5  = isset($row['m5p']) ? intval($row['m5p']) : null;
      $all = isset($row['all_quakes']) ? intval($row['all_quakes']) : null;
      // Compute YoY and MoM deltas for M5+
      $yoy = null; $mom = null;
      if ($mon !== '' && $m5 !== null) {
        try {
          $dtmCur = DateTime::createFromFormat('Y-m-d', $mon . '-01', new DateTimeZone('UTC'));
          if ($dtmCur instanceof DateTime) {
            // YoY
            $dtmYoY = clone $dtmCur; $dtmYoY->sub(new DateInterval('P1Y'));
            $prev_year_key = $dtmYoY->format('Y-m');
            if (isset($mon_idx[$prev_year_key]) && isset($mon_idx[$prev_year_key]['m5p'])) {
              $yoy = $m5 - intval($mon_idx[$prev_year_key]['m5p']);
            }
            // MoM
            $dtmMoM = clone $dtmCur; $dtmMoM->sub(new DateInterval('P1M'));
            $prev_mon_key = $dtmMoM->format('Y-m');
            if (isset($mon_idx[$prev_mon_key]) && isset($mon_idx[$prev_mon_key]['m5p'])) {
              $mom = $m5 - intval($mon_idx[$prev_mon_key]['m5p']);
            }
          }
        } catch (Exception $e) { /* ignore */ }
      }
      $monthly_rows[] = [ 'month' => $mon, 'm5p' => $m5, 'all' => $all, 'yoy_m5p' => $yoy, 'mom_m5p' => $mom ];
    }
    // After building $monthly_rows, compute per-year totals and YoY deltas for M5+
    $year_totals = [];
    if (!empty($hist_items) && is_array($hist_items)) {
      foreach ($hist_items as $row) {
        $rawMonth = $row['month'] ?? '';
        if ($rawMonth === '') continue;
        $year = substr($rawMonth, 0, 4);
        if ($year === '' || !ctype_digit($year)) continue;
        $m5  = isset($row['m5p']) ? intval($row['m5p']) : 0;
        if (!isset($year_totals[$year])) {
          $year_totals[$year] = 0;
        }
        $year_totals[$year] += $m5;
      }
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
        <h3 id="recent">Recent Events (Last 24 Hours) <a class="anchor-link" href="#recent" aria-label="Link to Recent Events">🔗</a></h3>
        <div class="ge-note">This list shows all earthquakes from the past 24 hours. Use the “Show” toggle to focus on M5+ events. Global stats above include all magnitudes.</div>
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
          <button type="button" class="btn-more" id="eqLessBtn">Show less</button>
        </div>

        <script>
          (function(){
            const listAll = <?php echo wp_json_encode($events); ?> || [];
            const listM5 = listAll.filter(function(ev){
              const m = (typeof ev.mag === 'number') ? ev.mag : parseFloat(ev.mag);
              return !isNaN(m) && m >= 5.0;
            });
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
            const btnLess = document.getElementById('eqLessBtn');

            function updateButtons(items){
              if (!items || items.length <= pageSize){
                // Not enough items to paginate
                moreCtl.style.display = 'none';
                return;
              }
              moreCtl.style.display = 'flex';
              // Toggle visibility per state
              btnMore.style.display = (shown < items.length) ? 'inline-block' : 'none';
              btnAll.style.display  = (shown < items.length) ? 'inline-block' : 'none';
              btnLess.style.display = (shown > pageSize) ? 'inline-block' : 'none';
            }

            function renderHintIfCapped(items){
              // If user chose All (sample) but we only have a small number of items, show a subtle hint
              const show = (filters.querySelector('input[name="eqShow"]:checked')||{}).value || 'm5';
              const hintId = 'geEqHint';
              let hint = document.getElementById(hintId);
              if (show === 'all' && items && items.length <= pageSize){
                if (!hint){
                  hint = document.createElement('div');
                  hint.id = hintId; hint.className = 'ge-note';
                  hint.textContent = 'Showing all available from today\'s sample. More history may need to be ingested to display additional events.';
                  wrap.appendChild(hint);
                }
              } else if (hint){ hint.remove(); }
            }

            function applyAndButtons(){
              const items = currentList();
              const sort = (filters.querySelector('input[name="eqSort"]:checked')||{}).value || 'latest';
              items.sort(sort==='mag'? sortMag : sortLatest);
              render(items);
              updateButtons(items);
              renderHintIfCapped(items);
            }

            btnMore.addEventListener('click', function(){ shown += pageSize; applyAndButtons(); });
            btnAll.addEventListener('click', function(){ shown = 1000; applyAndButtons(); });
            btnLess.addEventListener('click', function(){ shown = pageSize; applyAndButtons(); });
            filters.addEventListener('change', function(){ shown = pageSize; applyAndButtons(); });

            // initial draw using PHP-provided events
            applyAndButtons();
          })();
        </script>
      </article>

      <?php if (!empty($monthly_rows)) : ?>
      <article class="ge-card">
        <h3 id="monthly">Monthly & YoY <a class="anchor-link" href="#monthly" aria-label="Link to Monthly & YoY">🔗</a></h3>
        <div class="ge-note">
          <?php if ($view_last6): ?>
            Last 6 months (global). M5+ counts shown; totals where available.
          <?php else: ?>
            Year <?php echo esc_html($selected_year); ?> (global). M5+ counts shown; totals where available.
          <?php endif; ?>
        </div>
        <div class="ge-note" style="font-size:.85rem; opacity:.75; margin-top:2px;">
          <strong>YoY Δ</strong> compares each month’s M5+ count to the <em>same month last year</em>.<br>
          <strong>MoM Δ</strong> compares each month’s M5+ count to the <em>immediately preceding month</em>.
        </div>
        <?php if (!empty($year_list)): ?>
        <form method="get" class="ge-year-filter" style="margin-bottom:6px;">
          <label>
            View:
            <select name="quakes_year" onchange="this.form.submit()">
              <option value="last6"<?php if ($view_last6) echo ' selected'; ?>>Last 6 months</option>
              <?php foreach ($year_list as $yr): ?>
                <option value="<?php echo esc_attr($yr); ?>"<?php if (!$view_last6 && $selected_year === $yr) echo ' selected'; ?>>
                  Year <?php echo esc_html($yr); ?>
                </option>
              <?php endforeach; ?>
            </select>
          </label>
        </form>
        <?php
          if (!$view_last6 && !empty($year_totals)) {
            $cur_year = $selected_year;
            $cur_total = isset($year_totals[$cur_year]) ? $year_totals[$cur_year] : null;
            $prev_year = (string) ((int) $cur_year - 1);
            $prev_total = isset($year_totals[$prev_year]) ? $year_totals[$prev_year] : null;
            if ($cur_total !== null && $prev_total !== null) {
              $delta = $cur_total - $prev_total;
              $cls = ($delta > 0) ? 'delta-pos' : (($delta < 0) ? 'delta-neg' : '');
              echo '<div class="ge-note" style="margin-top:4px;">';
              echo 'Year&nbsp;' . esc_html($cur_year) . ' had ';
              echo '<span class="' . esc_attr($cls) . '">';
              echo ($delta > 0 ? '+' : '') . intval($delta);
              echo '</span> more M5+ earthquakes than ' . esc_html($prev_year) . '.';
              echo '</div>';
            } elseif ($cur_total !== null) {
              echo '<div class="ge-note" style="margin-top:4px;">';
              echo 'Year&nbsp;' . esc_html($cur_year) . ' had ' . intval($cur_total) . ' M5+ earthquakes.';
              echo '</div>';
            }
          }
        ?>
        <?php endif; ?>
        <table class="ge-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>M5+</th>
              <th>
                YoY Δ (M5+)
                <span class="ge-tip" title="Year‑over‑year difference: this month’s M5+ count minus the same month last year.">❔</span>
              </th>
              <th>
                MoM Δ (M5+)
                <span class="ge-tip" title="Month‑over‑month difference: this month’s M5+ count minus the previous month.">❔</span>
              </th>
              <th>All</th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($monthly_rows as $r): ?>
              <tr>
                <td><?php echo esc_html($r['month']); ?></td>
                <td><?php echo esc_html( $r['m5p']!==null ? $r['m5p'] : '—'); ?></td>
                <td>
                  <?php
                    if ($r['yoy_m5p'] === null) {
                      echo '—';
                    } else {
                      $cls = ($r['yoy_m5p'] > 0) ? 'delta-pos' : (($r['yoy_m5p'] < 0) ? 'delta-neg' : '');
                      echo '<span class="'.esc_attr($cls).'">'.(($r['yoy_m5p'] > 0 ? '+' : '').intval($r['yoy_m5p'])).'</span>';
                    }
                  ?>
                </td>
                <td>
                  <?php
                    if ($r['mom_m5p'] === null) {
                      echo '—';
                    } else {
                      $cls = ($r['mom_m5p'] > 0) ? 'delta-pos' : (($r['mom_m5p'] < 0) ? 'delta-neg' : '');
                      echo '<span class="'.esc_attr($cls).'">'.(($r['mom_m5p'] > 0 ? '+' : '').intval($r['mom_m5p'])).'</span>';
                    }
                  ?>
                </td>
                <td><?php echo esc_html( $r['all']!==null ? $r['all'] : '—'); ?></td>
              </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </article>
      <?php endif; ?>

      <article class="ge-card">
        <h3 id="quake-trends">10-Year Monthly M5+ Trends <a class="anchor-link" href="#quake-trends" aria-label="Link to 10-Year Monthly M5+ Trends">🔗</a></h3>
        <div class="ge-note">Each line represents a year. X-axis is month (Jan–Dec), Y-axis is M5+ count. Latest year is highlighted.</div>
        <div id="geQuakeChart" class="ge-quake-chart"></div>
        <div id="geQuakeChartLegend" class="ge-quake-chart-legend"></div>
        <script>
          (function(){
            const hist = <?php echo wp_json_encode($hist_items); ?> || [];
            if (!hist.length) return;
            const selectedYear = <?php echo $view_last6 ? 'null' : '"'.esc_js($selected_year).'"'; ?>;
            const selectedPrevYear = selectedYear ? String(parseInt(selectedYear, 10) - 1) : null;

            const byYear = {};
            hist.forEach(function(row){
              var raw = row && row.month ? String(row.month) : '';
              if (!raw) return;
              var year = raw.slice(0,4);
              var monthStr = raw.slice(5,7);
              var month = parseInt(monthStr, 10);
              if (!/^[0-9]{4}$/.test(year) || isNaN(month) || month < 1 || month > 12) return;
              var m5 = (row.m5p != null) ? parseInt(row.m5p, 10) : null;
              if (m5 === null || isNaN(m5)) return;
              if (!byYear[year]) byYear[year] = [];
              byYear[year].push({ m: month, v: m5 });
            });

            var years = Object.keys(byYear).filter(function(y){ return /^[0-9]{4}$/.test(y); }).sort();
            if (!years.length) return;
            // Keep at most the last 10 years
            if (years.length > 10) {
              years = years.slice(years.length - 10);
            }

            // Sort months ascending within each year and fill missing months with null
            years.forEach(function(y){
              byYear[y].sort(function(a,b){ return a.m - b.m; });
            });

            // Compute global max for scaling
            var maxVal = 0;
            years.forEach(function(y){
              byYear[y].forEach(function(p){
                if (p.v > maxVal) maxVal = p.v;
              });
            });
            if (maxVal <= 0) maxVal = 1;

            // Compute per-month min, max, median for band/median line
            var monthStats = {};
            for (var m = 1; m <= 12; m++) {
              var vals = [];
              years.forEach(function(y){
                var pts = byYear[y];
                for (var i = 0; i < pts.length; i++) {
                  if (pts[i].m === m && pts[i].v != null && !isNaN(pts[i].v)) {
                    vals.push(pts[i].v);
                    break;
                  }
                }
              });
              if (!vals.length) continue;
              vals.sort(function(a,b){ return a - b; });
              var minv = vals[0];
              var maxv = vals[vals.length - 1];
              var median;
              var mid = Math.floor(vals.length / 2);
              if (vals.length % 2 === 0) {
                median = (vals[mid - 1] + vals[mid]) / 2;
              } else {
                median = vals[mid];
              }
              monthStats[m] = { min: minv, max: maxv, median: median };
              if (maxv > maxVal) maxVal = maxv;
            }

            var w = 600, h = 240, pad = 36;
            var monthToX = function(m){ return pad + ((m - 1) / 11) * (w - pad * 2); };
            var valToY = function(v){ return h - pad - (v / maxVal) * (h - pad * 2); };

            var svgNS = "http://www.w3.org/2000/svg";
            var svg = document.createElementNS(svgNS, "svg");
            svg.setAttribute("viewBox", "0 0 " + w + " " + h);
            svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
            svg.classList.add("ge-quake-chart-svg");

            // Axes + grid
            var axis = document.createElementNS(svgNS, "g");
            axis.setAttribute("stroke", "rgba(255,255,255,0.4)");
            axis.setAttribute("stroke-width", "1");

            // Y axis
            var yAxis = document.createElementNS(svgNS, "line");
            yAxis.setAttribute("x1", pad);
            yAxis.setAttribute("y1", pad - 4);
            yAxis.setAttribute("x2", pad);
            yAxis.setAttribute("y2", h - pad + 4);
            axis.appendChild(yAxis);

            // X axis
            var xAxis = document.createElementNS(svgNS, "line");
            xAxis.setAttribute("x1", pad - 4);
            xAxis.setAttribute("y1", h - pad);
            xAxis.setAttribute("x2", w - pad + 4);
            xAxis.setAttribute("y2", h - pad);
            axis.appendChild(xAxis);

            // X-axis month ticks/labels
            var monthsShort = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            for (var m = 1; m <= 12; m++) {
              var mx = monthToX(m);
              var tick = document.createElementNS(svgNS, "line");
              tick.setAttribute("x1", mx);
              tick.setAttribute("y1", h - pad);
              tick.setAttribute("x2", mx);
              tick.setAttribute("y2", h - pad + 4);
              tick.setAttribute("stroke", "rgba(255,255,255,0.4)");
              axis.appendChild(tick);

              var lbl = document.createElementNS(svgNS, "text");
              lbl.setAttribute("x", mx);
              lbl.setAttribute("y", h - pad + 16);
              lbl.setAttribute("text-anchor", "middle");
              lbl.setAttribute("font-size", "10");
              lbl.setAttribute("fill", "rgba(255,255,255,0.8)");
              lbl.textContent = monthsShort[m-1];
              axis.appendChild(lbl);
            }

            // Y-axis ticks/labels
            var steps = 4;
            for (var i = 0; i <= steps; i++) {
              var val = (maxVal * i) / steps;
              var gy = valToY(val);
              if (i > 0 && i < steps) {
                var gl = document.createElementNS(svgNS, "line");
                gl.setAttribute("x1", pad);
                gl.setAttribute("y1", gy);
                gl.setAttribute("x2", w - pad);
                gl.setAttribute("y2", gy);
                gl.setAttribute("stroke", "rgba(255,255,255,0.08)");
                axis.appendChild(gl);
              }
              var yl = document.createElementNS(svgNS, "text");
              yl.setAttribute("x", pad - 6);
              yl.setAttribute("y", gy + 3);
              yl.setAttribute("text-anchor", "end");
              yl.setAttribute("font-size", "9");
              yl.setAttribute("fill", "rgba(255,255,255,0.7)");
              yl.textContent = Math.round(val);
              axis.appendChild(yl);
            }

            svg.appendChild(axis);

            // Colors for lines
            var palette = [
              "#7fc3ff","#ffb3b3","#ffe38f","#b9f2a1","#e3b3ff",
              "#ff9f80","#80ffd4","#ffd480","#a0a0ff"
            ];

            var latestYear = years[years.length - 1];

            // Median band (min/max envelope)
            var bandPath = "";
            var xs = [], upper = [], lower = [];
            for (var m2 = 1; m2 <= 12; m2++) {
              if (!monthStats[m2]) continue;
              xs.push(monthToX(m2));
              upper.push(valToY(monthStats[m2].max));
              lower.push(valToY(monthStats[m2].min));
            }
            if (xs.length > 1) {
              // Build polygon: upper from left→right, lower from right→left
              bandPath += "M" + xs[0] + " " + upper[0] + " ";
              for (var i2 = 1; i2 < xs.length; i2++) {
                bandPath += "L" + xs[i2] + " " + upper[i2] + " ";
              }
              for (var j = xs.length - 1; j >= 0; j--) {
                bandPath += "L" + xs[j] + " " + lower[j] + " ";
              }
              bandPath += "Z";
              var band = document.createElementNS(svgNS, "path");
              band.setAttribute("d", bandPath.trim());
              band.setAttribute("fill", "rgba(255,255,255,0.06)");
              band.setAttribute("stroke", "none");
              svg.appendChild(band);

              // Median line
              var medianPath = "";
              var firstMedian = true;
              for (var m3 = 1; m3 <= 12; m3++) {
                if (!monthStats[m3]) continue;
                var mx2 = monthToX(m3);
                var my2 = valToY(monthStats[m3].median);
                medianPath += (firstMedian ? "M" : "L") + mx2 + " " + my2 + " ";
                firstMedian = false;
              }
              var median = document.createElementNS(svgNS, "path");
              median.setAttribute("d", medianPath.trim());
              median.setAttribute("fill", "none");
              median.setAttribute("stroke", "rgba(255,255,255,0.7)");
              median.setAttribute("stroke-width", "1.2");
              median.setAttribute("stroke-dasharray", "4 3");
              svg.appendChild(median);
            }

            // Plot year lines
            var yearPaths = {};
            years.forEach(function(y, idx){
              var pts = byYear[y];
              if (!pts.length) return;
              var d = "";
              pts.forEach(function(p, i){
                var x = monthToX(p.m);
                var ycoord = valToY(p.v);
                d += (i === 0 ? "M" : "L") + x + " " + ycoord + " ";
              });
              var path = document.createElementNS(svgNS, "path");
              path.setAttribute("d", d.trim());
              var color = palette[idx % palette.length];
              path.setAttribute("fill", "none");
              path.setAttribute("stroke", color);
              path.setAttribute("data-year", y);
              path.setAttribute("stroke-width", y === latestYear ? "2.4" : "1.4");
              path.setAttribute("stroke-opacity", y === latestYear ? "1.0" : "0.6");
              svg.appendChild(path);
              yearPaths[y] = path;
            });

            var container = document.getElementById("geQuakeChart");
            if (container) {
              container.innerHTML = "";
              container.appendChild(svg);
            }

            // Legend with click/hover interactions
            var legend = document.getElementById("geQuakeChartLegend");
            var visibleYears = {};
            years.forEach(function(y){ visibleYears[y] = true; });
            // If a specific year is selected in the Monthly & YoY view, default to showing only that year + its previous year.
            if (selectedYear && years.indexOf(selectedYear) !== -1) {
              years.forEach(function(y){
                visibleYears[y] = (y === selectedYear || y === selectedPrevYear);
              });
            }

            function updateVisibility() {
              years.forEach(function(y){
                var p = yearPaths[y];
                if (!p) return;
                if (visibleYears[y]) {
                  p.style.display = "";
                } else {
                  p.style.display = "none";
                }
              });
            }

            if (legend) {
              legend.innerHTML = "";
              // Median legend entry
              var medianItem = document.createElement("span");
              medianItem.className = "ge-quake-legend-item median";
              medianItem.innerHTML = '<span class="swatch median"></span><span class="label">Median (dashed line)</span>';
              legend.appendChild(medianItem);

              // Show all years control
              var showAllItem = document.createElement("span");
              showAllItem.className = "ge-quake-legend-item showall";
              showAllItem.innerHTML = '<span class="swatch"></span><span class="label">Show all years</span>';
              showAllItem.addEventListener("click", function(){
                years.forEach(function(y){
                  visibleYears[y] = true;
                  var entry = legend.querySelector('.ge-quake-legend-item[data-year="'+y+'"]');
                  if (entry) {
                    entry.classList.remove("muted");
                    var cb = entry.querySelector('input.ge-year-toggle');
                    if (cb) cb.checked = true;
                  }
                });
                updateVisibility();
              });
              legend.appendChild(showAllItem);

              years.slice().reverse().forEach(function(y){
                var color = palette[(years.indexOf(y)) % palette.length];
                var item = document.createElement("span");
                item.className = "ge-quake-legend-item" + (y === latestYear ? " latest" : "");
                item.setAttribute("data-year", y);
                item.innerHTML =
                  '<label class="legend-year-label">' +
                    '<input type="checkbox" class="ge-year-toggle" checked>' +
                    '<span class="swatch" style="background:'+color+'"></span>' +
                    '<span class="label">'+y+(y === latestYear ? " (latest)" : "")+'</span>' +
                  '</label>';

                var checkbox = item.querySelector('input.ge-year-toggle');

                function setVisible(state) {
                  visibleYears[y] = state;
                  checkbox.checked = state;
                  if (!state) {
                    item.classList.add("muted");
                  } else {
                    item.classList.remove("muted");
                  }
                  updateVisibility();
                }

                checkbox.addEventListener("click", function(e){
                  e.stopPropagation();
                  setVisible(checkbox.checked);
                });

                item.addEventListener("click", function(){
                  setVisible(!visibleYears[y]);
                });

                item.addEventListener("mouseenter", function(){
                  var p = yearPaths[y];
                  if (!p) return;
                  p.setAttribute("stroke-width", "3");
                  p.setAttribute("stroke-opacity", "1.0");
                });
                item.addEventListener("mouseleave", function(){
                  var p = yearPaths[y];
                  if (!p) return;
                  var baseWidth = (y === latestYear) ? "2.4" : "1.4";
                  var baseOpacity = (y === latestYear) ? "1.0" : "0.6";
                  p.setAttribute("stroke-width", baseWidth);
                  p.setAttribute("stroke-opacity", baseOpacity);
                });

                legend.appendChild(item);
              });
            }

            updateVisibility();

            // Simple tooltip on hover
            var tooltip = document.createElement("div");
            tooltip.className = "ge-quake-tooltip";
            tooltip.style.position = "absolute";
            tooltip.style.pointerEvents = "none";
            tooltip.style.fontSize = "11px";
            tooltip.style.padding = "4px 6px";
            tooltip.style.borderRadius = "4px";
            tooltip.style.background = "rgba(0,0,0,0.85)";
            tooltip.style.color = "#fff";
            tooltip.style.display = "none";

            var chartWrap = container;
            if (chartWrap && chartWrap.style.position === "") {
              chartWrap.style.position = "relative";
            }
            if (chartWrap) {
              chartWrap.appendChild(tooltip);
            }

            function showTooltip(evt) {
              if (!chartWrap) return;
              var rect = svg.getBoundingClientRect();
              var bx = evt.clientX - rect.left;
              var by = evt.clientY - rect.top;

              // Map x to month index
              var rel = Math.max(pad, Math.min(w - pad, bx));
              var frac = (rel - pad) / (w - pad * 2);
              var mFloat = 1 + frac * 11;
              var mIdx = Math.round(mFloat);
              if (mIdx < 1) mIdx = 1;
              if (mIdx > 12) mIdx = 12;

              var rows = [];
              years.forEach(function(y){
                if (!visibleYears[y]) return;
                var pts = byYear[y];
                for (var i = 0; i < pts.length; i++) {
                  if (pts[i].m === mIdx) {
                    rows.push({ year: y, v: pts[i].v });
                    break;
                  }
                }
              });
              if (!rows.length) {
                tooltip.style.display = "none";
                return;
              }
              // Sort by year descending so latest is on top
              rows.sort(function(a,b){ return b.year.localeCompare(a.year); });

              var monthName = monthsShort[mIdx-1];
              var html = '<strong>' + monthName + '</strong><br>';
              rows.forEach(function(r){
                html += r.year + ': ' + r.v + '<br>';
              });
              tooltip.innerHTML = html;
              tooltip.style.left = (bx + 10) + "px";
              tooltip.style.top = (by + 10) + "px";
              tooltip.style.display = "block";
            }

            function hideTooltip() {
              tooltip.style.display = "none";
            }

            svg.addEventListener("mousemove", showTooltip);
            svg.addEventListener("mouseleave", hideTooltip);
          })();
        </script>
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
      .ge-note#geEqHint{ margin-top:.25rem }
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
      .delta-pos{ color:#aef2c0; }
      .delta-neg{ color:#ffb3b3; }
      .delta-tag{ opacity:.8; font-size:.8rem; margin-left:4px }
      .ge-tip {
        cursor: help;
        font-size: .85rem;
        opacity: .65;
        margin-left: 4px;
      }
      .ge-tip:hover {
        opacity: 1;
      }
      .ge-quake-chart { width: 100%; max-width: 100%; margin-top: 6px; }
      .ge-quake-chart-svg { width: 100%; height: auto; display: block; }
      .ge-quake-chart-legend { margin-top: 6px; font-size: .85rem; display:flex; flex-wrap:wrap; gap:8px; }
      .ge-quake-legend-item { display:inline-flex; align-items:center; gap:4px; opacity:.8; }
      .ge-quake-legend-item.latest { opacity: 1; font-weight: 600; }
      .ge-quake-legend-item .swatch { width:12px; height:12px; border-radius:2px; display:inline-block; }
      .ge-quake-legend-item.muted { opacity: .25; }
      .ge-quake-legend-item.showall .swatch {
        background: none;
        border: 1px solid rgba(255,255,255,0.4);
      }
      .ge-quake-legend-item.median .swatch {
        background: none;
        border: 1px dashed rgba(255,255,255,0.7);
      }
      .legend-year-label {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .legend-year-label input.ge-year-toggle {
        margin: 0;
      }
    </style>
  <?php if (isset($_GET['quakes_year']) && $_GET['quakes_year'] !== '' && $_GET['quakes_year'] !== 'last6'): ?>
    <script>
      (function(){
        // After the page reloads with a specific year selected, scroll to the Monthly & YoY section.
        if (location.hash !== '#monthly' && location.hash !== '#quake-trends') {
          location.hash = '#monthly';
        }
      })();
    </script>
  <?php endif; ?>
  </section>
  <?php
  return ob_get_clean();
}
add_shortcode('gaia_quakes_detail','gaiaeyes_quakes_detail_shortcode');
