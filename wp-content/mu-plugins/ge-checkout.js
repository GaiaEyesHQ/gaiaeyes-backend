(function () {
  const cfg = window.GE_CHECKOUT_CFG || {};
  const normalizeBase = (value) => (value || "").replace(/\/+$/, "");

  const backendBase = normalizeBase(cfg.backendBase);

  const init = () => {
    const buttons = document.querySelectorAll(".ge-checkout-btn");
    if (!buttons.length) return;

    const missing = [];
    if (!cfg.supabaseUrl) missing.push("SUPABASE_URL");
    if (!cfg.supabaseAnon) missing.push("SUPABASE_ANON_KEY");
    if (!backendBase) missing.push("GAIAEYES_API_BASE");

    const supabaseLib = window.supabase;
    const createClient = supabaseLib && supabaseLib.createClient;

    const setMsg = (btn, text) => {
      const container = btn.closest(".ge-checkout");
      const el = container ? container.querySelector(".ge-checkout-msg") : null;
      if (el) el.textContent = text || "";
    };

    if (missing.length) {
      buttons.forEach((btn) => setMsg(btn, "Checkout config missing: " + missing.join(", ")));
      return;
    }

    if (!createClient) {
      buttons.forEach((btn) => setMsg(btn, "Supabase client failed to load."));
      return;
    }

    const supabase = createClient(cfg.supabaseUrl, cfg.supabaseAnon);

    const ensureToken = async (btn) => {
      const { data, error } = await supabase.auth.getSession();
      if (error) {
        setMsg(btn, "Sign-in failed: " + error.message);
        return null;
      }
      const token = data && data.session ? data.session.access_token : null;
      if (token) return token;

      const email = prompt("Enter your email to sign in (magic link):");
      if (!email) {
        setMsg(btn, "Sign-in required to continue.");
        return null;
      }

      const { error: signInError } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.href },
      });
      if (signInError) {
        setMsg(btn, "Sign-in failed: " + signInError.message);
        return null;
      }
      setMsg(btn, "Check your email for the magic link. Return here after signing in.");
      return null;
    };

    buttons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.dataset.geCheckoutBusy === "1") return;
        btn.dataset.geCheckoutBusy = "1";
        btn.disabled = true;
        setMsg(btn, "");

        try {
          const token = await ensureToken(btn);
          if (!token) return;

          const plan = btn.getAttribute("data-plan") || "plus_monthly";
          const res = await fetch(`${backendBase}/v1/billing/checkout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${token}`,
            },
            body: JSON.stringify({ plan }),
          });

          const text = await res.text();
          let json = null;
          try { json = JSON.parse(text); } catch (e) { json = null; }

          if (!res.ok || !json || !json.ok) {
            const err = json && (json.error || json.detail);
            throw new Error(err || "Failed to start checkout.");
          }
          if (!json.url) {
            throw new Error("Checkout URL missing.");
          }
          window.location.href = json.url;
        } catch (e) {
          setMsg(btn, e && e.message ? e.message : String(e));
        } finally {
          btn.disabled = false;
          btn.dataset.geCheckoutBusy = "0";
        }
      });
    });
  };

  document.addEventListener("DOMContentLoaded", init);
})();
