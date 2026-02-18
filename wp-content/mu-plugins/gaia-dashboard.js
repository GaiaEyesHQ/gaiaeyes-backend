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

  const formatGaugeValue = (value) => {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return String(Math.round(Number(value)));
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

  const parseEarthscopeSections = (markdown) => {
    const buckets = { checkin: [], drivers: [], summary: [], actions: [] };
    if (!markdown || !String(markdown).trim()) {
      return {
        checkin: sectionDefaults.checkin,
        drivers: sectionDefaults.drivers,
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

  const renderEarthscopeBlocks = (earthscope) => {
    const sections = parseEarthscopeSections(earthscope && earthscope.body_markdown);
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
    const title = root.dataset.title || "Mission Control";
    const gaugesRaw = payload.gauges || {};
    const gaugeRows = [
      ["Pain", gaugesRaw.pain],
      ["Focus", gaugesRaw.focus],
      ["Heart", gaugesRaw.heart],
      ["Stamina", gaugesRaw.stamina],
      ["Energy", gaugesRaw.energy],
      ["Sleep", gaugesRaw.sleep],
      ["Mood", gaugesRaw.mood],
      ["Health", gaugesRaw.health_status],
    ];

    const alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
    const isPaid = payload.entitled === true || !!payload.memberPost;
    const displayRows = isPaid ? gaugeRows : gaugeRows.slice(0, 4);
    const earthscope = isPaid ? payload.memberPost || payload.publicPost || null : payload.publicPost || payload.memberPost || null;
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
        ${displayRows
          .map(
            ([label, value]) => `
              <div class="gaia-dashboard__gauge">
                <div class="gaia-dashboard__gauge-label">${esc(label)}</div>
                <div class="gaia-dashboard__gauge-value">${formatGaugeValue(value)}</div>
              </div>
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
      <div class="gaia-dashboard__earthscope">
        <h4>${esc((earthscope && earthscope.title) || "EarthScope")}</h4>
        ${
          earthscope && earthscope.caption
            ? `<p class="gaia-dashboard__muted">${esc(earthscope.caption)}</p>`
            : ""
        }
        <div class="gaia-dashboard__es-grid">${renderEarthscopeBlocks(earthscope)}</div>
      </div>
    `;
    applyEarthscopeBackgrounds(root);
    const signOutBtn = root.querySelector("[data-gaia-signout]");
    if (signOutBtn && authCtx && typeof authCtx.onSignOut === "function") {
        signOutBtn.addEventListener("click", authCtx.onSignOut);
    }
    const switchBtn = root.querySelector("[data-gaia-switch]");
    if (switchBtn && authCtx && typeof authCtx.onSwitch === "function") {
      switchBtn.addEventListener("click", authCtx.onSwitch);
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
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        entitled: dashboard ? dashboard.entitled : null,
        memberPost:
          (dashboard && (dashboard.member_post || dashboard.memberPost || dashboard.personal_post || dashboard.personalPost)) || null,
        publicPost: (dashboard && (dashboard.public_post || dashboard.publicPost)) || null,
      };
      const user = data && data.session && data.session.user ? data.session.user : null;
      renderDashboard(root, payload, {
        email: user && user.email ? user.email : "",
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
