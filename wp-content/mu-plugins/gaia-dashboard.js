(function () {
  const cfg = window.GAIA_DASHBOARD_CFG || {};
  const normalizeBase = (value) => (value || "").replace(/\/+$/, "");
  const backendBase = normalizeBase(cfg.backendBase);
  const dashboardProxy = normalizeBase(cfg.dashboardProxy);
  const memberRoutes = cfg.memberRoutes && typeof cfg.memberRoutes === "object" ? cfg.memberRoutes : {};
  const supportUrl = cfg.supportUrl || "/support/";
  const privacyUrl = cfg.privacyUrl || "/privacy/";
  const termsUrl = cfg.termsUrl || "/terms/";
  const publicLinks = cfg.publicLinks && typeof cfg.publicLinks === "object" ? cfg.publicLinks : {};
  const DEFAULT_TRACKED_STAT_KEYS = ["resting_hr", "respiratory", "hrv", "spo2", "steps"];
  const MAX_FAVORITE_SYMPTOM_CODES = 6;
  const DEFAULT_TIME_ZONE_OPTIONS = [
    "America/Chicago",
    "America/New_York",
    "America/Denver",
    "America/Los_Angeles",
    "UTC",
  ];
  const TRACKED_STAT_OPTIONS = [
    { key: "resting_hr", label: "Resting HR", detail: "Baseline shift or daily average" },
    { key: "respiratory", label: "Respiratory", detail: "Breathing-rate shift or average" },
    { key: "spo2", label: "SpO₂", detail: "Oxygen average" },
    { key: "hrv", label: "HRV", detail: "Recovery average" },
    { key: "temperature", label: "Temperature", detail: "Temperature deviation" },
    { key: "steps", label: "Steps", detail: "Today’s activity" },
    { key: "heart_range", label: "Heart range", detail: "Min and max heart rate" },
    { key: "blood_pressure", label: "Blood pressure", detail: "Average blood pressure" },
  ];

  const esc = (value) =>
    String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const normalizeTrackedStatKey = (value) =>
    String(value || "")
      .trim()
      .toLowerCase()
      .replace(/-/g, "_")
      .replace(/\s+/g, "_");

  const normalizeTrackedStatKeys = (value) => {
    const source = Array.isArray(value)
      ? value
      : typeof value === "string"
        ? value.split(",")
        : [];
    const normalized = [];
    source.forEach((item) => {
      const key = normalizeTrackedStatKey(item);
      if (!key) return;
      if (!TRACKED_STAT_OPTIONS.some((option) => option.key === key)) return;
      if (normalized.includes(key)) return;
      if (normalized.length < 5) normalized.push(key);
    });
    return normalized.length ? normalized : [...DEFAULT_TRACKED_STAT_KEYS];
  };

  const normalizeFavoriteSymptomCodes = (value) => {
    const source = Array.isArray(value)
      ? value
      : typeof value === "string"
        ? value.split(",")
        : [];
    const normalized = [];
    source.forEach((item) => {
      const code = normalizeSymptomCode(item);
      if (!code) return;
      if (normalized.includes(code)) return;
      if (normalized.length < MAX_FAVORITE_SYMPTOM_CODES) normalized.push(code);
    });
    return normalized;
  };

  const browserTimeZoneIdentifier = () =>
    ((Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || "America/Chicago").trim() || "America/Chicago";

  const normalizeTimeZoneIdentifier = (value) =>
    String(value || "").trim() || browserTimeZoneIdentifier();

  const timeZoneOptions = (selected) => {
    const normalizedSelected = normalizeTimeZoneIdentifier(selected);
    const ordered = [];
    [
      normalizedSelected,
      browserTimeZoneIdentifier(),
      ...DEFAULT_TIME_ZONE_OPTIONS,
    ].forEach((identifier) => {
      if (identifier && !ordered.includes(identifier)) ordered.push(identifier);
    });
    if (typeof Intl !== "undefined" && typeof Intl.supportedValuesOf === "function") {
      Intl.supportedValuesOf("timeZone").forEach((identifier) => {
        if (identifier && !ordered.includes(identifier)) ordered.push(identifier);
      });
    }
    return ordered;
  };

  const timeZoneLabel = (identifier) => {
    const normalized = normalizeTimeZoneIdentifier(identifier).replace(/_/g, " ");
    if (normalizeTimeZoneIdentifier(identifier) === browserTimeZoneIdentifier()) {
      return `${normalized} (browser)`;
    }
    return normalized;
  };

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

  const normalizeDriverKey = (driver) =>
    textOrEmpty(driver && driver.key).trim().toLowerCase();

  const dedupeDriverItems = (items) => {
    const seen = new Set();
    return maybeArray(items).filter((driver) => {
      const key = normalizeDriverKey(driver);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };

  const combinedDashboardDrivers = (payload) =>
    dedupeDriverItems([
      payload && payload.primaryDriver ? payload.primaryDriver : null,
      ...maybeArray(payload && payload.supportingDrivers),
      ...maybeArray(payload && payload.drivers),
    ]);

  const dashboardDriverFromDetail = (driver) => ({
    key: textOrEmpty(driver && driver.key),
    label: textOrEmpty(driver && driver.label),
    severity: textOrEmpty(driver && (driver.severity || driver.state)),
    state: textOrEmpty(driver && (driver.stateLabel || driver.state)),
    value: Number.isFinite(Number(driver && driver.readingValue)) ? Number(driver && driver.readingValue) : null,
    unit: textOrEmpty(driver && driver.readingUnit),
    display: textOrEmpty(driver && driver.reading),
    role: textOrEmpty(driver && driver.role),
    roleLabel: textOrEmpty(driver && (driver.roleLabel || driver.role_label)),
    personalReason: textOrEmpty(
      driver &&
      (
        driver.personalReason ||
        driver.personal_reason ||
        driver.shortReason ||
        driver.short_reason ||
        driver.outlookSummary ||
        driver.outlook_summary
      )
    ),
  });

  const combinedMissionDrivers = (payload, memberDriversSnapshot = null) => {
    const dashboardDrivers = combinedDashboardDrivers(payload);
    if (dashboardDrivers.length >= 3) {
      return dashboardDrivers;
    }
    const previewDrivers = maybeArray(memberDriversSnapshot && memberDriversSnapshot.drivers).map(dashboardDriverFromDetail);
    return dedupeDriverItems([...dashboardDrivers, ...previewDrivers]);
  };

  const allMissionDrivers = (payload, memberDriversSnapshot = null) => {
    const previewDrivers = maybeArray(memberDriversSnapshot && memberDriversSnapshot.drivers).map(dashboardDriverFromDetail);
    if (previewDrivers.length) {
      return dedupeDriverItems(previewDrivers);
    }
    return combinedMissionDrivers(payload, memberDriversSnapshot);
  };

  const renderDriversSection = (drivers, modalModels, limit = 6, options = {}) => {
    const heading = textOrEmpty(options && options.heading) || "What Matters Now";
    if (!Array.isArray(drivers) || !drivers.length) {
      return `
        <div class="gaia-dashboard__drivers">
          <h4>${esc(heading)}</h4>
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
        <h4>${esc(heading)}</h4>
        ${groups}
      </div>
    `;
  };

  const renderAllDriversModal = (payload, memberDriversSnapshot = null) => `
    <h3 class="gaia-dashboard__modal-title">All Drivers</h3>
    ${renderDriversSection(allMissionDrivers(payload, memberDriversSnapshot), payload && payload.modalModels ? payload.modalModels : {}, 12, { heading: "Drivers" })}
    <div class="gaia-dashboard__modal-actions">
      <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
    </div>
  `;

  const renderMissionBodyContext = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const dailyCheckIn = extractDailyCheckIn(state.member.dailyCheckIn);
    const currentSymptomsLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.currentSymptoms);
    const dailyCheckInLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.dailyCheckIn);
    const currentSymptomsError = textOrEmpty(state.member.errors && state.member.errors.currentSymptoms);
    const dailyCheckInError = textOrEmpty(state.member.errors && state.member.errors.dailyCheckIn);
    const summary = currentSymptoms && currentSymptoms.summary ? currentSymptoms.summary : {};
    const symptomCount = Math.round(Number(summary.active_count || summary.activeCount || 0));
    const symptomDriver = maybeArray(
      currentSymptoms && (currentSymptoms.contributing_drivers || currentSymptoms.contributingDrivers)
    )[0];
    const dailyEntry = dailyCheckIn && dailyCheckIn.latest_entry ? dailyCheckIn.latest_entry : null;
    const targetDay = textOrEmpty(dailyCheckIn && dailyCheckIn.target_day) || localDayISO();
    const completedToday = !!(dailyEntry && textOrEmpty(dailyEntry.day) === targetDay);
    const prompt = dailyCheckIn && dailyCheckIn.prompt ? dailyCheckIn.prompt : null;
    const symptomTitle = currentSymptomsLoading && !currentSymptoms
      ? "Loading current symptoms"
      : symptomCount > 0
        ? `${symptomCount} active right now`
        : currentSymptomsError
          ? "Current symptoms unavailable"
          : "Nothing active right now";
    const symptomCopy = currentSymptomsLoading && !currentSymptoms
      ? "Checking the latest symptom timeline."
      : symptomCount > 0
        ? sentence(
            currentSymptoms.current_context_summary || currentSymptoms.currentContextSummary || "",
            "Follow-up check-ins can keep the timeline current."
          )
        : currentSymptomsError
          ? "The current-symptoms service is having trouble right now."
          : "Open Body to log symptoms or update the current timeline.";
    const checkInTitle = dailyCheckInLoading && !dailyCheckIn
      ? "Checking for today's prompt"
      : completedToday
        ? "Completed for today"
        : prompt
          ? "Today's quick check-in is ready"
          : dailyCheckInError
            ? "Check-in unavailable"
            : "Nothing waiting right now";
    const checkInCopy = dailyCheckInLoading && !dailyCheckIn
      ? "Loading your daily check-in state."
      : completedToday
        ? `Completed for ${formatDayLabel(targetDay)}.`
        : dailyCheckInError && !prompt
          ? "The daily check-in service is having trouble right now."
          : sentence(prompt && prompt.question_text, "Open Body to update the day read.");

    return `
      <div class="gaia-dashboard__drivers gaia-dashboard__drivers--body-context">
        <h4>Body Context</h4>
        <div class="gaia-dashboard__nav-grid">
          <button class="gaia-dashboard__nav-card" type="button" data-tab-target="body">
            <div class="gaia-dashboard__nav-card-head">
              <strong>Current Symptoms</strong>
              ${
                symptomDriver
                  ? `<span class="${pillClass(symptomDriver.severity || "watch")}">${esc(
                      symptomDriver.label || symptomDriver.key || "Context"
                    )}</span>`
                  : symptomCount > 0
                    ? `<span class="${pillClass("watch")}">${esc(`${symptomCount} active`)}</span>`
                    : ""
              }
            </div>
            <span>${esc(symptomTitle)}</span>
            <span class="gaia-dashboard__helper">${esc(symptomCopy)}</span>
          </button>
          <button class="gaia-dashboard__nav-card" type="button" data-tab-target="body">
            <div class="gaia-dashboard__nav-card-head">
              <strong>Daily Check-In</strong>
              ${
                completedToday
                  ? `<span class="${pillClass("low")}">Done</span>`
                  : prompt
                    ? `<span class="${pillClass("watch")}">Ready</span>`
                    : ""
              }
            </div>
            <span>${esc(checkInTitle)}</span>
            <span class="gaia-dashboard__helper">${esc(checkInCopy)}</span>
          </button>
        </div>
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

  const guidePossibleSymptomPhrasesForDriver = (driver) => {
    const tokens = `${textOrEmpty(driver && driver.key)} ${textOrEmpty(driver && driver.label)}`.toLowerCase();
    if (!tokens) return [];
    if (tokens.includes("aqi") || tokens.includes("air quality")) {
      return ["Sinus pressure", "Headache", "Brain fog", "Shorter breath"];
    }
    if (tokens.includes("pressure")) {
      return ["Sinus pressure", "Headache", "Elevated pain", "Light sensitivity"];
    }
    if (tokens.includes("humidity")) {
      return ["Headache", "Elevated pain", "Fatigue", "Sinus pressure"];
    }
    if (["allergen", "pollen", "grass", "tree", "weed", "mold"].some((term) => tokens.includes(term))) {
      return ["Sinus pressure", "Headache", "Fatigue", "Irritation"];
    }
    if (["schumann", "ulf", "kp", "bz", "sw", "geomag", "solar", "magnetosphere"].some((term) => tokens.includes(term))) {
      return ["Energy variance", "Heightened sensitivity", "Sleep shifts", "Focus drift"];
    }
    if (tokens.includes("temp") || tokens.includes("temperature")) {
      return ["Elevated pain", "Fatigue", "Headache"];
    }
    if (tokens.includes("sleep")) {
      return ["Shortened sleep", "Fatigue", "Energy variance"];
    }
    if (["recovery", "stamina", "energy", "health", "pain"].some((term) => tokens.includes(term))) {
      return ["Fatigue", "Elevated pain", "Energy variance"];
    }
    return [];
  };

  const guidePossibleSymptoms = (state) => {
    const phrases = [];
    maybeArray(state && state.dashboard && state.dashboard.drivers)
      .slice(0, 4)
      .forEach((driver) => {
        guidePossibleSymptomPhrasesForDriver(driver).forEach((phrase) => {
          if (!phrases.includes(phrase) && phrases.length < 6) phrases.push(phrase);
        });
      });

    const lunar = maybeObject(state && state.member && state.member.lunar);
    const highlightWindow = textOrEmpty(lunar && lunar.highlight_window).toLowerCase();
    if (highlightWindow === "full" || highlightWindow === "new") {
      ["Shortened sleep", "Headache", "Elevated pain"].forEach((phrase) => {
        if (!phrases.includes(phrase) && phrases.length < 6) phrases.push(phrase);
      });
    }

    return phrases;
  };

  const guideHumanList = (items) => {
    const values = maybeArray(items).filter(Boolean);
    if (!values.length) return "";
    if (values.length === 1) return values[0];
    if (values.length === 2) return `${values[0]} or ${values[1]}`;
    return `${values.slice(0, -1).join(", ")}, or ${values[values.length - 1]}`;
  };

  const guidePossibleSymptomsSummary = (state) => {
    const phrases = guidePossibleSymptoms(state);
    if (!phrases.length) return "";
    return `Possible symptoms right now: ${guideHumanList(phrases.slice(0, 4))} may be easier to notice.`;
  };

  const guideProfileValue = (state, key, fallback = "") => {
    const preferences = extractProfilePreferences(state && state.member ? state.member.profilePreferences : null) || {};
    return textOrEmpty(preferences && preferences[key]) || fallback;
  };

  const guideHeaderLine = (state) => {
    const guide = guideProfileValue(state, "guide", "cat").toLowerCase();
    const mode = guideProfileValue(state, "mode", "scientific").toLowerCase();
    if (guide === "cat" && mode === "scientific") return "Here’s the clearest read on today’s signal mix.";
    if (guide === "cat" && mode === "mystical") return "Here’s the feel of what seems active today.";
    if (guide === "dog" && mode === "scientific") return "A steady read on today’s strongest inputs.";
    if (guide === "dog" && mode === "mystical") return "A grounded read on what may be nudging the day.";
    if (guide === "robot" && mode === "scientific") return "Current signal scan: highest-relevance items first.";
    if (guide === "robot" && mode === "mystical") return "Pattern scan: most likely influences first.";
    return "Current signal scan: highest-relevance items first.";
  };

  const guideHeaderSupportLine = (state) => {
    const guide = guideProfileValue(state, "guide", "cat").toLowerCase();
    const tone = guideProfileValue(state, "tone", "balanced").toLowerCase();
    if (tone === "straight") {
      return "Start with the essentials, then open the deeper layers only if you need them.";
    }
    if (tone === "humorous") {
      if (guide === "dog") return "Quick scan first. No need to chase every squirrel in the data.";
      if (guide === "robot") return "Quick scan first. No need to overclock the signal spaghetti.";
      return "Quick scan first. No need to cannonball into the signal soup.";
    }
    if (guide === "dog") {
      return "Use this space to get oriented fast, leave a little feedback, and keep the day grounded.";
    }
    if (guide === "robot") {
      return "Use this space to orient quickly, add lightweight feedback, and keep the day legible.";
    }
    return "Use this space for quick orientation, light feedback, and a calmer read on the day.";
  };

  const guideTitleForValue = (value, fallback = "") => {
    const normalized = textOrEmpty(value).toLowerCase();
    if (normalized === "cat") return "Cat";
    if (normalized === "dog") return "Dog";
    if (normalized === "robot") return "Robot";
    if (normalized === "scientific") return "Scientific";
    if (normalized === "mystical") return "Mystical";
    if (normalized === "straight") return "Straight";
    if (normalized === "balanced") return "Balanced";
    if (normalized === "humorous") return "Humorous";
    return fallback;
  };

  const guideProfileSummary = (state) => {
    const guide = guideTitleForValue(guideProfileValue(state, "guide", "cat"), "Cat");
    const mode = guideTitleForValue(guideProfileValue(state, "mode", "scientific"), "Scientific");
    const tone = guideTitleForValue(guideProfileValue(state, "tone", "balanced"), "Balanced");
    return [guide, mode, tone].filter(Boolean).join(" • ");
  };

  const renderGuideHeaderCard = (state) => {
    const possibleSymptoms = guidePossibleSymptoms(state);
    const lead = possibleSymptoms.length
      ? "Based on the current signal mix, these may be easier to notice."
      : guidePossibleSymptomsSummary(state) || guideHeaderLine(state);
    return `
      <article class="gaia-dashboard__card gaia-dashboard__card--guide-header">
        <div class="gaia-dashboard__card-title-row gaia-dashboard__card-title-row--guide">
          <div>
            <h4 class="gaia-dashboard__card-title">Possible symptoms</h4>
          </div>
          <button
            class="gaia-dashboard__guide-settings-btn"
            type="button"
            data-tab-target="settings"
            aria-label="Open guide settings"
            title="Open guide settings"
          >
            &#9881;
          </button>
        </div>
        <p class="gaia-dashboard__guide-topline">${esc(guideHeaderSupportLine(state))}</p>
        <p class="gaia-dashboard__card-copy">${esc(lead)}</p>
        ${
          possibleSymptoms.length
            ? `<div class="gaia-dashboard__guide-bullet-grid gaia-dashboard__guide-bullet-grid--compact">${possibleSymptoms
                .map((item) => `<div class="gaia-dashboard__guide-bullet">${esc(item)}</div>`)
                .join("")}</div>`
            : ""
        }
        <div class="gaia-dashboard__guide-profile-line">${esc(guideProfileSummary(state))}</div>
      </article>
    `;
  };

  const guideInfluenceDomain = (driver) => {
    const tokens = `${textOrEmpty(driver && driver.key)} ${textOrEmpty(driver && driver.label)}`.toLowerCase();
    if (!tokens) return "";
    if (["schumann", "kp", "bz", "sw", "solar", "geomag", "aurora", "magnetosphere", "space", "resonance"].some((term) => tokens.includes(term))) {
      return "space";
    }
    if (["symptom", "body", "sleep", "recovery", "fatigue", "pain", "mood", "energy", "stamina", "health"].some((term) => tokens.includes(term))) {
      return "body";
    }
    if (["humidity", "allergen", "pollen", "grass", "tree", "weed", "mold", "aqi", "air", "pressure", "temp", "weather", "local"].some((term) => tokens.includes(term))) {
      return "earth";
    }
    return "";
  };

  const guideInfluenceLine = (driver) => {
    const label = textOrEmpty(driver && (driver.label || driver.key));
    if (!label) return "";
    const badge = textOrEmpty(driver && (driver.severity || driver.state || driver.roleLabel || driver.role_label));
    return badge ? `${label} — ${badge}` : label;
  };

  const guideInfluenceBuckets = (state) => {
    const buckets = { earth: [], space: [], body: [] };
    maybeArray(state && state.dashboard && state.dashboard.drivers).forEach((driver) => {
      const domain = guideInfluenceDomain(driver);
      const line = guideInfluenceLine(driver);
      if (!domain || !line) return;
      if (!buckets[domain].includes(line) && buckets[domain].length < 3) {
        buckets[domain].push(line);
      }
    });
    const currentSymptoms = extractCurrentSymptoms(state && state.member && state.member.currentSymptoms);
    const semanticLabels = maybeArray(
      currentSymptoms && currentSymptoms.voiceSemantic && currentSymptoms.voiceSemantic.facts && currentSymptoms.voiceSemantic.facts.activeLabels
    )
      .map((item) => textOrEmpty(item))
      .filter(Boolean);
    const fallbackLabels = maybeArray(currentSymptoms && currentSymptoms.items)
      .map((item) => textOrEmpty(item && item.label))
      .filter(Boolean);
    const labels = semanticLabels.length ? semanticLabels : fallbackLabels;
    if (!buckets.body.length && labels.length) {
      buckets.body.push(`Current symptoms — ${labels.slice(0, 2).join(" • ")}`);
    }
    return buckets;
  };

  const currentSymptomsLabelSummary = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state && state.member && state.member.currentSymptoms);
    const semanticLabels = maybeArray(
      currentSymptoms && currentSymptoms.voiceSemantic && currentSymptoms.voiceSemantic.facts && currentSymptoms.voiceSemantic.facts.activeLabels
    )
      .map((item) => textOrEmpty(item))
      .filter(Boolean);
    if (semanticLabels.length) return semanticLabels.slice(0, 2).join(" • ");
    const fallback = maybeArray(currentSymptoms && currentSymptoms.items)
      .map((item) => textOrEmpty(item && item.label))
      .filter(Boolean);
    return fallback.length ? fallback.slice(0, 2).join(" • ") : "";
  };

  const localGuideSupportActions = (state) => {
    const codes = new Set(
      maybeArray(extractCurrentSymptoms(state && state.member && state.member.currentSymptoms)?.items)
        .map((item) => normalizeSymptomCode(item && (item.symptomCode || item.symptom_code)))
        .filter(Boolean)
    );
    const lines = [];
    const push = (line) => {
      const cleaned = textOrEmpty(line);
      if (!cleaned) return;
      const normalized = normalizeGuideSupportLine(cleaned);
      if (lines.some((item) => normalizeGuideSupportLine(item) === normalized)) return;
      lines.push(cleaned);
    };
    if (["PAIN", "NERVE_PAIN", "JOINT_PAIN", "STIFFNESS", "STOMACH_PAIN"].some((code) => codes.has(code))) {
      push("Use warmth, gentler movement, or a lighter task load if pain or stiffness is closer to the surface.");
    }
    if (["HEADACHE", "SINUS_PRESSURE", "LIGHT_SENSITIVITY", "RESP_IRRITATION"].some((code) => codes.has(code))) {
      push("Hydrate, use cleaner air, and lean on sinus or head-pressure support if that is a pattern for you.");
    }
    if (["DRAINED", "FATIGUE", "BRAIN_FOG", "INSOMNIA", "RESTLESS_SLEEP"].some((code) => codes.has(code))) {
      push("Use shorter effort blocks and leave more recovery space between heavier tasks.");
    }
    if (["ANXIOUS", "WIRED", "PALPITATIONS"].some((code) => codes.has(code))) {
      push("Use grounding or slower breathing before adding more stimulation if your system feels buzzy.");
    }
    return lines;
  };

  const normalizeGuideSupportLine = (value) =>
    textOrEmpty(value)
      .toLowerCase()
      .replace(/[.’]/g, "")
      .replace(/\s+/g, " ")
      .trim();

  const guideSupportNeedsGrounding = (state, items) => {
    const codes = new Set(
      maybeArray(extractCurrentSymptoms(state && state.member && state.member.currentSymptoms)?.items)
        .map((item) => normalizeSymptomCode(item && (item.symptomCode || item.symptom_code)))
        .filter(Boolean)
    );
    const nervousSystemCodes = new Set(["ANXIOUS", "WIRED", "PALPITATIONS", "RESTLESS_SLEEP", "DRAINED"]);
    for (const code of codes) {
      if (nervousSystemCodes.has(code)) return true;
    }
    return maybeArray(items).some((item) => {
      const tokens = `${textOrEmpty(item && item.key)} ${textOrEmpty(item && item.title)} ${textOrEmpty(item && item.message)} ${textOrEmpty(item && item.badge)}`.toLowerCase();
      return ["calm", "regulate", "nervous", "schumann", "kp", "bz", "sw", "solar", "geomag", "wired", "buzzy"].some((term) => tokens.includes(term));
    });
  };

  const guideSupportActions = (state, items) => {
    const lines = [];
    localGuideSupportActions(state).forEach((line) => lines.push(line));
    if (guideSupportNeedsGrounding(state, items)) {
      const grounding = "Use a grounding reset before adding more input if your system feels buzzy or overloaded.";
      if (!lines.some((line) => normalizeGuideSupportLine(line) === normalizeGuideSupportLine(grounding))) {
        lines.push(grounding);
      }
    }
    maybeArray(items).forEach((item) => {
      maybeArray(item && item.actions).forEach((action) => {
        const cleaned = textOrEmpty(action);
        if (!cleaned) return;
        const normalized = normalizeGuideSupportLine(cleaned);
        if (lines.some((line) => normalizeGuideSupportLine(line) === normalized)) return;
        lines.push(cleaned);
      });
    });
    if (lines.length < 4) {
      maybeArray(items).forEach((item) => {
        const cleaned = textOrEmpty(item && item.message);
        if (!cleaned) return;
        const normalized = normalizeGuideSupportLine(cleaned);
        if (lines.some((line) => normalizeGuideSupportLine(line) === normalized)) return;
        lines.push(cleaned);
      });
    }
    return lines.slice(0, 5);
  };

  const guideSupportIntro = (state, items) => {
    const summary = currentSymptomsLabelSummary(state);
    if (summary) {
      return `Current body context: ${summary}. Keep the next stretch a little gentler while this mix is up.`;
    }
    return textOrEmpty(items && items[0] && items[0].message) || "Keep following the body read and the current driver stack.";
  };

  const renderGuideInfluenceCard = (state) => {
    const buckets = guideInfluenceBuckets(state);
    const groups = [
      { title: "Earth influences", items: buckets.earth },
      { title: "Space influences", items: buckets.space },
      { title: "Body influences", items: buckets.body },
    ].filter((group) => group.items.length);
    if (!groups.length) return "";
    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <div>
            <h4 class="gaia-dashboard__card-title">Possible influences</h4>
          </div>
        </div>
        <p class="gaia-dashboard__card-copy">These are the strongest earth, space, and body signals in the current read.</p>
        <div class="gaia-dashboard__guide-influence-stack">
          ${groups
            .map(
              (group) => `
                <div class="gaia-dashboard__guide-influence-section">
                  <div class="gaia-dashboard__mini-title">${esc(group.title)}</div>
                  <div class="gaia-dashboard__guide-bullet-grid">
                    ${group.items.map((item) => `<div class="gaia-dashboard__guide-bullet-row">${esc(item)}</div>`).join("")}
                  </div>
                </div>
              `
            )
            .join("")}
        </div>
        <div class="gaia-dashboard__section-actions">
          <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="drivers">Open Drivers</button>
        </div>
      </article>
    `;
  };

  const normalizeSymptomCode = (value) =>
    String(value || "")
      .trim()
      .replace(/[-\s]+/g, "_")
      .toUpperCase();

  const dedupeStrings = (values, normalizer = textOrEmpty) => {
    const seen = new Set();
    return maybeArray(values).filter((value) => {
      const normalized = textOrEmpty(normalizer(value));
      if (!normalized) return false;
      if (seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    });
  };

  const normalizeSymptomLabel = (value) =>
    textOrEmpty(value)
      .replace(/\s+/g, " ")
      .toLowerCase();

  const dedupeSymptomCatalog = (items) => {
    const seenCodes = new Set();
    const seenLabels = new Set();
    return maybeArray(items).filter((item) => {
      if (!item || typeof item !== "object") return false;
      const normalizedCode = normalizeSymptomCode(item.symptom_code || item.symptomCode);
      const displayLabel =
        textOrEmpty(item.label) ||
        (normalizedCode ? titleFromKey(normalizedCode) : "");
      const normalizedLabel = normalizeSymptomLabel(displayLabel);
      if (!normalizedCode && !normalizedLabel) return false;
      if (normalizedCode && seenCodes.has(normalizedCode)) return false;
      if (normalizedLabel && seenLabels.has(normalizedLabel)) return false;
      if (normalizedCode) seenCodes.add(normalizedCode);
      if (normalizedLabel) seenLabels.add(normalizedLabel);
      return true;
    });
  };

  const extractSymptomCodeCatalog = (payload) =>
    dedupeSymptomCatalog(maybeArray(extractEnvelopeData(payload)));

  const extractPatternsPayload = (payload) => {
    const data = extractEnvelopeData(payload);
    if (data && typeof data === "object") return data;
    return maybeObject(payload) || {};
  };

  const symptomOptionLabel = (code, catalog) => {
    const normalized = normalizeSymptomCode(code);
    const match = maybeArray(catalog).find(
      (item) => normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)) === normalized
    );
    return textOrEmpty(match && (match.label || match.symptom_code || match.symptomCode)) || titleFromKey(normalized);
  };

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
            ? `<button class="gaia-dashboard__btn" type="button" data-open-symptom-picker="1" data-picker-title="${esc(ctaLabel)}" data-prefill='${ctaPrefillAttr}'>${esc(ctaLabel)}</button>`
            : ""
        }
        <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
      </div>
    `;
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

  const putJson = async (url, token, body) => {
    const response = await fetch(url, {
      method: "PUT",
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

  const deleteJson = async (url, token) => {
    const response = await fetch(url, {
      method: "DELETE",
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

  const fetchSymptomCodes = async (token) => {
    const url = routeFor("symptomCodes");
    if (!url) throw new Error("Symptom code route is not configured.");
    return fetchJson(url, token);
  };

  const postSymptomEvents = async (token, codes) => {
    const url = routeFor("symptomLog");
    if (!url) throw new Error("Symptom logging route is not configured.");
    const normalizedCodes = dedupeStrings(maybeArray(codes).map(normalizeSymptomCode), normalizeSymptomCode);
    if (!normalizedCodes.length) throw new Error("Choose at least one symptom.");
    for (const code of normalizedCodes) {
      const response = await postJson(url, token, { symptom_code: code });
      if (response && response.ok === false) {
        throw new Error(response.friendly_error || response.error || "Could not log symptom.");
      }
    }
    return { ok: true };
  };

  const routeFor = (key, fallback = "") => normalizeBase(memberRoutes[key] || fallback);

  const currentSymptomUpdateRoute = (episodeId) => {
    const base = routeFor("currentSymptomUpdatesBase");
    if (!base || !episodeId) return "";
    return `${base}/${encodeURIComponent(episodeId)}/updates`;
  };

  const followUpRespondRoute = (promptId) => {
    const base = routeFor("followUpBase");
    if (!base || !promptId) return "";
    return `${base}/${encodeURIComponent(promptId)}/respond`;
  };

  const followUpDismissRoute = (promptId) => {
    const base = routeFor("followUpBase");
    if (!base || !promptId) return "";
    return `${base}/${encodeURIComponent(promptId)}/dismiss`;
  };

  const updateCurrentSymptomState = async (token, episodeId, body) => {
    const url = currentSymptomUpdateRoute(episodeId);
    if (!url) throw new Error("Current symptom update route is not configured.");
    return postJson(url, token, body || {});
  };

  const respondCurrentSymptomFollowUp = async (token, promptId, body) => {
    const url = followUpRespondRoute(promptId);
    if (!url) throw new Error("Symptom follow-up route is not configured.");
    return postJson(url, token, body || {});
  };

  const dismissCurrentSymptomFollowUp = async (token, promptId, body) => {
    const url = followUpDismissRoute(promptId);
    if (!url) throw new Error("Symptom follow-up dismiss route is not configured.");
    return postJson(url, token, body || {});
  };

  const memberPreferredTimeZone = (state) => {
    const notifications = extractNotificationPreferences(state && state.member ? state.member.notifications : null);
    return normalizeTimeZoneIdentifier(notifications && (notifications.time_zone || notifications.timeZone));
  };

  const memberHubLoaders = (token, state) => {
    const timezone = memberPreferredTimeZone(state);
    return {
      profilePreferences: () =>
        fetchJson(routeFor("profilePreferences"), token).then((payload) => extractProfilePreferences(payload) || {}),
      notifications: () =>
        fetchJson(routeFor("notifications"), token).then((payload) => extractNotificationPreferences(payload) || {}),
      symptomCodes: () => fetchJson(routeFor("symptomCodes"), token),
      drivers: () => fetchJson(routeFor("drivers"), token),
      features: () => fetchJsonWithParams(routeFor("features"), token, { tz: timezone }),
      currentSymptoms: () => fetchJsonWithParams(routeFor("currentSymptoms"), token, { window_hours: 12 }),
      dailyCheckIn: () => fetchJson(routeFor("dailyCheckIn"), token),
      lunar: () => fetchJson(routeFor("lunar"), token),
      outlook: () => fetchJson(routeFor("outlook"), token),
      patternsSummary: () => fetchJson(routeFor("patternsSummary"), token),
    };
  };

  const loadFullPatterns = async (token) => {
    const url = routeFor("patterns");
    if (!url) return null;
    return fetchJson(url, token);
  };

  const defaultLoadingKeys = () => ({
    profilePreferences: false,
    notifications: false,
    symptomCodes: false,
    drivers: false,
    features: false,
    currentSymptoms: false,
    dailyCheckIn: false,
    lunar: false,
    outlook: false,
    patternsSummary: false,
    patterns: false,
  });

  const ensureLoadingKeys = (state) => {
    if (!state.ui.loadingKeys) {
      state.ui.loadingKeys = defaultLoadingKeys();
      return;
    }
    Object.keys(defaultLoadingKeys()).forEach((key) => {
      if (typeof state.ui.loadingKeys[key] !== "boolean") {
        state.ui.loadingKeys[key] = false;
      }
    });
  };

  const setMemberHydrationResult = (state, key, payload, errorMessage = "") => {
    state.member[key] = payload;
    if (errorMessage) {
      state.member.errors[key] = errorMessage;
    } else {
      delete state.member.errors[key];
    }
  };

  const hydrateMemberKeys = (root, state, keys, options = {}) => {
    const force = !!(options && options.force);
    const token = state && state.authCtx ? state.authCtx.token : "";
    if (!token) return;
    ensureLoadingKeys(state);
    const loaders = memberHubLoaders(token, state);
    maybeArray(keys).forEach((key) => {
      const loader = loaders[key];
      if (typeof loader !== "function") return;
      if (state.ui.loadingKeys[key]) return;
      if (!force && state.member[key]) return;
      state.ui.loadingKeys[key] = true;
      loader()
        .then((payload) => {
          setMemberHydrationResult(state, key, payload, "");
        })
        .catch((err) => {
          const message = err && err.message ? err.message : String(err);
          setMemberHydrationResult(state, key, null, message);
        })
        .finally(() => {
          state.ui.loadingKeys[key] = false;
          renderMemberHub(root, state);
        });
    });
  };

  const ensureFullPatternsLoaded = (root, state, options = {}) => {
    const force = !!(options && options.force);
    const token = state && state.authCtx ? state.authCtx.token : "";
    if (!token) return;
    ensureLoadingKeys(state);
    if (state.ui.loadingKeys.patterns) return;
    if (!force && state.member.patterns) return;
    state.ui.loadingKeys.patterns = true;
    state.ui.patternsLoading = true;
    loadFullPatterns(token)
      .then((patterns) => {
        state.member.patterns = patterns;
        delete state.member.errors.patterns;
      })
      .catch((err) => {
        state.member.errors.patterns = err && err.message ? err.message : String(err);
      })
      .finally(() => {
        state.ui.loadingKeys.patterns = false;
        state.ui.patternsLoading = false;
        renderMemberHub(root, state);
      });
  };

  const hydrateTabData = (root, state, tab) => {
    const key = normalizeTabKey(tab);
    if (key === "mission") {
      hydrateMemberKeys(root, state, ["drivers", "outlook", "currentSymptoms", "dailyCheckIn", "notifications"]);
      return;
    }
    if (key === "drivers") {
      hydrateMemberKeys(root, state, ["drivers"]);
      return;
    }
    if (key === "body") {
      hydrateMemberKeys(root, state, ["profilePreferences", "notifications", "currentSymptoms", "dailyCheckIn", "lunar", "features"]);
      return;
    }
    if (key === "patterns") {
      hydrateMemberKeys(root, state, ["patternsSummary"]);
      ensureFullPatternsLoaded(root, state);
      return;
    }
    if (key === "outlook") {
      hydrateMemberKeys(root, state, ["outlook"]);
      return;
    }
    if (key === "guide") {
      hydrateMemberKeys(root, state, ["profilePreferences", "currentSymptoms", "dailyCheckIn", "outlook", "notifications"]);
      return;
    }
    if (key === "settings") {
      hydrateMemberKeys(root, state, ["profilePreferences", "notifications", "symptomCodes"]);
    }
  };

  const scheduleIdleHydration = (root, state) => {
    const idle = window.requestIdleCallback || ((callback) => window.setTimeout(callback, 180));
    idle(() => {
      hydrateMemberKeys(root, state, ["profilePreferences", "notifications", "currentSymptoms", "dailyCheckIn", "lunar", "patternsSummary"]);
      idle(() => {
        hydrateMemberKeys(root, state, ["drivers", "features", "outlook"]);
      });
    });
  };

  const renderSymptomPickerModal = (state) => {
    const picker = state && state.ui ? state.ui.symptomPicker : null;
    const profilePreferences = extractProfilePreferences(state && state.member ? state.member.profilePreferences : null);
    const favoriteCodes = profileFavoriteSymptomCodes(profilePreferences);
    const favoriteSet = new Set(favoriteCodes);
    const catalog = dedupeSymptomCatalog(extractSymptomCodeCatalog(state && state.member ? state.member.symptomCodes : null))
      .filter((item) => item.is_active !== false && item.isActive !== false)
      .sort((a, b) =>
        textOrEmpty(a && a.label).localeCompare(textOrEmpty(b && b.label), undefined, { sensitivity: "base" })
      );
    const selected = new Set(dedupeStrings(picker && picker.selectedCodes, normalizeSymptomCode).map(normalizeSymptomCode));
    const query = textOrEmpty(picker && picker.query).toLowerCase();
    const suggested = dedupeStrings(picker && picker.suggestedCodes, normalizeSymptomCode)
      .map((code) => normalizeSymptomCode(code))
      .filter((code) =>
        catalog.some((item) => normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)) === code)
      );
    const selectedItems = catalog.filter((item) =>
      selected.has(normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)))
    );
    const favoriteItems = catalog.filter((item) => {
      const normalized = normalizeSymptomCode(item && (item.symptom_code || item.symptomCode));
      if (!favoriteSet.has(normalized)) return false;
      if (suggested.includes(normalized)) return false;
      if (selected.has(normalized)) return false;
      if (!query) return true;
      const label = textOrEmpty(item && item.label).toLowerCase();
      const description = textOrEmpty(item && item.description).toLowerCase();
      const code = normalized.toLowerCase();
      return label.includes(query) || description.includes(query) || code.includes(query);
    });
    const remaining = catalog.filter((item) => {
      const normalized = normalizeSymptomCode(item && (item.symptom_code || item.symptomCode));
      if (suggested.includes(normalized)) return false;
      if (selected.has(normalized)) return false;
      if (favoriteSet.has(normalized)) return false;
      if (!query) return true;
      const label = textOrEmpty(item && item.label).toLowerCase();
      const description = textOrEmpty(item && item.description).toLowerCase();
      const code = normalized.toLowerCase();
      return label.includes(query) || description.includes(query) || code.includes(query);
    });
    const selectedCount = selected.size;

    const renderOptionButton = (code, label, description) => `
      <button
        class="gaia-dashboard__symptom-pill${selected.has(code) ? " is-selected" : ""}"
        type="button"
        data-symptom-select="${esc(code)}"
      >
        <span class="gaia-dashboard__symptom-pill-title">${esc(label)}</span>
        ${description ? `<span class="gaia-dashboard__symptom-pill-copy">${esc(description)}</span>` : ""}
      </button>
    `;

    return `
      <div class="gaia-dashboard__symptom-sheet">
        <div class="gaia-dashboard__symptom-hero">
          <div class="gaia-dashboard__symptom-hero-copy">
            <h3 class="gaia-dashboard__modal-title">${esc((picker && picker.title) || "Log symptoms")}</h3>
            <p class="gaia-dashboard__modal-copy">Choose one or more symptoms to log right now. Suggestions use the current view, active drivers, and your recent symptom context.</p>
          </div>
          <div class="gaia-dashboard__symptom-count">${selectedCount}</div>
        </div>
        <section class="gaia-dashboard__symptom-section">
          <div class="gaia-dashboard__symptom-section-head">
            <div class="gaia-dashboard__symptom-section-copy">
              <h5 class="gaia-dashboard__symptom-section-title">Find a symptom</h5>
              <span class="gaia-dashboard__helper">Search the full list or tap the suggested chips first.</span>
            </div>
          </div>
          <input
            class="gaia-dashboard__symptom-search"
            type="search"
            placeholder="Search symptoms"
            value="${esc(picker && picker.query ? picker.query : "")}"
            data-symptom-search="1"
          />
        </section>
        ${
          suggested.length
            ? `
              <section class="gaia-dashboard__symptom-section">
                <div class="gaia-dashboard__symptom-section-head">
                  <div class="gaia-dashboard__symptom-section-copy">
                    <h5 class="gaia-dashboard__symptom-section-title">Suggested right now</h5>
                    <span class="gaia-dashboard__helper">These match the context you opened from.</span>
                  </div>
                </div>
                <div class="gaia-dashboard__symptom-grid">
                  ${suggested
                    .map((code) => renderOptionButton(code, symptomOptionLabel(code, catalog), ""))
                    .join("")}
                </div>
              </section>
            `
            : ""
        }
        ${
          favoriteItems.length
            ? `
              <section class="gaia-dashboard__symptom-section">
                <div class="gaia-dashboard__symptom-section-head">
                  <div class="gaia-dashboard__symptom-section-copy">
                    <h5 class="gaia-dashboard__symptom-section-title">Favorite symptoms</h5>
                    <span class="gaia-dashboard__helper">Your go-to symptoms appear first on app and web.</span>
                  </div>
                </div>
                <div class="gaia-dashboard__symptom-grid">
                  ${favoriteItems
                    .map((item) =>
                      renderOptionButton(
                        normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)),
                        textOrEmpty(item && item.label) || titleFromKey(item && (item.symptom_code || item.symptomCode)),
                        textOrEmpty(item && item.description)
                      )
                    )
                    .join("")}
                </div>
              </section>
            `
            : ""
        }
        ${
          selectedItems.length
            ? `
              <section class="gaia-dashboard__symptom-section">
                <div class="gaia-dashboard__symptom-section-head">
                  <div class="gaia-dashboard__symptom-section-copy">
                    <h5 class="gaia-dashboard__symptom-section-title">Selected symptoms</h5>
                    <span class="gaia-dashboard__helper">Tap × to remove any symptom before saving.</span>
                  </div>
                </div>
                <div class="gaia-dashboard__symptom-selected">
                  ${selectedItems
                    .map((item) => {
                      const code = normalizeSymptomCode(item && (item.symptom_code || item.symptomCode));
                      const label = textOrEmpty(item && item.label) || titleFromKey(code);
                      return `
                        <span class="gaia-dashboard__symptom-selected-chip">
                          ${esc(label)}
                          <button type="button" data-symptom-select="${esc(code)}" aria-label="Remove ${esc(label)}">×</button>
                        </span>
                      `;
                    })
                    .join("")}
                </div>
              </section>
            `
            : ""
        }
        <section class="gaia-dashboard__symptom-section">
          <div class="gaia-dashboard__symptom-section-head">
            <div class="gaia-dashboard__symptom-section-copy">
              <h5 class="gaia-dashboard__symptom-section-title">All symptom options</h5>
              <span class="gaia-dashboard__helper">${query ? `Showing results for “${picker.query}”.` : "Use the full list when the suggested set is too narrow."}</span>
            </div>
          </div>
          ${
            remaining.length
              ? `
                <div class="gaia-dashboard__symptom-grid">
                  ${remaining
                    .map((item) =>
                      renderOptionButton(
                        normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)),
                        textOrEmpty(item && item.label) || titleFromKey(item && (item.symptom_code || item.symptomCode)),
                        textOrEmpty(item && item.description)
                      )
                    )
                    .join("")}
                </div>
              `
              : `<div class="gaia-dashboard__symptom-empty">${query ? "No symptoms match that search yet." : "No symptom options are available right now."}</div>`
          }
        </section>
        ${
          picker && picker.status
            ? `<div class="gaia-dashboard__muted" data-modal-status>${esc(picker.status)}</div>`
            : '<div class="gaia-dashboard__muted" data-modal-status></div>'
        }
        <div class="gaia-dashboard__modal-actions">
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="gaia-dashboard__btn" type="button" data-symptom-submit="1"${selectedCount ? "" : " disabled"}${picker && picker.submitting ? " disabled" : ""}>
              ${picker && picker.submitting ? "Logging..." : selectedCount > 1 ? `Log ${selectedCount} symptoms` : "Log symptom"}
            </button>
            <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-symptom-clear="1"${selectedCount ? "" : " disabled"}>Clear</button>
          </div>
          <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-modal-close="1">Close</button>
        </div>
      </div>
    `;
  };

  const ensureSymptomCodesLoaded = async (state) => {
    const existing = extractSymptomCodeCatalog(state && state.member ? state.member.symptomCodes : null);
    if (existing.length) return existing;
    const token = state && state.authCtx ? state.authCtx.token : "";
    if (!token) throw new Error("Sign in again to load symptom options.");
    state.member.symptomCodes = await fetchSymptomCodes(token);
    return extractSymptomCodeCatalog(state.member.symptomCodes);
  };

  const ensureProfilePreferencesLoaded = async (state) => {
    const existing = extractProfilePreferences(state && state.member ? state.member.profilePreferences : null);
    if (existing && typeof existing === "object") return existing;
    const token = state && state.authCtx ? state.authCtx.token : "";
    if (!token) throw new Error("Sign in again to load your settings.");
    state.member.profilePreferences = await fetchJson(routeFor("profilePreferences"), token);
    return extractProfilePreferences(state.member.profilePreferences) || {};
  };

  const ensureNotificationPreferencesLoaded = async (state) => {
    const existing = extractNotificationPreferences(state && state.member ? state.member.notifications : null);
    if (existing && typeof existing === "object") return existing;
    const token = state && state.authCtx ? state.authCtx.token : "";
    if (!token) throw new Error("Sign in again to load your notification settings.");
    state.member.notifications = await fetchJson(routeFor("notifications"), token);
    return extractNotificationPreferences(state.member.notifications) || {};
  };

  const openSymptomPicker = async (root, state, options = {}) => {
    state.ui.symptomPicker = {
      title: textOrEmpty(options.title) || "Log symptoms",
      suggestedCodes: dedupeStrings(maybeArray(options.suggestedCodes).map(normalizeSymptomCode), normalizeSymptomCode),
      selectedCodes: dedupeStrings(maybeArray(options.selectedCodes).map(normalizeSymptomCode), normalizeSymptomCode),
      query: "",
      submitting: false,
      status: "Loading symptom options...",
    };
    openModal(root, renderSymptomPickerModal(state));
    try {
      await Promise.all([
        ensureSymptomCodesLoaded(state),
        ensureProfilePreferencesLoaded(state).catch(() => ({})),
      ]);
      state.ui.symptomPicker.status = "";
      openModal(root, renderSymptomPickerModal(state));
    } catch (err) {
      state.ui.symptomPicker.status = err && err.message ? err.message : "Could not load symptom options.";
      openModal(root, renderSymptomPickerModal(state));
    }
  };

  const toggleSymptomPickerSelection = (root, state, code) => {
    if (!state.ui.symptomPicker) return;
    const selected = new Set(dedupeStrings(state.ui.symptomPicker.selectedCodes, normalizeSymptomCode).map(normalizeSymptomCode));
    const normalized = normalizeSymptomCode(code);
    if (!normalized) return;
    if (selected.has(normalized)) {
      selected.delete(normalized);
    } else {
      selected.add(normalized);
    }
    state.ui.symptomPicker.selectedCodes = Array.from(selected);
    openModal(root, renderSymptomPickerModal(state));
  };

  const updateSymptomPickerQuery = (root, state, query) => {
    if (!state.ui.symptomPicker) return;
    state.ui.symptomPicker.query = textOrEmpty(query);
    openModal(root, renderSymptomPickerModal(state));
  };

  const clearSymptomPickerSelection = (root, state) => {
    if (!state.ui.symptomPicker) return;
    state.ui.symptomPicker.selectedCodes = [];
    openModal(root, renderSymptomPickerModal(state));
  };

  const submitSymptomPicker = async (root, state) => {
    if (!state.ui.symptomPicker || state.ui.symptomPicker.submitting) return;
    const selectedCodes = dedupeStrings(state.ui.symptomPicker.selectedCodes, normalizeSymptomCode).map(normalizeSymptomCode);
    if (!selectedCodes.length) {
      state.ui.symptomPicker.status = "Choose at least one symptom.";
      openModal(root, renderSymptomPickerModal(state));
      return;
    }
    state.ui.symptomPicker.submitting = true;
    state.ui.symptomPicker.status = selectedCodes.length > 1 ? `Logging ${selectedCodes.length} symptoms...` : "Logging symptom...";
    openModal(root, renderSymptomPickerModal(state));
    try {
      await postSymptomEvents(state.authCtx && state.authCtx.token ? state.authCtx.token : "", selectedCodes);
      try {
        state.member.currentSymptoms = await fetchJsonWithParams(routeFor("currentSymptoms"), state.authCtx && state.authCtx.token ? state.authCtx.token : "", { window_hours: 12 });
      } catch (_) {}
      hideModal(root);
      state.ui.symptomPicker = null;
      renderMemberHub(root, state);
    } catch (err) {
      state.ui.symptomPicker.submitting = false;
      state.ui.symptomPicker.status = err && err.message ? err.message : "Could not log symptom.";
      openModal(root, renderSymptomPickerModal(state));
    }
  };

  const refreshCurrentSymptomsInBackground = async (root, state) => {
    try {
      state.member.currentSymptoms = await fetchJsonWithParams(
        routeFor("currentSymptoms"),
        state.authCtx && state.authCtx.token ? state.authCtx.token : "",
        { window_hours: 12 }
      );
      delete state.member.errors.currentSymptoms;
    } catch (err) {
      state.member.errors.currentSymptoms = err && err.message ? err.message : String(err);
    } finally {
      renderMemberHub(root, state);
    }
  };

  const commitCurrentSymptomStateChange = async (root, state, item, nextState) => {
    const episodeId = textOrEmpty(item && item.id);
    if (!episodeId || isCurrentSymptomPending(state, episodeId)) return;
    const normalizedState = normalizeCurrentSymptomState(nextState);
    const prompt = maybeObject(item && item.pending_follow_up);
    const previousSnapshot = cloneJson(state.member.currentSymptoms);
    const previousStatus = currentSymptomRowStatus(state, episodeId);
    setCurrentSymptomPending(state, episodeId, true);
    setCurrentSymptomRowStatus(state, episodeId, normalizedState === "resolved" ? "Saving resolution…" : "Saving update…", false);
    updateCurrentSymptomsSnapshot(state, (snapshot) => {
      const items = maybeArray(snapshot.items);
      const index = items.findIndex((row) => textOrEmpty(row && row.id) === episodeId);
      if (index < 0) return;
      if (normalizedState === "resolved") {
        items.splice(index, 1);
      } else {
        items[index] = {
          ...items[index],
          current_state: normalizedState,
          current_context_badge: normalizedState === "improving" ? "Trending better" : items[index].current_context_badge,
          pending_follow_up: null,
          last_interaction_at: new Date().toISOString(),
        };
      }
      snapshot.items = items;
    });
    renderMemberHub(root, state);
    try {
      const token = state.authCtx && state.authCtx.token ? state.authCtx.token : "";
      let response;
      if (prompt && textOrEmpty(prompt.id)) {
        response = await respondCurrentSymptomFollowUp(token, prompt.id, {
          state: normalizedState,
          ts_utc: new Date().toISOString(),
        });
      } else {
        response = await updateCurrentSymptomState(token, episodeId, {
          state: normalizedState,
          ts_utc: new Date().toISOString(),
        });
      }
      if (response && response.ok === false) {
        throw new Error(response.friendly_error || response.error || "Could not update symptom.");
      }
      const payload = extractEnvelopeData(response);
      if (prompt && payload && typeof payload === "object" && payload.episode) {
        upsertCurrentSymptomItem(state, payload.episode);
      } else if (payload && typeof payload === "object") {
        upsertCurrentSymptomItem(state, payload);
      }
      setCurrentSymptomRowStatus(
        state,
        episodeId,
        normalizedState === "resolved"
          ? `${textOrEmpty(item && item.label) || "Symptom"} resolved.`
          : `${textOrEmpty(item && item.label) || "Symptom"} updated.`,
        false
      );
      delete state.member.errors.currentSymptoms;
      renderMemberHub(root, state);
      refreshCurrentSymptomsInBackground(root, state);
    } catch (err) {
      state.member.currentSymptoms = previousSnapshot;
      if (previousStatus && previousStatus.message) {
        setCurrentSymptomRowStatus(state, episodeId, previousStatus.message, !!previousStatus.isError);
      } else {
        setCurrentSymptomRowStatus(
          state,
          episodeId,
          err && err.message ? err.message : "Could not update symptom.",
          true
        );
      }
      renderMemberHub(root, state);
    } finally {
      setCurrentSymptomPending(state, episodeId, false);
      renderMemberHub(root, state);
    }
  };

  const moveCurrentSymptomFollowUp = async (root, state, item, action) => {
    const episodeId = textOrEmpty(item && item.id);
    const prompt = maybeObject(item && item.pending_follow_up);
    if (!episodeId || !prompt || !textOrEmpty(prompt.id) || isCurrentSymptomPending(state, episodeId)) return;
    const previousSnapshot = cloneJson(state.member.currentSymptoms);
    setCurrentSymptomPending(state, episodeId, true);
    setCurrentSymptomRowStatus(
      state,
      episodeId,
      action === "dismiss" ? "Dismissing follow-up…" : "Moving follow-up later…",
      false
    );
    updateCurrentSymptomsSnapshot(state, (snapshot) => {
      const items = maybeArray(snapshot.items);
      const index = items.findIndex((row) => textOrEmpty(row && row.id) === episodeId);
      if (index < 0) return;
      items[index] = {
        ...items[index],
        pending_follow_up: null,
        last_interaction_at: new Date().toISOString(),
      };
      snapshot.items = items;
    });
    renderMemberHub(root, state);
    try {
      const response = await dismissCurrentSymptomFollowUp(
        state.authCtx && state.authCtx.token ? state.authCtx.token : "",
        prompt.id,
        action === "dismiss" ? { action: "dismiss" } : { action: "snooze", snooze_hours: 12 }
      );
      if (response && response.ok === false) {
        throw new Error(response.friendly_error || response.error || "Could not update follow-up.");
      }
      setCurrentSymptomRowStatus(
        state,
        episodeId,
        action === "dismiss" ? "Follow-up dismissed." : "Follow-up moved later.",
        false
      );
      delete state.member.errors.currentSymptoms;
      renderMemberHub(root, state);
      refreshCurrentSymptomsInBackground(root, state);
    } catch (err) {
      state.member.currentSymptoms = previousSnapshot;
      setCurrentSymptomRowStatus(
        state,
        episodeId,
        err && err.message ? err.message : "Could not update follow-up.",
        true
      );
      renderMemberHub(root, state);
    } finally {
      setCurrentSymptomPending(state, episodeId, false);
      renderMemberHub(root, state);
    }
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
          if (state.ui) state.ui.symptomPicker = null;
          hideModal(root);
          return;
        }
        const pickerBtn = target.closest("[data-open-symptom-picker]");
        if (pickerBtn) {
          let prefill = [];
          try {
            prefill = JSON.parse(pickerBtn.getAttribute("data-prefill") || "[]");
          } catch (_) {
            prefill = [];
          }
          await openSymptomPicker(root, state, {
            title: pickerBtn.getAttribute("data-picker-title") || "Log symptoms",
            suggestedCodes: prefill,
          });
          return;
        }
        const symptomSelect = target.closest("[data-symptom-select]");
        if (symptomSelect) {
          toggleSymptomPickerSelection(root, state, symptomSelect.getAttribute("data-symptom-select"));
          return;
        }
        const symptomClear = target.closest("[data-symptom-clear]");
        if (symptomClear) {
          clearSymptomPickerSelection(root, state);
          return;
        }
        const symptomSubmit = target.closest("[data-symptom-submit]");
        if (symptomSubmit) {
          await submitSymptomPicker(root, state);
          return;
        }
        const modalDriver = target.closest("[data-driver-key]");
        if (modalDriver) {
          const key = modalDriver.getAttribute("data-driver-key");
          const entry = key ? modalDrivers[key] : null;
          if (entry) {
            openModal(root, renderContextModal(entry));
          }
          return;
        }
        const allDriversBtn = target.closest("[data-open-all-drivers-modal]");
        if (allDriversBtn) {
          openModal(root, renderAllDriversModal(payload, state.member && state.member.drivers));
          return;
        }
      });
      modalNode.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        const search = target.closest("[data-symptom-search]");
        if (!search) return;
        updateSymptomPickerQuery(root, state, search.value || "");
      });
    }

    const rerender = () => renderMemberHub(root, state);
    syncMissionMobileNavPortal(root, state, rerender);

    const signOutBtn = root.querySelector("[data-gaia-signout]");
    if (signOutBtn && state.authCtx && typeof state.authCtx.onSignOut === "function") {
      signOutBtn.addEventListener("click", () => {
        void state.authCtx.onSignOut();
      });
    }
    const accountPreflightBtn = root.querySelector("[data-gaia-account-preflight]");
    if (accountPreflightBtn) {
      accountPreflightBtn.addEventListener("click", () => {
        void runAccountDeletePreflight(root, state);
      });
    }
    const deleteAccountBtn = root.querySelector("[data-gaia-delete-account]");
    if (deleteAccountBtn) {
      deleteAccountBtn.addEventListener("click", () => {
        void deleteMemberAccount(root, state);
      });
    }
    const switchBtn = root.querySelector("[data-gaia-switch]");
    if (switchBtn && state.authCtx && typeof state.authCtx.onSwitch === "function") {
      switchBtn.addEventListener("click", state.authCtx.onSwitch);
    }

    root.querySelectorAll("[data-tab-target]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.activeTab = normalizeTabKey(node.getAttribute("data-tab-target"));
        if (state.ui.activeTab === "guide") {
          void markGuideSeenRemotely(state);
        }
        writeTabHash(state.ui.activeTab);
        hydrateTabData(root, state, state.ui.activeTab);
        rerender();
      });
    });

    root.querySelectorAll("[data-tracked-stat-toggle]").forEach((node) => {
      node.addEventListener("click", async () => {
        const key = normalizeTrackedStatKey(node.getAttribute("data-tracked-stat-toggle"));
        if (!key) return;
        const current = profileTrackedStatKeys(extractProfilePreferences(state.member.profilePreferences));
        let next = current.slice();
        if (next.includes(key)) {
          next = next.filter((item) => item !== key);
        } else if (next.length < 5) {
          next.push(key);
        }
        if (!next.length) next = [...DEFAULT_TRACKED_STAT_KEYS];
        await saveProfilePreferences(root, state, { tracked_stat_keys: next });
      });
    });

    root.querySelectorAll("[data-smart-swap-toggle]").forEach((node) => {
      node.addEventListener("change", async () => {
        await saveProfilePreferences(root, state, {
          smart_stat_swap_enabled: !!node.checked,
        });
      });
    });

    root.querySelectorAll("[data-favorite-symptom-toggle]").forEach((node) => {
      node.addEventListener("click", async () => {
        const code = normalizeSymptomCode(node.getAttribute("data-favorite-symptom-toggle"));
        if (!code) return;
        const current = profileFavoriteSymptomCodes(extractProfilePreferences(state.member.profilePreferences));
        let next = current.slice();
        if (next.includes(code)) {
          next = next.filter((item) => item !== code);
        } else if (next.length < MAX_FAVORITE_SYMPTOM_CODES) {
          next.push(code);
        }
        await saveProfilePreferences(root, state, { favorite_symptom_codes: next });
      });
    });

    root.querySelectorAll("[data-notification-timezone]").forEach((node) => {
      node.addEventListener("change", async () => {
        await saveNotificationPreferences(root, state, {
          time_zone: normalizeTimeZoneIdentifier(node.value),
        });
      });
    });

    root.querySelectorAll("[data-notification-timezone-use-browser]").forEach((node) => {
      node.addEventListener("click", async () => {
        await saveNotificationPreferences(root, state, {
          time_zone: browserTimeZoneIdentifier(),
        });
      });
    });

    root.querySelectorAll("[data-guide-poll-choice]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.guidePollChoice = textOrEmpty(node.getAttribute("data-guide-poll-choice"));
        rerender();
      });
    });

    root.querySelectorAll("[data-open-symptom-picker]").forEach((node) => {
      node.addEventListener("click", async () => {
        let prefill = [];
        try {
          prefill = JSON.parse(node.getAttribute("data-prefill") || "[]");
        } catch (_) {
          prefill = [];
        }
        await openSymptomPicker(root, state, {
          title: node.getAttribute("data-picker-title") || "Log symptoms",
          suggestedCodes: prefill,
        });
      });
    });

    root.querySelectorAll("[data-current-symptom-action]").forEach((node) => {
      node.addEventListener("click", async () => {
        const episodeId = textOrEmpty(node.getAttribute("data-current-symptom-episode"));
        const nextState = textOrEmpty(node.getAttribute("data-current-symptom-action"));
        const item = currentSymptomItemById(state, episodeId);
        if (!item) return;
        await commitCurrentSymptomStateChange(root, state, item, nextState);
      });
    });

    root.querySelectorAll("[data-current-symptom-followup-later]").forEach((node) => {
      node.addEventListener("click", async () => {
        const episodeId = textOrEmpty(node.getAttribute("data-current-symptom-followup-later"));
        const item = currentSymptomItemById(state, episodeId);
        if (!item) return;
        await moveCurrentSymptomFollowUp(root, state, item, "later");
      });
    });

    root.querySelectorAll("[data-current-symptom-followup-dismiss]").forEach((node) => {
      node.addEventListener("click", async () => {
        const episodeId = textOrEmpty(node.getAttribute("data-current-symptom-followup-dismiss"));
        const item = currentSymptomItemById(state, episodeId);
        if (!item) return;
        await moveCurrentSymptomFollowUp(root, state, item, "dismiss");
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
        const pickerBtn = target.closest("[data-open-symptom-picker]");
        if (pickerBtn) {
          const legacyState = root.__gaiaLegacyState || {
            member: { symptomCodes: null, currentSymptoms: null },
            authCtx,
            ui: { symptomPicker: null },
          };
          root.__gaiaLegacyState = legacyState;
          let prefill = [];
          try {
            prefill = JSON.parse(pickerBtn.getAttribute("data-prefill") || "[]");
          } catch (_) {
            prefill = [];
          }
          await openSymptomPicker(root, legacyState, {
            title: pickerBtn.getAttribute("data-picker-title") || "Log symptoms",
            suggestedCodes: prefill,
          });
          return;
        }
        const symptomSelect = target.closest("[data-symptom-select]");
        if (symptomSelect) {
          const legacyState = root.__gaiaLegacyState;
          if (!legacyState) return;
          toggleSymptomPickerSelection(root, legacyState, symptomSelect.getAttribute("data-symptom-select"));
          return;
        }
        const symptomClear = target.closest("[data-symptom-clear]");
        if (symptomClear) {
          const legacyState = root.__gaiaLegacyState;
          if (!legacyState) return;
          clearSymptomPickerSelection(root, legacyState);
          return;
        }
        const symptomSubmit = target.closest("[data-symptom-submit]");
        if (symptomSubmit) {
          const legacyState = root.__gaiaLegacyState;
          if (!legacyState) return;
          await submitSymptomPicker(root, legacyState);
        }
      });
      modalNode.addEventListener("input", (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        const search = target.closest("[data-symptom-search]");
        if (!search) return;
        const legacyState = root.__gaiaLegacyState;
        if (!legacyState) return;
        updateSymptomPickerQuery(root, legacyState, search.value || "");
      });
    }

    const signOutBtn = root.querySelector("[data-gaia-signout]");
    if (signOutBtn && authCtx && typeof authCtx.onSignOut === "function") {
        signOutBtn.addEventListener("click", () => {
          void authCtx.onSignOut();
        });
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

  const MEMBER_TAB_ORDER = ["mission", "drivers", "body", "patterns", "outlook", "guide", "settings"];

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

  const maybeObject = (value) => (value && typeof value === "object" && !Array.isArray(value) ? value : null);

  const titleFromKey = (value) =>
    textOrEmpty(value)
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (match) => match.toUpperCase());

  const guideSeenStorageKey = (state) => {
    const identity = textOrEmpty(state && state.authCtx && state.authCtx.email).toLowerCase() || "anon";
    return `gaia.guide.last_seen_signature.${identity}`;
  };

  const guideStatePayload = (state) => maybeObject(state && state.dashboard && state.dashboard.guide_state);

  const readGuideSeenSignature = (state) => {
    try {
      return window.localStorage.getItem(guideSeenStorageKey(state)) || "";
    } catch (_) {
      return "";
    }
  };

  const writeGuideSeenSignature = (state) => {
    const signature = guideStateSignature(state);
    try {
      if (signature) {
        window.localStorage.setItem(guideSeenStorageKey(state), signature);
      } else {
        window.localStorage.removeItem(guideSeenStorageKey(state));
      }
    } catch (_) {}
  };

  const markGuideSeenRemotely = async (state) => {
    const signature = guideStateSignature(state);
    if (!signature) return;
    writeGuideSeenSignature(state);
    if (state.dashboard) {
      state.dashboard.guide_state = {
        ...(guideStatePayload(state) || {}),
        signature,
        has_unseen: false,
        last_viewed_signature: signature,
      };
    }
    const token = state && state.authCtx ? state.authCtx.token : "";
    const url = routeFor("guideSeen");
    if (!token || !url) return;
    try {
      const payload = await postJson(url, token, { signature });
      const guideState = maybeObject(payload && payload.guide_state);
      if (state.dashboard && guideState) {
        state.dashboard.guide_state = guideState;
      }
    } catch (_) {}
  };

  const isOutlookHealthRelevantDriver = (driver) => {
    const key = textOrEmpty(driver && driver.key).toLowerCase();
    const label = textOrEmpty(driver && driver.label).toLowerCase();
    const detail = textOrEmpty(driver && driver.detail).toLowerCase();
    if (key === "radio" || key === "radio_blackout" || key === "radio-blackout") return false;
    return !label.includes("radio blackout") && !detail.includes("radio blackout");
  };

  const guideStateSignature = (state) => {
    const remoteState = guideStatePayload(state);
    if (remoteState && textOrEmpty(remoteState.signature)) {
      return textOrEmpty(remoteState.signature);
    }
    const currentSymptoms = extractCurrentSymptoms(state && state.member && state.member.currentSymptoms);
    const followUp = firstPendingFollowUp(currentSymptoms);
    const dailyCheckIn = extractDailyCheckIn(state && state.member && state.member.dailyCheckIn);
    const prompt = dailyCheckIn && dailyCheckIn.prompt ? dailyCheckIn.prompt : null;
    const earthscopeSummary = resolveEarthscopeSummary(
      state && state.dashboard && state.dashboard.earthscopeSummary,
      (state && state.dashboard && (state.dashboard.memberPost || state.dashboard.publicPost)) || null,
      (state && state.dashboard && state.dashboard.driversCompact) || []
    );
    const parts = [];
    if (prompt && textOrEmpty(prompt.status).toLowerCase() !== "answered") {
      parts.push(`checkin:${textOrEmpty(prompt.id)}:${textOrEmpty(prompt.day)}:${textOrEmpty(prompt.status) || "ready"}`);
    }
    if (followUp) {
      const followUpPrompt = maybeObject(followUp.pending_follow_up);
      parts.push(
        `followup:${textOrEmpty(followUpPrompt && followUpPrompt.id)}:${textOrEmpty(followUp && followUp.id)}:${textOrEmpty(followUpPrompt && followUpPrompt.status) || "pending"}`
      );
    }
    if (earthscopeSummary) {
      parts.push(`summary:${earthscopeSummary}`);
    }
    const supportItems = supportItemsFromDashboard(state && state.dashboard);
    if (supportItems.length) {
      parts.push(
        `support:${supportItems
          .map((item) =>
            [
              textOrEmpty(item && item.key),
              textOrEmpty(item && item.badge),
              textOrEmpty(item && item.title),
              textOrEmpty(item && item.message),
            ]
              .filter(Boolean)
              .join(":")
          )
          .join("~")}`
      );
    }
    return parts.join("|");
  };

  const guideHasUnseen = (state) => {
    const remoteState = guideStatePayload(state);
    if (remoteState && typeof remoteState.has_unseen === "boolean") {
      return remoteState.has_unseen;
    }
    const signature = guideStateSignature(state);
    if (!signature) return false;
    return readGuideSeenSignature(state) !== signature;
  };

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

  const extractEnvelopeData = (payload) => {
    const direct = maybeObject(payload);
    if (!direct) return null;
    if (Object.prototype.hasOwnProperty.call(direct, "data")) {
      const data = direct.data;
      if (data && typeof data === "object") return data;
      return null;
    }
    if (
      Object.prototype.hasOwnProperty.call(direct, "ok") ||
      Object.prototype.hasOwnProperty.call(direct, "error") ||
      Object.prototype.hasOwnProperty.call(direct, "friendly_error")
    ) {
      return null;
    }
    return direct;
  };

  const extractDailyCheckIn = (payload) => extractEnvelopeData(payload);

  const extractCurrentSymptoms = (payload) => extractEnvelopeData(payload);

  const extractFeatures = (payload) => extractEnvelopeData(payload);

  const extractProfilePreferences = (payload) => {
    const direct = maybeObject(payload);
    if (!direct) return null;
    if (maybeObject(direct.preferences)) return direct.preferences;
    return extractEnvelopeData(payload);
  };

  const extractNotificationPreferences = (payload) => {
    const direct = maybeObject(payload);
    if (!direct) return null;
    if (maybeObject(direct.preferences)) return direct.preferences;
    return extractEnvelopeData(payload);
  };

  const readPathValue = (source, path) =>
    textOrEmpty(path)
      .split(".")
      .reduce((acc, segment) => (acc && typeof acc === "object" ? acc[segment] : null), source);

  const firstDefinedValue = (source, paths) => {
    for (const path of maybeArray(paths)) {
      const value = readPathValue(source, path);
      if (value != null && value !== "") return value;
    }
    return null;
  };

  const featureValue = (features, ...paths) => firstDefinedValue(features, paths);

  const firstPendingFollowUp = (currentSymptoms) =>
    maybeArray(currentSymptoms && currentSymptoms.items).find(
      (item) => item && item.pending_follow_up && typeof item.pending_follow_up === "object"
    ) || null;

  const supportItemsFromDashboard = (dashboard) =>
    maybeArray(dashboard && (dashboard.support_items || dashboard.supportItems))
      .filter((item) => item && typeof item === "object")
      .slice(0, 3);

  const cloneJson = (value) => {
    if (value == null) return value;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (_) {
      return value;
    }
  };

  const normalizeCurrentSymptomState = (value) => {
    const token = textOrEmpty(value).toLowerCase();
    return ["new", "ongoing", "improving", "worse", "resolved"].includes(token) ? token : "new";
  };

  const currentSymptomRowStatus = (state, episodeId) =>
    state &&
    state.ui &&
    state.ui.currentSymptomStatusById &&
    state.ui.currentSymptomStatusById[episodeId]
      ? state.ui.currentSymptomStatusById[episodeId]
      : null;

  const setCurrentSymptomRowStatus = (state, episodeId, message, isError = false) => {
    if (!state.ui.currentSymptomStatusById) state.ui.currentSymptomStatusById = {};
    if (!message) {
      delete state.ui.currentSymptomStatusById[episodeId];
      return;
    }
    state.ui.currentSymptomStatusById[episodeId] = { message, isError: !!isError };
  };

  const setCurrentSymptomPending = (state, episodeId, pending) => {
    if (!state.ui.currentSymptomPendingById) state.ui.currentSymptomPendingById = {};
    if (pending) {
      state.ui.currentSymptomPendingById[episodeId] = true;
    } else {
      delete state.ui.currentSymptomPendingById[episodeId];
    }
  };

  const isCurrentSymptomPending = (state, episodeId) =>
    !!(state && state.ui && state.ui.currentSymptomPendingById && state.ui.currentSymptomPendingById[episodeId]);

  const currentSymptomItemById = (state, episodeId) =>
    maybeArray(extractCurrentSymptoms(state && state.member && state.member.currentSymptoms)?.items).find(
      (item) => textOrEmpty(item && item.id) === textOrEmpty(episodeId)
    ) || null;

  const currentSymptomStateLabel = (value) => {
    const normalized = normalizeCurrentSymptomState(value);
    if (normalized === "improving") return "Improving";
    if (normalized === "worse") return "Worse";
    if (normalized === "resolved") return "Resolved";
    return "Ongoing";
  };

  const currentSymptomToneClass = (value) => {
    const normalized = normalizeCurrentSymptomState(value);
    if (normalized === "improving") return "is-positive";
    if (normalized === "worse") return "is-warning";
    if (normalized === "resolved") return "is-danger";
    return "";
  };

  const renderCurrentSymptomRow = (state, item) => {
    const episodeId = textOrEmpty(item && item.id);
    const normalizedState = normalizeCurrentSymptomState(item && item.current_state);
    const status = currentSymptomRowStatus(state, episodeId);
    const pending = isCurrentSymptomPending(state, episodeId);
    const prompt = maybeObject(item && item.pending_follow_up);
    const primaryDriver = maybeArray(item && item.likely_drivers)[0];
    const contextLine =
      textOrEmpty(prompt && prompt.question_text) ||
      textOrEmpty(item && item.note_preview) ||
      textOrEmpty(primaryDriver && (primaryDriver.pattern_hint || primaryDriver.relation || primaryDriver.display)) ||
      "Mark whether this is holding steady, easing, or getting heavier.";
    const severity = Number(item && (item.severity ?? item.original_severity));
    const severityLine = Number.isFinite(severity) ? `Severity ${Math.round(severity)}/10` : "Recently logged";
    const timestampLine = formatIsoDate(
      textOrEmpty(item && item.last_interaction_at) || textOrEmpty(item && item.logged_at)
    );
    const renderAction = (nextState, label) => {
      const selected =
        nextState === "ongoing"
          ? normalizedState === "ongoing" || normalizedState === "new"
          : normalizedState === nextState;
      const toneClass = currentSymptomToneClass(nextState);
      return `
        <button
          class="gaia-dashboard__current-symptom-btn${selected ? " is-selected" : ""}${toneClass ? ` ${toneClass}` : ""}"
          type="button"
          data-current-symptom-action="${esc(nextState)}"
          data-current-symptom-episode="${esc(episodeId)}"
          ${pending ? " disabled" : ""}
        >
          ${esc(label)}
        </button>
      `;
    };

    return `
      <article class="gaia-dashboard__current-symptom-row${pending ? " is-pending" : ""}">
        <div class="gaia-dashboard__current-symptom-head">
          <div class="gaia-dashboard__current-symptom-copy">
            <strong>${esc(textOrEmpty(item && item.label) || "Symptom")}</strong>
            <span>${esc(`${severityLine} • ${timestampLine}`)}</span>
            <span>${esc(contextLine)}</span>
          </div>
          <span class="${pillClass(normalizedState === "new" ? "watch" : normalizedState === "ongoing" ? "watch" : normalizedState)}">
            ${esc(currentSymptomStateLabel(normalizedState))}
          </span>
        </div>
        <div class="gaia-dashboard__current-symptom-actions">
          ${renderAction("ongoing", "Still active")}
          ${renderAction("improving", "Improving")}
          ${renderAction("worse", "Worse")}
          ${renderAction("resolved", "Resolved")}
        </div>
        ${
          prompt && textOrEmpty(prompt.id)
            ? `
              <div class="gaia-dashboard__current-symptom-subactions">
                <button
                  class="gaia-dashboard__current-symptom-btn"
                  type="button"
                  data-current-symptom-followup-later="${esc(episodeId)}"
                  ${pending ? " disabled" : ""}
                >
                  Later
                </button>
                <button
                  class="gaia-dashboard__current-symptom-btn"
                  type="button"
                  data-current-symptom-followup-dismiss="${esc(episodeId)}"
                  ${pending ? " disabled" : ""}
                >
                  Dismiss
                </button>
              </div>
            `
            : ""
        }
        ${
          status && textOrEmpty(status.message)
            ? `<div class="gaia-dashboard__current-symptom-feedback${status.isError ? " is-error" : ""}">${esc(status.message)}</div>`
            : ""
        }
      </article>
    `;
  };

  const renderGuideSupportCard = (state) => {
    const items = supportItemsFromDashboard(state && state.dashboard);
    if (!items.length) return "";
    const bullets = guideSupportActions(state, items);
    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <div>
            <span class="gaia-dashboard__eyebrow">Support right now</span>
            <h4 class="gaia-dashboard__card-title">${esc(textOrEmpty(items[0].title) || "A steadier way through it")}</h4>
          </div>
          ${
            textOrEmpty(items[0].badge)
              ? `<span class="${pillClass(textOrEmpty(items[0].tone) || "watch")}">${esc(items[0].badge)}</span>`
              : ""
          }
        </div>
        <p class="gaia-dashboard__card-copy">${esc(guideSupportIntro(state, items))}</p>
        ${
          bullets.length
            ? `<div class="gaia-dashboard__guide-bullet-list">${bullets
                .map((item) => `<div class="gaia-dashboard__guide-bullet-row">${esc(item)}</div>`)
                .join("")}</div>`
            : ""
        }
        <div class="gaia-dashboard__section-actions">
          <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="body">Open Body</button>
          <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="drivers">Open Drivers</button>
        </div>
      </article>
    `;
  };

  const rebuildCurrentSymptomsSummary = (snapshot) => {
    if (!snapshot || typeof snapshot !== "object") return snapshot;
    const items = maybeArray(snapshot.items).filter(Boolean);
    const summary = {
      ...(maybeObject(snapshot.summary) || {}),
      active_count: items.length,
      new_count: items.filter((item) => normalizeCurrentSymptomState(item && item.current_state) === "new").length,
      ongoing_count: items.filter((item) => normalizeCurrentSymptomState(item && item.current_state) === "ongoing").length,
      improving_count: items.filter((item) => normalizeCurrentSymptomState(item && item.current_state) === "improving").length,
      worse_count: items.filter((item) => normalizeCurrentSymptomState(item && item.current_state) === "worse").length,
      follow_up_available: items.some((item) => item && item.pending_follow_up),
      last_updated_at: new Date().toISOString(),
    };
    snapshot.summary = summary;
    return snapshot;
  };

  const updateCurrentSymptomsSnapshot = (state, updater) => {
    const current = extractCurrentSymptoms(state && state.member && state.member.currentSymptoms);
    if (!current || typeof updater !== "function") return;
    const snapshot = cloneJson(current);
    updater(snapshot);
    rebuildCurrentSymptomsSummary(snapshot);
    if (state.member.currentSymptoms && typeof state.member.currentSymptoms === "object" && "data" in state.member.currentSymptoms) {
      state.member.currentSymptoms = {
        ...state.member.currentSymptoms,
        data: snapshot,
      };
    } else {
      state.member.currentSymptoms = snapshot;
    }
  };

  const upsertCurrentSymptomItem = (state, item) => {
    if (!item || typeof item !== "object") return;
    updateCurrentSymptomsSnapshot(state, (snapshot) => {
      const items = maybeArray(snapshot.items);
      const index = items.findIndex((row) => textOrEmpty(row && row.id) === textOrEmpty(item.id));
      if (normalizeCurrentSymptomState(item.current_state) === "resolved") {
        if (index >= 0) items.splice(index, 1);
      } else if (index >= 0) {
        items[index] = item;
      } else {
        items.unshift(item);
      }
      snapshot.items = items;
    });
  };

  const currentSymptomLabels = (currentSymptoms) =>
    maybeArray(currentSymptoms && currentSymptoms.items)
      .map((item) => textOrEmpty(item && item.label))
      .filter(Boolean);

  const profileTrackedStatKeys = (profilePreferences) =>
    normalizeTrackedStatKeys(profilePreferences && profilePreferences.tracked_stat_keys);

  const profileFavoriteSymptomCodes = (profilePreferences) =>
    normalizeFavoriteSymptomCodes(profilePreferences && profilePreferences.favorite_symptom_codes);

  const profileSmartSwapEnabled = (profilePreferences) =>
    profilePreferences && typeof profilePreferences.smart_stat_swap_enabled === "boolean"
      ? profilePreferences.smart_stat_swap_enabled
      : true;

  const healthStatCards = (features, profilePreferences) => {
    if (!features || typeof features !== "object") return [];
    const cards = [];
    const restingHrDelta = asNumber(featureValue(features, "resting_hr_baseline_delta", "restingHrBaselineDelta"));
    const respiratoryDelta = asNumber(featureValue(features, "respiratory_rate_baseline_delta", "respiratoryRateBaselineDelta"));
    const spo2 =
      asNumber(featureValue(features, "spo2_avg", "spo2Avg", "health.spo2_avg", "health.spo2Avg")) ||
      asNumber(featureValue(features, "spo2_avg_pct", "spo2AvgPct", "spo2_avg_percent", "spo2AvgPercent", "spo2_mean", "spo2Mean"));
    const steps = asNumber(featureValue(features, "steps_total", "stepsTotal"));
    const hrv = asNumber(featureValue(features, "hrv_avg", "hrvAvg", "hrv_sdnn", "hrvSdnn"));
    const tempDeviation = asNumber(featureValue(features, "temperature_deviation_baseline_delta", "temperatureDeviationBaselineDelta", "temperature_deviation", "temperatureDeviation"));
    const hrMin = asNumber(featureValue(features, "hr_min", "hrMin"));
    const hrMax = asNumber(featureValue(features, "hr_max", "hrMax"));
    const respiratoryAvg = asNumber(featureValue(features, "respiratory_rate_avg", "respiratoryRateAvg", "respiratory_rate_sleep_avg", "respiratoryRateSleepAvg"));
    const bpSys = asNumber(featureValue(features, "bp_sys_avg", "bpSysAvg"));
    const bpDia = asNumber(featureValue(features, "bp_dia_avg", "bpDiaAvg"));

    if (Number.isFinite(restingHrDelta)) {
      cards.push({
        key: "resting_hr",
        label: "Resting HR Δ",
        value: `${restingHrDelta > 0 ? "+" : ""}${restingHrDelta.toFixed(1)} bpm`,
        detail: restingHrDelta > 0 ? "above usual" : "below usual",
        salience: Math.max(0, Math.min(1, Math.abs(restingHrDelta) / 8)),
      });
    } else if (Number.isFinite(asNumber(featureValue(features, "resting_hr_avg", "restingHrAvg")))) {
      const restingHrAvg = asNumber(featureValue(features, "resting_hr_avg", "restingHrAvg"));
      cards.push({
        key: "resting_hr",
        label: "Resting HR",
        value: `${Math.round(restingHrAvg)} bpm`,
        detail: "daily average",
        salience: 0.16,
      });
    }
    if (Number.isFinite(respiratoryDelta)) {
      cards.push({
        key: "respiratory",
        label: "Respiratory Δ",
        value: `${respiratoryDelta > 0 ? "+" : ""}${respiratoryDelta.toFixed(1)} br/min`,
        detail: respiratoryDelta > 0 ? "above usual" : "below usual",
        salience: Math.max(0, Math.min(1, Math.abs(respiratoryDelta) / 3)),
      });
    } else if (Number.isFinite(respiratoryAvg)) {
      cards.push({ key: "respiratory", label: "Respiratory", value: `${respiratoryAvg.toFixed(1)} br/min`, detail: "daily average", salience: 0.16 });
    }
    if (Number.isFinite(spo2)) {
      cards.push({
        key: "spo2",
        label: "SpO₂",
        value: `${Math.round(spo2)}%`,
        detail: "daily average",
        salience: Math.max(0, Math.min(1, (96 - spo2) / 4)),
      });
    }
    if (Number.isFinite(hrv)) {
      cards.push({ key: "hrv", label: "HRV", value: `${Math.round(hrv)} ms`, detail: "daily average", salience: 0.12 });
    }
    if (Number.isFinite(tempDeviation)) {
      cards.push({
        key: "temperature",
        label: "Temp Δ",
        value: `${tempDeviation > 0 ? "+" : ""}${tempDeviation.toFixed(1)}°`,
        detail: tempDeviation > 0 ? "above usual" : "below usual",
        salience: Math.max(0, Math.min(1, Math.abs(tempDeviation) / 3)),
      });
    }
    if (Number.isFinite(steps)) {
      cards.push({ key: "steps", label: "Steps", value: `${Math.round(steps)}`, detail: "today", salience: 0.08 });
    }
    if (Number.isFinite(hrMin) || Number.isFinite(hrMax)) {
      cards.push({
        key: "heart_range",
        label: "Heart range",
        value: `${Number.isFinite(hrMin) ? Math.round(hrMin) : "—"}-${Number.isFinite(hrMax) ? Math.round(hrMax) : "—"} bpm`,
        detail: "today",
        salience: 0.06,
      });
    }
    if (Number.isFinite(bpSys) || Number.isFinite(bpDia)) {
      cards.push({
        key: "blood_pressure",
        label: "Blood pressure",
        value: `${Number.isFinite(bpSys) ? Math.round(bpSys) : "—"}/${Number.isFinite(bpDia) ? Math.round(bpDia) : "—"}`,
        detail: "average",
        salience: 0.06,
      });
    }

    const cardsByKey = new Map(cards.map((card) => [card.key, card]));
    const preferredOrder = [
      ...profileTrackedStatKeys(profilePreferences),
      ...DEFAULT_TRACKED_STAT_KEYS.filter((key) => !profileTrackedStatKeys(profilePreferences).includes(key)),
      ...TRACKED_STAT_OPTIONS.map((option) => option.key).filter((key) => !profileTrackedStatKeys(profilePreferences).includes(key)),
    ].filter((key, index, source) => source.indexOf(key) === index);
    const availableOrder = preferredOrder.filter((key) => cardsByKey.has(key));
    if (!availableOrder.length) return cards;

    const selectedKeys = availableOrder.slice(0, 4);
    const fifthPinned = availableOrder.slice(4, 5)[0];
    if (profileSmartSwapEnabled(profilePreferences)) {
      const dynamic = cards
        .filter((card) => !selectedKeys.includes(card.key) && Number(card.salience || 0) >= 0.55)
        .sort((left, right) => {
          if (left.salience === right.salience) {
            return preferredOrder.indexOf(left.key) - preferredOrder.indexOf(right.key);
          }
          return right.salience - left.salience;
        })[0];
      if (dynamic) {
        selectedKeys.push(dynamic.key);
      } else if (fifthPinned) {
        selectedKeys.push(fifthPinned);
      }
    } else if (fifthPinned) {
      selectedKeys.push(fifthPinned);
    }
    for (const key of availableOrder) {
      if (!selectedKeys.includes(key) && selectedKeys.length < 5) selectedKeys.push(key);
    }
    return selectedKeys.map((key) => cardsByKey.get(key)).filter(Boolean);
  };

  const sleepStageCards = (features) => {
    if (!features || typeof features !== "object") return [];
    return [
      { label: "REM", value: formatMinutesShort(featureValue(features, "rem_m", "remM", "sleep_rem_minutes", "sleepRemMinutes")) },
      { label: "Core", value: formatMinutesShort(featureValue(features, "core_m", "coreM", "sleep_core_minutes", "sleepCoreMinutes")) },
      { label: "Deep", value: formatMinutesShort(featureValue(features, "deep_m", "deepM", "sleep_deep_minutes", "sleepDeepMinutes")) },
      { label: "Awake", value: formatMinutesShort(featureValue(features, "awake_m", "awakeM", "sleep_awake_minutes", "sleepAwakeMinutes")) },
      { label: "In bed", value: formatMinutesShort(featureValue(features, "inbed_m", "inbedM")) },
    ].filter((item) => item.value !== "—");
  };

  const missionNavCard = (state, key, title, body) => `
    <button class="gaia-dashboard__nav-card${state.ui.activeTab === key ? " is-active" : ""}${key === "guide" && guideHasUnseen(state) ? " gaia-dashboard__nav-card--unseen" : ""}" type="button" data-tab-target="${esc(key)}">
      <div class="gaia-dashboard__nav-card-head">
        <strong>${esc(title)}</strong>
        ${key === "guide" && guideHasUnseen(state) ? '<span class="gaia-dashboard__nav-badge">New</span>' : ""}
      </div>
      <span>${esc(body)}</span>
    </button>
  `;

  const missionMobileNavItem = (state, key, label, icon) => `
    <button
      class="gaia-dashboard__mobile-tab${state.ui.activeTab === key ? " is-active" : ""}${key === "guide" && guideHasUnseen(state) ? " gaia-dashboard__mobile-tab--unseen" : ""}"
      type="button"
      data-tab-target="${esc(key)}"
      aria-label="${esc(label)}"
      title="${esc(label)}"
    >
      <span class="gaia-dashboard__mobile-tab-icon" aria-hidden="true">${icon}</span>
      <span class="gaia-dashboard__mobile-tab-label">${esc(label)}</span>
      ${key === "guide" && guideHasUnseen(state) ? '<span class="gaia-dashboard__mobile-tab-dot" aria-hidden="true"></span>' : ""}
    </button>
  `;

  const renderMissionMobileNav = (state) => `
    <nav class="gaia-dashboard__mobile-tabbar" aria-label="Mission Control">
      <div class="gaia-dashboard__mobile-tabbar-scroll">
        ${missionMobileNavItem(state, "mission", "Home", "⌂")}
        ${missionMobileNavItem(state, "drivers", "Drivers", "◌")}
        ${missionMobileNavItem(state, "body", "Body", "♡")}
        ${missionMobileNavItem(state, "patterns", "Patterns", "≈")}
        ${missionMobileNavItem(state, "outlook", "Outlook", "◔")}
        ${missionMobileNavItem(state, "guide", "Guide", "✦")}
        ${missionMobileNavItem(state, "settings", "Settings", "⚙")}
      </div>
    </nav>
  `;

  const mobileNavPortalKey = (root) => {
    if (!root.dataset.gaiaMobileNavPortalKey) {
      root.dataset.gaiaMobileNavPortalKey = `gaia-mobile-nav-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    return root.dataset.gaiaMobileNavPortalKey;
  };

  const removeMissionMobileNavPortal = (root) => {
    const key = root.dataset.gaiaMobileNavPortalKey;
    if (!key) return;
    document.querySelectorAll(`[data-gaia-mobile-nav-portal="${key}"]`).forEach((node) => node.remove());
  };

  const syncMissionMobileNavPortal = (root, state, rerender) => {
    const key = mobileNavPortalKey(root);
    let portal = document.querySelector(`[data-gaia-mobile-nav-portal="${key}"]`);
    if (!portal) {
      portal = document.createElement("div");
      portal.setAttribute("data-gaia-mobile-nav-portal", key);
      document.body.appendChild(portal);
    }
    portal.innerHTML = `${renderMissionStickyNav(state)}${renderMissionMobileNav(state)}`;
    portal.querySelectorAll("[data-tab-target]").forEach((node) => {
      node.addEventListener("click", () => {
        state.ui.activeTab = normalizeTabKey(node.getAttribute("data-tab-target"));
        if (state.ui.activeTab === "guide") {
          void markGuideSeenRemotely(state);
        }
        writeTabHash(state.ui.activeTab);
        hydrateTabData(root, state, state.ui.activeTab);
        rerender();
      });
    });
  };

  const missionStickyTab = (state, key, label) => `
    <button
      class="gaia-dashboard__sticky-tab${state.ui.activeTab === key ? " is-active" : ""}${key === "guide" && guideHasUnseen(state) ? " gaia-dashboard__sticky-tab--unseen" : ""}"
      type="button"
      data-tab-target="${esc(key)}"
    >
      ${esc(label)}
      ${key === "guide" && guideHasUnseen(state) ? '<span class="gaia-dashboard__sticky-tab-dot" aria-hidden="true"></span>' : ""}
    </button>
  `;

  const renderMissionStickyNav = (state) => `
    <nav class="gaia-dashboard__sticky-tabs" aria-label="Mission Control sections">
      <div class="gaia-dashboard__sticky-tabs-scroll">
        ${missionStickyTab(state, "mission", "Home")}
        ${missionStickyTab(state, "drivers", "Drivers")}
        ${missionStickyTab(state, "body", "Body")}
        ${missionStickyTab(state, "patterns", "Patterns")}
        ${missionStickyTab(state, "outlook", "Outlook")}
        ${missionStickyTab(state, "guide", "Guide")}
        ${missionStickyTab(state, "settings", "Settings")}
      </div>
    </nav>
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

    const drivers = maybeArray(window.topDrivers || window.top_drivers).filter(isOutlookHealthRelevantDriver);
    const primary = drivers[0] || null;
    const supporting = drivers.slice(1, 4).filter(isOutlookHealthRelevantDriver);
    const domains = maybeArray(window.likelyElevatedDomains || window.likely_elevated_domains).slice(0, 3);
    const driverStatCard = (driver, primaryCard = false) => `
      <div class="gaia-dashboard__outlook-signal-card">
        <div class="gaia-dashboard__outlook-signal-label">${esc(driver.label || driver.key || "Driver")}</div>
        <div class="gaia-dashboard__outlook-signal-value">${esc(primaryCard ? (driver.severity || "Watch") : formatDriverValue(driver))}</div>
      </div>
    `;

    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <h4 class="gaia-dashboard__card-title">${esc(label)}</h4>
          ${primary ? `<span class="${pillClass(primary.severity || "watch")}">${esc(primary.severity || "Watch")}</span>` : ""}
        </div>
        ${
          primary
            ? `
              <div>
                <div class="gaia-dashboard__mini-title">Main thing to watch</div>
                <div class="gaia-dashboard__outlook-signal-grid">
                  ${driverStatCard(primary, true)}
                </div>
              </div>
            `
            : ""
        }
        ${
          supporting.length
            ? `
              <div>
                <div class="gaia-dashboard__mini-title">Also contributing</div>
                <div class="gaia-dashboard__outlook-signal-grid">
                  ${supporting.map((driver) => driverStatCard(driver, false)).join("")}
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
                <div class="gaia-dashboard__outlook-domain-grid">
                  ${domains
                    .map(
                      (domain) => `
                        <div class="gaia-dashboard__outlook-domain">
                          <div class="gaia-dashboard__outlook-domain-head">
                            <strong>${esc(domain.label || titleFromKey(domain.key))}</strong>
                            <span class="${pillClass(domain.likelihood || "watch")}">${esc(domain.likelihood || "Watch")}</span>
                          </div>
                          ${domain.currentGauge != null ? `<p>${esc(`Gauge now ${Math.round(Number(domain.currentGauge))}`)}</p>` : ""}
                          ${
                            textOrEmpty(domain.topDriverLabel || domain.top_driver_label || domain.topDriverKey || domain.top_driver_key)
                              ? `<div class="gaia-dashboard__meta-row"><span class="gaia-dashboard__meta-chip">${esc(domain.topDriverLabel || domain.top_driver_label || titleFromKey(domain.topDriverKey || domain.top_driver_key))}</span></div>`
                              : ""
                          }
                        </div>
                      `
                    )
                    .join("")}
                </div>
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
      const followUpLabel = textOrEmpty(followUp.symptom_label || followUp.label).toLowerCase() || "this symptom";
      return {
        question: `Has ${followUpLabel} shifted since the last check?`,
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
    const dailyCheckInLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.dailyCheckIn);
    const dailyCheckInError = textOrEmpty(state.member.errors && state.member.errors.dailyCheckIn);
    const targetDay = textOrEmpty(dailyCheckIn && dailyCheckIn.target_day) || localDayISO();
    const entry = dailyCheckIn && dailyCheckIn.latest_entry ? dailyCheckIn.latest_entry : null;
    const completedToday = !!(entry && textOrEmpty(entry.day) === targetDay);
    const prompt = dailyCheckIn && dailyCheckIn.prompt ? dailyCheckIn.prompt : null;
    ensureCheckInFormState(state);
    const form = state.ui.checkInForm;
    const showForm = state.ui.checkInEditing || (!completedToday && !!prompt);
    const exposureSet = new Set(maybeArray(form && form.exposures));
    const title = dailyCheckInLoading && !dailyCheckIn
      ? "Checking for today's prompt"
      : completedToday
        ? "Completed for today"
        : prompt
          ? "Check in with the day"
          : dailyCheckInError
            ? "Check-in temporarily unavailable"
            : "Nothing waiting right now";
    const copy = dailyCheckInLoading && !dailyCheckIn
      ? "Loading your daily check-in state."
      : completedToday
        ? `Completed for ${formatDayLabel(targetDay)}${maybeArray(entry && entry.exposures).length ? `. Also logged: ${maybeArray(entry.exposures).map(titleFromKey).join(", ")}` : "."}`
        : dailyCheckInError && !prompt
          ? "The daily check-in service is having trouble right now. Try again in a moment."
          : sentence(prompt && prompt.question_text, "Use the full check-in to keep the body read current.");

    return `
      <article class="gaia-dashboard__card">
        <div class="gaia-dashboard__card-title-row">
          <div>
            <span class="gaia-dashboard__eyebrow">${esc(location === "guide" ? "Daily check-in" : "Body check-in")}</span>
            <h4 class="gaia-dashboard__card-title">${esc(title)}</h4>
          </div>
          ${
            completedToday
              ? `<span class="${pillClass("low")}">Done</span>`
              : prompt
                ? `<span class="${pillClass("watch")}">Ready</span>`
                : ""
          }
        </div>
        <p class="gaia-dashboard__card-copy">${esc(copy)}</p>
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
                    <div class="gaia-dashboard__exposure-grid">
                      ${DAILY_CHECKIN_EXPOSURES
                        .map(
                          ([key, label]) => `
                            <label class="gaia-dashboard__toggle-chip">
                              <input type="checkbox" name="exposures" value="${esc(key)}"${exposureSet.has(key) ? " checked" : ""} />
                              <span>${esc(label)}</span>
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

  const missionOutlookFallbackSummary = (state, fallbackSummary) => {
    const trimmedFallback = textOrEmpty(fallbackSummary);
    const drivers = maybeArray(state && state.dashboard && state.dashboard.drivers).filter(isOutlookHealthRelevantDriver);
    const primary = drivers[0] || null;
    const secondary = drivers[1] || null;
    if (primary && secondary) {
      return `${primary.label || titleFromKey(primary.key)} looks most active right now, with ${secondary.label || titleFromKey(secondary.key)} also in the mix.`;
    }
    if (primary) {
      return `${primary.label || titleFromKey(primary.key)} looks most active right now.`;
    }
    return trimmedFallback || "Your near-future read is still filling in.";
  };

  const renderMissionOutlookCard = (state, fallbackSummary) => {
    const outlook = state.member.outlook && typeof state.member.outlook === "object" ? state.member.outlook : {};
    const window24 = maybeObject(outlook.next24h || outlook.next_24h);
    const outlookLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.outlook);
    const outlookError = textOrEmpty(state.member.errors && state.member.errors.outlook);
    const drivers = maybeArray(window24 && (window24.topDrivers || window24.top_drivers)).filter(isOutlookHealthRelevantDriver);
    const primary = drivers[0] || null;
    const supportLine = textOrEmpty(window24 && (window24.supportLine || window24.support_line));
    const summary = textOrEmpty(window24 && window24.summary) || missionOutlookFallbackSummary(state, fallbackSummary);

    return `
      <div class="gaia-dashboard__earthscope gaia-dashboard__earthscope--outlook">
        <div class="gaia-dashboard__card-title-row">
          <div>
            <span class="gaia-dashboard__eyebrow">Current outlook</span>
            <h4>${esc(
              outlookLoading && !window24
                ? "Current outlook loading"
                : "Here's what's affecting you"
            )}</h4>
          </div>
          ${primary ? `<span class="${pillClass(primary.severity || "watch")}">${esc(primary.severity || "Watch")}</span>` : ""}
        </div>
        <p class="gaia-dashboard__earthscope-summary">${
          outlookLoading && !window24
            ? "Loading the latest personal outlook."
            : esc(summary)
        }</p>
        ${
          primary
            ? `
              <div class="gaia-dashboard__earthscope-preview">
                <div class="gaia-dashboard__earthscope-row">
                  <div class="gaia-dashboard__earthscope-label">Main thing to watch</div>
                  <div class="gaia-dashboard__earthscope-copy">${esc(sentence(primary.detail, "This looks most relevant in the current window."))}</div>
                </div>
                ${
                  supportLine
                    ? `
                      <div class="gaia-dashboard__earthscope-row">
                        <div class="gaia-dashboard__earthscope-label">A steadier way through it</div>
                        <div class="gaia-dashboard__earthscope-copy">${esc(supportLine)}</div>
                      </div>
                    `
                    : ""
                }
              </div>
            `
            : outlookError
              ? `<div class="gaia-dashboard__muted">Current outlook is temporarily unavailable. Guide and Body can still use the last-good state.</div>`
              : ""
        }
        <button class="gaia-dashboard__earthscope-link" type="button" data-tab-target="outlook">Open full Outlook</button>
      </div>
    `;
  };

  const renderMissionSection = (state) => {
    const payload = state.dashboard;
    const gaugesRaw = payload.gauges || {};
    const gaugesMeta = payload.gaugesMeta && typeof payload.gaugesMeta === "object" ? payload.gaugesMeta : {};
    const gaugesDelta = payload.gaugesDelta && typeof payload.gaugesDelta === "object" ? payload.gaugesDelta : {};
    const gaugeZones = normalizeGaugeZones(payload.gaugeZones);
    const gaugeLabels = payload.gaugeLabels && typeof payload.gaugeLabels === "object" ? payload.gaugeLabels : {};
    const drivers = combinedMissionDrivers(payload, state.member && state.member.drivers);
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
        ${renderMissionBodyContext(state)}
        ${renderDriversSection(drivers, payload.modalModels || {}, 3)}
        ${
          drivers.length
            ? `<div class="gaia-dashboard__section-actions"><button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="drivers">View all drivers</button></div>`
            : ""
        }
        ${renderGeomagneticContext(geomagneticContext)}
        ${renderMissionOutlookCard(state, earthscopeSummary)}
      </section>
    `;
  };

  const renderDriversHubSection = (state) => {
    const payload = state.dashboard;
    const drivers = allMissionDrivers(payload, state.member && state.member.drivers);
    const driversLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.drivers);
    const driversError = textOrEmpty(state.member.errors && state.member.errors.drivers);

    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "drivers" ? " is-active" : ""}" data-section="drivers">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Drivers</h3>
            <p class="gaia-dashboard__section-subtitle">The full active driver stack, grouped by what is leading, also in play, and in the background.</p>
          </div>
        </div>
        ${
          driversLoading && !drivers.length
            ? '<div class="gaia-dashboard__muted">Loading the full driver stack…</div>'
            : driversError && !drivers.length
              ? `<div class="gaia-dashboard__muted">${esc(driversError)}</div>`
              : renderDriversSection(drivers, payload.modalModels || {}, 12, { heading: "Drivers" })
        }
      </section>
    `;
  };

  const renderBodySection = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const features = extractFeatures(state.member.features);
    const profilePreferences = extractProfilePreferences(state.member.profilePreferences);
    const lunar = state.member.lunar && typeof state.member.lunar === "object" ? state.member.lunar : null;
    const currentSymptomsLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.currentSymptoms);
    const featuresLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.features);
    const lunarLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.lunar);
    const currentSymptomsError = textOrEmpty(state.member.errors && state.member.errors.currentSymptoms);
    const featuresError = textOrEmpty(state.member.errors && state.member.errors.features);
    const lunarError = textOrEmpty(state.member.errors && state.member.errors.lunar);
    const symptomItems = maybeArray(currentSymptoms && currentSymptoms.items).slice(0, 4);
    const summary = currentSymptoms && currentSymptoms.summary ? currentSymptoms.summary : {};
    const healthCards = healthStatCards(features, profilePreferences).slice(0, 5);
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
            <button class="gaia-dashboard__btn" type="button" data-open-symptom-picker="1" data-picker-title="Log symptoms">Log symptoms</button>
          </div>
        </div>
        <div class="gaia-dashboard__split">
          <div class="gaia-dashboard__grid">
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Current symptoms</span>
                  <h4 class="gaia-dashboard__card-title">${
                    currentSymptomsLoading && !currentSymptoms
                      ? "Loading current symptoms"
                      : summary && Number(summary.active_count || 0) > 0
                        ? `${Math.round(Number(summary.active_count || 0))} active right now`
                        : currentSymptomsError
                          ? "Current symptoms unavailable"
                          : "Nothing active right now"
                  }</h4>
                </div>
                ${
                  topDriver
                    ? `<span class="${pillClass(topDriver.severity || "watch")}">${esc(topDriver.label || topDriver.key || "Context")}</span>`
                    : ""
                }
              </div>
              <p class="gaia-dashboard__card-copy">${
                currentSymptomsLoading && !currentSymptoms
                  ? "Checking your recent symptom state."
                  : topDriver
                  ? esc(sentence(topDriver.pattern_hint || topDriver.display || topDriver.relation, `${topDriver.label || "Current body context"} looks closest to this window.`))
                  : currentSymptomsError
                    ? "Current symptom context is temporarily unavailable. Try again in a moment."
                  : "No symptom follow-up is waiting right now."
              }</p>
              ${
                symptomItems.length
                  ? `<div class="gaia-dashboard__current-symptom-list">${symptomItems
                      .map((item) => renderCurrentSymptomRow(state, item))
                      .join("")}</div>`
                  : `<div class="gaia-dashboard__helper">${
                      currentSymptomsLoading && !currentSymptoms
                        ? "Recent symptoms will appear here as soon as the current state loads."
                      : currentSymptomsError
                          ? "Once the feed reconnects, the current symptom list will return here."
                          : "As symptoms are logged or updated, they will show here with the most likely context."
                    }</div>`
              }
            </article>
            ${renderDailyCheckInCard(state, "body")}
          </div>
          <div class="gaia-dashboard__grid">
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Sleep</span>
                  <h4 class="gaia-dashboard__card-title">${formatHoursSummary(featureValue(features, "sleep_total_minutes", "sleepTotalMinutes"))} total</h4>
                </div>
                <span class="${pillClass("low")}">${formatPercent(featureValue(features, "sleep_efficiency", "sleepEfficiency"))}</span>
              </div>
              ${
                featuresLoading && !sleepCards.length
                  ? '<div class="gaia-dashboard__empty">Loading synced sleep data…</div>'
                  : ""
              }
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
                  : !featuresLoading
                    ? featuresError
                      ? '<div class="gaia-dashboard__empty">Sleep is temporarily unavailable right now. Try again in a moment.</div>'
                      : '<div class="gaia-dashboard__empty">Sleep will appear here once synced data is available.</div>'
                    : ""
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
                featuresLoading && !healthCards.length
                  ? '<div class="gaia-dashboard__empty">Loading synced body data…</div>'
                  : ""
              }
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
                  : !featuresLoading
                    ? featuresError
                      ? '<div class="gaia-dashboard__empty">Health stats are temporarily unavailable right now. Try again in a moment.</div>'
                      : '<div class="gaia-dashboard__empty">Health stats appear here once the app has synced body data to your account.</div>'
                    : ""
              }
              <div class="gaia-dashboard__section-actions">
                <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-tab-target="settings">Edit tracked stats</button>
              </div>
            </article>
            <article class="gaia-dashboard__card">
              <div class="gaia-dashboard__card-title-row">
                <div>
                  <span class="gaia-dashboard__eyebrow">Lunar watch</span>
                  <h4 class="gaia-dashboard__card-title">${esc(
                    lunarLoading && !lunar
                      ? "Tracking"
                      : (lunar && (lunar.pattern_strength || "tracking"))
                        ? titleFromKey(lunar.pattern_strength || "tracking")
                        : lunarError
                          ? "Temporarily unavailable"
                          : "Tracking"
                  )}</h4>
                </div>
              </div>
              <p class="gaia-dashboard__card-copy">${esc(
                lunarLoading && !lunar
                  ? "Loading the latest lunar watch."
                  : lunarError
                    ? "Lunar watch is temporarily unavailable right now."
                    : sentence(lunar && (lunar.message_scientific || lunar.message_mystical), "No clear lunar signal yet.")
              )}</p>
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
    const fullPatterns = extractPatternsPayload(state.member.patterns);
    const summaryPatterns = extractPatternsPayload(state.member.patternsSummary);
    const partial = Object.keys(fullPatterns).length ? fullPatterns : summaryPatterns;
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
    const outlookLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.outlook);
    const outlookError = textOrEmpty(state.member.errors && state.member.errors.outlook);
    const availableWindows = maybeArray(outlook.availableWindows || outlook.available_windows).map((item) => {
      const key = textOrEmpty(item).toLowerCase();
      if (key === "next_24h" || key === "next24h") return "24h";
      if (key === "next_72h" || key === "next72h") return "72h";
      if (key === "next_7d" || key === "next7d") return "7d";
      return item;
    });
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
              <h4 class="gaia-dashboard__card-title">${
                outlookLoading && !availableWindows.length
                  ? "Loading windows"
                  : outlookError && !availableWindows.length
                    ? "Outlook temporarily unavailable"
                    : "Ready windows"
              }</h4>
            </div>
          </div>
          ${
            outlookError && !availableWindows.length
              ? `<p class="gaia-dashboard__card-copy">The personal outlook feed is temporarily unavailable. Try again in a moment.</p>`
              : ""
          }
          <div class="gaia-dashboard__meta-row">
            ${availableWindows
              .map((item) => `<span class="gaia-dashboard__meta-chip">${esc(item)}</span>`)
              .join("") || `<span class="gaia-dashboard__meta-chip">${outlookLoading ? "Loading" : "Building"}</span>`}
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

  const renderGuideSection = (state) => {
    const currentSymptoms = extractCurrentSymptoms(state.member.currentSymptoms);
    const followUp = firstPendingFollowUp(currentSymptoms);
    const poll = derivedDailyPoll(state);
    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "guide" ? " is-active" : ""}" data-section="guide">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Guide</h3>
            <p class="gaia-dashboard__section-subtitle">A lighter read of what is surfacing now, what is feeding it, and what may help next.</p>
          </div>
        </div>
        <div class="gaia-dashboard__guide-stack">
          ${renderGuideHeaderCard(state)}
          ${renderGuideInfluenceCard(state)}
          ${renderGuideSupportCard(state)}
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
                ? esc(`${textOrEmpty(followUp.pending_follow_up && followUp.pending_follow_up.question_text) || "A follow-up is ready."} Open Body to respond in the current symptom workflow.`)
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

  const saveProfilePreferences = async (root, state, partial) => {
    const token = state && state.authCtx ? state.authCtx.token : "";
    const url = routeFor("profilePreferences");
    if (!token || !url) return;
    const previous = extractProfilePreferences(state.member.profilePreferences) || {};
    const optimistic = { ...previous, ...partial };
    state.member.profilePreferences = optimistic;
    state.ui.profilePreferencesSaving = true;
    state.ui.profilePreferencesStatus = "Saving settings…";
    renderMemberHub(root, state);
    try {
      const payload = await putJson(url, token, partial);
      state.member.profilePreferences = extractProfilePreferences(payload) || optimistic;
      delete state.member.errors.profilePreferences;
      state.ui.profilePreferencesStatus = "Settings updated.";
    } catch (err) {
      state.member.profilePreferences = previous;
      state.member.errors.profilePreferences = err && err.message ? err.message : String(err);
      state.ui.profilePreferencesStatus = state.member.errors.profilePreferences;
    } finally {
      state.ui.profilePreferencesSaving = false;
      renderMemberHub(root, state);
    }
  };

  const saveNotificationPreferences = async (root, state, partial) => {
    const token = state && state.authCtx ? state.authCtx.token : "";
    const url = routeFor("notifications");
    if (!token || !url) return;
    const previous = (await ensureNotificationPreferencesLoaded(state).catch(() => ({}))) || {};
    const optimistic = {
      ...previous,
      ...partial,
      time_zone: normalizeTimeZoneIdentifier((partial && partial.time_zone) || previous.time_zone || previous.timeZone),
    };
    state.member.notifications = { ok: true, preferences: optimistic };
    state.ui.notificationPreferencesSaving = true;
    state.ui.notificationPreferencesStatus = "Saving timing settings…";
    renderMemberHub(root, state);
    try {
      const payload = await putJson(url, token, optimistic);
      state.member.notifications = payload;
      delete state.member.errors.notifications;
      state.ui.notificationPreferencesStatus = "Timing settings updated.";
      hydrateMemberKeys(root, state, ["features", "dailyCheckIn"], { force: true });
    } catch (err) {
      state.member.notifications = previous;
      state.member.errors.notifications = err && err.message ? err.message : String(err);
      state.ui.notificationPreferencesStatus = state.member.errors.notifications;
    } finally {
      state.ui.notificationPreferencesSaving = false;
      renderMemberHub(root, state);
    }
  };

  const formatAccountPreflightStatus = (payload) => {
    const data = extractEnvelopeData(payload) || maybeObject(payload) || {};
    const rowsFound = toNumber(data.rows_found ?? data.rowsFound, 0);
    const tablesWithRows = toNumber(data.tables_with_rows ?? data.tablesWithRows, 0);
    const issues = maybeArray(data.issues)
      .map((item) => textOrEmpty(item))
      .filter(Boolean);
    const largest = maybeArray(data.largest_tables ?? data.largestTables)
      .map((item) => {
        const table = textOrEmpty(item && item.table);
        const rows = toNumber(item && item.rows, 0);
        return table ? `${table} (${rows})` : "";
      })
      .filter(Boolean)
      .slice(0, 3)
      .join(", ");
    const segments = [];
    if (data.delete_ready === true || data.deleteReady === true) {
      segments.push(`Ready. Would delete ${rowsFound} rows across ${tablesWithRows} areas.`);
    } else {
      segments.push("Preflight found setup issues.");
    }
    if (largest) {
      segments.push(`Largest areas: ${largest}.`);
    }
    if (issues.length) {
      segments.push(issues.join(" "));
    }
    return segments.join(" ").trim();
  };

  const runAccountDeletePreflight = async (root, state) => {
    const token = state && state.authCtx ? state.authCtx.token : "";
    const url = routeFor("accountPreflight");
    if (!token || !url || state.ui.accountPreflightPending) return;
    state.ui.accountPreflightPending = true;
    state.ui.accountPreflightStatus = "Checking safe preflight…";
    renderMemberHub(root, state);
    try {
      const payload = await fetchJson(url, token);
      if (payload && payload.ok === false) {
        throw new Error(payload.error || "Could not run the delete preflight.");
      }
      state.ui.accountPreflightStatus = formatAccountPreflightStatus(payload);
    } catch (err) {
      state.ui.accountPreflightStatus = err && err.message ? err.message : "Could not run the delete preflight.";
    } finally {
      state.ui.accountPreflightPending = false;
      renderMemberHub(root, state);
    }
  };

  const deleteMemberAccount = async (root, state) => {
    const token = state && state.authCtx ? state.authCtx.token : "";
    const url = routeFor("accountDelete");
    if (!token || !url || state.ui.accountDeletionPending) return;
    const confirmed = window.confirm(
      "Delete your Gaia Eyes account? This permanently deletes your account and associated app data. App Store subscriptions are managed separately in Apple Subscriptions."
    );
    if (!confirmed) return;
    state.ui.accountDeletionPending = true;
    state.ui.accountDeletionStatus = "Deleting account…";
    renderMemberHub(root, state);
    try {
      const payload = await deleteJson(url, token);
      if (payload && payload.ok === false) {
        throw new Error(payload.error || "Could not delete your account.");
      }
      state.ui.accountDeletionStatus = "Account deleted.";
      renderMemberHub(root, state);
      if (state.authCtx && typeof state.authCtx.onSignOut === "function") {
        await state.authCtx.onSignOut("Account deleted. Sign in with email if you want to return.");
      }
    } catch (err) {
      state.ui.accountDeletionStatus = err && err.message ? err.message : "Could not delete your account.";
      state.ui.accountDeletionPending = false;
      renderMemberHub(root, state);
    }
  };

  const renderSettingsSection = (state) => {
    const authCtx = state.authCtx || {};
    const isMember = state.dashboard.entitled === true || !!state.dashboard.memberPost;
    const profilePreferences = extractProfilePreferences(state.member.profilePreferences) || {};
    const notificationPreferences = extractNotificationPreferences(state.member.notifications) || {};
    const selectedTrackedStats = profileTrackedStatKeys(profilePreferences);
    const smartSwapEnabled = profileSmartSwapEnabled(profilePreferences);
    const favoriteSymptomCodes = profileFavoriteSymptomCodes(profilePreferences);
    const favoriteSymptomSet = new Set(favoriteSymptomCodes);
    const selectedTimeZone = normalizeTimeZoneIdentifier(notificationPreferences.time_zone || notificationPreferences.timeZone);
    const notificationOptions = timeZoneOptions(selectedTimeZone);
    const symptomCatalog = dedupeSymptomCatalog(extractSymptomCodeCatalog(state.member.symptomCodes))
      .filter((item) => item && item.is_active !== false && item.isActive !== false)
      .filter((item) => normalizeSymptomCode(item && (item.symptom_code || item.symptomCode)) !== "OTHER");
    const profilePreferencesLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.profilePreferences);
    const notificationPreferencesLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.notifications);
    const symptomCodesLoading = !!(state.ui.loadingKeys && state.ui.loadingKeys.symptomCodes);
    const profilePreferencesStatus = textOrEmpty(state.ui.profilePreferencesStatus || state.member.errors.profilePreferences);
    const notificationPreferencesStatus = textOrEmpty(state.ui.notificationPreferencesStatus || state.member.errors.notifications);
    const accountPreflightStatus = textOrEmpty(state.ui.accountPreflightStatus);
    const accountDeletionStatus = textOrEmpty(state.ui.accountDeletionStatus);
    return `
      <section class="gaia-dashboard__section${state.ui.activeTab === "settings" ? " is-active" : ""}" data-section="settings">
        <div class="gaia-dashboard__section-head">
          <div class="gaia-dashboard__section-copy">
            <h3 class="gaia-dashboard__section-title">Settings</h3>
            <p class="gaia-dashboard__section-subtitle">Account actions, support links, and website shortcuts live here so the core hub can stay focused on the signal read.</p>
          </div>
        </div>
        <div class="gaia-dashboard__grid gaia-dashboard__grid--2">
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Account</span>
                <h4 class="gaia-dashboard__card-title">${esc(isMember ? "Member access" : "Free access")}</h4>
              </div>
              <span class="gaia-dashboard__mode">${isMember ? "Member" : "Free"}</span>
            </div>
            <div class="gaia-dashboard__list">
              <div class="gaia-dashboard__list-row">
                <strong>Email</strong>
                <p>${esc(authCtx.email || "Signed-in email unavailable.")}</p>
              </div>
            </div>
            <div class="gaia-dashboard__section-actions">
              <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-switch>Email link</button>
              <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-signout>Sign out</button>
            </div>
            <div class="gaia-dashboard__empty">
              <strong>Safe delete preflight</strong>
              <p>Checks whether account deletion is fully wired and shows what would be removed, without deleting anything.</p>
              <div class="gaia-dashboard__section-actions">
                <button class="gaia-dashboard__btn gaia-dashboard__btn--ghost" type="button" data-gaia-account-preflight${state.ui.accountPreflightPending ? " disabled" : ""}>${state.ui.accountPreflightPending ? "Checking..." : "Run safe preflight"}</button>
              </div>
              ${accountPreflightStatus ? `<div class="gaia-dashboard__status-note">${esc(accountPreflightStatus)}</div>` : ""}
            </div>
            <div class="gaia-dashboard__empty">
              <strong>Delete account</strong>
              <p>Permanently deletes your Gaia Eyes account and associated app data. App Store subscriptions are managed separately in Apple Subscriptions.</p>
              <div class="gaia-dashboard__section-actions">
                <button class="gaia-dashboard__btn gaia-dashboard__btn--danger" type="button" data-gaia-delete-account${state.ui.accountDeletionPending ? " disabled" : ""}>${state.ui.accountDeletionPending ? "Deleting..." : "Delete account"}</button>
              </div>
              ${accountDeletionStatus ? `<div class="gaia-dashboard__status-note">${esc(accountDeletionStatus)}</div>` : ""}
            </div>
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Timing</span>
                <h4 class="gaia-dashboard__card-title">Time zone</h4>
              </div>
            </div>
            <p class="gaia-dashboard__card-copy">Used for daily windows, check-in timing, reminders, and the member day boundary.</p>
            ${
              notificationPreferencesLoading && !state.member.notifications
                ? '<div class="gaia-dashboard__empty">Loading your timing settings…</div>'
                : `
                  <div class="gaia-dashboard__field">
                    <label for="gaia-settings-time-zone">Time zone</label>
                    <select id="gaia-settings-time-zone" data-notification-timezone>
                      ${notificationOptions
                        .map(
                          (identifier) => `
                            <option value="${esc(identifier)}"${identifier === selectedTimeZone ? " selected" : ""}>${esc(timeZoneLabel(identifier))}</option>
                          `
                        )
                        .join("")}
                    </select>
                  </div>
                  <div class="gaia-dashboard__section-actions">
                    <button class="gaia-dashboard__btn gaia-dashboard__btn--quiet" type="button" data-notification-timezone-use-browser="1">Use browser time zone</button>
                    <span class="gaia-dashboard__helper">Current browser zone: ${esc(browserTimeZoneIdentifier())}</span>
                  </div>
                `
            }
            ${notificationPreferencesStatus ? `<div class="gaia-dashboard__status-note">${esc(notificationPreferencesStatus)}</div>` : ""}
          </article>
          <article class="gaia-dashboard__card">
            <div class="gaia-dashboard__card-title-row">
              <div>
                <span class="gaia-dashboard__eyebrow">Website</span>
                <h4 class="gaia-dashboard__card-title">Quick links</h4>
              </div>
            </div>
            <div class="gaia-dashboard__link-grid gaia-dashboard__link-grid--settings">
              <a class="gaia-dashboard__link-card" href="${esc(publicLinks.spaceWeather || "/space-weather/")}"><strong>Space Weather</strong><small>Scientific forecast and current conditions.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(publicLinks.schumann || "/schumann-resonance/")}"><strong>Schumann</strong><small>Current resonance detail and scientific context.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(publicLinks.magnetosphere || "/magnetosphere/")}"><strong>Magnetosphere</strong><small>Shield state, compression, and recent change.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(publicLinks.aurora || "/aurora-tracker/")}"><strong>Aurora</strong><small>Live tracker and viewlines.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(publicLinks.earthquakes || "/earthquakes/")}"><strong>Earthquakes</strong><small>Global quake activity and recent clusters.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(supportUrl)}"><strong>Help Center</strong><small>Support, sync help, billing, and account guidance.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(privacyUrl)}"><strong>Privacy Policy</strong><small>Public privacy disclosures for the app and website.</small></a>
              <a class="gaia-dashboard__link-card" href="${esc(termsUrl)}"><strong>Terms of Use</strong><small>Public terms, billing boundaries, and app-use conditions.</small></a>
            </div>
          </article>
        </div>
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <div>
              <span class="gaia-dashboard__eyebrow">Body stats</span>
              <h4 class="gaia-dashboard__card-title">Tracked stat bar</h4>
            </div>
          </div>
          <p class="gaia-dashboard__card-copy">Choose up to five default body stats. When smart swap is on, Gaia can rotate a more relevant stat into the last slot when something stands out.</p>
          ${
            profilePreferencesLoading && !state.member.profilePreferences
              ? '<div class="gaia-dashboard__empty">Loading your stat preferences…</div>'
              : `
                <div class="gaia-dashboard__symptom-grid">
                  ${TRACKED_STAT_OPTIONS.map(
                    (option) => `
                      <button
                        class="gaia-dashboard__symptom-pill${selectedTrackedStats.includes(option.key) ? " is-selected" : ""}"
                        type="button"
                        data-tracked-stat-toggle="${esc(option.key)}"
                        ${!selectedTrackedStats.includes(option.key) && selectedTrackedStats.length >= 5 ? "disabled" : ""}
                      >
                        <span class="gaia-dashboard__symptom-pill-title">${esc(option.label)}</span>
                        <span class="gaia-dashboard__symptom-pill-copy">${esc(option.detail)}</span>
                      </button>
                    `
                  ).join("")}
                </div>
                <label class="gaia-dashboard__toggle-chip">
                  <input type="checkbox" data-smart-swap-toggle="1" ${smartSwapEnabled ? "checked" : ""} />
                  <span>
                    <strong>Smart swap the last slot</strong>
                    <span class="gaia-dashboard__helper">Keeps four pinned stats stable and lets one slot rotate when another body stat matters more.</span>
                  </span>
                </label>
              `
          }
          ${profilePreferencesStatus ? `<div class="gaia-dashboard__status-note">${esc(profilePreferencesStatus)}</div>` : ""}
        </article>
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <div>
              <span class="gaia-dashboard__eyebrow">Symptoms</span>
              <h4 class="gaia-dashboard__card-title">Favorite symptoms</h4>
            </div>
          </div>
          <p class="gaia-dashboard__card-copy">Choose up to ${MAX_FAVORITE_SYMPTOM_CODES} symptoms you log often. Gaia shows these first in the app and website symptom pickers.</p>
          ${
            symptomCodesLoading && !state.member.symptomCodes
              ? '<div class="gaia-dashboard__empty">Loading symptom options…</div>'
              : symptomCatalog.length
                ? `
                  <div class="gaia-dashboard__symptom-grid">
                    ${symptomCatalog
                      .map((item) => {
                        const code = normalizeSymptomCode(item && (item.symptom_code || item.symptomCode));
                        const isSelected = favoriteSymptomSet.has(code);
                        const label = textOrEmpty(item && item.label) || titleFromKey(code);
                        const description = textOrEmpty(item && item.description);
                        return `
                          <button
                            class="gaia-dashboard__symptom-pill${isSelected ? " is-selected" : ""}"
                            type="button"
                            data-favorite-symptom-toggle="${esc(code)}"
                            ${!isSelected && favoriteSymptomCodes.length >= MAX_FAVORITE_SYMPTOM_CODES ? "disabled" : ""}
                          >
                            <span class="gaia-dashboard__symptom-pill-title">${esc(label)}</span>
                            ${description ? `<span class="gaia-dashboard__symptom-pill-copy">${esc(description)}</span>` : ""}
                          </button>
                        `;
                      })
                      .join("")}
                  </div>
                `
                : '<div class="gaia-dashboard__empty">Symptom options will appear here once the catalog loads.</div>'
          }
        </article>
        <article class="gaia-dashboard__card">
          <div class="gaia-dashboard__card-title-row">
            <div>
              <span class="gaia-dashboard__eyebrow">About this web hub</span>
              <h4 class="gaia-dashboard__card-title">What syncs here</h4>
            </div>
          </div>
          <p class="gaia-dashboard__card-copy">Body data on the website comes from the app’s synced account data. If sleep or health stats look light, open the app first so the latest device sync reaches your account.</p>
        </article>
      </section>
    `;
  };

  const renderMissionControlApp = (root, state) => {
    const title = root.dataset.title || "Mission Control";
    root.innerHTML = `
      <div class="gaia-dashboard__shell gaia-dashboard__shell--hub">
        <div class="gaia-dashboard__shell-head">
          <div class="gaia-dashboard__shell-copy">
            <span class="gaia-dashboard__shell-kicker">Member Hub</span>
            <h2 class="gaia-dashboard__title">${esc(title)}</h2>
            <p class="gaia-dashboard__shell-subtitle">Mission Control for the web: gauges, body context, patterns, outlook, drivers, and a lighter Guide layer in one signed-in shell.</p>
          </div>
        </div>
        <div class="gaia-dashboard__nav-grid gaia-dashboard__nav-grid--hub">
          ${missionNavCard(state, "mission", "Mission Control", "Gauges, drivers, and your current outlook live here.")}
          ${missionNavCard(state, "drivers", "Drivers", "The full active stack Gaia is weighing right now.")}
          ${missionNavCard(state, "body", "Body", "Current symptoms, check-in, sleep, health stats, and lunar watch.")}
          ${missionNavCard(state, "patterns", "Patterns", "The clearest repeats in your logs and wearable history.")}
          ${missionNavCard(state, "outlook", "Outlook", "Your 24h, 72h, and 7-day personal forecast windows.")}
          ${missionNavCard(state, "guide", "Guide", "A lighter orientation layer with daily check-in and help links.")}
          ${missionNavCard(state, "settings", "Settings", "Account actions, support, and website shortcuts.")}
        </div>
        ${renderMissionSection(state)}
        ${renderDriversHubSection(state)}
        ${renderBodySection(state)}
        ${renderPatternsSection(state)}
        ${renderOutlookSection(state)}
        ${renderGuideSection(state)}
        ${renderSettingsSection(state)}
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
    removeMissionMobileNavPortal(root);
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
      removeMissionMobileNavPortal(root);
      root.innerHTML = `<div class="gaia-dashboard__status">Dashboard config missing: ${esc(
        missing.join(", ")
      )}</div>`;
      return;
    }

    if (!window.supabase || !window.supabase.createClient) {
      removeMissionMobileNavPortal(root);
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
      removeMissionMobileNavPortal(root);
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
        primaryDriver:
          (dashboard && (dashboard.primary_driver || dashboard.primaryDriver)) || null,
        supportingDrivers:
          (dashboard && (dashboard.supporting_drivers || dashboard.supportingDrivers)) || [],
        driversCompact:
          (dashboard && (dashboard.drivers_compact || dashboard.driversCompact)) || [],
        modalModels:
          (dashboard && (dashboard.modal_models || dashboard.modalModels)) || {},
        earthscopeSummary:
          (dashboard && (dashboard.earthscope_summary || dashboard.earthscopeSummary)) || "",
        supportItems:
          (dashboard && (dashboard.support_items || dashboard.supportItems)) || [],
        geomagneticContext:
          (dashboard && (dashboard.geomagnetic_context || dashboard.geomagneticContext)) || null,
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        entitled: dashboard ? dashboard.entitled : null,
        memberPost:
          (dashboard && (dashboard.member_post || dashboard.memberPost || dashboard.personal_post || dashboard.personalPost)) || null,
        publicPost: (dashboard && (dashboard.public_post || dashboard.publicPost)) || null,
      };
      const user = data && data.session && data.session.user ? data.session.user : null;
      const state = {
        dashboard: payload,
        member: {
          profilePreferences: null,
          notifications: null,
          drivers: null,
          features: null,
          currentSymptoms: null,
          dailyCheckIn: null,
          lunar: null,
          outlook: null,
          patternsSummary: null,
          patterns: null,
          symptomCodes: null,
          errors: {},
        },
        authCtx: {
        email: user && user.email ? user.email : "",
        token,
        onSignOut: async (message) => {
          try {
            await supabase.auth.signOut();
          } finally {
            renderSignInPrompt(root, supabase, message || "Signed out. Sign in with email.");
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
          guidePollChoice: "",
          checkInEditing: false,
          checkInSubmitting: false,
          checkInStatus: "",
          checkInForm: null,
          patternsLoading: false,
          loadingKeys: defaultLoadingKeys(),
          currentSymptomPendingById: {},
          currentSymptomStatusById: {},
          accountPreflightPending: false,
          accountPreflightStatus: "",
          accountDeletionPending: false,
          accountDeletionStatus: "",
        },
      };
      if (state.ui.activeTab === "guide") {
        void markGuideSeenRemotely(state);
      }
      renderMemberHub(root, state);
      if (!root.dataset.gaiaHashBound) {
        window.addEventListener("hashchange", () => {
          state.ui.activeTab = currentTabFromHash();
          if (state.ui.activeTab === "guide") {
            void markGuideSeenRemotely(state);
          }
          hydrateTabData(root, state, state.ui.activeTab);
          renderMemberHub(root, state);
        });
        root.dataset.gaiaHashBound = "1";
      }
      hydrateTabData(root, state, state.ui.activeTab);
      scheduleIdleHydration(root, state);
    } catch (err) {
      removeMissionMobileNavPortal(root);
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
