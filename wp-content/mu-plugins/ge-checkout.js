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

    const credentialPrompt = (btn) => new Promise((resolve) => {
      const container = btn.closest(".ge-checkout");
      if (!container) {
        resolve(null);
        return;
      }

      const existing = container.querySelector(".ge-checkout-auth");
      if (existing) existing.remove();

      const form = document.createElement("form");
      form.className = "ge-checkout-auth";
      form.innerHTML = `
        <label>
          <span>Email</span>
          <input type="email" name="email" autocomplete="email" required>
        </label>
        <label>
          <span>Password</span>
          <input type="password" name="password" autocomplete="current-password" required>
        </label>
        <label class="ge-checkout-auth__check">
          <input type="checkbox" name="create" checked>
          <span>Create account if this is new</span>
        </label>
        <div class="ge-checkout-auth__actions">
          <button type="submit">Continue</button>
          <button type="button" data-ge-auth-cancel>Cancel</button>
        </div>
      `;

      const cleanup = () => form.remove();
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const formData = new FormData(form);
        const email = String(formData.get("email") || "").trim();
        const password = String(formData.get("password") || "");
        const create = formData.get("create") === "on";
        cleanup();
        resolve(email && password ? { email, password, create } : null);
      });
      form.querySelector("[data-ge-auth-cancel]").addEventListener("click", () => {
        cleanup();
        resolve(null);
      });

      const msg = container.querySelector(".ge-checkout-msg");
      if (msg && msg.parentNode) {
        msg.parentNode.insertBefore(form, msg.nextSibling);
      } else {
        container.appendChild(form);
      }
      const emailInput = form.querySelector('input[name="email"]');
      if (emailInput) emailInput.focus();
    });

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

      const credentials = await credentialPrompt(btn);
      if (!credentials) {
        setMsg(btn, "Sign-in required to continue.");
        return null;
      }
      const { email, password, create } = credentials;

      const signIn = await supabase.auth.signInWithPassword({ email, password });
      if (signIn.error) {
        if (!create) {
          setMsg(btn, "Sign-in failed: " + signIn.error.message);
          return null;
        }

        const signUp = await supabase.auth.signUp({ email, password });
        if (signUp.error) {
          setMsg(btn, "Account creation failed: " + signUp.error.message);
          return null;
        }

        const signUpToken = signUp.data && signUp.data.session ? signUp.data.session.access_token : null;
        if (signUpToken) return signUpToken;

        setMsg(btn, "Check your email to verify the account, then return here to subscribe.");
        return null;
      }

      const signedInToken = signIn.data && signIn.data.session ? signIn.data.session.access_token : null;
      if (!signedInToken) {
        setMsg(btn, "Sign-in did not return a session. Please try again.");
      }
      return signedInToken;
    };

    buttons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.dataset.geCheckoutBusy === "1") return;
        btn.dataset.geCheckoutBusy = "1";
        btn.disabled = true;
        setMsg(btn, "");

        try {
          const plan = btn.getAttribute("data-plan") || "plus_monthly";
          const token = await ensureToken(btn);
          if (!token) return;

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
            const hint = ` (HTTP ${res.status})`;
            throw new Error((err || "Failed to start checkout.") + hint);
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
