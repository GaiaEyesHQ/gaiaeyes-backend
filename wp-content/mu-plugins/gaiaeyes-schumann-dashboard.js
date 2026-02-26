(function () {
  "use strict";

  var GLOBAL_CFG = window.GAIAEYES_SCHUMANN_DASHBOARD_CFG || {};
  var sharedPayloadPromise = null;

  var STATE_LEVELS = [
    { key: "calm", min: 0.0, max: 0.03, label: "Calm", color: "#6fcde3" },
    { key: "stable", min: 0.03, max: 0.06, label: "Stable", color: "#7ce0d8" },
    { key: "active", min: 0.06, max: 0.1, label: "Active", color: "#e7e184" },
    { key: "elevated", min: 0.1, max: 0.16, label: "Elevated", color: "#f7b27f" },
    { key: "intense", min: 0.16, max: Number.POSITIVE_INFINITY, label: "Intense", color: "#f08f90" },
  ];

  var BAND_LABELS = {
    band_7_9: "7-9 Hz \u2022 Ground",
    band_13_15: "13-15 Hz \u2022 Flow",
    band_18_20: "18-20 Hz \u2022 Spark",
  };

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function toNumber(value, fallback) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback || 0);
  }

  function parseJSON(input, fallback) {
    if (!input) {
      return fallback;
    }
    try {
      var parsed = JSON.parse(input);
      return parsed && typeof parsed === "object" ? parsed : fallback;
    } catch (_err) {
      return fallback;
    }
  }

  function formatDateTime(value) {
    if (!value) {
      return "-";
    }
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatNumber(value, digits) {
    if (!Number.isFinite(value)) {
      return "-";
    }
    return value.toFixed(digits);
  }

  function qualityStatus(quality) {
    var usable = quality && quality.usable;
    var score = quality ? toNumber(quality.quality_score, 0) : 0;
    if (usable === false || score < 0.5) {
      return { text: "Low confidence", className: "ge-sch-chip-low" };
    }
    return { text: "OK", className: "ge-sch-chip-ok" };
  }

  function deriveState(amplitude) {
    var value = toNumber(amplitude, 0);
    for (var i = 0; i < STATE_LEVELS.length; i += 1) {
      var level = STATE_LEVELS[i];
      if (value >= level.min && value < level.max) {
        return level;
      }
    }
    return STATE_LEVELS[0];
  }

  function paletteForContrast(highContrast) {
    var stops = highContrast
      ? [
          [0.0, [0, 0, 0]],
          [0.25, [11, 96, 142]],
          [0.55, [94, 212, 223]],
          [0.8, [255, 220, 125]],
          [1.0, [255, 123, 96]],
        ]
      : [
          [0.0, [6, 18, 28]],
          [0.3, [14, 98, 129]],
          [0.6, [116, 208, 188]],
          [1.0, [248, 188, 101]],
        ];

    var out = new Array(256);
    for (var i = 0; i < 256; i += 1) {
      var t = i / 255;
      var lower = stops[0];
      var upper = stops[stops.length - 1];

      for (var s = 0; s < stops.length - 1; s += 1) {
        if (t >= stops[s][0] && t <= stops[s + 1][0]) {
          lower = stops[s];
          upper = stops[s + 1];
          break;
        }
      }

      var segmentRange = Math.max(upper[0] - lower[0], 1e-6);
      var localT = (t - lower[0]) / segmentRange;
      out[i] = [
        Math.round(lower[1][0] + (upper[1][0] - lower[1][0]) * localT),
        Math.round(lower[1][1] + (upper[1][1] - lower[1][1]) * localT),
        Math.round(lower[1][2] + (upper[1][2] - lower[1][2]) * localT),
      ];
    }

    return out;
  }

  function percentile(sortedValues, ratio) {
    if (!sortedValues.length) {
      return 0;
    }
    var idx = clamp(Math.round((sortedValues.length - 1) * ratio), 0, sortedValues.length - 1);
    return sortedValues[idx];
  }

  function resizeCanvas(canvas, cssWidth, cssHeight) {
    var ratio = window.devicePixelRatio || 1;
    var width = Math.max(1, Math.floor(cssWidth * ratio));
    var height = Math.max(1, Math.floor(cssHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    canvas.style.width = cssWidth + "px";
    canvas.style.height = cssHeight + "px";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return ctx;
  }

  function fetchDashboardPayload(restUrl) {
    if (!restUrl) {
      return Promise.reject(new Error("Missing rest URL"));
    }
    if (!sharedPayloadPromise) {
      sharedPayloadPromise = fetch(restUrl, {
        credentials: "same-origin",
        cache: "no-store",
      }).then(function (resp) {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status);
        }
        return resp.json();
      });
    }
    return sharedPayloadPromise;
  }

  function normalizeSeriesRows(seriesPayload) {
    var rows = Array.isArray(seriesPayload && seriesPayload.rows) ? seriesPayload.rows.slice() : [];
    return rows
      .map(function (row) {
        var ts = row && row.ts ? row.ts : null;
        var date = ts ? new Date(ts) : null;
        var amp = row && row.amplitude ? row.amplitude : {};
        var harm = row && row.harmonics ? row.harmonics : {};
        var quality = row && row.quality ? row.quality : {};

        return {
          ts: ts,
          date: date,
          sr: toNumber(amp.sr_total_0_20, Number.NaN),
          band7_9: toNumber(amp.band_7_9, Number.NaN),
          band13_15: toNumber(amp.band_13_15, Number.NaN),
          band18_20: toNumber(amp.band_18_20, Number.NaN),
          f0: toNumber(harm.f0, Number.NaN),
          usable: quality.usable !== false,
          qualityScore: toNumber(quality.quality_score, 1),
        };
      })
      .filter(function (row) {
        return row.date && !Number.isNaN(row.date.getTime());
      })
      .sort(function (a, b) {
        return a.date.getTime() - b.date.getTime();
      });
  }

  function normalizeHeatmap(heatmapPayload) {
    var axis = heatmapPayload && heatmapPayload.axis ? heatmapPayload.axis : {};
    var points = Array.isArray(heatmapPayload && heatmapPayload.points) ? heatmapPayload.points.slice() : [];

    var normalizedPoints = points
      .map(function (point) {
        var ts = point && point.ts ? point.ts : null;
        var date = ts ? new Date(ts) : null;
        var bins = Array.isArray(point && point.bins)
          ? point.bins.map(function (v) {
              return toNumber(v, Number.NaN);
            })
          : [];
        return {
          ts: ts,
          date: date,
          bins: bins,
        };
      })
      .filter(function (point) {
        return point.date && !Number.isNaN(point.date.getTime()) && point.bins.length > 0;
      });

    return {
      axis: {
        freqStartHz: Number.isFinite(toNumber(axis.freq_start_hz, Number.NaN)) ? toNumber(axis.freq_start_hz, 0) : 0,
        freqStepHz: Number.isFinite(toNumber(axis.freq_step_hz, Number.NaN)) ? toNumber(axis.freq_step_hz, 0) : 0,
        bins: toNumber(axis.bins, normalizedPoints[0] ? normalizedPoints[0].bins.length : 160),
      },
      points: normalizedPoints,
    };
  }

  function SchumannWidget(root) {
    this.root = root;
    var cfg = parseJSON(root.getAttribute("data-config"), {});

    this.state = {
      highContrast: false,
      appLink: cfg.appLink || GLOBAL_CFG.appLink || "",
      proEnabled: !!(typeof cfg.proEnabled === "boolean" ? cfg.proEnabled : GLOBAL_CFG.proEnabled),
      payload: null,
      seriesRows: [],
      heatmap: null,
    };

    this.refs = {};
    this.cachedHeatmap = null;
    this.cachedHeatmapKey = "";

    this.mount();
    this.bindEvents();
    this.load();
  }

  SchumannWidget.prototype.mount = function () {
    this.root.innerHTML = [
      '<div class="ge-sch-wrap">',
      '  <div class="ge-sch-header">',
      '    <h2 class="ge-sch-title">Schumann Dashboard</h2>',
      '    <div class="ge-sch-controls">',
      '      <button type="button" class="ge-sch-pill-btn" data-action="toggle-contrast">Contrast</button>',
      '      <button type="button" class="ge-sch-pill-btn" data-action="download-heatmap">Download PNG</button>',
      '      <a class="ge-sch-action-link" data-role="open-app" target="_blank" rel="noopener noreferrer">Open in app</a>',
      '    </div>',
      '  </div>',
      '  <details class="ge-sch-help">',
      '    <summary>How to read this</summary>',
      '    <ul>',
      '      <li>Gauge: overall intensity level (0-20 Hz).</li>',
      '      <li>Heatmap: time x frequency; brighter = stronger.</li>',
      '      <li>Bands: relative strength in key ranges.</li>',
      '      <li>Pulse: intensity trend; dashed line = frequency.</li>',
      '    </ul>',
      '  </details>',
      '  <div class="ge-sch-meta-row">',
      '    <span class="ge-sch-chip" data-role="updated">Last updated: -</span>',
      '    <span class="ge-sch-chip" data-role="quality">Quality: -</span>',
      '    <span class="ge-sch-chip" data-role="station">Station: -</span>',
      '  </div>',
      '  <div class="ge-sch-grid">',
      '    <section class="ge-sch-card ge-sch-card--gauge">',
      '      <h3>Earth Resonance Gauge</h3>',
      '      <div class="ge-sch-gauge-wrap">',
      '        <canvas class="ge-sch-gauge-canvas" aria-label="Earth resonance gauge"></canvas>',
      '        <div>',
      '          <div class="ge-sch-gauge-value" data-role="gauge-value">-</div>',
      '          <div class="ge-sch-muted" data-role="gauge-label">Index (0-20 Hz intensity; updates every 15 minutes).</div>',
      '          <p class="ge-sch-muted" data-role="interpretation">Loading signal interpretation...</p>',
      '        </div>',
      '      </div>',
      '    </section>',
      '    <section class="ge-sch-card ge-sch-card--readouts">',
      '      <h3>Latest Readouts</h3>',
      '      <div class="ge-sch-readouts" data-role="readouts"></div>',
      '      <div class="ge-sch-band-bars" data-role="band-bars"></div>',
      '    </section>',
      '    <section class="ge-sch-card ge-sch-card--heatmap">',
      '      <h3>48h Heatmap</h3>',
      '      <div class="ge-sch-heatmap-wrap">',
      '        <canvas class="ge-sch-canvas ge-sch-heatmap-canvas"></canvas>',
      '        <div class="ge-sch-tooltip" data-role="heatmap-tooltip"></div>',
      '      </div>',
      '      <div class="ge-sch-axes" data-role="heatmap-axes"></div>',
      '      <div class="ge-sch-muted ge-sch-legend">Heatmap = time x frequency. Brighter = stronger.</div>',
      '    </section>',
      '    <section class="ge-sch-card ge-sch-card--pulse">',
      '      <h3>48h Pulse Line</h3>',
      '      <div class="ge-sch-pulse-wrap">',
      '        <canvas class="ge-sch-canvas ge-sch-pulse-canvas"></canvas>',
      '        <div class="ge-sch-tooltip" data-role="pulse-tooltip"></div>',
      '      </div>',
      '      <div class="ge-sch-muted ge-sch-legend">Cyan: Intensity (0-20 Hz) \u2022 Yellow dashed: Fundamental (Hz)</div>',
      '      <div class="ge-sch-axes" data-role="pulse-axes"></div>',
      '    </section>',
      '    <section class="ge-sch-card ge-sch-card--pro">',
      '      <h3>History</h3>',
      '      <div class="ge-sch-pro-lock" data-role="pro-lock"></div>',
      '    </section>',
      '  </div>',
      '</div>'
    ].join("");

    this.refs.toggleContrast = this.root.querySelector('[data-action="toggle-contrast"]');
    this.refs.downloadHeatmap = this.root.querySelector('[data-action="download-heatmap"]');
    this.refs.openApp = this.root.querySelector('[data-role="open-app"]');

    this.refs.updated = this.root.querySelector('[data-role="updated"]');
    this.refs.quality = this.root.querySelector('[data-role="quality"]');
    this.refs.station = this.root.querySelector('[data-role="station"]');
    this.refs.gaugeCanvas = this.root.querySelector('.ge-sch-gauge-canvas');
    this.refs.gaugeValue = this.root.querySelector('[data-role="gauge-value"]');
    this.refs.gaugeLabel = this.root.querySelector('[data-role="gauge-label"]');
    this.refs.interpretation = this.root.querySelector('[data-role="interpretation"]');
    this.refs.readouts = this.root.querySelector('[data-role="readouts"]');
    this.refs.bandBars = this.root.querySelector('[data-role="band-bars"]');

    this.refs.heatmapCanvas = this.root.querySelector('.ge-sch-heatmap-canvas');
    this.refs.heatmapTooltip = this.root.querySelector('[data-role="heatmap-tooltip"]');
    this.refs.heatmapAxes = this.root.querySelector('[data-role="heatmap-axes"]');

    this.refs.pulseCanvas = this.root.querySelector('.ge-sch-pulse-canvas');
    this.refs.pulseTooltip = this.root.querySelector('[data-role="pulse-tooltip"]');
    this.refs.pulseAxes = this.root.querySelector('[data-role="pulse-axes"]');

    this.refs.proLock = this.root.querySelector('[data-role="pro-lock"]');
    if (this.refs.openApp) {
      this.refs.openApp.href = this.state.appLink || "#";
    }

    this.updateControlState();
  };

  SchumannWidget.prototype.bindEvents = function () {
    var self = this;

    this.refs.toggleContrast.addEventListener("click", function () {
      self.state.highContrast = !self.state.highContrast;
      self.cachedHeatmap = null;
      self.render();
    });

    this.refs.downloadHeatmap.addEventListener("click", function () {
      if (!self.refs.heatmapCanvas) {
        return;
      }
      var anchor = document.createElement("a");
      anchor.href = self.refs.heatmapCanvas.toDataURL("image/png");
      anchor.download = "gaiaeyes-schumann-heatmap.png";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    });

    this.refs.heatmapCanvas.addEventListener("mousemove", function (event) {
      self.updateHeatmapTooltip(event);
    });

    this.refs.heatmapCanvas.addEventListener("mouseleave", function () {
      self.refs.heatmapTooltip.style.display = "none";
    });

    this.refs.pulseCanvas.addEventListener("mousemove", function (event) {
      self.updatePulseTooltip(event);
    });

    this.refs.pulseCanvas.addEventListener("mouseleave", function () {
      self.refs.pulseTooltip.style.display = "none";
    });
  };

  SchumannWidget.prototype.load = function () {
    var self = this;
    this.root.classList.remove("ge-sch-high-contrast");
    fetchDashboardPayload(GLOBAL_CFG.restUrl)
      .then(function (payload) {
        self.state.payload = payload;
        self.state.seriesRows = normalizeSeriesRows(payload && payload.series);
        self.state.heatmap = normalizeHeatmap(payload && payload.heatmap);
        self.render();
      })
      .catch(function (err) {
        self.root.innerHTML = '<div class="ge-sch-empty">Schumann dashboard is currently unavailable (' + String(err && err.message ? err.message : "error") + ').</div>';
      });
  };

  SchumannWidget.prototype.latestSnapshot = function () {
    var latest = this.state.payload && this.state.payload.latest;
    if (latest && latest.ok) {
      return latest;
    }
    var rows = this.state.seriesRows;
    if (!rows.length) {
      return null;
    }
    var last = rows[rows.length - 1];
    return {
      generated_at: last.ts,
      harmonics: { f0: last.f0 },
      amplitude: {
        sr_total_0_20: last.sr,
        band_7_9: last.band7_9,
        band_13_15: last.band13_15,
        band_18_20: last.band18_20,
      },
      quality: {
        usable: last.usable,
        quality_score: last.qualityScore,
        primary_source: "cumiana",
      },
    };
  };

  SchumannWidget.prototype.updateControlState = function () {
    this.refs.toggleContrast.textContent = this.state.highContrast ? "Contrast on" : "Contrast";
  };

  SchumannWidget.prototype.render = function () {
    this.updateControlState();
    this.root.classList.toggle("ge-sch-high-contrast", this.state.highContrast);

    var latest = this.latestSnapshot();
    var amplitude = latest && latest.amplitude ? latest.amplitude : {};
    var harmonics = latest && latest.harmonics ? latest.harmonics : {};
    var quality = latest && latest.quality ? latest.quality : {};

    var srTotal = toNumber(amplitude.sr_total_0_20, 0);
    var gaugeIndex = clamp(srTotal * 1000, 0, 100);
    var stateLevel = deriveState(srTotal);
    var qualityText = qualityStatus(quality);

    this.refs.updated.textContent = "Last updated: " + formatDateTime(latest && latest.generated_at);
    this.refs.quality.textContent = "Quality: " + qualityText.text;
    this.refs.quality.className = "ge-sch-chip " + qualityText.className;
    this.refs.station.textContent = "Station: " + ((quality && quality.primary_source) || "cumiana");

    this.refs.gaugeValue.textContent = formatNumber(gaugeIndex, 1) + " \u2014 " + stateLevel.label;
    this.refs.gaugeLabel.textContent = "Index (0-20 Hz intensity; updates every 15 minutes).";
    this.refs.interpretation.textContent = "Current state: " + stateLevel.label + ".";

    this.renderGauge(gaugeIndex, stateLevel.color);
    this.renderReadouts(harmonics, amplitude, quality);
    this.renderBandBars();
    this.renderHeatmap();
    this.renderPulseLine();
    this.renderProState();
  };

  SchumannWidget.prototype.renderGauge = function (value, color) {
    var canvas = this.refs.gaugeCanvas;
    var rect = canvas.getBoundingClientRect();
    var width = rect.width || 260;
    var height = rect.height || 160;
    var ctx = resizeCanvas(canvas, width, height);

    ctx.clearRect(0, 0, width, height);
    var cx = width * 0.5;
    var cy = height * 0.88;
    var radius = Math.min(width * 0.36, height * 0.8);
    var start = Math.PI * 1.1;
    var end = Math.PI * 1.9;

    ctx.lineCap = "round";
    ctx.lineWidth = 16;

    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.beginPath();
    ctx.arc(cx, cy, radius, start, end);
    ctx.stroke();

    var t = clamp(value / 100, 0, 1);
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, start, start + (end - start) * t);
    ctx.stroke();

    ctx.lineWidth = 1;
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("0", cx - radius + 4, cy + 6);
    ctx.fillText("100", cx + radius - 4, cy + 6);
  };

  SchumannWidget.prototype.renderReadouts = function (harmonics, amplitude, quality) {
    var station = quality && quality.primary_source ? quality.primary_source : "cumiana";

    var rows = [
      { label: "f0", value: Number.isFinite(toNumber(harmonics.f0, Number.NaN)) ? formatNumber(toNumber(harmonics.f0, 0), 2) + " Hz" : "-" },
      { label: BAND_LABELS.band_7_9, value: Number.isFinite(toNumber(amplitude.band_7_9, Number.NaN)) ? formatNumber(toNumber(amplitude.band_7_9, 0) * 100, 1) + "%" : "-" },
      { label: BAND_LABELS.band_13_15, value: Number.isFinite(toNumber(amplitude.band_13_15, Number.NaN)) ? formatNumber(toNumber(amplitude.band_13_15, 0) * 100, 1) + "%" : "-" },
      { label: BAND_LABELS.band_18_20, value: Number.isFinite(toNumber(amplitude.band_18_20, Number.NaN)) ? formatNumber(toNumber(amplitude.band_18_20, 0) * 100, 1) + "%" : "-" },
      { label: "Source", value: station },
    ];

    this.refs.readouts.innerHTML = rows
      .map(function (row) {
        return '<div class="ge-sch-readout"><span>' + row.label + '</span><strong>' + row.value + "</strong></div>";
      })
      .join("");
  };

  SchumannWidget.prototype.renderBandBars = function () {
    var rows = this.state.seriesRows;
    if (!rows.length) {
      this.refs.bandBars.innerHTML = '<div class="ge-sch-muted">Band trends unavailable.</div>';
      return;
    }

    var latest = rows[rows.length - 1];
    var baseline = rows.slice(Math.max(0, rows.length - 9), Math.max(0, rows.length - 1));

    function avg(list, key) {
      var vals = list.map(function (item) { return item[key]; }).filter(Number.isFinite);
      if (!vals.length) {
        return Number.NaN;
      }
      var total = vals.reduce(function (sum, value) { return sum + value; }, 0);
      return total / vals.length;
    }

    function robustRange(list, key) {
      var preferred = list
        .filter(function (item) { return item.usable !== false; })
        .map(function (item) { return item[key]; })
        .filter(Number.isFinite);

      var vals = preferred.length >= 8
        ? preferred.slice()
        : list.map(function (item) { return item[key]; }).filter(Number.isFinite);
      if (!vals.length) {
        return null;
      }
      vals.sort(function (a, b) { return a - b; });
      if (vals.length < 8) {
        return { min: vals[0], max: vals[vals.length - 1] };
      }

      var low = percentile(vals, 0.05);
      var high = percentile(vals, 0.95);
      if (high > low) {
        return { min: low, max: high };
      }

      return {
        min: vals[0],
        max: vals[vals.length - 1],
      };
    }

    var ranges = {
      band7_9: robustRange(rows, "band7_9"),
      band13_15: robustRange(rows, "band13_15"),
      band18_20: robustRange(rows, "band18_20"),
    };

    var bands = [
      { key: "band7_9", label: BAND_LABELS.band_7_9 },
      { key: "band13_15", label: BAND_LABELS.band_13_15 },
      { key: "band18_20", label: BAND_LABELS.band_18_20 },
    ];

    var html = bands
      .map(function (band) {
        var current = toNumber(latest[band.key], Number.NaN);
        var baselineAvg = avg(baseline, band.key);
        var delta = Number.isFinite(current) && Number.isFinite(baselineAvg) ? current - baselineAvg : 0;
        var trendClass = "ge-sch-trend-flat";
        var trendArrow = "\u2192";
        if (delta > 0.008) {
          trendClass = "ge-sch-trend-up";
          trendArrow = "\u2191";
        } else if (delta < -0.008) {
          trendClass = "ge-sch-trend-down";
          trendArrow = "\u2193";
        }

        var pct = 0;
        var range = ranges[band.key];
        if (Number.isFinite(current) && range && range.max > range.min) {
          pct = clamp(((current - range.min) / (range.max - range.min)) * 100, 0, 100);
        }
        if (Number.isFinite(current) && current > 0 && pct < 4) {
          pct = 4;
        }

        return [
          '<div class="ge-sch-band-row" style="opacity:' + (latest.usable ? "1" : "0.55") + '">',
          '  <span>' + band.label + '</span>',
          '  <div class="ge-sch-progress"><span style="width:' + pct.toFixed(1) + '%"></span></div>',
          '  <span class="' + trendClass + '">' + trendArrow + " " + (Number.isFinite(current) ? formatNumber(current * 100, 1) + "%" : "-") + "</span>",
          '</div>'
        ].join("");
      })
      .join("");

    this.refs.bandBars.innerHTML = html + '<div class="ge-sch-muted">Relative strength vs last 48h. Trend compares to previous 2 hours.</div>';
  };

  SchumannWidget.prototype.renderHeatmap = function () {
    var heatmap = this.state.heatmap;
    var points = heatmap && Array.isArray(heatmap.points) ? heatmap.points : [];

    if (!points.length) {
      this.refs.heatmapAxes.innerHTML = '<span>Heatmap unavailable</span>';
      var ctxEmpty = resizeCanvas(this.refs.heatmapCanvas, this.refs.heatmapCanvas.clientWidth || 600, this.refs.heatmapCanvas.clientHeight || 230);
      ctxEmpty.clearRect(0, 0, this.refs.heatmapCanvas.clientWidth || 600, this.refs.heatmapCanvas.clientHeight || 230);
      ctxEmpty.fillStyle = "rgba(255,255,255,0.65)";
      ctxEmpty.font = "13px sans-serif";
      ctxEmpty.fillText("Heatmap data unavailable", 14, 24);
      return;
    }

    var cssWidth = this.refs.heatmapCanvas.clientWidth || this.refs.heatmapCanvas.parentElement.clientWidth || 640;
    var cssHeight = this.refs.heatmapCanvas.clientHeight || 230;
    var ctx = resizeCanvas(this.refs.heatmapCanvas, cssWidth, cssHeight);

    var bins = points[0].bins.length;
    var values = [];
    var i;
    for (i = 0; i < points.length; i += 1) {
      for (var b = 0; b < bins; b += 1) {
        var v = points[i].bins[b];
        if (Number.isFinite(v)) {
          values.push(v);
        }
      }
    }

    values.sort(function (a, b) { return a - b; });
    var minValue = percentile(values, 0.03);
    var maxValue = percentile(values, 0.97);
    if (!(maxValue > minValue)) {
      maxValue = minValue + 1e-3;
    }

    var heatKey = [points.length, bins, this.state.highContrast ? 1 : 0, minValue.toFixed(5), maxValue.toFixed(5)].join(":");
    if (!this.cachedHeatmap || this.cachedHeatmapKey !== heatKey) {
      var offscreen = document.createElement("canvas");
      offscreen.width = points.length;
      offscreen.height = bins;
      var offCtx = offscreen.getContext("2d");
      var imageData = offCtx.createImageData(offscreen.width, offscreen.height);
      var palette = paletteForContrast(this.state.highContrast);

      var qualityByTs = {};
      this.state.seriesRows.forEach(function (row) {
        qualityByTs[row.ts] = row.usable;
      });

      for (var x = 0; x < points.length; x += 1) {
        var col = points[x];
        var usable = qualityByTs[col.ts] !== false;
        for (var y = 0; y < bins; y += 1) {
          var idx = (y * offscreen.width + x) * 4;
          var raw = toNumber(col.bins[y], minValue);
          var normalized = clamp((raw - minValue) / (maxValue - minValue), 0, 1);
          var colorIdx = clamp(Math.round(normalized * 255), 0, 255);
          var rgb = palette[colorIdx];

          imageData.data[idx] = rgb[0];
          imageData.data[idx + 1] = rgb[1];
          imageData.data[idx + 2] = rgb[2];
          imageData.data[idx + 3] = usable ? 255 : 100;
        }
      }

      offCtx.putImageData(imageData, 0, 0);
      this.cachedHeatmap = {
        canvas: offscreen,
        minValue: minValue,
        maxValue: maxValue,
      };
      this.cachedHeatmapKey = heatKey;
    }

    ctx.clearRect(0, 0, cssWidth, cssHeight);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this.cachedHeatmap.canvas, 0, 0, cssWidth, cssHeight);

    var axis = heatmap.axis || {};
    var freqStart = toNumber(axis.freqStartHz, 0);
    var freqStep = toNumber(axis.freqStepHz, 0);
    if (!(freqStep > 0)) {
      freqStep = 20 / Math.max(1, bins);
    }

    var guides = [7.8, 14.1, 20.0];
    ctx.strokeStyle = "rgba(255,255,255,0.36)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    guides.forEach(function (freq) {
      var binPos = (freq - freqStart) / freqStep;
      var yPx = cssHeight - (binPos / Math.max(1, bins - 1)) * cssHeight;
      if (yPx >= 0 && yPx <= cssHeight) {
        ctx.beginPath();
        ctx.moveTo(0, yPx);
        ctx.lineTo(cssWidth, yPx);
        ctx.stroke();
      }
    });
    ctx.setLineDash([]);

    this.refs.heatmapAxes.innerHTML = [
      '<span>' + formatDateTime(points[0].ts) + '</span>',
      '<span>0-20 Hz</span>',
      '<span>' + formatDateTime(points[points.length - 1].ts) + '</span>'
    ].join("");
  };

  SchumannWidget.prototype.updateHeatmapTooltip = function (event) {
    var heatmap = this.state.heatmap;
    var points = heatmap && heatmap.points ? heatmap.points : [];
    if (!points.length) {
      return;
    }

    var rect = this.refs.heatmapCanvas.getBoundingClientRect();
    var x = clamp(event.clientX - rect.left, 0, rect.width - 1);
    var y = clamp(event.clientY - rect.top, 0, rect.height - 1);

    var pointIndex = clamp(Math.floor((x / rect.width) * points.length), 0, points.length - 1);
    var bins = points[pointIndex].bins;
    var binCount = bins.length;
    var binIndex = clamp(Math.floor((1 - y / rect.height) * binCount), 0, binCount - 1);

    var axis = heatmap.axis || {};
    var freqStart = toNumber(axis.freqStartHz, 0);
    var freqStep = toNumber(axis.freqStepHz, 0);
    if (!(freqStep > 0)) {
      freqStep = 20 / Math.max(1, binCount);
    }

    var freq = freqStart + freqStep * binIndex;
    var intensity = toNumber(bins[binIndex], Number.NaN);

    this.refs.heatmapTooltip.style.display = "block";
    this.refs.heatmapTooltip.style.left = x + "px";
    this.refs.heatmapTooltip.style.top = y + "px";
    this.refs.heatmapTooltip.innerHTML = [
      '<div><strong>' + formatDateTime(points[pointIndex].ts) + '</strong></div>',
      '<div>Freq: ' + formatNumber(freq, 2) + ' Hz</div>',
      '<div>Intensity: ' + (Number.isFinite(intensity) ? formatNumber(intensity, 3) : '-') + '</div>'
    ].join("");
  };

  SchumannWidget.prototype.renderPulseLine = function () {
    var rows = this.state.seriesRows;
    var canvas = this.refs.pulseCanvas;

    if (!rows.length) {
      var emptyCtx = resizeCanvas(canvas, canvas.clientWidth || 600, canvas.clientHeight || 210);
      emptyCtx.clearRect(0, 0, canvas.clientWidth || 600, canvas.clientHeight || 210);
      emptyCtx.fillStyle = "rgba(255,255,255,0.65)";
      emptyCtx.font = "13px sans-serif";
      emptyCtx.fillText("Pulse series unavailable", 14, 24);
      this.refs.pulseAxes.innerHTML = '<span>Series unavailable</span>';
      return;
    }

    var cssWidth = canvas.clientWidth || canvas.parentElement.clientWidth || 640;
    var cssHeight = canvas.clientHeight || 210;
    var ctx = resizeCanvas(canvas, cssWidth, cssHeight);
    var margin = { top: 14, right: 52, bottom: 26, left: 50 };

    var plotWidth = Math.max(12, cssWidth - margin.left - margin.right);
    var plotHeight = Math.max(12, cssHeight - margin.top - margin.bottom);

    var srValues = rows.map(function (row) { return row.sr; }).filter(Number.isFinite);
    var f0Values = rows.map(function (row) { return row.f0; }).filter(Number.isFinite);
    var yMax = Math.max(0.16, srValues.length ? Math.max.apply(null, srValues) * 1.2 : 0.16);
    var yMin = 0;

    var tMin = rows[0].date.getTime();
    var tMax = rows[rows.length - 1].date.getTime();
    if (tMax <= tMin) {
      tMax = tMin + 1;
    }

    function xForDate(date) {
      return margin.left + ((date.getTime() - tMin) / (tMax - tMin)) * plotWidth;
    }

    function yForSR(value) {
      return margin.top + (1 - (value - yMin) / Math.max(1e-6, yMax - yMin)) * plotHeight;
    }

    var f0Min = f0Values.length ? Math.min.apply(null, f0Values) : 7.4;
    var f0Max = f0Values.length ? Math.max.apply(null, f0Values) : 8.2;
    if (f0Max <= f0Min) {
      f0Max = f0Min + 0.2;
    }

    function yForF0(value) {
      var normalized = (value - f0Min) / Math.max(1e-6, f0Max - f0Min);
      return margin.top + (1 - normalized) * plotHeight;
    }

    ctx.clearRect(0, 0, cssWidth, cssHeight);

    ctx.strokeStyle = "rgba(255,255,255,0.14)";
    ctx.lineWidth = 1;
    for (var i = 0; i <= 4; i += 1) {
      var yTick = margin.top + (plotHeight / 4) * i;
      ctx.beginPath();
      ctx.moveTo(margin.left, yTick);
      ctx.lineTo(margin.left + plotWidth, yTick);
      ctx.stroke();

      var srAtTick = yMax - (yMax / 4) * i;
      ctx.fillStyle = "rgba(255,255,255,0.75)";
      ctx.font = "11px sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(formatNumber(srAtTick, 3), margin.left - 6, yTick + 3);
    }

    var timeIndices = [0, Math.floor(rows.length / 2), rows.length - 1];
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    timeIndices.forEach(function (idx) {
      var row = rows[idx];
      var xTick = xForDate(row.date);
      ctx.fillText(
        row.date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        xTick,
        margin.top + plotHeight + 16
      );
    });

    ctx.lineWidth = 2;
    for (var j = 1; j < rows.length; j += 1) {
      var a = rows[j - 1];
      var b = rows[j];
      if (!Number.isFinite(a.sr) || !Number.isFinite(b.sr)) {
        continue;
      }

      var alpha = (a.usable === false || b.usable === false) ? 0.28 : 0.98;
      ctx.strokeStyle = "rgba(92, 214, 232, " + alpha + ")";
      ctx.beginPath();
      ctx.moveTo(xForDate(a.date), yForSR(a.sr));
      ctx.lineTo(xForDate(b.date), yForSR(b.sr));
      ctx.stroke();
    }

    rows.forEach(function (row) {
      if (!Number.isFinite(row.sr) || row.usable !== false) {
        return;
      }
      ctx.fillStyle = "rgba(243,159,150,0.8)";
      ctx.beginPath();
      ctx.arc(xForDate(row.date), yForSR(row.sr), 2.2, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.strokeStyle = "rgba(255, 209, 126, 0.95)";
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.4;
    var started = false;
    ctx.beginPath();
    rows.forEach(function (row) {
      if (!Number.isFinite(row.f0)) {
        return;
      }
      var x = xForDate(row.date);
      var y = yForF0(row.f0);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "rgba(255, 230, 181, 0.9)";
    ctx.textAlign = "left";
    var steps = 3;
    for (var tick = 0; tick <= steps; tick += 1) {
      var f0Tick = f0Min + ((f0Max - f0Min) / steps) * tick;
      var yTick2 = yForF0(f0Tick);
      ctx.fillText(formatNumber(f0Tick, 2) + " Hz", margin.left + plotWidth + 6, yTick2 + 3);
    }

    this.refs.pulseAxes.innerHTML = '<span>sr_total_0_20</span><span>f0 overlay (Hz)</span><span>Low quality points dimmed</span>';
  };

  SchumannWidget.prototype.updatePulseTooltip = function (event) {
    var rows = this.state.seriesRows;
    if (!rows.length) {
      return;
    }

    var rect = this.refs.pulseCanvas.getBoundingClientRect();
    var x = clamp(event.clientX - rect.left, 0, rect.width - 1);
    var idx = clamp(Math.round((x / rect.width) * (rows.length - 1)), 0, rows.length - 1);
    var row = rows[idx];

    this.refs.pulseTooltip.style.display = "block";
    this.refs.pulseTooltip.style.left = x + "px";
    this.refs.pulseTooltip.style.top = "18px";
    this.refs.pulseTooltip.innerHTML = [
      '<div><strong>' + formatDateTime(row.ts) + '</strong></div>',
      '<div>Pulse: ' + (Number.isFinite(row.sr) ? formatNumber(row.sr, 3) : '-') + '</div>',
      '<div>f0: ' + (Number.isFinite(row.f0) ? formatNumber(row.f0, 2) + ' Hz' : '-') + '</div>',
      '<div>' + (row.usable ? 'Quality OK' : 'Low confidence') + '</div>'
    ].join("");
  };

  SchumannWidget.prototype.renderProState = function () {
    if (this.state.proEnabled) {
      this.refs.proLock.innerHTML = [
        '<span>Pro history enabled. 30-day window hook is active.</span>',
        '<button class="ge-sch-pill-btn" type="button" disabled>30d history (coming soon)</button>'
      ].join("");
      return;
    }

    this.refs.proLock.innerHTML = [
      '<span>Free window: 48h (15-minute cadence).</span>',
      '<button class="ge-sch-pill-btn" type="button" disabled>Pro: 30d history</button>'
    ].join("");
  };

  function boot() {
    var roots = document.querySelectorAll('[data-gaiaeyes-schumann-dashboard="1"]');
    if (!roots.length) {
      return;
    }
    roots.forEach(function (root) {
      new SchumannWidget(root);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
