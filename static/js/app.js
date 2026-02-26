/* ========================================================================
   PMM Integration — Frontend Application
   ======================================================================== */

(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------

  const state = {
    currentStep: 1,
    doToken: "",
    pmmPassword: "",
    selectedEngine: null,
    usePrivate: false,
    databases: [],
    selectedDbs: [],
    userCredentials: {},
  };

  // -----------------------------------------------------------------------
  // DOM references
  // -----------------------------------------------------------------------

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  const panels = $$(".panel");
  const steps = $$(".step");

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  function toast(msg, type = "info", duration = 4000) {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), duration);
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok && !data.message) {
      data.message = `Server error (${res.status})`;
    }
    return data;
  }

  function setLoading(btn, loading) {
    if (loading) {
      btn.dataset.origText = btn.innerHTML;
      btn.innerHTML = '<span class="spinner"></span> Working&hellip;';
      btn.disabled = true;
    } else {
      btn.innerHTML = btn.dataset.origText || btn.innerHTML;
      btn.disabled = false;
    }
  }

  function fieldStatus(el, cls, text) {
    el.className = "field-status " + cls;
    el.textContent = text;
  }

  // -----------------------------------------------------------------------
  // Navigation
  // -----------------------------------------------------------------------

  function goToStep(n) {
    state.currentStep = n;

    panels.forEach((p, i) => {
      p.classList.toggle("active", i + 1 === n);
    });

    steps.forEach((s) => {
      const sn = +s.dataset.step;
      s.classList.remove("active", "done");
      if (sn === n) s.classList.add("active");
      else if (sn < n) s.classList.add("done");
    });

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $$("[data-back]").forEach((btn) => {
    btn.addEventListener("click", () => goToStep(+btn.dataset.back));
  });

  // -----------------------------------------------------------------------
  // Step 1 — Credentials
  // -----------------------------------------------------------------------

  $$(".toggle-vis").forEach((btn) => {
    btn.addEventListener("click", () => {
      const inp = $(`#${btn.dataset.target}`);
      inp.type = inp.type === "password" ? "text" : "password";
    });
  });

  $("#btn-validate").addEventListener("click", async () => {
    const tokenInput = $("#do-token");
    const pmmInput = $("#pmm-password");
    const tokenStatus = $("#token-status");
    const pmmStatus = $("#pmm-status");
    const btn = $("#btn-validate");

    state.doToken = tokenInput.value.trim();
    state.pmmPassword = pmmInput.value.trim();

    if (!state.doToken) {
      fieldStatus(tokenStatus, "err", "Token is required.");
      return;
    }
    if (!state.pmmPassword) {
      fieldStatus(pmmStatus, "err", "Password is required.");
      return;
    }

    setLoading(btn, true);
    fieldStatus(tokenStatus, "loading", "Validating token…");
    fieldStatus(pmmStatus, "loading", "Validating PMM password…");

    const tokenRes = await api("/api/validate-token", { do_token: state.doToken });
    if (!tokenRes.ok) {
      fieldStatus(tokenStatus, "err", tokenRes.message);
      fieldStatus(pmmStatus, "", "");
      setLoading(btn, false);
      return;
    }
    fieldStatus(tokenStatus, "ok", "Token valid.");

    const pmmRes = await api("/api/validate-pmm", { pmm_password: state.pmmPassword });
    if (!pmmRes.ok) {
      fieldStatus(pmmStatus, "err", pmmRes.message);
      setLoading(btn, false);
      return;
    }
    fieldStatus(pmmStatus, "ok", "PMM connected.");

    setLoading(btn, false);

    loadEngines();
    goToStep(2);
  });

  // -----------------------------------------------------------------------
  // Step 2 — Engine selection
  // -----------------------------------------------------------------------

  async function loadEngines() {
    const res = await fetch("/api/engines");
    const data = await res.json();
    const container = $("#engine-cards");
    container.innerHTML = "";

    data.engines.forEach((eng) => {
      const card = document.createElement("div");
      card.className = "engine-card" + (eng.supported ? "" : " disabled");
      card.dataset.engine = eng.id;
      card.innerHTML = `
        <div class="engine-card-name">${eng.name}</div>
        <span class="engine-card-badge ${eng.supported ? "badge-supported" : "badge-coming"}">${eng.supported ? "Supported" : "Coming Soon"}</span>
      `;

      if (eng.supported) {
        card.addEventListener("click", () => {
          $$(".engine-card").forEach((c) => c.classList.remove("selected"));
          card.classList.add("selected");
          state.selectedEngine = eng.id;
          $("#btn-fetch-dbs").disabled = false;
        });
      }

      container.appendChild(card);
    });
  }

  $("#btn-fetch-dbs").addEventListener("click", async () => {
    const btn = $("#btn-fetch-dbs");
    state.usePrivate = $("#use-private").checked;

    setLoading(btn, true);

    const res = await api("/api/databases", {
      do_token: state.doToken,
      pmm_password: state.pmmPassword,
      engine: state.selectedEngine,
      use_private: state.usePrivate,
    });

    setLoading(btn, false);

    if (!res.ok) {
      toast(res.message, "error");
      return;
    }

    state.databases = res.databases;
    renderDbList();
    goToStep(3);
  });

  // -----------------------------------------------------------------------
  // Step 3 — Database selection
  // -----------------------------------------------------------------------

  function isOnline(db) {
    return db.status === "online";
  }

  function renderDbList() {
    const wrap = $("#db-list-wrap");
    const dbs = state.databases;

    if (!dbs.length) {
      wrap.innerHTML =
        '<div class="empty-state">No databases found for the selected engine.</div>';
      return;
    }

    const selectable = dbs.filter((d) => !d.monitored && isOnline(d));

    let html = "";

    if (selectable.length > 1) {
      html += `
        <div class="select-all-row">
          <input type="checkbox" class="db-check" id="select-all">
          <label for="select-all">Select all available (${selectable.length})</label>
        </div>`;
    }

    dbs.forEach((db, idx) => {
      const online = isOnline(db);
      const canSelect = !db.monitored && online;
      const disabled = canSelect ? "" : "disabled";

      let rowClass = "db-row";
      if (db.monitored) rowClass += " monitored";
      else if (!online) rowClass += " offline";

      let badge = "";
      if (db.monitored) {
        badge = `<button class="btn btn-sm btn-danger-ghost btn-remove" data-idx="${idx}" data-service="${db.pmm_service_name}">Remove</button>`;
      } else if (!online) {
        badge = `<span class="offline-badge">${db.status}</span>`;
      }

      html += `
        <div class="${rowClass}" data-idx="${idx}">
          <input type="checkbox" class="db-check" data-idx="${idx}" ${disabled}>
          <div class="db-info">
            <div class="db-name">${db.name}</div>
            <div class="db-meta">
              <span class="db-tag">${db.region}</span>
              <span class="db-tag">${db.host}:${db.port}</span>
              <span class="db-tag">${db.num_nodes} node${db.num_nodes > 1 ? "s" : ""}</span>
              <span class="db-tag">${online ? db.status : '<strong style="color:var(--color-danger)">' + db.status + '</strong>'}</span>
            </div>
          </div>
          ${badge}
        </div>`;
    });

    wrap.innerHTML = html;

    const selectAll = wrap.querySelector("#select-all");
    if (selectAll) {
      selectAll.addEventListener("change", () => {
        wrap.querySelectorAll(".db-check:not(#select-all):not([disabled])").forEach((cb) => {
          cb.checked = selectAll.checked;
        });
        syncDbSelection();
      });
    }

    wrap.querySelectorAll(".db-check:not(#select-all)").forEach((cb) => {
      cb.addEventListener("change", syncDbSelection);
    });

    wrap.querySelectorAll(".db-row:not(.monitored):not(.offline)").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.classList.contains("db-check")) return;
        if (e.target.closest(".btn-remove")) return;
        const cb = row.querySelector(".db-check");
        cb.checked = !cb.checked;
        syncDbSelection();
      });
    });

    wrap.querySelectorAll(".btn-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        handleRemove(+btn.dataset.idx, btn.dataset.service, btn);
      });
    });

    syncDbSelection();
  }

  async function handleRemove(idx, serviceName, btn) {
    if (!confirm(`Remove "${serviceName}" from PMM monitoring?`)) return;

    setLoading(btn, true);

    const res = await api("/api/remove", {
      pmm_password: state.pmmPassword,
      service_name: serviceName,
      engine: state.selectedEngine,
    });

    setLoading(btn, false);

    if (res.ok) {
      state.databases[idx].monitored = false;
      state.databases[idx].pmm_service_name = "";
      renderDbList();
      toast(`Removed "${serviceName}" from PMM.`, "success");
    } else {
      toast(res.message || "Failed to remove service.", "error");
    }
  }

  function syncDbSelection() {
    const selected = [];
    $$("#db-list-wrap .db-check:not(#select-all)").forEach((cb) => {
      if (cb.checked) {
        selected.push(state.databases[+cb.dataset.idx]);
      }
    });
    state.selectedDbs = selected;
    $("#btn-to-user").disabled = selected.length === 0;
  }

  $("#btn-to-user").addEventListener("click", () => {
    renderUserSections();
    goToStep(4);
  });

  // -----------------------------------------------------------------------
  // Step 4 — Monitoring user setup
  // -----------------------------------------------------------------------

  function renderUserSections() {
    const container = $("#user-sections");
    container.innerHTML = "";

    state.selectedDbs.forEach((db) => {
      const key = db.id;

      if (!state.userCredentials[key]) {
        state.userCredentials[key] = { mode: "auto", username: "pmm_monitor", password: "", ready: false };
      }

      const cred = state.userCredentials[key];

      const section = document.createElement("div");
      section.className = "user-section";
      section.dataset.dbId = key;
      section.innerHTML = `
        <div class="user-section-header">
          <span class="user-section-title">${db.name}</span>
          <div class="user-mode-toggle">
            <button class="mode-btn ${cred.mode === "auto" ? "active" : ""}" data-mode="auto">Auto-create</button>
            <button class="mode-btn ${cred.mode === "manual" ? "active" : ""}" data-mode="manual">Manual</button>
          </div>
        </div>
        <div class="user-form">
          ${cred.mode === "auto" ? `
            <p class="hint" style="margin-bottom:0.65rem">The monitoring user <strong>pmm_monitor</strong> will be created automatically via the DigitalOcean API. Your API token must have <strong>write</strong> permissions.</p>
            <button class="btn btn-sm btn-success btn-create-user" data-db-id="${db.id}" data-db-name="${db.name}">Create User Now</button>
          ` : `
            <p class="hint" style="margin-bottom:0.65rem">Enter the credentials of an existing monitoring user.</p>
            <div class="form-row">
              <div class="form-group" style="margin-bottom:0">
                <label>Username</label>
                <input type="text" class="manual-user" data-db-id="${db.id}" value="${cred.username}" placeholder="pmm_monitor">
              </div>
              <div class="form-group" style="margin-bottom:0">
                <label>Password</label>
                <input type="password" class="manual-pass" data-db-id="${db.id}" value="${cred.password}" placeholder="password">
              </div>
            </div>
          `}
          <div class="user-status" data-db-id="${db.id}"></div>
        </div>
      `;

      section.querySelectorAll(".mode-btn").forEach((mbtn) => {
        mbtn.addEventListener("click", () => {
          cred.mode = mbtn.dataset.mode;
          cred.ready = false;
          renderUserSections();
        });
      });

      const createBtn = section.querySelector(".btn-create-user");
      if (createBtn) {
        createBtn.addEventListener("click", () => handleAutoCreate(db, createBtn));
      }

      const manualUser = section.querySelector(".manual-user");
      const manualPass = section.querySelector(".manual-pass");
      if (manualUser && manualPass) {
        const sync = () => {
          cred.username = manualUser.value.trim();
          cred.password = manualPass.value.trim();
          cred.ready = !!(cred.username && cred.password);
        };
        manualUser.addEventListener("input", sync);
        manualPass.addEventListener("input", sync);
        sync();
      }

      container.appendChild(section);
    });
  }

  async function handleAutoCreate(db, btn) {
    const key = db.id;
    const statusEl = $(`.user-status[data-db-id="${db.id}"]`);
    setLoading(btn, true);
    fieldStatus(statusEl, "loading", "Creating user…");

    const res = await api("/api/create-user", {
      do_token: state.doToken,
      db_id: db.id,
      db_name: db.name,
      engine: state.selectedEngine,
    });

    setLoading(btn, false);

    if (res.ok) {
      state.userCredentials[key] = {
        mode: "auto",
        username: res.username,
        password: res.password,
        ready: true,
      };
      fieldStatus(statusEl, "ok", `User "${res.username}" ready.`);
      btn.textContent = "User Created";
      btn.disabled = true;
      toast(`User "${res.username}" created for ${db.name}`, "success");
    } else if (res.error_code === "user_exists") {
      const username = res.username || "pmm_monitor";
      statusEl.className = "user-status";
      statusEl.innerHTML = `
        <div class="user-exists-notice">
          <p class="user-exists-title">User "${username}" already exists on "${db.name}"</p>
          <p>Switch to <strong>Manual</strong> mode above and enter the existing user's credentials.</p>
          <p class="user-exists-help-title">How to find the password:</p>
          <ul>
            <li><strong>DigitalOcean UI:</strong> Go to <a href="https://cloud.digitalocean.com/databases" target="_blank" rel="noopener">Databases</a> &rarr; select <em>${db.name}</em> &rarr; <em>Users &amp; Databases</em> tab &rarr; click <em>show-password</em> next to <strong>${username}</strong>.</li>
            <li><strong>DigitalOcean API:</strong><br><code>curl -s -H "Authorization: Bearer $DIGITALOCEAN_API_TOKEN" "https://api.digitalocean.com/v2/databases/${db.id}/users/${username}" | jq '.user.password'</code></li>
          </ul>
        </div>
      `;
      state.userCredentials[key] = { mode: "auto", username: username, password: "", ready: false };
    } else {
      fieldStatus(statusEl, "err", res.message || "Failed to create user.");
      toast(res.message || "Failed to create user.", "error");
    }
  }

  $("#btn-to-integrate").addEventListener("click", () => {
    const notReady = state.selectedDbs.filter(
      (db) => !state.userCredentials[db.id]?.ready
    );
    if (notReady.length) {
      toast(
        `Monitoring user not configured for: ${notReady.map((d) => d.name).join(", ")}`,
        "warning"
      );
      return;
    }
    goToStep(5);
    runIntegrations();
  });

  // -----------------------------------------------------------------------
  // Step 5 — Integration execution
  // -----------------------------------------------------------------------

  async function runIntegrations() {
    const container = $("#integration-results");
    container.innerHTML = "";

    for (const db of state.selectedDbs) {
      const cred = state.userCredentials[db.id];
      const card = document.createElement("div");
      card.className = "result-card";
      card.id = `result-${db.id}`;
      card.innerHTML = `
        <div class="result-header">
          <svg class="result-icon pending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
          <span class="result-name">${db.name}</span>
        </div>
        <div class="result-output">Adding to PMM…</div>
      `;
      container.appendChild(card);
    }

    for (const db of state.selectedDbs) {
      const cred = state.userCredentials[db.id];
      const card = $(`#result-${db.id}`);
      const icon = card.querySelector(".result-icon");
      const output = card.querySelector(".result-output");

      const res = await api("/api/integrate", {
        pmm_password: state.pmmPassword,
        engine: state.selectedEngine,
        instance: {
          name: db.name,
          host: db.host,
          port: db.port,
          username: cred.username,
          password: cred.password,
        },
      });

      icon.classList.remove("pending");

      if (res.ok) {
        icon.classList.add("ok");
        icon.innerHTML =
          '<path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>';
        output.textContent = res.output || "Successfully added to PMM.";

        if (res.post_steps) {
          const ps = document.createElement("div");
          ps.className = "post-steps";
          let html = '<div class="post-steps-title">Post-Integration Steps</div>';

          if (res.post_steps.steps && res.post_steps.steps.length) {
            res.post_steps.steps.forEach((step) => {
              html += `<div class="post-step-item">`;
              html += `<div class="post-step-heading">${step.title}</div>`;
              html += `<p class="post-step-desc">${step.description}</p>`;
              html += `<pre class="post-step-cmd">${step.command}</pre>`;
              html += `</div>`;
            });
          }

          if (res.post_steps.note) {
            html += `<div class="post-step-note">${res.post_steps.note}</div>`;
          }

          ps.innerHTML = html;
          card.appendChild(ps);
        }
      } else {
        icon.classList.add("fail");
        icon.innerHTML =
          '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>';
        output.textContent = res.message + (res.output ? "\n\n" + res.output : "");
      }
    }
  }

  // -----------------------------------------------------------------------
  // Start over
  // -----------------------------------------------------------------------

  $("#btn-start-over").addEventListener("click", () => {
    state.selectedEngine = null;
    state.databases = [];
    state.selectedDbs = [];
    state.userCredentials = {};
    goToStep(1);
  });

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------

  goToStep(1);
})();
