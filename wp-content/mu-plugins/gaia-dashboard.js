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
    const isPaid = !!payload.memberPost;
    const displayRows = isPaid ? gaugeRows : gaugeRows.slice(0, 4);
    const earthscope = payload.memberPost || payload.publicPost || null;

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

  const renderSignInPrompt = (root, supabase) => {
    root.innerHTML = `
      <div class="gaia-dashboard__signin">
        <span class="gaia-dashboard__status">Sign in to view your dashboard.</span>
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
          options: { emailRedirectTo: cfg.redirectUrl || window.location.href },
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
      const [dashboard, member, features] = await Promise.all([
        fetchJson(`${backendBase}/v1/dashboard`, token),
        fetchJson(`${backendBase}/v1/earthscope/member`, token).catch(() => null),
        fetchJson(`${backendBase}/v1/features/today`, token).catch(() => null),
      ]);

      const payload = {
        gauges: dashboard && dashboard.gauges ? dashboard.gauges : null,
        alerts: dashboard && Array.isArray(dashboard.alerts) ? dashboard.alerts : [],
        memberPost: member && member.ok && member.post ? member.post : null,
        publicPost:
          features && (features.post_body || features.post_title)
            ? {
                title: features.post_title || "EarthScope Daily",
                caption: features.post_caption || "",
                body_markdown: features.post_body || "",
              }
            : null,
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
