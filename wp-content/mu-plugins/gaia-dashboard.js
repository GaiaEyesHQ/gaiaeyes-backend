(function () {
  const cfg = window.GAIA_DASHBOARD_CFG || {};
  const normalizeBase = (value) => (value || "").replace(/\/+$/, "");
  const backendBase = normalizeBase(cfg.backendBase);

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

  const markdownToHtml = (markdown) => {
    const lines = String(markdown || "").split(/\r?\n/);
    const out = [];
    let listOpen = false;

    const closeList = () => {
      if (listOpen) {
        out.push("</ul>");
        listOpen = false;
      }
    };

    for (const raw of lines) {
      const line = raw.trim();
      if (!line) {
        closeList();
        continue;
      }
      if (line.startsWith("## ")) {
        closeList();
        out.push(`<h2>${esc(line.slice(3))}</h2>`);
      } else if (line.startsWith("### ")) {
        closeList();
        out.push(`<h3>${esc(line.slice(4))}</h3>`);
      } else if (line.startsWith("- ")) {
        if (!listOpen) {
          out.push("<ul>");
          listOpen = true;
        }
        out.push(`<li>${esc(line.slice(2))}</li>`);
      } else {
        closeList();
        out.push(`<p>${esc(line)}</p>`);
      }
    }
    closeList();
    return out.join("");
  };

  const fetchJson = async (url, token) => {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };

  const hashParams = () => {
    const hash = (window.location.hash || "").replace(/^#/, "");
    if (!hash) return new URLSearchParams();
    return new URLSearchParams(hash);
  };

  const cleanURLHash = () => {
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

  const renderDashboard = (root, payload) => {
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

    root.innerHTML = `
      <div class="gaia-dashboard__head">
        <h2 class="gaia-dashboard__title">${esc(title)}</h2>
        <span class="gaia-dashboard__mode">${isPaid ? "Member" : "Free"}</span>
      </div>
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
        <div class="gaia-dashboard__markdown">${
          earthscope && earthscope.body_markdown ? markdownToHtml(earthscope.body_markdown) : "<p>EarthScope is updating.</p>"
        }</div>
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
    if (!backendBase) missing.push("GAIAEYES_API_BASE");
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
      const dashboard = await fetchJson(`${backendBase}/v1/dashboard?day=${encodeURIComponent(day)}`, token);
      const elapsed = Date.now() - started;
      console.info("[gaia-dashboard] loaded payload in ms=", elapsed);

      const payload = {
        gauges: dashboard && dashboard.gauges ? dashboard.gauges : null,
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        entitled: dashboard ? dashboard.entitled : null,
        memberPost:
          (dashboard && (dashboard.member_post || dashboard.memberPost || dashboard.personal_post || dashboard.personalPost)) || null,
        publicPost: (dashboard && (dashboard.public_post || dashboard.publicPost)) || null,
      };
      renderDashboard(root, payload);
    } catch (err) {
      root.innerHTML = `<div class="gaia-dashboard__status">Failed to load dashboard: ${esc(
        err.message || String(err)
      )}</div>`;
    }
  };

  const init = () => {
    document.querySelectorAll("[data-gaia-dashboard]").forEach((root) => {
      load(root);
    });
  };

  document.addEventListener("DOMContentLoaded", init);
})();
