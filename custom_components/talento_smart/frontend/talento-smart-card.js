class TalentoSmartCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("Angiv entity: sensor.xxx_timerprogram");
    this.config = config;
    this._draft = null;
    this._lastEntityState = null;
    this.render();
  }

  set hass(hass) {
    const firstRender = !this._hass;
    this._hass = hass;
    const st = hass.states[this.config?.entity];

    if (firstRender) {
      if (st) {
        this._lastEntityState = st.last_updated;
        this._loadDraft(st);
      }
      this.render();
      return;
    }

    // Do not rebuild the editor while the user is editing.
    // Rebuilding closes Android's native time picker.
    if (this._dirty || this._editing || this._busy) return;

    if (st && st.last_updated !== this._lastEntityState) {
      this._lastEntityState = st.last_updated;
      this._loadDraft(st);
      this.render();
    }
  }

  getCardSize() { return 8; }

  _loadDraft(st) {
    if (!st) return;
    const a = st.attributes || {};
    this._draft = {
      program_name: a.program_name || "Prog1",
      priority: Number(a.priority || 0),
      switching_times: (a.switching_times || []).map(x => ({
        talento_function: x.talento_function || "ON",
        mode: x.mode || (x.kind === "clock" ? "clock" : "sunset"),
        time: x.time || "00:00",
        offset_minutes: Number(x.offset_minutes || 0),
        day_mask: Number(x.day_mask ?? parseInt((x.day_mask_hex || "0x7F"), 16) ?? 0x7F),
      }))
    };
    this._dirty = false;
  }

  _entity() {
    return this._hass?.states?.[this.config?.entity];
  }

  async _service(service, data={}) {
    if (!this._hass) return;
    this._busy = service;
    this._message = "";
    this.render();
    try {
      await this._hass.callService("talento_smart", service, data);
      this._message = service === "write_program"
        ? "Program sendt. Home Assistant læser det tilbage og verificerer."
        : "Udført.";
      if (service === "set_mode" || service === "read_mode") {
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      if (service === "read_program") this._dirty = false;
    } catch (err) {
      this._message = "Fejl: " + (err?.message || err);
    } finally {
      this._busy = null;
      this.render();
    }
  }

  _address() {
    return this._entity()?.attributes?.address;
  }

  _modeEntityId() {
    if (this.config?.mode_entity) return this.config.mode_entity;

    // Auto-detect the Talento Driftstilstand select belonging to the same device/name.
    const programEntity = this._entity();
    const programName = (programEntity?.attributes?.friendly_name || "").toLowerCase();
    const prefix = programName.replace(/\s*timerprogram\s*$/i, "").trim();

    const candidates = Object.entries(this._hass?.states || {})
      .filter(([id, st]) =>
        id.startsWith("select.") &&
        (st.attributes?.friendly_name || "").toLowerCase().includes("driftstilstand")
      );

    if (prefix) {
      const match = candidates.find(([id, st]) =>
        (st.attributes?.friendly_name || "").toLowerCase().includes(prefix)
      );
      if (match) return match[0];
    }

    // If there is only one mode select in HA, use it as fallback.
    return candidates.length === 1 ? candidates[0][0] : null;
  }

  _currentMode() {
    const id = this._modeEntityId();
    return id ? this._hass?.states?.[id]?.state : null;
  }

  _days(mask) {
    const d = [
      ["M", 0x02], ["T", 0x04], ["O", 0x08], ["T", 0x10],
      ["F", 0x20], ["L", 0x40], ["S", 0x01]
    ];
    return d.map(([label, bit]) =>
      `<button class="day ${mask & bit ? "on" : ""}" data-day="${bit}">${label}</button>`
    ).join("");
  }

  _actual(fn) {
    return fn === "OFF" ? "TÆNDT" : "SLUKKET";
  }

  _hourOptions(selected) {
    return Array.from({length:24}, (_,h) => {
      const v = String(h).padStart(2,"0");
      return `<option value="${v}" ${v === selected ? "selected" : ""}>${v}</option>`;
    }).join("");
  }

  _minuteOptions(selected) {
    return Array.from({length:60}, (_,m) => {
      const v = String(m).padStart(2,"0");
      return `<option value="${v}" ${v === selected ? "selected" : ""}>${v}</option>`;
    }).join("");
  }

  _row(entry, i) {
    const astro = entry.mode !== "clock";
    return `
      <div class="program-row" data-index="${i}">
        <div class="row-top">
          <span class="row-no">${i + 1}</span>
          <select class="fn">
            <option value="ON" ${entry.talento_function === "ON" ? "selected" : ""}>ON</option>
            <option value="OFF" ${entry.talento_function === "OFF" ? "selected" : ""}>OFF</option>
          </select>
          <select class="mode">
            <option value="clock" ${entry.mode === "clock" ? "selected" : ""}>Klokkeslæt</option>
            <option value="sunset" ${entry.mode === "sunset" ? "selected" : ""}>Solnedgang</option>
            <option value="sunrise" ${entry.mode === "sunrise" ? "selected" : ""}>Solopgang</option>
          </select>
          ${astro
            ? `<label class="timebox">Offset <input class="offset" type="number" min="-128" max="127" value="${entry.offset_minutes}"> min</label>`
            : (() => {
                const parts = (entry.time || "00:00").split(":");
                const hh = parts[0] || "00";
                const mm = parts[1] || "00";
                return `<div class="clock-select">
                  <select class="hour" aria-label="Time">${this._hourOptions(hh)}</select>
                  <span class="colon">:</span>
                  <select class="minute" aria-label="Minut">${this._minuteOptions(mm)}</select>
                </div>`;
              })()
          }
          <button class="delete" title="Slet">✕</button>
        </div>
        <div class="row-bottom">
          <div class="days">${this._days(entry.day_mask)}</div>
          <div class="actual">Faktisk lys: <b>${this._actual(entry.talento_function)}</b></div>
        </div>
      </div>`;
  }

  render() {
    if (!this.config) return;
    const st = this._entity();
    if (!this._draft && st) this._loadDraft(st);

    const name = st?.attributes?.program_name || "Talento Smart";
    const address = st?.attributes?.address || "";
    const d = this._draft;
    const disabled = this._busy ? "disabled" : "";

    this.innerHTML = `
      <ha-card>
        <style>
          ha-card { padding: 16px; }
          .header { display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
          .title { font-size:20px; font-weight:600; }
          .sub { opacity:.65; font-size:12px; margin-top:2px; }
          .actions { display:flex; gap:8px; flex-wrap:wrap; }
          .modebar { display:flex; gap:7px; align-items:center; flex-wrap:wrap; margin-top:12px; }
          .mode-label { font-weight:600; margin-right:2px; }
          .modebtn.mode-active {
            background: var(--primary-color);
            color: white;
            font-weight: 700;
            box-shadow: inset 0 0 0 2px rgba(255,255,255,.25);
          }
          button, select, input { font:inherit; }
          .action { border:0; border-radius:18px; padding:8px 13px; cursor:pointer; background:var(--secondary-background-color); color:var(--primary-text-color); }
          .primary { background:var(--primary-color); color:var(--text-primary-color, white); }
          .danger { background:var(--error-color); color:white; }
          .editor { margin-top:16px; }
          .program-name { display:flex; gap:8px; align-items:center; margin-bottom:10px; }
          .program-name input { max-width:180px; padding:7px; border:1px solid var(--divider-color); border-radius:6px; background:var(--card-background-color); color:var(--primary-text-color); }
          .program-row { border-top:1px solid var(--divider-color); padding:12px 0; }
          .row-top { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
          .row-no { width:24px; height:24px; display:grid; place-items:center; border-radius:50%; background:var(--secondary-background-color); font-size:12px; }
          select, input[type=number] { padding:7px; border:1px solid var(--divider-color); border-radius:6px; background:var(--card-background-color); color:var(--primary-text-color); }
          .clock-select { display:flex; align-items:center; gap:4px; }
          .clock-select select { min-width:62px; }
          .colon { font-weight:600; }
          .timebox { display:flex; gap:5px; align-items:center; }
          .timebox input { width:64px; }
          .delete { border:0; background:transparent; color:var(--error-color); font-size:18px; cursor:pointer; margin-left:auto; }
          .row-bottom { display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; margin-top:10px; padding-left:32px; }
          .days { display:flex; gap:5px; }
          .day { border:1px solid var(--divider-color); border-radius:50%; width:31px; height:31px; padding:0; background:transparent; color:var(--secondary-text-color); cursor:pointer; }
          .day.on { background:var(--primary-color); color:white; border-color:var(--primary-color); }
          .actual { font-size:13px; opacity:.8; }
          .footer { border-top:1px solid var(--divider-color); padding-top:14px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
          .message { margin-top:10px; font-size:13px; opacity:.8; }
          .warning { margin:12px 0; padding:10px; border-radius:8px; background:var(--secondary-background-color); font-size:13px; }
          .dirty { color:var(--warning-color, #ff9800); font-weight:600; }
          @media (max-width: 600px) {
            ha-card { padding:12px; }
            .row-top { align-items:stretch; }
            .row-top select { flex:1; }
            .row-bottom { padding-left:0; }
            .actual { width:100%; }
          }
        </style>

        <div class="header">
          <div>
            <div class="title">${this.config.title || name || "Talento Smart"}</div>
            <div class="sub">${address} ${this._dirty ? ' · <span class="dirty">ikke gemt</span>' : ""}</div>
          </div>
          <div class="actions">
            <button class="action read" ${disabled}>↻ Hent</button>
            <button class="action sync" ${disabled}>◷ Synk tid</button>
          </div>
        </div>
        <div class="modebar">
          <span class="mode-label">Drift:</span>
          ${["AUTO","OVR","FIX ON","FIX OFF"].map(mode => `
            <button class="action modebtn ${this._currentMode() === mode ? "mode-active" : ""}"
                    data-mode="${mode}" ${disabled}>${mode}</button>
          `).join("")}
          <button class="action readmode" ${disabled}>↻</button>
        </div>

        ${!d ? `<div class="warning">Programmet er ikke hentet endnu. Tryk <b>Hent</b>.</div>` : `
          <div class="editor">
            <div class="program-name">
              <label>Programnavn</label>
              <input class="name" maxlength="11" value="${d.program_name.replace(/"/g, "&quot;")}">
              <span>${d.switching_times.length} skiftetider</span>
            </div>

            ${d.switching_times.map((x,i) => this._row(x,i)).join("")}

            <div class="footer">
              <button class="action add" ${disabled}>＋ Tilføj skiftetid</button>
              <button class="action primary save" ${disabled}>Gem til Talento</button>
              
            </div>
          </div>
        `}
        ${this._busy ? `<div class="message">Arbejder: ${this._busy} …</div>` : ""}
        ${this._message ? `<div class="message">${this._message}</div>` : ""}
      </ha-card>`;

    this._bind();
  }

  _markDirty(redraw = false) {
    this._dirty = true;
    if (redraw) this.render();
  }

  _bind() {
    const q = s => this.querySelector(s);

    this.querySelectorAll("input, select").forEach(el => {
      el.addEventListener("focus", () => { this._editing = true; });
      el.addEventListener("blur", () => { this._editing = false; });
    });
    q(".read")?.addEventListener("click", () => this._service("read_program", {address:this._address()}));
    q(".sync")?.addEventListener("click", () => this._service("sync_time", {address:this._address()}));
    q(".readmode")?.addEventListener("click", () => this._service("read_mode", {address:this._address()}));
    this.querySelectorAll(".modebtn").forEach(btn => btn.addEventListener("click", () =>
      this._service("set_mode", {address:this._address(), mode:btn.dataset.mode})
    ));

    q(".name")?.addEventListener("change", e => {
      this._draft.program_name = e.target.value;
      this._markDirty();
    });

    this.querySelectorAll(".program-row").forEach(row => {
      const i = Number(row.dataset.index);
      const entry = this._draft.switching_times[i];

      row.querySelector(".fn")?.addEventListener("change", e => {
        entry.talento_function = e.target.value; this._markDirty(true);
      });
      row.querySelector(".mode")?.addEventListener("change", e => {
        entry.mode = e.target.value; this._markDirty(true);
      });
      const hour = row.querySelector(".hour");
      const minute = row.querySelector(".minute");
      const updateTime = () => {
        if (!hour || !minute) return;
        entry.time = `${hour.value}:${minute.value}`;
        this._markDirty();
      };
      hour?.addEventListener("change", updateTime);
      minute?.addEventListener("change", updateTime);
      row.querySelector(".offset")?.addEventListener("change", e => {
        entry.offset_minutes = Number(e.target.value); this._markDirty();
      });
      row.querySelector(".delete")?.addEventListener("click", () => {
        this._draft.switching_times.splice(i,1); this._markDirty(true);
      });
      row.querySelectorAll(".day").forEach(btn => btn.addEventListener("click", () => {
        const bit = Number(btn.dataset.day);
        entry.day_mask ^= bit;
        this._markDirty(true);
      }));
    });

    q(".add")?.addEventListener("click", () => {
      this._draft.switching_times.push({
        talento_function:"ON", mode:"clock", time:"12:00",
        offset_minutes:0, day_mask:0x7F
      });
      this._markDirty();
    });

    q(".save")?.addEventListener("click", async () => {
      if (!this._draft.switching_times.length) {
        this._message = "Programmet skal have mindst én skiftetid."; this.render(); return;
      }
      const ok = confirm(
        "Skriv det viste program til Talento Smart?\n\n" +
        "Home Assistant tager først backup og kontrollerer programmet med read-back efter skrivningen."
      );
      if (!ok) return;
      await this._service("write_program", {
        address:this._address(),
        program: JSON.parse(JSON.stringify(this._draft))
      });
    });
  }
}

customElements.define("talento-smart-card", TalentoSmartCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "talento-smart-card",
  name: "Talento Smart Programeditor",
  description: "Læs, redigér og skriv Grässlin Talento Smart timerprogrammer via Home Assistant."
});
console.info("%c TALENTO-SMART-CARD %c v1.1.0 ", "color:white;background:#7b1fa2;font-weight:bold", "");
