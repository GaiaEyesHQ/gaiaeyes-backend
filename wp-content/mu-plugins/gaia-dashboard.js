(function () {
  const cfg = window.GAIA_DASHBOARD_CFG || {};
  const normalizeBase = (value) => (value || "").replace(/\/+$/, "");
  const backendBase = normalizeBase(cfg.backendBase);
  const dashboardProxy = normalizeBase(cfg.dashboardProxy);

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

  const gaugeIsClickable = (zoneKey, delta) => {
    const zone = normalizeZoneKey(zoneKey);
    return zone === "elevated" || zone === "high" || Math.abs(Number(delta) || 0) >= 5;
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

  const driverIsClickable = (severity) => {
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

  const renderGaugeCard = (row, zones, hasModal) => {
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
    const clickable = hasModal && gaugeIsClickable(zoneKey, delta);
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
    const arcStyle = `filter:drop-shadow(0 0 ${palette.glowPx}px ${palette.glow})`;
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
        ${clickable ? '<div class="gaia-dashboard__tap-hint">Tap for context</div>' : ""}
      </article>
    `;
  };

  const renderDriversSection = (drivers, modalModels) => {
    if (!Array.isArray(drivers) || !drivers.length) {
      return `
        <div class="gaia-dashboard__drivers">
          <h4>Environmental Drivers</h4>
          <div class="gaia-dashboard__muted">No major environmental drivers are elevated right now.</div>
        </div>
      `;
    }
    const modalDrivers = modalModels && modalModels.drivers && typeof modalModels.drivers === "object"
      ? modalModels.drivers
      : {};

    const rows = drivers.slice(0, 6).map((driver) => {
      const severity = normalizeDriverSeverity(driver && driver.severity);
      const zoneKey = driverZoneFromSeverity(severity);
      const color = (GAUGE_PALETTE[zoneKey] || GAUGE_PALETTE.mild).hex;
      const width = Math.max(10, Math.round(driverProgress(severity) * 100));
      const canOpen = driverIsClickable(severity) && !!modalDrivers[String(driver.key || "")];
      const rowClass = canOpen ? "gaia-dashboard__driver-row gaia-dashboard__driver-row--clickable" : "gaia-dashboard__driver-row";

      return `
        <div class="${rowClass}" ${canOpen ? `data-driver-key="${esc(driver.key)}"` : ""}>
          <div class="gaia-dashboard__driver-head">
            <span class="gaia-dashboard__driver-label">${esc(driver.label || driver.key || "Driver")}</span>
            <span class="gaia-dashboard__driver-state" style="color:${color}">${esc(driver.state || "Low")}</span>
            <span class="gaia-dashboard__driver-value">${esc(formatDriverValue(driver))}</span>
          </div>
          <div class="gaia-dashboard__driver-bar-track">
            <div class="gaia-dashboard__driver-bar-fill" style="width:${width}%;background:${color}"></div>
          </div>
        </div>
      `;
    }).join("");

    return `
      <div class="gaia-dashboard__drivers">
        <h4>Environmental Drivers</h4>
        <div class="gaia-dashboard__drivers-list">${rows}</div>
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
    checkin: "Today's Check-in",
    drivers: "Drivers",
    summary: "Summary Note",
    actions: "Supportive Actions",
  };

  const sectionDefaults = {
    checkin: "Today's check-in is still being prepared.",
    drivers: "No primary driver is highlighted right now.",
    summary: "Keep an eye on your gauges for the latest context.",
    actions: "• Hydrate\n• Keep your sleep window steady\n• Use gentle movement",
  };

  const mediaBase = () => {
    const fromCfg = normalizeBase(cfg.mediaBase);
    if (fromCfg) return fromCfg;
    const supabase = normalizeBase(cfg.supabaseUrl);
    if (supabase) return `${supabase}/storage/v1/object/public/space-visuals`;
    return "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals";
  };

  const sectionKeyForHeading = (heading) => {
    const h = String(heading || "").toLowerCase();
    if (h.includes("check") || h.includes("today")) return "checkin";
    if (h.includes("driver")) return "drivers";
    if (h.includes("supportive action") || h === "actions" || h.includes("action")) return "actions";
    if (h.includes("summary") || h.includes("note")) return "summary";
    return null;
  };

  const cleanMarkdownLine = (line) =>
    String(line || "")
      .trim()
      .replace(/\*\*/g, "")
      .replace(/__/g, "")
      .replace(/^[-*]\s+/, "")
      .replace(/^\d+\.\s+/, "")
      .trim();

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
      checkin: ["checkin", "today_checkin", "todays_checkin"],
      drivers: ["drivers"],
      summary: ["summary", "note"],
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
      ${renderModalList("Why", entry.why)}
      ${renderModalList("What You May Notice", entry.what_you_may_notice || entry.whatYouMayNotice)}
      ${renderModalList("Supportive Actions", entry.suggested_actions || entry.suggestedActions)}
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
      <div class="gaia-dashboard__earthscope">
        <h4>${esc((earthscope && earthscope.title) || "EarthScope")}</h4>
        ${
          earthscope && earthscope.caption
            ? `<p class="gaia-dashboard__muted">${esc(earthscope.caption)}</p>`
            : ""
        }
        <p class="gaia-dashboard__earthscope-summary">${esc(earthscopeSummary)}</p>
        <button class="gaia-dashboard__earthscope-link" type="button" data-earthscope-full="1">Read full EarthScope</button>
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
          <h3 class="gaia-dashboard__modal-title">${esc((earthscope && earthscope.title) || "EarthScope")}</h3>
          ${
            earthscope && earthscope.caption
              ? `<p class="gaia-dashboard__muted">${esc(earthscope.caption)}</p>`
              : ""
          }
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
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        entitled: dashboard ? dashboard.entitled : null,
        memberPost:
          (dashboard && (dashboard.member_post || dashboard.memberPost || dashboard.personal_post || dashboard.personalPost)) || null,
        publicPost: (dashboard && (dashboard.public_post || dashboard.publicPost)) || null,
      };
      const user = data && data.session && data.session.user ? data.session.user : null;
      renderDashboard(root, payload, {
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
      });
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
