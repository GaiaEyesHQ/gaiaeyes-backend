(function () {
  const cfg = window.GAIA_DASHBOARD_CFG || {};
  const normalizeBase = (value) => (value || "").replace(/\/+$/, "");
  const backendBase = normalizeBase(cfg.backendBase);
  const dashboardProxy = normalizeBase(cfg.dashboardProxy);
  const memberRoutes = cfg.memberRoutes && typeof cfg.memberRoutes === "object" ? cfg.memberRoutes : {};
  const supportUrl = cfg.supportUrl || "/support/";
  const publicLinks = cfg.publicLinks && typeof cfg.publicLinks === "object" ? cfg.publicLinks : {};

  const esc = (value) =>
    String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const pillClass = (severity) => {
    const s = String(severity || "").toLowerCase();
    if (s === "high" || s === "red" || s === "alert") return "gaia-dashboard__pill gaia-dashboard__pill--high";
    if (s === "watch" || s === "warn" || s === "orange" || s === "yellow")
      return "gaia-dashboard__pill gaia-dashboard__pill--watch";
    return "gaia-dashboard__pill";
  };

  const DEFAULT_GAUGE_ZONES = [
    { min: 0, max: 29, key: "low" },
    { min: 30, max: 59, key: "mild" },
    { min: 60, max: 79, key: "elevated" },
    { min: 80, max: 100, key: "high" },
  ];

  const GAUGE_PALETTE = {
    low: { hex: "#63b787", glow: "rgba(99,183,135,0.30)", glowPx: 2 },
    mild: { hex: "#9ea66c", glow: "rgba(158,166,108,0.34)", glowPx: 2 },
    elevated: { hex: "#c8925b", glow: "rgba(200,146,91,0.42)", glowPx: 4 },
    high: { hex: "#c9756d", glow: "rgba(201,117,109,0.56)", glowPx: 6 },
    calibrating: { hex: "#9da9c1", glow: "rgba(157,169,193,0.28)", glowPx: 1 },
  };

  const normalizeZoneKey = (raw) => {
    const key = String(raw || "").toLowerCase().trim();
    if (key === "low" || key === "mild" || key === "elevated" || key === "high") return key;
    if (key === "calibrating") return "calibrating";
    return "";
  };

  const zoneLabelFromKey = (zoneKey) => {
    const key = normalizeZoneKey(zoneKey);
    if (!key) return "";
    if (key === "calibrating") return "Calibrating";
    return key.charAt(0).toUpperCase() + key.slice(1);
  };

  const normalizeGaugeZones = (zonesRaw) => {
    const source = Array.isArray(zonesRaw) && zonesRaw.length ? zonesRaw : DEFAULT_GAUGE_ZONES;
    const normalized = source
      .map((zone) => {
        const min = Number(zone && zone.min);
        const max = Number(zone && zone.max);
        const key = normalizeZoneKey(zone && zone.key);
        if (!Number.isFinite(min) || !Number.isFinite(max) || !key || key === "calibrating") return null;
        const lo = Math.min(min, max);
        const hi = Math.max(min, max);
        const start = Math.max(0, Math.min(100, lo));
        const end = Math.max(start, Math.min(100, hi + 1));
        return {
          min: lo,
          max: hi,
          key,
          startPct: start,
          widthPct: Math.max(1, end - start),
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.min - b.min);

    return normalized.length ? normalized : DEFAULT_GAUGE_ZONES.map((z) => ({
      ...z,
      startPct: z.min,
      widthPct: Math.max(1, Math.min(100, z.max + 1) - z.min),
    }));
  };

  const zoneKeyForValue = (value, zones) => {
    if (!Number.isFinite(value)) return "";
    const numeric = Math.max(0, Math.min(100, Number(value)));
    for (const zone of zones || []) {
      if (numeric >= zone.min && numeric <= zone.max) return zone.key;
    }
    if (Array.isArray(zones) && zones.length) {
      if (numeric < zones[0].min) return zones[0].key;
      return zones[zones.length - 1].key;
    }
    return "";
  };

  const formatGaugeValue = (value) => {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return String(Math.round(Number(value)));
  };

  const formatGaugeDelta = (delta) => {
    const numeric = Number(delta);
    if (!Number.isFinite(numeric)) return "(0)";
    const rounded = Math.round(numeric);
    return `(${rounded > 0 ? "+" : ""}${rounded})`;
  };

  const gaugeHasAffordance = (zoneKey) => {
    const zone = normalizeZoneKey(zoneKey);
    return zone === "elevated" || zone === "high";
  };

  const normalizeDriverSeverity = (severity) => {
    const s = String(severity || "").toLowerCase();
    if (s === "high") return "high";
    if (s === "watch") return "watch";
    if (s === "elevated") return "elevated";
    if (s === "mild") return "mild";
    return "low";
  };

  const driverZoneFromSeverity = (severity) => {
    const s = normalizeDriverSeverity(severity);
    if (s === "high") return "high";
    if (s === "watch" || s === "elevated") return "elevated";
    if (s === "mild") return "mild";
    return "low";
  };

  const driverProgress = (severity) => {
    const s = normalizeDriverSeverity(severity);
    if (s === "high") return 1;
    if (s === "watch" || s === "elevated") return 0.76;
    if (s === "mild") return 0.5;
    return 0.28;
  };

  const driverHasAffordance = (severity) => {
    const s = normalizeDriverSeverity(severity);
    return s === "watch" || s === "elevated" || s === "high";
  };

  const formatDriverValue = (driver) => {
    if (!driver || driver.value == null || Number.isNaN(Number(driver.value))) return "";
    const raw = Number(driver.value);
    const key = String(driver.key || "").toLowerCase();
    const unit = String(driver.unit || "").trim();
    let valueText = "";
    if (key === "aqi" || key === "sw") {
      valueText = String(Math.round(raw));
    } else if (key === "schumann") {
      valueText = raw.toFixed(2);
    } else if (Math.abs(raw - Math.round(raw)) < 0.01) {
      valueText = String(Math.round(raw));
    } else {
      valueText = raw.toFixed(1);
    }
    if (!unit) return valueText;
    if (key === "temp") return `${valueText}°C`;
    return `${valueText} ${unit}`;
  };

  const renderGaugeCard = (row, zones, entry) => {
    const numeric = Number(row && row.value);
    const hasValue = Number.isFinite(numeric);
    const meta = row && row.meta && typeof row.meta === "object" ? row.meta : {};
    const zoneKey =
      normalizeZoneKey(meta.zone) ||
      (hasValue ? zoneKeyForValue(numeric, zones) : "calibrating");
    const zoneLabel = String(meta.label || "").trim() || zoneLabelFromKey(zoneKey) || "Calibrating";
    const zoneKeyLabel = zoneKey && zoneKey !== "calibrating" ? zoneLabelFromKey(zoneKey) : "";
    const delta = Number(row && row.delta);
    const deltaStrong = Math.abs(delta || 0) >= 5;
    const clickable = !!entry;
    const emphasized = gaugeHasAffordance(zoneKey);
    const clamped = hasValue ? Math.max(0, Math.min(100, numeric)) : 0;
    const progress = clamped / 100;
    const radius = 40;
    const circumference = 2 * Math.PI * radius;
    const dash = (circumference * progress).toFixed(3);
    const gap = Math.max(0, circumference - Number(dash)).toFixed(3);
    const theta = ((progress * 360) - 90) * (Math.PI / 180);
    const markerX = (50 + radius * Math.cos(theta)).toFixed(2);
    const markerY = (50 + radius * Math.sin(theta)).toFixed(2);
    const gradientKey = String((row && row.key) || "gauge").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
    const gradientId = `gaia-gauge-grad-${gradientKey}`;
    const palette = GAUGE_PALETTE[zoneKey] || GAUGE_PALETTE.mild;
    const zoneColor = zoneKey === "calibrating" ? GAUGE_PALETTE.calibrating.hex : palette.hex;
    const arcStyle = emphasized ? `filter:drop-shadow(0 0 ${palette.glowPx}px ${palette.glow})` : "";
    const cardClass = clickable ? "gaia-dashboard__gauge gaia-dashboard__gauge--clickable" : "gaia-dashboard__gauge";
    const deltaClass = deltaStrong ? "gaia-dashboard__gauge-delta gaia-dashboard__gauge-delta--strong" : "gaia-dashboard__gauge-delta";

    return `
      <article class="${cardClass}" ${clickable ? `data-gauge-key="${esc(row && row.key ? row.key : "")}"` : ""}>
        <div class="gaia-dashboard__gauge-label">${esc(row && row.label ? row.label : "")}</div>
        <div class="gaia-dashboard__gauge-meter">
          <svg class="gaia-dashboard__gauge-arc" viewBox="0 0 100 100" aria-hidden="true">
            <defs>
              <linearGradient id="${gradientId}" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="${GAUGE_PALETTE.low.hex}" />
                <stop offset="40%" stop-color="${GAUGE_PALETTE.mild.hex}" />
                <stop offset="70%" stop-color="${GAUGE_PALETTE.elevated.hex}" />
                <stop offset="100%" stop-color="${GAUGE_PALETTE.high.hex}" />
              </linearGradient>
            </defs>
            <circle class="gaia-dashboard__gauge-ring" cx="50" cy="50" r="${radius}"></circle>
            ${
              hasValue
                ? `<circle class="gaia-dashboard__gauge-value-arc" cx="50" cy="50" r="${radius}" stroke="url(#${gradientId})" style="${arcStyle}" stroke-dasharray="${dash} ${gap}" transform="rotate(-90 50 50)"></circle>`
                : ""
            }
            ${
              hasValue
                ? `<circle class="gaia-dashboard__gauge-dot" cx="${markerX}" cy="${markerY}" r="4.2" style="stroke:${palette.hex}"></circle>`
                : ""
            }
          </svg>
          <div class="gaia-dashboard__gauge-center">
            <div class="gaia-dashboard__gauge-value">
              <span>${formatGaugeValue(row && row.value)}</span>
              ${hasValue ? `<span class="${deltaClass}">${esc(formatGaugeDelta(delta))}</span>` : ""}
            </div>
            <div class="gaia-dashboard__gauge-zone" style="color:${zoneColor}">${esc(zoneLabel)}</div>
          </div>
        </div>
        ${zoneKeyLabel ? `<div class="gaia-dashboard__gauge-zone-key">${esc(zoneKeyLabel)}</div>` : ""}
        ${emphasized ? '<div class="gaia-dashboard__tap-hint">Tap for context</div>' : ""}
      </article>
    `;
  };

  const DRIVER_ROLE_META = {
    leading: {
      title: "Leading now",
      subtitle: "The clearest active signal in your mix right now.",
    },
    supporting: {
      title: "Also in play",
      subtitle: "Still active, but secondary to the lead signal.",
    },
    background: {
      title: "In the background",
      subtitle: "Present, but not leading the picture.",
    },
  };

  const driverRoleKey = (driver, index) => {
    const explicitRole = String(driver && driver.role ? driver.role : "").trim().toLowerCase();
    if (explicitRole === "primary") return "leading";
    if (explicitRole === "supporting") return "supporting";
    if (explicitRole === "background") return "background";

    const roleLabel = String(
      driver && (driver.roleLabel || driver.role_label) ? (driver.roleLabel || driver.role_label) : ""
    ).trim().toLowerCase();
    if (roleLabel === "leading now") return "leading";
    if (roleLabel === "also in play") return "supporting";
    if (roleLabel === "in the background") return "background";

    if (index === 0) return "leading";
    if (index < 3) return "supporting";
    return "background";
  };

  const renderDriversSection = (drivers, modalModels, limit = 6) => {
    if (!Array.isArray(drivers) || !drivers.length) {
      return `
        <div class="gaia-dashboard__drivers">
          <h4>What Matters Now</h4>
          <div class="gaia-dashboard__muted">Nothing is standing out strongly right now.</div>
        </div>
      `;
    }
    const modalDrivers = modalModels && modalModels.drivers && typeof modalModels.drivers === "object"
      ? modalModels.drivers
      : {};
    const buckets = { leading: [], supporting: [], background: [] };

    drivers.slice(0, limit).forEach((driver, index) => {
      const severity = normalizeDriverSeverity(driver && driver.severity);
      const zoneKey = driverZoneFromSeverity(severity);
      const color = (GAUGE_PALETTE[zoneKey] || GAUGE_PALETTE.mild).hex;
      const width = Math.max(10, Math.round(driverProgress(severity) * 100));
      const canOpen = !!modalDrivers[String(driver.key || "")];
      const emphasized = driverHasAffordance(severity);
      const roleKey = driverRoleKey(driver, index);
      const rowClass = [
        "gaia-dashboard__driver-row",
        `gaia-dashboard__driver-row--${roleKey}`,
        canOpen ? "gaia-dashboard__driver-row--clickable" : "",
      ].filter(Boolean).join(" ");
      const personalReason = String(
        driver && (driver.personalReason || driver.personal_reason)
          ? (driver.personalReason || driver.personal_reason)
          : ""
      ).trim();

      buckets[roleKey].push(`
        <div class="${rowClass}" ${canOpen ? `data-driver-key="${esc(driver.key)}"` : ""}>
          <div class="gaia-dashboard__driver-head">
            <div class="gaia-dashboard__driver-copy">
              <span class="gaia-dashboard__driver-label">${esc(driver.label || driver.key || "Driver")}</span>
              ${personalReason ? `<div class="gaia-dashboard__driver-reason">${esc(personalReason)}</div>` : ""}
            </div>
            <div class="gaia-dashboard__driver-meta">
              <span class="gaia-dashboard__driver-state" style="color:${color}">${esc(driver.state || "Low")}</span>
              <span class="gaia-dashboard__driver-value">${esc(formatDriverValue(driver))}</span>
              ${emphasized ? '<span class="gaia-dashboard__driver-value">✦</span>' : ""}
            </div>
          </div>
          <div class="gaia-dashboard__driver-bar-track">
            <div class="gaia-dashboard__driver-bar-fill" style="width:${width}%;background:${color}"></div>
          </div>
        </div>
      `);
    });

    const groups = ["leading", "supporting", "background"]
      .filter((roleKey) => buckets[roleKey].length)
      .map((roleKey) => `
        <section class="gaia-dashboard__driver-group gaia-dashboard__driver-group--${roleKey}">
          <div class="gaia-dashboard__driver-section-head">
            <h5>${esc(DRIVER_ROLE_META[roleKey].title)}</h5>
            <p>${esc(DRIVER_ROLE_META[roleKey].subtitle)}</p>
          </div>
          <div class="gaia-dashboard__drivers-list">${buckets[roleKey].join("")}</div>
        </section>
      `)
      .join("");

    return `
      <div class="gaia-dashboard__drivers">
        <h4>What Matters Now</h4>
        ${groups}
      </div>
    `;
  };

  const normalizeGeomagneticContext = (raw) => {
    if (!raw || typeof raw !== "object") return null;
    const label = String(raw.label || raw.ulf_context_label || "").trim();
    const classRaw = String(raw.class_raw || raw.classRaw || raw.ulf_context_class_raw || "").trim();
    const confidenceLabel = String(raw.confidence_label || raw.confidenceLabel || raw.ulf_confidence_label || "").trim();
    const confidenceScore = Number(raw.confidence_score ?? raw.confidenceScore ?? raw.ulf_confidence_score);
    const qualityFlags = Array.isArray(raw.quality_flags)
      ? raw.quality_flags.filter(Boolean).map(String)
      : Array.isArray(raw.qualityFlags)
        ? raw.qualityFlags.filter(Boolean).map(String)
        : [];
    const isProvisional = raw.is_provisional === true || raw.isProvisional === true || raw.ulf_is_provisional === true;
    const isUsable =
      raw.is_usable === true ||
      raw.isUsable === true ||
      raw.ulf_is_usable === true ||
      (Number.isFinite(confidenceScore) && confidenceScore >= 0.2);
    const stationCount = Number(raw.station_count ?? raw.stationCount ?? raw.ulf_station_count);
    const value = Number(raw.regional_intensity ?? raw.regionalIntensity ?? raw.ulf_regional_intensity);

    if (!label && !classRaw && !qualityFlags.length && !Number.isFinite(value)) return null;

    return {
      label: label || classRaw || "Quiet",
      classRaw,
      confidenceLabel,
      qualityFlags,
      isProvisional,
      isUsable,
      stationCount: Number.isFinite(stationCount) ? stationCount : null,
      intensity: Number.isFinite(value) ? value : null,
    };
  };

  const geomagneticToneKey = (context) => {
    const label = String(context && context.label ? context.label : "").trim().toLowerCase();
    if (label === "strong") return "high";
    if (label === "elevated") return "elevated";
    if (label === "active") return "mild";
    return "low";
  };

  const geomagneticSummary = (context) => {
    const label = String(context && context.label ? context.label : "Quiet").trim().toLowerCase();
    if (label === "strong" || label === "elevated") return `Ground-level geomagnetic context is ${label} right now.`;
    if (label === "active") return "Ground-level variability is active right now.";
    return "Ground-level geomagnetic context is quiet right now.";
  };

  const geomagneticSupport = (context) => {
    if (!context) return "";
    if (context.isProvisional) return "Baseline still building.";
    if (String(context.classRaw || "").toLowerCase().includes("coherent")) return "Coherent ground variability detected.";
    if (context.confidenceLabel) return `Confidence: ${context.confidenceLabel}`;
    return "";
  };

  const renderGeomagneticContext = (context) => {
    if (!context || !context.isUsable) return "";
    const zoneKey = geomagneticToneKey(context);
    const support = geomagneticSupport(context);
    return `
      <div class="gaia-dashboard__geomag">
        <div class="gaia-dashboard__geomag-head">
          <div>
            <h4>Geomagnetic Context</h4>
            <p class="gaia-dashboard__geomag-summary">${esc(geomagneticSummary(context))}</p>
          </div>
          <span class="${pillClass(zoneKey === "high" ? "high" : zoneKey === "elevated" || zoneKey === "mild" ? "watch" : "low")}">${esc(context.label)}</span>
        </div>
        <div class="gaia-dashboard__geomag-meta">
          ${context.confidenceLabel ? `<span class="gaia-dashboard__geomag-chip">Confidence: ${esc(context.confidenceLabel)}</span>` : ""}
          ${support ? `<span class="gaia-dashboard__geomag-chip">${esc(support)}</span>` : ""}
          ${context.stationCount != null ? `<span class="gaia-dashboard__geomag-chip">${esc(`${context.stationCount} station${context.stationCount === 1 ? "" : "s"}`)}</span>` : ""}
        </div>
      </div>
    `;
  };

  const hasGaugeData = (gauges) => {
    if (!gauges || typeof gauges !== "object") return false;
    return Object.values(gauges).some((value) => Number.isFinite(Number(value)));
  };

  const extractErrorMessage = (obj) => {
    if (!obj || typeof obj !== "object") return "";
    return String(obj.detail || obj.error || obj.message || "").trim();
  };

  const sectionOrder = ["checkin", "drivers", "summary", "actions"];
  const sectionTitles = {
    checkin: "Now",
    drivers: "What's shaping things now",
    summary: "What may stand out",
    actions: "What may help right now",
  };

  const sectionDefaults = {
    checkin: "EarthScope is still taking shape right now.",
    drivers: "Nothing is clearly leading right now.",
    summary: "Most signals look fairly steady right now. Check the highlighted cards for fresher context.",
    actions: "• Hydrate\n• Keep your sleep window steady\n• Use gentle movement",
  };
  const legacyEarthscopePrefixRegex = /^\s*Gaia Eyes\s+[—-]\s+Daily EarthScope\s*/i;
  const legacyActionMarkers = [
    "5-10 minutes paced breathing",
    "Work in 25-50 minute blocks",
    "Hydrate, add gentle movement",
    "Wind down earlier",
    "If pain flares",
  ];
  const legacyActionSplitRegex =
    /(?=(?:5-10 minutes paced breathing|Work in 25-50 minute blocks|Hydrate, add gentle movement|Wind down earlier|If pain flares))/gi;

  const mediaBase = () => {
    const fromCfg = normalizeBase(cfg.mediaBase);
    if (fromCfg) return fromCfg;
    const supabase = normalizeBase(cfg.supabaseUrl);
    if (supabase) return `${supabase}/storage/v1/object/public/space-visuals`;
    return "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals";
  };

  const cleanEarthscopeTitle = (value) => {
    const cleaned = String(value || "")
      .trim()
      .replace(/\s+—\s+\d{4}-\d{2}-\d{2}$/, "")
      .trim();
    return cleaned || "EarthScope";
  };

  const sectionKeyForHeading = (heading) => {
    const h = String(heading || "").toLowerCase();
    if (h === "now" || h.includes("check") || h.includes("today")) return "checkin";
    if (h.includes("current driver") || h.includes("driver")) return "drivers";
    if (h.includes("supportive action") || h === "actions" || h.includes("action")) return "actions";
    if (h.includes("what you may feel") || h.includes("may feel") || h.includes("summary") || h.includes("note") || h.includes("feel")) return "summary";
    return null;
  };

  const cleanMarkdownLine = (line) =>
    String(line || "")
      .trim()
      .replace(/\*\*/g, "")
      .replace(/__/g, "")
      .replace(/^[-*]\s+/, "")
      .replace(/^\d+\.\s+/, "")
      .replace(legacyEarthscopePrefixRegex, "")
      .replace(/–/g, "-")
      .trim();

  const dedupePreservingOrder = (lines) => {
    const seen = new Set();
    return (Array.isArray(lines) ? lines : [])
      .map((line) => cleanMarkdownLine(line))
      .filter((line) => {
        if (!line) return false;
        const key = line.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  };

  const splitLegacyActionChunks = (text) => {
    const input = String(text || "").trim();
    if (!input) return [];
    const starts = [];
    legacyActionSplitRegex.lastIndex = 0;
    let match = legacyActionSplitRegex.exec(input);
    while (match) {
      starts.push(match.index);
      if (legacyActionSplitRegex.lastIndex === match.index) {
        legacyActionSplitRegex.lastIndex += 1;
      }
      match = legacyActionSplitRegex.exec(input);
    }
    if (!starts.length) return [input];
    return starts
      .map((start, index) => input.slice(start, starts[index + 1] || input.length).trim())
      .filter(Boolean);
  };

  const extractLegacyActionsFromSummary = (lines) => {
    const summary = [];
    const actions = [];

    (Array.isArray(lines) ? lines : []).forEach((raw) => {
      const cleaned = cleanMarkdownLine(raw);
      if (!cleaned) return;

      const lower = cleaned.toLowerCase();
      const markerPositions = legacyActionMarkers
        .map((marker) => lower.indexOf(marker.toLowerCase()))
        .filter((index) => index >= 0)
        .sort((a, b) => a - b);

      if (!markerPositions.length) {
        summary.push(cleaned);
        return;
      }

      const markerIndex = markerPositions[0];
      const summaryPrefix = cleaned.slice(0, markerIndex).trim();
      if (summaryPrefix) {
        summary.push(summaryPrefix);
      }

      splitLegacyActionChunks(cleaned.slice(markerIndex)).forEach((chunk) => {
        const action = cleanMarkdownLine(chunk);
        if (action) actions.push(action);
      });
    });

    return {
      summary: dedupePreservingOrder(summary),
      actions: dedupePreservingOrder(actions),
    };
  };

  const parseEarthscopeSections = (markdown, driversCompact) => {
    const buckets = { checkin: [], drivers: [], summary: [], actions: [] };
    const compactDrivers = Array.isArray(driversCompact)
      ? driversCompact.map((line) => cleanMarkdownLine(line)).filter(Boolean)
      : [];
    if (!markdown || !String(markdown).trim()) {
      return {
        checkin: sectionDefaults.checkin,
        drivers: compactDrivers.length ? compactDrivers.join("\n") : sectionDefaults.drivers,
        summary: sectionDefaults.summary,
        actions: sectionDefaults.actions,
      };
    }

    const lines = String(markdown).replace(/\r\n/g, "\n").split("\n");
    let current = null;
    let hasActionItems = false;
    const unknown = [];

    for (const raw of lines) {
      const trimmed = String(raw || "").trim();
      if (!trimmed) continue;

      if (trimmed.startsWith("#")) {
        const heading = trimmed.replace(/^#+\s*/, "");
        current = sectionKeyForHeading(heading);
        continue;
      }

      const cleaned = cleanMarkdownLine(trimmed);
      if (!cleaned) continue;

      const isListItem = /^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed);
      if (current === "actions" && !isListItem && hasActionItems) {
        buckets.summary.push(cleaned);
        continue;
      }

      if (current && buckets[current]) {
        buckets[current].push(cleaned);
        if (current === "actions" && isListItem) hasActionItems = true;
      } else {
        unknown.push(cleaned);
      }
    }

    if (!buckets.summary.length && unknown.length) {
      buckets.summary = unknown.slice();
    }
    if (!buckets.checkin.length && buckets.summary.length) {
      buckets.checkin = buckets.summary.slice(0, 2);
      buckets.summary = buckets.summary.slice(Math.min(2, buckets.summary.length));
    }
    if (compactDrivers.length) {
      buckets.drivers = compactDrivers;
    }
    const extracted = extractLegacyActionsFromSummary(buckets.summary);
    if (extracted.actions.length || extracted.summary.length) {
      buckets.summary = extracted.summary;
    }
    if (extracted.actions.length) {
      buckets.actions = dedupePreservingOrder([...(buckets.actions || []), ...extracted.actions]);
    }

    return {
      checkin: buckets.checkin.length ? buckets.checkin.join("\n") : sectionDefaults.checkin,
      drivers: buckets.drivers.length ? buckets.drivers.join("\n") : sectionDefaults.drivers,
      summary: buckets.summary.length ? buckets.summary.join("\n") : sectionDefaults.summary,
      actions: buckets.actions.length
        ? buckets.actions.map((line) => `• ${line}`).join("\n")
        : sectionDefaults.actions,
    };
  };

  const backgroundCandidates = (key) => {
    const namesByKey = {
      checkin: ["now", "checkin", "today_checkin", "todays_checkin"],
      drivers: ["current_drivers", "drivers"],
      summary: ["what_you_may_feel", "summary", "note"],
      actions: ["actions", "supportive_actions"],
    };
    const names = namesByKey[key] || [key];
    const exts = ["png", "jpg", "PNG", "JPG"];
    const base = mediaBase();
    const out = [];
    names.forEach((name) => {
      exts.forEach((ext) => out.push(`${base}/social/earthscope/backgrounds/${name}.${ext}`));
    });
    return out;
  };

  const loadFirstImage = (urls, index = 0) =>
    new Promise((resolve) => {
      if (!urls || index >= urls.length) {
        resolve(null);
        return;
      }
      const img = new Image();
      img.onload = () => resolve(urls[index]);
      img.onerror = () => {
        loadFirstImage(urls, index + 1).then(resolve);
      };
      img.src = urls[index];
    });

  const applyEarthscopeBackgrounds = (root) => {
    root.querySelectorAll("[data-bg-candidates]").forEach((node) => {
      const raw = node.getAttribute("data-bg-candidates");
      if (!raw) return;
      const candidates = raw
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean);
      if (!candidates.length) return;
      loadFirstImage(candidates).then((url) => {
        if (!url) return;
        node.style.backgroundImage = `url("${url}")`;
      });
    });
  };

  const renderEarthscopeBlocks = (earthscope, driversCompact) => {
    const sections = parseEarthscopeSections(
      earthscope && earthscope.body_markdown,
      driversCompact
    );
    return sectionOrder
      .map((key) => {
        const candidates = backgroundCandidates(key).join("|");
        return `
          <article class="gaia-dashboard__es-block gaia-dashboard__es-block--${esc(key)}" data-bg-candidates="${esc(candidates)}">
            <div class="gaia-dashboard__es-overlay"></div>
            <div class="gaia-dashboard__es-content">
              <h5 class="gaia-dashboard__es-title">${esc(sectionTitles[key] || key)}</h5>
              <p class="gaia-dashboard__es-body">${esc(sections[key] || sectionDefaults[key] || "")}</p>
            </div>
          </article>
        `;
      })
      .join("");
  };

  const compactEarthscopeLine = (text) => {
    const lines = String(text || "")
      .replace(/•\s*/g, "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    return lines[0] || "";
  };

  const renderEarthscopePreview = (earthscope, driversCompact, summaryText) => {
    const sections = parseEarthscopeSections(
      earthscope && earthscope.body_markdown,
      driversCompact
    );
    const rows = ["checkin", "drivers", "actions"]
      .map((key) => {
        const body = compactEarthscopeLine(sections[key] || (key === "checkin" ? summaryText : ""));
        if (!body) return "";
        return `
          <div class="gaia-dashboard__earthscope-row">
            <div class="gaia-dashboard__earthscope-label">${esc(sectionTitles[key] || key)}</div>
            <div class="gaia-dashboard__earthscope-copy">${esc(body)}</div>
          </div>
        `;
      })
      .filter(Boolean)
      .join("");
    return rows || `<p class="gaia-dashboard__earthscope-summary">${esc(summaryText || sectionDefaults.summary)}</p>`;
  };

  const resolveEarthscopeSummary = (summaryText, earthscope, driversCompact) => {
    const direct = String(summaryText || "").trim();
    if (direct) return direct;
    const sections = parseEarthscopeSections(
      earthscope && earthscope.body_markdown,
      driversCompact
    );
    return sections.summary || sectionDefaults.summary;
  };

  const normalizeSymptomCode = (value) =>
    String(value || "")
      .trim()
      .replace(/[-\s]+/g, "_")
      .toUpperCase();

  const hideModal = (root) => {
    const modal = root.querySelector("[data-gaia-modal]");
    if (!modal) return;
    modal.classList.remove("is-open");
    document.body.classList.remove("gaia-modal-open");
  };

  const openModal = (root, html) => {
    const modal = root.querySelector("[data-gaia-modal]");
    const slot = root.querySelector("[data-gaia-modal-content]");
    if (!modal || !slot) return null;
    slot.innerHTML = html;
    modal.classList.add("is-open");
    document.body.classList.add("gaia-modal-open");
    return modal;
  };

  const renderModalList = (title, items) => {
    if (!Array.isArray(items) || !items.length) return "";
    return `
      <section class="gaia-dashboard__modal-group">
        <h5>${esc(title)}</h5>
        <ul>${items.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
      </section>
    `;
  };

  const renderContextModal = (entry) => {
    if (!entry || typeof entry !== "object") {
      return `
        <h3 class="gaia-dashboard__modal-title">Details</h3>
        <div class="gaia-dashboard__muted">No details are available for this item.</div>
      `;
    }
    const ctaPrefill = Array.isArray(entry.cta && entry.cta.prefill) ? entry.cta.prefill : [];
    const ctaPrefillAttr = esc(JSON.stringify(ctaPrefill));
    const ctaLabel = String(entry.cta && entry.cta.label ? entry.cta.label : "Log symptoms");
    const ctaAction = String(entry.cta && entry.cta.action ? entry.cta.action : "");

    return `
      <h3 class="gaia-dashboard__modal-title">${esc(entry.title || "Mission Context")}</h3>
      ${renderModalList("What's shaping things now", entry.why)}
      ${renderModalList("What may stand out", entry.what_you_may_notice || entry.whatYouMayNotice)}
      ${renderModalList("What may help right now", entry.suggested_actions || entry.suggestedActions)}
      <div class="gaia-dashboard__muted" data-modal-status></div>
      <div class="gaia-dashboard__modal-actions">
        ${
          ctaAction === "open_symptom_log"
            ? `<button class="gaia-dashboard__btn" type="button" data-modal-log="1" data-prefill='${ctaPrefillAttr}'>${esc(ctaLabel)}</button>`
            : ""
        }
        <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
      </div>
    `;
  };

  const postQuickSymptom = async (token, prefill) => {
    if (!backendBase) {
      throw new Error("Backend base URL is not configured for symptom logging.");
    }
    const list = Array.isArray(prefill) ? prefill.map(normalizeSymptomCode).filter(Boolean) : [];
    const code = list[0] || "OTHER";
    const response = await fetch(`${backendBase}/v1/symptoms`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        symptom_code: code,
        tags: list.length ? list : undefined,
      }),
    });
    const raw = await response.text();
    let parsed = null;
    try {
      parsed = raw ? JSON.parse(raw) : null;
    } catch (_) {
      parsed = null;
    }
    if (!response.ok) {
      const detail = parsed && (parsed.detail || parsed.error || parsed.message)
        ? parsed.detail || parsed.error || parsed.message
        : raw.slice(0, 180);
      throw new Error(`HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    if (parsed && parsed.ok === false) {
      throw new Error(parsed.friendly_error || parsed.error || "Could not log symptom.");
    }
    return parsed;
  };

  const fetchJson = async (url, token) => {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    const raw = await response.text();
    let parsed = null;
    try {
      parsed = raw ? JSON.parse(raw) : null;
    } catch {
      parsed = null;
    }
    if (!response.ok) {
      const detail =
        (parsed && (parsed.error || parsed.detail || parsed.message)) ||
        (raw ? raw.slice(0, 180) : "");
      throw new Error(`HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    if (parsed != null) return parsed;
    throw new Error("Invalid JSON response");
  };

  const fetchJsonWithParams = (url, token, params) => {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value == null || value === "") return;
      query.set(key, String(value));
    });
    const finalUrl = query.toString() ? `${url}?${query.toString()}` : url;
    return fetchJson(finalUrl, token);
  };

  const postJson = async (url, token, body) => {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body || {}),
    });
    const raw = await response.text();
    let parsed = null;
    try {
      parsed = raw ? JSON.parse(raw) : null;
    } catch (_) {
      parsed = null;
    }
    if (!response.ok) {
      const detail =
        (parsed && (parsed.error || parsed.detail || parsed.message || parsed.friendly_error)) ||
        (raw ? raw.slice(0, 180) : "");
      throw new Error(`HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    return parsed;
  };

  const routeFor = (key, fallback = "") => normalizeBase(memberRoutes[key] || fallback);

  const memberHubFetches = async (token) => {
    const timezone = (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "America/Chicago";
    const out = {
      features: null,
      currentSymptoms: null,
      dailyCheckIn: null,
      lunar: null,
      outlook: null,
      patternsSummary: null,
      allDrivers: null,
      errors: {},
    };

    const loaders = [
      ["features", () => fetchJsonWithParams(routeFor("features"), token, { tz: timezone })],
      ["currentSymptoms", () => fetchJsonWithParams(routeFor("currentSymptoms"), token, { window_hours: 12 })],
      ["dailyCheckIn", () => fetchJson(routeFor("dailyCheckIn"), token)],
      ["lunar", () => fetchJson(routeFor("lunar"), token)],
      ["outlook", () => fetchJson(routeFor("outlook"), token)],
      ["patternsSummary", () => fetchJson(routeFor("patternsSummary"), token)],
      ["allDrivers", () => fetchJsonWithParams(routeFor("drivers"), token, { day: localDayISO() })],
    ];

    await Promise.all(
      loaders.map(async ([key, loader]) => {
        try {
          out[key] = await loader();
        } catch (err) {
          out.errors[key] = err && err.message ? err.message : String(err);
        }
      })
    );

    return out;
  };

  const loadFullPatterns = async (token) => {
    const url = routeFor("patterns");
    if (!url) return null;
    return fetchJson(url, token);
  };

  const renderMemberHub = (root, state) => {
    renderMissionControlApp(root, state);
    const payload = state.dashboard || {};
    const modalModels = payload.modalModels && typeof payload.modalModels === "object" ? payload.modalModels : {};
    const modalGauges = modalModels.gauges && typeof modalModels.gauges === "object" ? modalModels.gauges : {};
    const modalDrivers = modalModels.drivers && typeof modalModels.drivers === "object" ? modalModels.drivers : {};
    const driversCompact = Array.isArray(payload.driversCompact) ? payload.driversCompact : [];
    const earthscope = payload.entitled === true || !!payload.memberPost ? payload.memberPost || payload.publicPost || null : payload.publicPost || payload.memberPost || null;

    const modalNode = root.querySelector("[data-gaia-modal]");
    if (modalNode) {
      modalNode.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest("[data-modal-close]") || target.closest("[data-gaia-modal-backdrop]")) {
          hideModal(root);
          return;
        }
        const logBtn = target.closest("[data-modal-log]");
        if (logBtn) {
          const status = modalNode.querySelector("[data-modal-status]");
          let prefill = [];
          try {
            prefill = JSON.parse(logBtn.getAttribute("data-prefill") || "[]");
          } catch (_) {
            prefill = [];
          }
          logBtn.disabled = true;
          if (status) status.textContent = "Logging symptom...";
          try {
            await postQuickSymptom(state.authCtx && state.authCtx.token ? state.authCtx.token : "", prefill);
            if (status) status.textContent = "Symptom logged.";
          } catch (err) {
            if (status) {
              status.textContent = err && err.message ? err.message : "Could not log symptom.";
            }
          } finally {
            logBtn.disabled = false;
          }
        }
      });
    }

    const rerender = () => renderMemberHub(root, state);

    const signOutBtn = root.querySelector("[data-gaia-signout]");
    if (signOutBtn && state.authCtx && typeof state.authCtx.onSignOut === "function") {
      signOutBtn.addEventListener("click", state.authCtx.onSignOut);
    }
    const switchBtn = root.querySelector("[data-gaia-switch]");
    if (switchBtn && state.authCtx && typeof state.authCtx.onSwitch === "function") {
      switchBtn.addEventListener("click", state.authCtx.onSwitch);
    }

    root.querySelectorAll("[data-tab-target]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.activeTab = normalizeTabKey(node.getAttribute("data-tab-target"));
        writeTabHash(state.ui.activeTab);
        rerender();
      });
    });

    root.querySelectorAll("[data-explore-filter]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.exploreFilter = textOrEmpty(node.getAttribute("data-explore-filter")) || "all";
        rerender();
      });
    });

    root.querySelectorAll("[data-guide-poll-choice]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.guidePollChoice = textOrEmpty(node.getAttribute("data-guide-poll-choice"));
        rerender();
      });
    });

    root.querySelectorAll("[data-gauge-key]").forEach((node) => {
      node.addEventListener("click", () => {
        const key = node.getAttribute("data-gauge-key");
        const entry = key ? modalGauges[key] : null;
        if (!entry) return;
        openModal(root, renderContextModal(entry));
      });
    });

    root.querySelectorAll("[data-driver-key]").forEach((node) => {
      node.addEventListener("click", () => {
        const key = node.getAttribute("data-driver-key");
        const entry = key ? modalDrivers[key] : null;
        if (!entry) return;
        openModal(root, renderContextModal(entry));
      });
    });

    const earthscopeBtn = root.querySelector("[data-earthscope-full]");
    if (earthscopeBtn) {
      earthscopeBtn.addEventListener("click", () => {
        const blocks = renderEarthscopeBlocks(earthscope, driversCompact);
        const html = `
          <h3 class="gaia-dashboard__modal-title">${esc(cleanEarthscopeTitle(earthscope && earthscope.title))}</h3>
          <div class="gaia-dashboard__es-grid">${blocks}</div>
          <div class="gaia-dashboard__modal-actions">
            <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
          </div>
        `;
        const modal = openModal(root, html);
        if (modal) applyEarthscopeBackgrounds(modal);
      });
    }

    root.querySelectorAll("[data-checkin-edit]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.checkInEditing = true;
        state.ui.checkInStatus = "";
        rerender();
      });
    });

    root.querySelectorAll("[data-checkin-cancel]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.checkInEditing = false;
        state.ui.checkInStatus = "";
        ensureCheckInFormState(state);
        rerender();
      });
    });

    root.querySelectorAll("[data-checkin-dismiss]").forEach((node) => {
      node.addEventListener("click", async () => {
        const promptId = textOrEmpty(state.ui.checkInForm && state.ui.checkInForm.prompt_id);
        if (!promptId) return;
        state.ui.checkInSubmitting = true;
        state.ui.checkInStatus = "Dismissing today’s prompt…";
        rerender();
        try {
          await postJson(`${routeFor("dailyCheckIn")}/${encodeURIComponent(promptId)}/dismiss`, state.authCtx.token, { action: "dismiss" });
          state.member.dailyCheckIn = await fetchJson(routeFor("dailyCheckIn"), state.authCtx.token);
          state.ui.checkInEditing = false;
          state.ui.checkInStatus = "";
        } catch (err) {
          state.ui.checkInStatus = err && err.message ? err.message : "Could not dismiss this prompt.";
        } finally {
          state.ui.checkInSubmitting = false;
          rerender();
        }
      });
    });

    root.querySelectorAll("[data-daily-checkin-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const element = event.currentTarget;
        if (!(element instanceof HTMLFormElement)) return;
        const data = new FormData(element);
        const exposures = data.getAll("exposures").map((value) => String(value));
        const payloadBody = {
          prompt_id: textOrEmpty(data.get("prompt_id")),
          day: ensureTodayString(data.get("day")),
          compared_to_yesterday: textOrEmpty(data.get("compared_to_yesterday")) || "same",
          energy_level: textOrEmpty(data.get("energy_level")) || "manageable",
          usable_energy: textOrEmpty(data.get("usable_energy")) || "enough",
          system_load: textOrEmpty(data.get("system_load")) || "moderate",
          pain_level: textOrEmpty(data.get("pain_level")) || "a_little",
          mood_level: textOrEmpty(data.get("mood_level")) || "calm",
          note_text: textOrEmpty(data.get("note_text")) || null,
          exposures,
          completed_at: new Date().toISOString(),
        };

        state.ui.checkInSubmitting = true;
        state.ui.checkInStatus = "Saving today’s check-in…";
        state.ui.checkInForm = payloadBody;
        rerender();

        try {
          await postJson(routeFor("dailyCheckIn"), state.authCtx.token, payloadBody);
          state.member.dailyCheckIn = await fetchJson(routeFor("dailyCheckIn"), state.authCtx.token);
          state.ui.checkInEditing = false;
          state.ui.checkInStatus = "";
        } catch (err) {
          state.ui.checkInStatus = err && err.message ? err.message : "Could not save the daily check-in.";
        } finally {
          state.ui.checkInSubmitting = false;
          rerender();
        }
      });
    });
  };

  const hashParams = () => {
    let hash = (window.location.hash || "").replace(/^#/, "");
    if (!hash) {
      try {
        hash = (window.sessionStorage && window.sessionStorage.getItem("gaia_auth_fragment")) || "";
      } catch (_) {
        hash = "";
      }
    }
    if (!hash) return new URLSearchParams();
    return new URLSearchParams(hash);
  };

  const cleanURLHash = () => {
    try {
      if (window.sessionStorage) {
        window.sessionStorage.removeItem("gaia_auth_fragment");
      }
    } catch (_) {}
    if (!window.location.hash) return;
    const clean = `${window.location.pathname}${window.location.search}`;
    window.history.replaceState({}, document.title, clean);
  };

  const localDayISO = () => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const isDebugEnabled = () => {
    const qp = new URLSearchParams(window.location.search || "");
    return qp.get("gaia_debug") === "1";
  };

  const hydrateSessionFromHash = async (supabase) => {
    const params = hashParams();
    const hashError = params.get("error");
    if (hashError) {
      const description = params.get("error_description") || hashError;
      cleanURLHash();
      return { error: description };
    }

    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    if (!accessToken || !refreshToken) {
      return { error: null };
    }

    const { error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    cleanURLHash();
    return { error: error ? error.message || String(error) : null };
  };

  const renderDashboard = (root, payload, authCtx) => {
    document.body.classList.remove("gaia-modal-open");
    const title = root.dataset.title || "Mission Control";
    const gaugesRaw = payload.gauges || {};
    const gaugesMeta = payload.gaugesMeta && typeof payload.gaugesMeta === "object" ? payload.gaugesMeta : {};
    const gaugesDelta = payload.gaugesDelta && typeof payload.gaugesDelta === "object" ? payload.gaugesDelta : {};
    const gaugeZones = normalizeGaugeZones(payload.gaugeZones);
    const gaugeLabels = payload.gaugeLabels && typeof payload.gaugeLabels === "object" ? payload.gaugeLabels : {};
    const drivers = Array.isArray(payload.drivers) ? payload.drivers : [];
    const modalModels = payload.modalModels && typeof payload.modalModels === "object" ? payload.modalModels : {};
    const modalGauges = modalModels.gauges && typeof modalModels.gauges === "object" ? modalModels.gauges : {};
    const modalDrivers = modalModels.drivers && typeof modalModels.drivers === "object" ? modalModels.drivers : {};
    const fallbackLabels = {
      pain: "Pain",
      focus: "Focus",
      heart: "Heart",
      stamina: "Recovery Load",
      energy: "Energy",
      sleep: "Sleep",
      mood: "Mood",
      health_status: "Health Status",
    };
    const gaugeRows = [
      { key: "pain", value: gaugesRaw.pain },
      { key: "focus", value: gaugesRaw.focus },
      { key: "heart", value: gaugesRaw.heart },
      { key: "stamina", value: gaugesRaw.stamina },
      { key: "energy", value: gaugesRaw.energy },
      { key: "sleep", value: gaugesRaw.sleep },
      { key: "mood", value: gaugesRaw.mood },
      { key: "health_status", value: gaugesRaw.health_status },
    ].map((row) => ({
      key: row.key,
      label: gaugeLabels[row.key] || fallbackLabels[row.key] || row.key,
      value: row.value,
      delta: gaugesDelta[row.key],
      meta: gaugesMeta[row.key] || null,
    }));

    const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
    const driversCompact = Array.isArray(payload.driversCompact) ? payload.driversCompact : [];
    const isPaid = payload.entitled === true || !!payload.memberPost;
    const displayRows = isPaid ? gaugeRows : gaugeRows.slice(0, 4);
    const earthscope = isPaid ? payload.memberPost || payload.publicPost || null : payload.publicPost || payload.memberPost || null;
    const earthscopeSummary = resolveEarthscopeSummary(payload.earthscopeSummary, earthscope, driversCompact);
    const geomagneticContext = normalizeGeomagneticContext(payload.geomagneticContext || payload);
    const hasData = hasGaugeData(gaugesRaw) || !!earthscope;

    const email = authCtx && authCtx.email ? authCtx.email : "";
    root.innerHTML = `
      <div class="gaia-dashboard__head">
        <h2 class="gaia-dashboard__title">${esc(title)}</h2>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
          <span class="gaia-dashboard__mode">${isPaid ? "Member" : "Free"}</span>
          ${email ? `<span class="gaia-dashboard__muted">${esc(email)}</span>` : ""}
          <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-switch>Email link</button>
          <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-signout>Sign out</button>
        </div>
      </div>
      ${
        hasData
          ? ""
          : '<div class="gaia-dashboard__muted" style="margin-bottom:10px">No dashboard data yet for this account. Use a magic link for another email, or refresh shortly.</div>'
      }
      <div class="gaia-dashboard__gauges">
        ${displayRows.map((row) => renderGaugeCard(row, gaugeZones, !!modalGauges[row.key])).join("")}
      </div>
      <div class="gaia-dashboard__gauge-legend">
        ${["low", "mild", "elevated", "high"]
          .map(
            (zone) => `
              <span class="gaia-dashboard__legend-item">
                <span class="gaia-dashboard__legend-dot" style="background:${(GAUGE_PALETTE[zone] || GAUGE_PALETTE.mild).hex}"></span>
                ${esc(zoneLabelFromKey(zone))}
              </span>
            `
          )
          .join("")}
      </div>
      ${
        alerts.length
          ? `<div class="gaia-dashboard__alerts">${alerts
              .map(
                (item) =>
                  `<span class="${pillClass(item && item.severity)}">${esc(
                    (item && item.title) || (item && item.key) || "Alert"
                  )}</span>`
              )
              .join("")}</div>`
          : '<div class="gaia-dashboard__muted">No active alerts.</div>'
      }
      ${renderDriversSection(drivers, modalModels)}
      ${renderGeomagneticContext(geomagneticContext)}
      <div class="gaia-dashboard__earthscope">
        <h4>${esc(cleanEarthscopeTitle(earthscope && earthscope.title))}</h4>
        <div class="gaia-dashboard__earthscope-preview">
          ${renderEarthscopePreview(earthscope, driversCompact, earthscopeSummary)}
        </div>
        <button class="gaia-dashboard__earthscope-link" type="button" data-earthscope-full="1">Open full EarthScope</button>
      </div>
      <div class="gaia-dashboard__modal" data-gaia-modal>
        <div class="gaia-dashboard__modal-backdrop" data-gaia-modal-backdrop="1"></div>
        <div class="gaia-dashboard__modal-card" role="dialog" aria-modal="true">
          <div data-gaia-modal-content></div>
        </div>
      </div>
    `;

    const modalNode = root.querySelector("[data-gaia-modal]");
    if (modalNode) {
      modalNode.addEventListener("click", async (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest("[data-modal-close]") || target.closest("[data-gaia-modal-backdrop]")) {
          hideModal(root);
          return;
        }
        const logBtn = target.closest("[data-modal-log]");
        if (logBtn) {
          const status = modalNode.querySelector("[data-modal-status]");
          let prefill = [];
          try {
            prefill = JSON.parse(logBtn.getAttribute("data-prefill") || "[]");
          } catch (_) {
            prefill = [];
          }
          logBtn.disabled = true;
          if (status) status.textContent = "Logging symptom...";
          try {
            await postQuickSymptom(authCtx && authCtx.token ? authCtx.token : "", prefill);
            if (status) status.textContent = "Symptom logged.";
          } catch (err) {
            if (status) {
              status.textContent = err && err.message ? err.message : "Could not log symptom.";
            }
          } finally {
            logBtn.disabled = false;
          }
        }
      });
    }

    const signOutBtn = root.querySelector("[data-gaia-signout]");
    if (signOutBtn && authCtx && typeof authCtx.onSignOut === "function") {
        signOutBtn.addEventListener("click", authCtx.onSignOut);
    }
    const switchBtn = root.querySelector("[data-gaia-switch]");
    if (switchBtn && authCtx && typeof authCtx.onSwitch === "function") {
      switchBtn.addEventListener("click", authCtx.onSwitch);
    }

    root.querySelectorAll("[data-gauge-key]").forEach((node) => {
      node.addEventListener("click", () => {
        const key = node.getAttribute("data-gauge-key");
        const entry = key ? modalGauges[key] : null;
        if (!entry) return;
        openModal(root, renderContextModal(entry));
      });
    });

    root.querySelectorAll("[data-driver-key]").forEach((node) => {
      node.addEventListener("click", () => {
        const key = node.getAttribute("data-driver-key");
        const entry = key ? modalDrivers[key] : null;
        if (!entry) return;
        openModal(root, renderContextModal(entry));
      });
    });

    const earthscopeBtn = root.querySelector("[data-earthscope-full]");
    if (earthscopeBtn) {
      earthscopeBtn.addEventListener("click", () => {
        const blocks = renderEarthscopeBlocks(earthscope, driversCompact);
        const html = `
          <h3 class="gaia-dashboard__modal-title">${esc(cleanEarthscopeTitle(earthscope && earthscope.title))}</h3>
          <div class="gaia-dashboard__es-grid">${blocks}</div>
          <div class="gaia-dashboard__modal-actions">
            <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
          </div>
        `;
        const modal = openModal(root, html);
        if (modal) applyEarthscopeBackgrounds(modal);
      });
    }
  };

  const MEMBER_TAB_ORDER = ["mission", "body", "patterns", "outlook", "explore", "guide"];

  const DAILY_CHECKIN_SELECTS = {
    compared_to_yesterday: [
      ["better", "Better"],
      ["same", "About the same"],
      ["worse", "Worse"],
    ],
    energy_level: [
      ["good", "Good"],
      ["manageable", "Manageable"],
      ["low", "Low"],
      ["depleted", "Depleted"],
    ],
    usable_energy: [
      ["plenty", "Plenty"],
      ["enough", "Enough"],
      ["limited", "Limited"],
      ["very_limited", "Very limited"],
    ],
    system_load: [
      ["light", "Light"],
      ["moderate", "Moderate"],
      ["heavy", "Heavy"],
      ["overwhelming", "Overwhelming"],
    ],
    pain_level: [
      ["none", "None"],
      ["a_little", "A little"],
      ["noticeable", "Noticeable"],
      ["strong", "Strong"],
    ],
    mood_level: [
      ["calm", "Calm"],
      ["slightly_off", "Slightly off"],
      ["noticeable", "Noticeable"],
      ["strong", "Strong"],
    ],
  };

  const DAILY_CHECKIN_EXPOSURES = [
    ["overexertion", "Heavy activity"],
    ["allergen_exposure", "Allergen exposure"],
  ];

  const normalizeTabKey = (value) => {
    const key = String(value || "").trim().toLowerCase().replace(/[^a-z]/g, "");
    return MEMBER_TAB_ORDER.includes(key) ? key : "mission";
  };

  const currentTabFromHash = () => normalizeTabKey(window.location.hash.replace(/^#/, ""));

  const writeTabHash = (tab) => {
    const key = normalizeTabKey(tab);
    if (window.location.hash === `#${key}`) return;
    window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.search}#${key}`);
  };

  const textOrEmpty = (value) => String(value == null ? "" : value).trim();

  const maybeArray = (value) => (Array.isArray(value) ? value : []);

  const titleFromKey = (value) =>
    textOrEmpty(value)
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (match) => match.toUpperCase());

  const asNumber = (value) => {
    if (value == null) return null;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric : null;
    }
    if (typeof value === "object" && value && Number.isFinite(Number(value.value))) {
      return Number(value.value);
    }
    return null;
  };

  const formatPercent = (value, digits = 0) => {
    let numeric = asNumber(value);
    if (!Number.isFinite(numeric)) return "—";
    if (numeric > 0 && numeric <= 1) numeric *= 100;
    return `${numeric.toFixed(digits)}%`;
  };

  const formatMaybeNumber = (value, suffix = "", digits = 0) => {
    const numeric = asNumber(value);
    if (!Number.isFinite(numeric)) return "—";
    const formatted = digits > 0 ? numeric.toFixed(digits) : String(Math.round(numeric));
    return suffix ? `${formatted}${suffix}` : formatted;
  };

  const formatMinutesShort = (value) => {
    const numeric = asNumber(value);
    if (!Number.isFinite(numeric)) return "—";
    return `${Math.round(numeric)}m`;
  };

  const formatMinutesDelta = (value) => {
    const numeric = asNumber(value);
    if (!Number.isFinite(numeric)) return "—";
    const rounded = Math.round(Math.abs(numeric));
    return `${rounded}m ${numeric <= 0 ? "below usual" : "above usual"}`;
  };

  const formatHoursSummary = (value) => {
    const numeric = asNumber(value);
    if (!Number.isFinite(numeric) || numeric <= 0) return "—";
    const hours = Math.floor(numeric / 60);
    const minutes = Math.round(numeric % 60);
    if (hours <= 0) return `${minutes}m`;
    return `${hours}h ${minutes}m`;
  };

  const formatIsoDate = (value) => {
    const raw = textOrEmpty(value);
    if (!raw) return "—";
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;
    return parsed.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  const formatDayLabel = (value) => {
    const raw = textOrEmpty(value);
    if (!raw) return "today";
    const parsed = new Date(`${raw}T12:00:00`);
    if (Number.isNaN(parsed.getTime())) return raw;
    return parsed.toLocaleDateString([], {
      month: "short",
      day: "numeric",
    });
  };

  const sentence = (value, fallback = "") => {
    const cleaned = textOrEmpty(value);
    return cleaned || fallback;
  };

  const truncate = (value, max = 160) => {
    const cleaned = textOrEmpty(value);
    if (!cleaned || cleaned.length <= max) return cleaned;
    return `${cleaned.slice(0, max - 1).trim()}…`;
  };

  const driverSeverityColor = (severity) =>
    (GAUGE_PALETTE[driverZoneFromSeverity(severity)] || GAUGE_PALETTE.mild).hex;

  const driverPill = (driver) => `
    <span class="gaia-dashboard__driver-pill" style="border:1px solid ${driverSeverityColor(driver.severity)}33">
      ${esc(driver.label || driver.key || "Driver")}
      ${driver.state ? `• ${esc(driver.state)}` : ""}
    </span>
  `;

  const ensureTodayString = (value) => {
    if (textOrEmpty(value)) return textOrEmpty(value);
    return localDayISO();
  };

  const extractEnvelopeData = (payload) =>
    payload && payload.data && typeof payload.data === "object" ? payload.data : null;

  const extractDailyCheckIn = (payload) => extractEnvelopeData(payload);

  const extractCurrentSymptoms = (payload) => extractEnvelopeData(payload);

  const extractFeatures = (payload) => extractEnvelopeData(payload);

  const firstPendingFollowUp = (currentSymptoms) =>
    maybeArray(currentSymptoms && currentSymptoms.items).find(
      (item) => item && item.pending_follow_up && typeof item.pending_follow_up === "object"
    ) || null;

  const currentSymptomLabels = (currentSymptoms) =>
    maybeArray(currentSymptoms && currentSymptoms.items)
      .map((item) => textOrEmpty(item && item.label))
      .filter(Boolean);

  const healthStatCards = (features) => {
    if (!features || typeof features !== "object") return [];
    const cards = [];
    const restingHrDelta = asNumber(features.restingHrBaselineDelta);
    const respiratoryDelta = asNumber(features.respiratoryRateBaselineDelta);
    const spo2 = asNumber(features.spo2Avg) || asNumber(features.spo2AvgPct) || asNumber(features.spo2AvgPercent) || asNumber(features.spo2Mean) || (features.health && asNumber(features.health.spo2Avg));
    const steps = asNumber(features.stepsTotal);
    const hrv = asNumber(features.hrvAvg);
    const tempDeviation = asNumber(features.temperatureDeviationBaselineDelta) ?? asNumber(features.temperatureDeviation);
    const hrMin = asNumber(features.hrMin);
    const hrMax = asNumber(features.hrMax);
    const respiratoryAvg = asNumber(features.respiratoryRateAvg) ?? asNumber(features.respiratoryRateSleepAvg);
    const bpSys = asNumber(features.bpSysAvg);
    const bpDia = asNumber(features.bpDiaAvg);

    if (Number.isFinite(restingHrDelta)) {
      cards.push({ label: "Resting HR Δ", value: `${restingHrDelta > 0 ? "+" : ""}${restingHrDelta.toFixed(1)} bpm`, detail: restingHrDelta > 0 ? "above usual" : "below usual" });
    }
    if (Number.isFinite(respiratoryDelta)) {
      cards.push({ label: "Respiratory Δ", value: `${respiratoryDelta > 0 ? "+" : ""}${respiratoryDelta.toFixed(1)} br/min`, detail: respiratoryDelta > 0 ? "above usual" : "below usual" });
    } else if (Number.isFinite(respiratoryAvg)) {
      cards.push({ label: "Respiratory", value: `${respiratoryAvg.toFixed(1)} br/min`, detail: "daily average" });
    }
    if (Number.isFinite(spo2)) {
      cards.push({ label: "SpO₂", value: `${Math.round(spo2)}%`, detail: "daily average" });
    }
    if (Number.isFinite(hrv)) {
      cards.push({ label: "HRV", value: `${Math.round(hrv)} ms`, detail: "daily average" });
    }
    if (Number.isFinite(tempDeviation)) {
      cards.push({ label: "Temp Δ", value: `${tempDeviation > 0 ? "+" : ""}${tempDeviation.toFixed(1)}°`, detail: tempDeviation > 0 ? "above usual" : "below usual" });
    }
    if (Number.isFinite(steps)) {
      cards.push({ label: "Steps", value: `${Math.round(steps)}`, detail: "today" });
    }
    if (Number.isFinite(hrMin) || Number.isFinite(hrMax)) {
      cards.push({
        label: "Heart range",
        value: `${Number.isFinite(hrMin) ? Math.round(hrMin) : "—"}-${Number.isFinite(hrMax) ? Math.round(hrMax) : "—"} bpm`,
        detail: "today",
      });
    }
    if (Number.isFinite(bpSys) || Number.isFinite(bpDia)) {
      cards.push({
        label: "Blood pressure",
        value: `${Number.isFinite(bpSys) ? Math.round(bpSys) : "—"}/${Number.isFinite(bpDia) ? Math.round(bpDia) : "—"}`,
        detail: "average",
      });
    }
    return cards;
  };

  const sleepStageCards = (features) => {
    if (!features || typeof features !== "object") return [];
    return [
      { label: "REM", value: formatMinutesShort(features.remM) },
      { label: "Core", value: formatMinutesShort(features.coreM) },
      { label: "Deep", value: formatMinutesShort(features.deepM) },
      { label: "Awake", value: formatMinutesShort(features.awakeM) },
      { label: "In bed", value: formatMinutesShort(features.inbedM) },
    ].filter((item) => item.value !== "—");
  };

  const missionNavCard = (key, title, body) => `
    <button class="gaia-dashboard__nav-card" type="button" data-tab-target="${esc(key)}">
      <strong>${esc(title)}</strong>
      <span>${esc(body)}</span>
    </button>
  `;

  const renderMemberPatternsList = (cards, emptyText) => {
    const items = maybeArray(cards).slice(0, 4);
    if (!items.length) return `<div class="gaia-dashboard__empty">${esc(emptyText)}</div>`;
    return `
      <div class="gaia-dashboard__list">
        ${items
          .map(
            (card) => `
              <article class="gaia-dashboard__list-row">
                <strong>${esc(card.outcome || card.signal || "Pattern")}</strong>
                <p>${esc(sentence(card.explanation, "Pattern details are still forming."))}</p>
                <div class="gaia-dashboard__meta-row">
                  <span class="${pillClass(card.confidence || "watch")}">${esc(card.confidence || "Observed")}</span>
                  ${card.signal ? `<span class="gaia-dashboard__meta-chip">${esc(card.signal)}</span>` : ""}
                  ${card.lagLabel ? `<span class="gaia-dashboard__meta-chip">${esc(card.lagLabel)}</span>` : ""}
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  };

  const renderOutlookWindow = (label, window) => {
    if (!window || typeof window !== "object") {
      return `
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <h4 class="gaia-dashboard__card-title">${esc(label)}</h4>
          </div>
          <div class="gaia-dashboard__empty">This window is still filling in.</div>
        </article>
      `;
    }

    const drivers = maybeArray(window.topDrivers || window.top_drivers).filter((driver) => !/radio blackout/i.test(textOrEmpty(driver && driver.label)));
    const primary = drivers[0] || null;
    const supporting = drivers.slice(1, 3);
    const domains = maybeArray(window.likelyElevatedDomains || window.likely_elevated_domains).slice(0, 3);

    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <h4 class="gaia-dashboard__card-title">${esc(label)}</h4>
          ${primary ? `<span class="${pillClass(primary.severity || "watch")}">${esc(primary.severity || "Watch")}</span>` : ""}
        </div>
        <p class="gaia-dashboard__card-copy">${esc(sentence(window.summary, "No clear outlook note yet."))}</p>
        ${
          primary
            ? `
              <div class="gaia-dashboard__list-row">
                <span class="gaia-dashboard__eyebrow">Main thing to watch</span>
                <strong>${esc(primary.label || primary.key || "Driver")}</strong>
                <p>${esc(sentence(primary.detail, "This looks most relevant in this window."))}</p>
              </div>
            `
            : ""
        }
        ${
          supporting.length
            ? `
              <div>
                <div class="gaia-dashboard__mini-title">Also contributing</div>
                <div class="gaia-dashboard__meta-row">
                  ${supporting
                    .map(
                      (driver) => `
                        <span class="gaia-dashboard__meta-chip">${esc(driver.label || driver.key || "Driver")}</span>
                      `
                    )
                    .join("")}
                </div>
              </div>
            `
            : ""
        }
        ${
          domains.length
            ? `
              <div>
                <div class="gaia-dashboard__mini-title">Most likely to show up in</div>
                <div class="gaia-dashboard__grid gaia-dashboard__grid--3">
                  ${domains
                    .map(
                      (domain) => `
                        <div class="gaia-dashboard__metric">
                          <div class="gaia-dashboard__metric-label">${esc(domain.label || titleFromKey(domain.key))}</div>
                          <div class="gaia-dashboard__metric-value">${esc(domain.likelihood || "Watch")}</div>
                          <div class="gaia-dashboard__metric-detail">${esc(truncate(domain.explanation || "", 120) || "This domain may be easier to notice in this window.")}</div>
                        </div>
                      `
                    )
                    .join("")}
                </div>
              </div>
            `
            : ""
        }
        ${
          textOrEmpty(window.supportLine || window.support_line)
            ? `
              <div>
                <div class="gaia-dashboard__mini-title">A steadier way through it</div>
                <p class="gaia-dashboard__card-copy">${esc(window.supportLine || window.support_line)}</p>
              </div>
            `
            : ""
        }
      </article>
    `;
  };

  const derivedDailyPoll = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const followUp = firstPendingFollowUp(currentSymptoms);
    if (followUp) {
      return {
        question: `Has ${textOrEmpty(followUp.symptom_label).toLowerCase()} shifted since the last check?`,
        support: "A quick pulse helps Guide stay current without asking for a full check-in.",
        choices: ["Yes", "A little", "Not really"],
      };
    }
    const firstSymptom = currentSymptomLabels(currentSymptoms)[0];
    if (firstSymptom) {
      return {
        question: `Did ${firstSymptom.toLowerCase()} shape the day more than expected?`,
        support: "A light answer keeps the guide current and leaves the longer check-in optional.",
        choices: ["Yes", "Somewhat", "No"],
      };
    }
    return {
      question: "Compared with yesterday, does today feel better, about the same, or worse?",
      support: "A short compare-day check helps Guide keep its read on the day.",
      choices: ["Better", "About the same", "Worse"],
    };
  };

  const buildCheckInFormState = (dailyCheckIn) => {
    const data = extractDailyCheckIn(dailyCheckIn);
    const entry = data && data.latest_entry ? data.latest_entry : null;
    const exposures = new Set(maybeArray(entry && entry.exposures));
    return {
      prompt_id: textOrEmpty(data && data.prompt && data.prompt.id) || textOrEmpty(entry && entry.prompt_id),
      day: ensureTodayString(textOrEmpty(data && data.target_day) || textOrEmpty(entry && entry.day)),
      compared_to_yesterday: textOrEmpty(entry && entry.compared_to_yesterday) || "same",
      energy_level: textOrEmpty(entry && entry.energy_level) || "manageable",
      usable_energy: textOrEmpty(entry && entry.usable_energy) || "enough",
      system_load: textOrEmpty(entry && entry.system_load) || "moderate",
      pain_level: textOrEmpty(entry && entry.pain_level) || "a_little",
      mood_level: textOrEmpty(entry && entry.mood_level) || "calm",
      note_text: textOrEmpty(entry && entry.note_text),
      exposures: DAILY_CHECKIN_EXPOSURES.filter(([key]) => exposures.has(key)).map(([key]) => key),
    };
  };

  const ensureCheckInFormState = (state) => {
    const data = extractDailyCheckIn(state.member.dailyCheckIn);
    const formDay = state.ui.checkInForm ? textOrEmpty(state.ui.checkInForm.day) : "";
    const targetDay = textOrEmpty(data && data.target_day);
    if (!state.ui.checkInForm || (targetDay && targetDay !== formDay)) {
      state.ui.checkInForm = buildCheckInFormState(state.member.dailyCheckIn);
    }
  };

  const renderCheckInSelect = (name, label, options, selected) => `
    <div class="gaia-dashboard__field">
      <label for="gaia-checkin-${esc(name)}">${esc(label)}</label>
      <select id="gaia-checkin-${esc(name)}" name="${esc(name)}">
        ${options
          .map(
            ([value, title]) =>
              `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(title)}</option>`
          )
          .join("")}
      </select>
    </div>
  `;

  const renderDailyCheckInCard = (state, location) => {
    const dailyCheckIn = extractDailyCheckIn(state.member.dailyCheckIn);
    const targetDay = textOrEmpty(dailyCheckIn && dailyCheckIn.target_day) || localDayISO();
    const entry = dailyCheckIn && dailyCheckIn.latest_entry ? dailyCheckIn.latest_entry : null;
    const completedToday = !!(entry && textOrEmpty(entry.day) === targetDay);
    const prompt = dailyCheckIn && dailyCheckIn.prompt ? dailyCheckIn.prompt : null;
    ensureCheckInFormState(state);
    const form = state.ui.checkInForm;
    const showForm = state.ui.checkInEditing || (!completedToday && !!prompt);
    const exposureSet = new Set(maybeArray(form && form.exposures));

    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <div>
            <span class="gaia-dashboard__eyebrow">${esc(location === "guide" ? "Daily check-in" : "Body check-in")}</span>
            <h4 class="gaia-dashboard__card-title">${completedToday ? "Completed for today" : prompt ? "Check in with the day" : "Nothing waiting right now"}</h4>
          </div>
          ${
            completedToday
              ? `<span class="${pillClass("low")}">Done</span>`
              : prompt
                ? `<span class="${pillClass("watch")}">Ready</span>`
                : ""
          }
        </div>
        <p class="gaia-dashboard__card-copy">${
          completedToday
            ? esc(`Completed for ${formatDayLabel(targetDay)}${maybeArray(entry && entry.exposures).length ? `. Also logged: ${maybeArray(entry.exposures).map(titleFromKey).join(", ")}` : "."}`)
            : esc(sentence(prompt && prompt.question_text, "Use the full check-in to keep the body read current."))
        }</p>
        ${
          completedToday && !showForm
            ? `
              <div class="gaia-dashboard__meta-row">
                <span class="gaia-dashboard__meta-chip">${esc(titleFromKey(entry && entry.energy_level))}</span>
                <span class="gaia-dashboard__meta-chip">${esc(titleFromKey(entry && entry.usable_energy))}</span>
                <span class="gaia-dashboard__meta-chip">${esc(titleFromKey(entry && entry.system_load))}</span>
                <span class="gaia-dashboard__meta-chip">${esc(titleFromKey(entry && entry.pain_level))}</span>
              </div>
              <div class="gaia-dashboard__section-actions">
                <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-checkin-edit="1">Update check-in</button>
              </div>
            `
            : showForm
              ? `
                <form class="gaia-dashboard__form" data-daily-checkin-form="1">
                  <input type="hidden" name="day" value="${esc(form.day)}" />
                  <input type="hidden" name="prompt_id" value="${esc(form.prompt_id)}" />
                  <div class="gaia-dashboard__form-grid">
                    ${renderCheckInSelect("compared_to_yesterday", "Compared with yesterday", DAILY_CHECKIN_SELECTS.compared_to_yesterday, form.compared_to_yesterday)}
                    ${renderCheckInSelect("energy_level", "Energy", DAILY_CHECKIN_SELECTS.energy_level, form.energy_level)}
                    ${renderCheckInSelect("usable_energy", "Usable energy", DAILY_CHECKIN_SELECTS.usable_energy, form.usable_energy)}
                    ${renderCheckInSelect("system_load", "System load", DAILY_CHECKIN_SELECTS.system_load, form.system_load)}
                    ${renderCheckInSelect("pain_level", "Pain", DAILY_CHECKIN_SELECTS.pain_level, form.pain_level)}
                    ${renderCheckInSelect("mood_level", "Mood", DAILY_CHECKIN_SELECTS.mood_level, form.mood_level)}
                  </div>
                  <div class="gaia-dashboard__field">
                    <label for="gaia-checkin-note_text">Quick note</label>
                    <textarea id="gaia-checkin-note_text" name="note_text" placeholder="Anything worth noting?">${esc(form.note_text || "")}</textarea>
                  </div>
                  <div class="gaia-dashboard__field">
                    <label>Also logged</label>
                    <div class="gaia-dashboard__meta-row">
                      ${DAILY_CHECKIN_EXPOSURES
                        .map(
                          ([key, label]) => `
                            <label class="gaia-dashboard__meta-chip">
                              <input type="checkbox" name="exposures" value="${esc(key)}"${exposureSet.has(key) ? " checked" : ""} />
                              ${esc(label)}
                            </label>
                          `
                        )
                        .join("")}
                    </div>
                  </div>
                  <div class="gaia-dashboard__section-actions">
                    <button class="gaia-dashboard__btn" type="submit"${state.ui.checkInSubmitting ? " disabled" : ""}>${completedToday ? "Save update" : "Save check-in"}</button>
                    <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-checkin-cancel="1">Cancel</button>
                    ${
                      prompt && !completedToday
                        ? `<button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-checkin-dismiss="1"${state.ui.checkInSubmitting ? " disabled" : ""}>Dismiss</button>`
                        : ""
                    }
                  </div>
                </form>
                ${
                  state.ui.checkInStatus
                    ? `<div class="gaia-dashboard__status-note">${esc(state.ui.checkInStatus)}</div>`
                    : ""
                }
              `
              : `
                <div class="gaia-dashboard__helper">The next prompt will appear here when it is scheduled.</div>
              `
        }
      </article>
    `;
  };

  const renderMissionSection = (state) => {
    const payload = state.dashboard;
    const gaugesRaw = payload.gauges || {};
    const gaugesMeta = payload.gaugesMeta && typeof payload.gaugesMeta === "object" ? payload.gaugesMeta : {};
    const gaugesDelta = payload.gaugesDelta && typeof payload.gaugesDelta === "object" ? payload.gaugesDelta : {};
    const gaugeZones = normalizeGaugeZones(payload.gaugeZones);
    const gaugeLabels = payload.gaugeLabels && typeof payload.gaugeLabels === "object" ? payload.gaugeLabels : {};
    const drivers = Array.isArray(payload.drivers) ? payload.drivers : [];
    const fallbackLabels = {
      pain: "Pain",
      focus: "Focus",
      heart: "Heart",
      stamina: "Recovery Load",
      energy: "Energy",
      sleep: "Sleep",
      mood: "Mood",
      health_status: "Health Status",
    };
    const gaugeRows = [
      { key: "pain", value: gaugesRaw.pain },
      { key: "focus", value: gaugesRaw.focus },
      { key: "heart", value: gaugesRaw.heart },
      { key: "stamina", value: gaugesRaw.stamina },
      { key: "energy", value: gaugesRaw.energy },
      { key: "sleep", value: gaugesRaw.sleep },
      { key: "mood", value: gaugesRaw.mood },
      { key: "health_status", value: gaugesRaw.health_status },
    ].map((row) => ({
      key: row.key,
      label: gaugeLabels[row.key] || fallbackLabels[row.key] || row.key,
      value: row.value,
      delta: gaugesDelta[row.key],
      meta: gaugesMeta[row.key] || null,
    }));
    const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
    const driversCompact = Array.isArray(payload.driversCompact) ? payload.driversCompact : [];
    const earthscope = payload.entitled === true || !!payload.memberPost ? payload.memberPost || payload.publicPost || null : payload.publicPost || payload.memberPost || null;
    const earthscopeSummary = resolveEarthscopeSummary(payload.earthscopeSummary, earthscope, driversCompact);
    const geomagneticContext = normalizeGeomagneticContext(payload.geomagneticContext || payload);

    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "mission" ? " is-active" : ""}" data-section="mission">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Mission Control</h3>
            <p class="gaia-dashboard__section-subtitle">Your gauges, drivers, and EarthScope live here. Use the section cards to move through the same core read you get in the app.</p>
          </div>
        </div>
        <div class="gaia-dashboard__nav-grid">
          ${missionNavCard("body", "Body", "Current symptoms, check-in, sleep, health stats, and lunar watch.")}
          ${missionNavCard("patterns", "Patterns", "The clearest repeats in your logs and wearable history.")}
          ${missionNavCard("outlook", "Outlook", "Your 24h, 72h, and 7-day personal forecast windows.")}
          ${missionNavCard("explore", "Explore", "All drivers plus links to deeper public detail pages.")}
          ${missionNavCard("guide", "Guide", "A lighter orientation layer with daily check-in and help links.")}
        </div>
        <div class="gaia-dashboard__gauges">
          ${gaugeRows.map((row) => renderGaugeCard(row, gaugeZones, !!(payload.modalModels && payload.modalModels.gauges && payload.modalModels.gauges[row.key]))).join("")}
        </div>
        <div class="gaia-dashboard__gauge-legend">
          ${["low", "mild", "elevated", "high"]
            .map(
              (zone) => `
                <span class="gaia-dashboard__legend-item">
                  <span class="gaia-dashboard__legend-dot" style="background:${(GAUGE_PALETTE[zone] || GAUGE_PALETTE.mild).hex}"></span>
                  ${esc(zoneLabelFromKey(zone))}
                </span>
              `
            )
            .join("")}
        </div>
        ${
          alerts.length
            ? `<div class="gaia-dashboard__alerts">${alerts
                .map((item) => `<span class="${pillClass(item && item.severity)}">${esc((item && item.title) || (item && item.key) || "Alert")}</span>`)
                .join("")}</div>`
            : '<div class="gaia-dashboard__muted">No active alerts.</div>'
        }
        ${renderDriversSection(drivers, payload.modalModels || {})}
        ${renderGeomagneticContext(geomagneticContext)}
        <div class="gaia-dashboard__earthscope">
          <h4>${esc(cleanEarthscopeTitle(earthscope && earthscope.title))}</h4>
          <div class="gaia-dashboard__earthscope-preview">${renderEarthscopePreview(earthscope, driversCompact, earthscopeSummary)}</div>
          <button class="gaia-dashboard__earthscope-link" type="button" data-earthscope-full="1">Open full EarthScope</button>
        </div>
      </section>
    `;
  };

  const renderBodySection = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const features = extractFeatures(state.member.features);
    const lunar = state.member.lunar && typeof state.member.lunar === "object" ? state.member.lunar : null;
    const symptomItems = maybeArray(currentSymptoms && currentSymptoms.items).slice(0, 4);
    const summary = currentSymptoms && currentSymptoms.summary ? currentSymptoms.summary : {};
    const healthCards = healthStatCards(features).slice(0, 8);
    const sleepCards = sleepStageCards(features);
    const topDriver = maybeArray(currentSymptoms && currentSymptoms.contributing_drivers)[0];

    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "body" ? " is-active" : ""}" data-section="body">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Body</h3>
            <p class="gaia-dashboard__section-subtitle">Current symptoms, your daily check-in, sleep, synced health stats, and the current lunar watch.</p>
          </div>
          <div class="gaia-dashboard__section-actions">
            <a class="gaia-dashboard__btn" href="${esc(cfg.symptomLogUrl || "/symptoms/")}">Log symptoms</a>
          </div>
        </div>
        <div class="gaia-dashboard__split">
          <div class="gaia-dashboard__grid">
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Current symptoms</span>
                  <h4 class="gaia-dashboard__card-title">${summary && Number(summary.active_count || 0) > 0 ? `${Math.round(Number(summary.active_count || 0))} active right now` : "Nothing active right now"}</h4>
                </div>
                ${
                  topDriver
                    ? `<span class="${pillClass(topDriver.severity || "watch")}">${esc(topDriver.label || topDriver.key || "Context")}</span>`
                    : ""
                }
              </div>
              <p class="gaia-dashboard__card-copy">${
                topDriver
                  ? esc(sentence(topDriver.pattern_hint || topDriver.display || topDriver.relation, `${topDriver.label || "Current body context"} looks closest to this window.`))
                  : "No symptom follow-up is waiting right now."
              }</p>
              ${
                symptomItems.length
                  ? `<div class="gaia-dashboard__meta-row">${symptomItems.map((item) => `<span class="gaia-dashboard__meta-chip">${esc(item.label || item.symptom_code || "Symptom")}</span>`).join("")}</div>`
                  : `<div class="gaia-dashboard__helper">As symptoms are logged or updated, they will show here with the most likely context.</div>`
              }
            </article>
            ${renderDailyCheckInCard(state, "body")}
          </div>
          <div class="gaia-dashboard__grid">
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Sleep</span>
                  <h4 class="gaia-dashboard__card-title">${formatHoursSummary(features && features.sleepTotalMinutes)} total</h4>
                </div>
                <span class="${pillClass("low")}">${formatPercent(features && features.sleepEfficiency)}</span>
              </div>
              ${
                sleepCards.length
                  ? `<div class="gaia-dashboard__stat-grid">${sleepCards
                      .map(
                        (item) => `
                          <div class="gaia-dashboard__stat-box">
                            <strong>${esc(item.label)}</strong>
                            <span>${esc(item.value)}</span>
                          </div>
                        `
                      )
                      .join("")}</div>`
                  : '<div class="gaia-dashboard__empty">Sleep will appear here once synced data is available.</div>'
              }
            </article>
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Health stats</span>
                  <h4 class="gaia-dashboard__card-title">Synced body metrics</h4>
                </div>
              </div>
              ${
                healthCards.length
                  ? `<div class="gaia-dashboard__metric-grid gaia-dashboard__metric-grid--4">${healthCards
                      .map(
                        (card) => `
                          <div class="gaia-dashboard__metric">
                            <div class="gaia-dashboard__metric-label">${esc(card.label)}</div>
                            <div class="gaia-dashboard__metric-value">${esc(card.value)}</div>
                            <div class="gaia-dashboard__metric-detail">${esc(card.detail)}</div>
                          </div>
                        `
                      )
                      .join("")}</div>`
                  : '<div class="gaia-dashboard__empty">Health stats appear here once the app has synced body data to your account.</div>'
              }
            </article>
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Lunar watch</span>
                  <h4 class="gaia-dashboard__card-title">${esc((lunar && (lunar.pattern_strength || "tracking")) ? titleFromKey(lunar.pattern_strength || "tracking") : "Tracking")}</h4>
                </div>
              </div>
              <p class="gaia-dashboard__card-copy">${esc(sentence(lunar && (lunar.message_scientific || lunar.message_mystical), "No clear lunar signal yet."))}</p>
              <div class="gaia-dashboard__meta-row">
                ${
                  lunar && lunar.highlight_window
                    ? `<span class="gaia-dashboard__meta-chip">${esc(titleFromKey(lunar.highlight_window))}</span>`
                    : ""
                }
                ${
                  lunar && lunar.highlight_metric
                    ? `<span class="gaia-dashboard__meta-chip">${esc(titleFromKey(lunar.highlight_metric))}</span>`
                    : ""
                }
                ${
                  lunar && Number.isFinite(Number(lunar.observed_days || lunar.n_nights))
                    ? `<span class="gaia-dashboard__meta-chip">${esc(`${Math.round(Number(lunar.observed_days || lunar.n_nights))} days observed`)}</span>`
                    : ""
                }
              </div>
            </article>
          </div>
        </div>
      </section>
    `;
  };

  const renderPatternsSection = (state) => {
    const partial = state.member.patterns || state.member.patternsSummary || {};
    const strongest = maybeArray(partial.strongestPatterns);
    const emerging = maybeArray(partial.emergingPatterns);
    const bodySignals = maybeArray(partial.bodySignalsPatterns);
    const lunarCards = strongest
      .concat(emerging)
      .concat(bodySignals)
      .filter((card) => /^lunar_/i.test(textOrEmpty(card && card.signalKey)));

    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "patterns" ? " is-active" : ""}" data-section="patterns">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Patterns</h3>
            <p class="gaia-dashboard__section-subtitle">The clearest repeats in your history, with body-signal overlaps and lunar context when those comparisons are strong enough.</p>
          </div>
        </div>
        <div class="gaia-dashboard__grid gaia-dashboard__grid--2">
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <h4 class="gaia-dashboard__card-title">Clearest patterns</h4>
            </div>
            ${renderMemberPatternsList(strongest, "No clear patterns yet. Keep logging so this section can build from real overlap.")}
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <h4 class="gaia-dashboard__card-title">Still taking shape</h4>
            </div>
            ${renderMemberPatternsList(emerging, state.ui.patternsLoading ? "Loading the rest of your pattern history." : "Nothing is clearly emerging yet.")}
          </article>
        </div>
        <div class="gaia-dashboard__grid gaia-dashboard__grid--2">
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <h4 class="gaia-dashboard__card-title">Body signals</h4>
            </div>
            ${renderMemberPatternsList(bodySignals, "No body-signal patterns are standing out yet.")}
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <h4 class="gaia-dashboard__card-title">Lunar</h4>
            </div>
            ${renderMemberPatternsList(lunarCards, "No lunar pattern is standing out yet.")}
          </article>
        </div>
      </section>
    `;
  };

  const renderOutlookSection = (state) => {
    const outlook = state.member.outlook || {};
    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "outlook" ? " is-active" : ""}" data-section="outlook">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Outlook</h3>
            <p class="gaia-dashboard__section-subtitle">Your near-future personal outlook across 24h, 72h, and 7-day windows.</p>
          </div>
        </div>
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <div>
              <span class="gaia-dashboard__eyebrow">Near-future outlook</span>
              <h4 class="gaia-dashboard__card-title">Ready windows</h4>
            </div>
          </div>
          <div class="gaia-dashboard__meta-row">
            ${maybeArray(outlook.availableWindows || outlook.available_windows)
              .map((item) => `<span class="gaia-dashboard__meta-chip">${esc(item)}</span>`)
              .join("") || `<span class="gaia-dashboard__meta-chip">Building</span>`}
          </div>
        </article>
        <div class="gaia-dashboard__grid gaia-dashboard__grid--3">
          ${renderOutlookWindow("Next 24 Hours", outlook.next24h || outlook.next_24h)}
          ${renderOutlookWindow("Next 72 Hours", outlook.next72h || outlook.next_72h)}
          ${renderOutlookWindow("Next 7 Days", outlook.next7d || outlook.next_7d)}
        </div>
      </section>
    `;
  };

  const renderExploreSection = (state) => {
    const allDrivers = state.member.allDrivers || {};
    const filters = maybeArray(allDrivers.filters);
    const currentFilter = state.ui.exploreFilter || "all";
    const drivers = maybeArray(allDrivers.drivers).filter((driver) => currentFilter === "all" || textOrEmpty(driver && driver.category) === currentFilter);
    const setupHints = maybeArray(allDrivers.setup_hints).slice(0, 3);
    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "explore" ? " is-active" : ""}" data-section="explore">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Explore</h3>
            <p class="gaia-dashboard__section-subtitle">The full driver stack, grouped like the app, plus direct links into the public detail pages.</p>
          </div>
        </div>
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <div>
              <span class="gaia-dashboard__eyebrow">All drivers</span>
              <h4 class="gaia-dashboard__card-title">${esc(sentence(allDrivers.summary && allDrivers.summary.note, "Nothing especially strong right now."))}</h4>
            </div>
          </div>
          <div class="gaia-dashboard__pill-row">
            ${filters
              .map(
                (filter) => `
                  <button class="gaia-dashboard__pill-button${currentFilter === filter.key ? " is-active" : ""}" type="button" data-explore-filter="${esc(filter.key)}">
                    ${esc(filter.label || filter.key)}
                  </button>
                `
              )
              .join("")}
          </div>
          ${
            drivers.length
              ? renderDriversSection(drivers, { drivers: {} }, drivers.length)
              : '<div class="gaia-dashboard__empty">No drivers are matching this filter right now.</div>'
          }
          ${
            setupHints.length
              ? `
                <div class="gaia-dashboard__grid gaia-dashboard__grid--3">
                  ${setupHints
                    .map(
                      (hint) => `
                        <div class="gaia-dashboard__metric">
                          <div class="gaia-dashboard__metric-label">${esc(hint.label || "Setup")}</div>
                          <div class="gaia-dashboard__metric-detail">${esc(sentence(hint.reason, ""))}</div>
                        </div>
                      `
                    )
                    .join("")}
                </div>
              `
              : ""
          }
        </article>
        <div class="gaia-dashboard__link-grid">
          <a class="gaia-dashboard__link-card" href="${esc(publicLinks.spaceWeather || "/space-weather/")}"><strong>Space Weather</strong><small>Scientific forecast and current conditions.</small></a>
          <a class="gaia-dashboard__link-card" href="${esc(publicLinks.schumann || "/schumann-resonance/")}"><strong>Schumann</strong><small>Current resonance detail and scientific context.</small></a>
          <a class="gaia-dashboard__link-card" href="${esc(publicLinks.magnetosphere || "/magnetosphere/")}"><strong>Magnetosphere</strong><small>Shield state, compression, and recent change.</small></a>
          <a class="gaia-dashboard__link-card" href="${esc(publicLinks.aurora || "/aurora-tracker/")}"><strong>Aurora</strong><small>Live tracker and viewlines.</small></a>
          <a class="gaia-dashboard__link-card" href="${esc(publicLinks.earthquakes || "/earthquakes/")}"><strong>Earthquakes</strong><small>Global quake activity and recent clusters.</small></a>
        </div>
      </section>
    `;
  };

  const renderGuideSection = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const followUp = firstPendingFollowUp(currentSymptoms);
    const poll = derivedDailyPoll(state);
    const earthscopeSummary = resolveEarthscopeSummary(
      state.dashboard.earthscopeSummary,
      state.dashboard.memberPost || state.dashboard.publicPost || null,
      state.dashboard.driversCompact || []
    );
    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "guide" ? " is-active" : ""}" data-section="guide">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Guide</h3>
            <p class="gaia-dashboard__section-subtitle">A lighter orientation layer built from today’s dashboard read, your body context, and the help center.</p>
          </div>
        </div>
        <div class="gaia-dashboard__guide-stack">
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Today’s translated read</span>
                <h4 class="gaia-dashboard__card-title">Guide snapshot</h4>
              </div>
            </div>
            <p class="gaia-dashboard__card-copy">${esc(sentence(earthscopeSummary, "Guide is still shaping today’s summary."))}</p>
            <div class="gaia-dashboard__section-actions">
              <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="explore">Open Drivers</button>
              <a class="gaia-dashboard__btn gaia-dashboard__btn--quiet" href="${esc(supportUrl)}">Support</a>
            </div>
          </article>
          ${renderDailyCheckInCard(state, "guide")}
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Daily poll</span>
                <h4 class="gaia-dashboard__card-title">${esc(poll.question)}</h4>
              </div>
            </div>
            <p class="gaia-dashboard__card-copy">${esc(poll.support)}</p>
            <div class="gaia-dashboard__poll-choices">
              ${poll.choices
                .map(
                  (choice) => `
                    <button class="gaia-dashboard__poll-choice${state.ui.guidePollChoice === choice ? " is-selected" : ""}" type="button" data-guide-poll-choice="${esc(choice)}">
                      ${esc(choice)}
                    </button>
                  `
                )
                .join("")}
            </div>
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Symptom follow-up</span>
                <h4 class="gaia-dashboard__card-title">${followUp ? "A follow-up is waiting" : "Nothing is waiting right now"}</h4>
              </div>
            </div>
            <p class="gaia-dashboard__card-copy">${
              followUp
                ? esc(`${followUp.question_text} Open Body to respond in the real symptom workflow.`)
                : "If Gaia wants one more body detail, the follow-up will appear here and in Body."
            }</p>
            ${followUp ? `<button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="body">Open Body</button>` : ""}
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Understanding</span>
                <h4 class="gaia-dashboard__card-title">Need a deeper explanation?</h4>
              </div>
            </div>
            <p class="gaia-dashboard__card-copy">Use the support center for billing, sync help, permissions, and a plain-language explanation of how Gaia Eyes works.</p>
            <div class="gaia-dashboard__link-grid">
              <a class="gaia-dashboard__link-card" href="${esc(`${supportUrl}#what-gaia-eyes-does`)}"><strong>How Gaia works</strong><small>The high-level model and product promises.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(`${supportUrl}#health-sync`)}"><strong>Health sync</strong><small>How device data gets into the app and web surfaces.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(`${supportUrl}#billing`)}"><strong>Billing</strong><small>Subscriptions, restore access, and plan help.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(supportUrl)}"><strong>Help Center</strong><small>Browse the full support index.</small></a>
            </div>
          </article>
        </div>
      </section>
    `;
  };

  const renderMissionControlApp = (root, state) => {
    const authCtx = state.authCtx || {};
    const email = authCtx.email || "";
    const title = root.dataset.title || "Mission Control";
    root.innerHTML = `
      <div class="gaia-dashboard__shell">
        <div class="gaia-dashboard__shell-head">
          <div class="gaia-dashboard__shell-copy">
            <span class="gaia-dashboard__shell-kicker">Member Hub</span>
            <h2 class="gaia-dashboard__title">${esc(title)}</h2>
            <p class="gaia-dashboard__shell-subtitle">Mission Control for the web: gauges, body context, patterns, outlook, drivers, and a lighter Guide layer in one signed-in shell.</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
            <span class="gaia-dashboard__mode">${state.dashboard.entitled === true || !!state.dashboard.memberPost ? "Member" : "Free"}</span>
            ${email ? `<span class="gaia-dashboard__muted">${esc(email)}</span>` : ""}
            <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-switch>Email link</button>
            <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-signout>Sign out</button>
          </div>
        </div>
        <div class="gaia-dashboard__tabbar">
          ${MEMBER_TAB_ORDER.map((key) => `<button class="gaia-dashboard__tab${state.ui.activeTab === key ? " is-active" : ""}" type="button" data-tab-target="${esc(key)}">${esc(titleFromKey(key === "mission" ? "Mission Control" : key))}</button>`).join("")}
        </div>
        ${renderMissionSection(state)}
        ${renderBodySection(state)}
        ${renderPatternsSection(state)}
        ${renderOutlookSection(state)}
        ${renderExploreSection(state)}
        ${renderGuideSection(state)}
        <div class="gaia-dashboard__modal" data-gaia-modal>
          <div class="gaia-dashboard__modal-backdrop" data-gaia-modal-backdrop="1"></div>
          <div class="gaia-dashboard__modal-card" role="dialog" aria-modal="true">
            <div data-gaia-modal-content></div>
          </div>
        </div>
      </div>
    `;
  };

  const renderSignInPrompt = (root, supabase, statusText) => {
    root.innerHTML = `
      <div class="gaia-dashboard__signin">
        <span class="gaia-dashboard__status">${esc(statusText || "Sign in to view your dashboard.")}</span>
        <button class="gaia-dashboard__btn" type="button">Sign in with email</button>
      </div>
    `;
    const button = root.querySelector("button");
    if (!button) return;

    button.addEventListener("click", async () => {
      const email = window.prompt("Enter your email for a magic link:");
      if (!email) return;
      button.disabled = true;
      try {
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: {
            emailRedirectTo:
              cfg.redirectUrl ||
              `${window.location.origin}${window.location.pathname}${window.location.search}`,
          },
        });
        if (error) throw error;
        root.querySelector(".gaia-dashboard__status").textContent =
          "Check your email for the sign-in link, then return to this page.";
      } catch (err) {
        root.querySelector(".gaia-dashboard__status").textContent = `Sign-in failed: ${err.message || err}`;
      } finally {
        button.disabled = false;
      }
    });
  };

  const load = async (root) => {
    const missing = [];
    if (!cfg.supabaseUrl) missing.push("SUPABASE_URL");
    if (!cfg.supabaseAnon) missing.push("SUPABASE_ANON_KEY");
    if (!dashboardProxy && !backendBase) missing.push("GAIAEYES_API_BASE or dashboardProxy");
    if (missing.length) {
      root.innerHTML = `<div class="gaia-dashboard__status">Dashboard config missing: ${esc(
        missing.join(", ")
      )}</div>`;
      return;
    }

    if (!window.supabase || !window.supabase.createClient) {
      root.innerHTML = '<div class="gaia-dashboard__status">Supabase client did not load.</div>';
      return;
    }

    const supabase = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnon);
    const hashResult = await hydrateSessionFromHash(supabase);
    if (hashResult.error) {
      renderSignInPrompt(root, supabase, `Sign-in link issue: ${hashResult.error}`);
      return;
    }

    const { data, error } = await supabase.auth.getSession();
    if (error) {
      root.innerHTML = `<div class="gaia-dashboard__status">${esc(error.message || "Session check failed.")}</div>`;
      return;
    }
    const token = data && data.session ? data.session.access_token : null;
    if (!token) {
      renderSignInPrompt(root, supabase);
      return;
    }

    try {
      const started = Date.now();
      const day = localDayISO();
      const debug = isDebugEnabled();
      const urls = [];
      if (dashboardProxy) {
        urls.push(
          `${dashboardProxy}?day=${encodeURIComponent(day)}${debug ? "&debug=1" : ""}`
        );
      }
      if (backendBase) {
        urls.push(
          `${backendBase}/v1/dashboard?day=${encodeURIComponent(day)}${debug ? "&debug=1" : ""}`
        );
      }
      let dashboard = null;
      let lastErr = null;
      for (const url of urls) {
        try {
          dashboard = await fetchJson(url, token);
          break;
        } catch (err) {
          lastErr = err;
          console.warn("[gaia-dashboard] fetch failed:", url, err && err.message ? err.message : String(err));
        }
      }
      if (!dashboard) {
        throw lastErr || new Error("Failed to fetch");
      }
      const elapsed = Date.now() - started;
      console.info("[gaia-dashboard] loaded payload in ms=", elapsed);
      if (debug && dashboard && dashboard._debug) {
        console.info("[gaia-dashboard] _debug:", dashboard._debug);
      } else if (debug) {
        const keys =
          dashboard && typeof dashboard === "object"
            ? Object.keys(dashboard)
            : [];
        console.info("[gaia-dashboard] debug requested but _debug missing; payload keys:", keys);
      }

      if (dashboard && dashboard.ok === false) {
        throw new Error(extractErrorMessage(dashboard) || "Dashboard returned ok=false");
      }

      if (
        dashboard &&
        typeof dashboard === "object" &&
        extractErrorMessage(dashboard).toLowerCase().includes("authorization")
      ) {
        throw new Error(extractErrorMessage(dashboard));
      }

      const payload = {
        gauges: dashboard && dashboard.gauges ? dashboard.gauges : null,
        gaugesMeta:
          (dashboard && (dashboard.gauges_meta || dashboard.gaugesMeta)) || {},
        gaugesDelta:
          (dashboard && (dashboard.gauges_delta || dashboard.gaugesDelta)) || {},
        gaugeZones:
          (dashboard && (dashboard.gauge_zones || dashboard.gaugeZones)) || null,
        gaugeLabels:
          (dashboard && (dashboard.gauge_labels || dashboard.gaugeLabels)) || {},
        drivers:
          (dashboard && (dashboard.drivers || dashboard.driverModels)) || [],
        driversCompact:
          (dashboard && (dashboard.drivers_compact || dashboard.driversCompact)) || [],
        modalModels:
          (dashboard && (dashboard.modal_models || dashboard.modalModels)) || {},
        earthscopeSummary:
          (dashboard && (dashboard.earthscope_summary || dashboard.earthscopeSummary)) || "",
        geomagneticContext:
          (dashboard && (dashboard.geomagnetic_context || dashboard.geomagneticContext)) || null,
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        entitled: dashboard ? dashboard.entitled : null,
        memberPost:
          (dashboard && (dashboard.member_post || dashboard.memberPost || dashboard.personal_post || dashboard.personalPost)) || null,
        publicPost: (dashboard && (dashboard.public_post || dashboard.publicPost)) || null,
      };
      const user = data && data.session && data.session.user ? data.session.user : null;
      root.innerHTML = '<div class="gaia-dashboard__status">Loading Mission Control…</div>';
      const member = await memberHubFetches(token);
      const state = {
        dashboard: payload,
        member,
        authCtx: {
        email: user && user.email ? user.email : "",
        token,
        onSignOut: async () => {
          try {
            await supabase.auth.signOut();
          } finally {
            renderSignInPrompt(root, supabase, "Signed out. Sign in with email.");
          }
        },
        onSwitch: async () => {
          const email = window.prompt("Use this email for a new magic link:");
          if (!email) return;
          try {
            const { error: signErr } = await supabase.auth.signInWithOtp({
              email,
              options: {
                emailRedirectTo:
                  cfg.redirectUrl ||
              `${window.location.origin}${window.location.pathname}${window.location.search}`,
              },
            });
            if (signErr) throw signErr;
            window.alert("Magic link sent. Open your email, then return to this page.");
          } catch (switchErr) {
            window.alert(`Could not send magic link: ${switchErr && switchErr.message ? switchErr.message : switchErr}`);
          }
        },
        },
        ui: {
          activeTab: currentTabFromHash(),
          exploreFilter: "all",
          guidePollChoice: "",
          checkInEditing: false,
          checkInSubmitting: false,
          checkInStatus: "",
          checkInForm: null,
          patternsLoading: true,
        },
      };
      renderMemberHub(root, state);
      if (!root.dataset.gaiaHashBound) {
        window.addEventListener("hashchange", () => {
          state.ui.activeTab = currentTabFromHash();
          renderMemberHub(root, state);
        });
        root.dataset.gaiaHashBound = "1";
      }
      try {
        state.member.patterns = await loadFullPatterns(token);
      } catch (err) {
        console.warn("[gaia-dashboard] full patterns fetch failed:", err && err.message ? err.message : String(err));
      } finally {
        state.ui.patternsLoading = false;
        renderMemberHub(root, state);
      }
    } catch (err) {
      const msg = err && err.message ? String(err.message) : String(err);
      const authErr =
        msg.includes("401") ||
        msg.includes("403") ||
        msg.toLowerCase().includes("authorization");
      if (authErr) {
        try {
          await supabase.auth.signOut();
        } catch (_) {}
        renderSignInPrompt(root, supabase, "Session expired. Sign in with email.");
      } else {
        root.innerHTML = `<div class="gaia-dashboard__status">Failed to load dashboard: ${esc(msg)}</div>`;
      }
    }
  };

  const init = () => {
    document.querySelectorAll("[data-gaia-dashboard]").forEach((root) => {
      load(root);
    });
  };

  document.addEventListener("DOMContentLoaded", init);
})();
