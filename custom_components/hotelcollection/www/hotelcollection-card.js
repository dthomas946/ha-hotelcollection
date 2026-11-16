/*
 * Hotel Collection diffuser card (read-only schedule view)
 *   type: custom:hotelcollection-card
 *   device: villa          # entity prefix, e.g. switch.villa_power  (default "villa")
 *   name: Villa            # optional title
 *
 * Shows the diffuser's five modes on a weekly 24 h timeline with a "now" marker,
 * which mode is running, oil level, run time left, scent, and power/fan toggles.
 * Tap a mode (bar or list row) to edit its days, times, spray and pause seconds;
 * saving calls the hotelcollection.set_mode action.
 * Created with Claude.ai. MIT licence. Layout idea from the schedule overview in
 * jrx-code/hassio-integration-aroma-link (MIT).
 */

const HC_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HC_ML_PER_OZ = 29.5735;
const hcOz = (ml) => (isNaN(ml) ? "–" : (ml / HC_ML_PER_OZ).toFixed(1));

/* ------------------------------------------------------------ pure helpers */

function hcMinutes(hhmm) {
  const [h, m] = String(hhmm || "0:0").split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** Monday = 0 … Sunday = 6 */
function hcDayIndex(date) {
  return (date.getDay() + 6) % 7;
}

/** Bars to draw for one weekday: [{slot, startMin, endMin, enabled, work_s, pause_s}] */
function hcBarsForDay(slots, day) {
  const bars = [];
  for (const s of slots || []) {
    if (!(s.days || []).includes(HC_DAYS[day])) continue;
    const a = hcMinutes(s.start);
    let b = hcMinutes(s.end);
    if (s.end === "23:59") b = 1440;
    if (b > a) {
      bars.push({ ...s, startMin: a, endMin: b });
    } else if (b < a) {
      // runs past midnight: draw the evening part here; the morning part
      // belongs to the next day and is added by hcCarryOver
      bars.push({ ...s, startMin: a, endMin: 1440 });
    }
  }
  return bars.concat(hcCarryOver(slots, day));
}

function hcCarryOver(slots, day) {
  const prev = HC_DAYS[(day + 6) % 7];
  const out = [];
  for (const s of slots || []) {
    const a = hcMinutes(s.start);
    const b = hcMinutes(s.end);
    if (b < a && (s.days || []).includes(prev) && b > 0) {
      out.push({ ...s, startMin: 0, endMin: b });
    }
  }
  return out;
}

/** "Mon–Fri", "Sat–Sun", "Mon, Wed, Fri", "Every day", "No days" */
function hcDaySummary(days) {
  const idx = HC_DAYS.map((d, i) => ((days || []).includes(d) ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) return "No days";
  if (idx.length === 7) return "Every day";
  const runs = [];
  for (const i of idx) {
    const last = runs[runs.length - 1];
    if (last && i === last[1] + 1) last[1] = i;
    else runs.push([i, i]);
  }
  return runs
    .map(([a, b]) => (a === b ? HC_DAYS[a] : b === a + 1 ? `${HC_DAYS[a]}, ${HC_DAYS[b]}` : `${HC_DAYS[a]}–${HC_DAYS[b]}`))
    .join(", ");
}

/** The enabled mode covering `date`, or null. */
function hcActiveMode(slots, date) {
  const day = hcDayIndex(date);
  const now = date.getHours() * 60 + date.getMinutes();
  for (const bar of hcBarsForDay(slots, day)) {
    if (bar.enabled && now >= bar.startMin && now < bar.endMin) return bar;
  }
  return null;
}

/** Next enabled mode start after `date` within 7 days: {slot, day, start} or null. */
function hcNextMode(slots, date) {
  const today = hcDayIndex(date);
  const now = date.getHours() * 60 + date.getMinutes();
  for (let offset = 0; offset < 8; offset++) {
    const day = (today + offset) % 7;
    const starts = (slots || [])
      .filter((s) => s.enabled && (s.days || []).includes(HC_DAYS[day]))
      .map((s) => ({ slot: s, min: hcMinutes(s.start) }))
      .filter((x) => offset > 0 || x.min > now)
      .sort((x, y) => x.min - y.min);
    if (starts.length) return { slot: starts[0].slot, day, offset, start: starts[0].slot.start };
  }
  return null;
}

/* ------------------------------------------------------------------- card */

const hcEsc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class HotelCollectionCard extends HTMLElement {
  setConfig(config) {
    this._config = { device: "villa", ...(config || {}) };
    this._lastKey = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  static getStubConfig() {
    return { device: "villa" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "device", required: true, selector: { text: {} } },
        { name: "name", selector: { text: {} } },
      ],
      computeLabel: (s) => ({ device: "Device prefix (e.g. villa)", name: "Title" }[s.name]),
    };
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _id(domain, suffix) {
    return `${domain}.${this._config.device}_${suffix}`;
  }

  _st(domain, suffix) {
    return this._hass ? this._hass.states[this._id(domain, suffix)] : undefined;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._edit) return; // keep the editor's inputs while it is open
    const ids = [
      ["switch", "power"], ["switch", "fan"], ["sensor", "oil_level"], ["sensor", "oil_remaining"],
      ["sensor", "bottle_size"], ["sensor", "run_time_remaining"], ["sensor", "consumption_rate"],
      ["sensor", "active_schedule_slots"], ["text", "scent"], ["sensor", "oil_days_left"],
      ["switch", "scent"], ["sensor", "scent_status"],
    ];
    const minute = Math.floor(Date.now() / 60000);
    const key = minute + "|" + ids.map(([d, s]) => {
      const st = this._st(d, s);
      return st ? st.last_updated + st.state : "-";
    }).join("|");
    if (key === this._lastKey) return;
    this._lastKey = key;
    this._render();
  }

  connectedCallback() {
    // keep the "now" marker moving even when no state changes
    this._timer = setInterval(() => { this._lastKey = null; if (this._hass && !this._edit) this.hass = this._hass; }, 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  _toggle(suffix) {
    this._hass.callService("switch", "toggle", { entity_id: this._id("switch", suffix) });
  }

  _more(domain, suffix) {
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId: this._id(domain, suffix) };
    this.dispatchEvent(ev);
  }

  _slots() {
    const sched = this._st("sensor", "active_schedule_slots");
    return (sched && sched.attributes.slots) || [];
  }

  _openEditor(slotNo) {
    const s = this._slots().find((x) => x.slot === slotNo);
    if (!s) return;
    this._edit = { slot: s.slot, days: [...(s.days || [])], start: s.start, end: s.end,
                   enabled: !!s.enabled, work_s: s.work_s, pause_s: s.pause_s };
    this._error = null;
    this._render();
  }

  _closeEditor() {
    this._edit = null;
    this._error = null;
    this._saving = false;
    this._lastKey = null;
    this._render();
  }

  async _callSetMode(data) {
    const payload = { ...data };
    if (this._config.config_entry_id) payload.config_entry_id = this._config.config_entry_id;
    await this._hass.callService("hotelcollection", "set_mode", payload);
  }

  async _saveEditor() {
    const e = this._edit;
    if (!e || this._saving) return;
    if (!e.days.length && e.enabled) { this._error = "Pick at least one day, or turn the mode off."; return this._render(); }
    if (!(e.work_s >= 5 && e.work_s <= 300 && e.pause_s >= 5 && e.pause_s <= 300)) {
      this._error = "Spray and pause must be 5–300 seconds."; return this._render();
    }
    if (hcMinutes(e.end) <= hcMinutes(e.start)) {
      this._error = "End must be after start — a mode can't run past midnight. Use 23:59 here and another mode from 00:00.";
      return this._render();
    }
    this._saving = true; this._error = null; this._render();
    try {
      await this._callSetMode({ mode: e.slot, enabled: e.enabled, days: e.days, start: e.start, end: e.end,
                                spray_seconds: Number(e.work_s), pause_seconds: Number(e.pause_s) });
      this._closeEditor();
    } catch (err) {
      this._saving = false;
      this._error = (err && err.message) || "The diffuser did not accept the change.";
      this._render();
    }
  }

  async _quickToggle(slotNo, enabled) {
    try { await this._callSetMode({ mode: slotNo, enabled }); }
    catch (err) { this._error = (err && err.message) || "Could not change the mode."; this._lastKey = null; this._render(); }
  }

  _listHtml(slots) {
    if (!slots.length) return "";
    const rows = slots.map((s) => `
      <div class="mrow ${s.enabled ? "" : "off"}" data-slot="${s.slot}">
        <div class="mnum">${s.slot}</div>
        <div class="mtxt"><div>${hcEsc(hcDaySummary(s.days))} · ${hcEsc(s.start)}–${hcEsc(s.end)}</div>
          <div class="msub">${s.work_s} s spray · ${s.pause_s} s pause</div></div>
        <label class="sw" title="${s.enabled ? "Turn mode off" : "Turn mode on"}">
          <input type="checkbox" data-toggle="${s.slot}" ${s.enabled ? "checked" : ""}><span></span></label>
        <button class="icon" data-edit="${s.slot}" title="Edit mode ${s.slot}"><ha-icon icon="mdi:pencil"></ha-icon></button>
      </div>`).join("");
    return `<div class="list"><div class="lhead">Modes</div>${rows}
      ${this._error && !this._edit ? `<div class="err">${hcEsc(this._error)}</div>` : ""}</div>`;
  }

  _editorHtml() {
    const e = this._edit;
    const chips = HC_DAYS.map((d) => `<button class="chip ${e.days.includes(d) ? "sel" : ""}" data-day="${d}">${d}</button>`).join("");
    return `
      <div class="editor">
        <div class="ehead"><span>Edit mode ${e.slot}</span>
          <label class="sw" title="Mode on/off"><input type="checkbox" id="e-en" ${e.enabled ? "checked" : ""}><span></span></label></div>
        <div class="chips">${chips}</div>
        <div class="fields">
          <label>Start<input type="time" id="e-start" value="${hcEsc(e.start)}"></label>
          <label>End<input type="time" id="e-end" value="${hcEsc(e.end)}"></label>
          <label>Spray (s)<input type="number" id="e-work" min="5" max="300" value="${e.work_s}"></label>
          <label>Pause (s)<input type="number" id="e-pause" min="5" max="300" value="${e.pause_s}"></label>
        </div>
        <div class="hint">Spray and pause: 5–300 s; at least 15 s of spray lets the diffuser draw and atomize the oil.
          ${e.work_s > 0 && e.work_s < 15 ? `<b>Under 15 s may give little or no mist.</b>` : ""}</div>
        ${this._error ? `<div class="err">${hcEsc(this._error)}</div>` : ""}
        <div class="eact">
          <button id="e-cancel" ${this._saving ? "disabled" : ""}>Cancel</button>
          <button id="e-save" class="on" ${this._saving ? "disabled" : ""}>${this._saving ? "Saving…" : "Save"}</button>
        </div>
      </div>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const sched = this._st("sensor", "active_schedule_slots");
    if (this._hass && !sched) {
      this.shadowRoot.innerHTML = `<ha-card><div class="warn">Entity ${hcEsc(this._id("sensor", "active_schedule_slots"))} not found. Check the <b>device</b> prefix.</div></ha-card>`;
      return;
    }
    const slots = (sched && sched.attributes.slots) || [];
    const power = this._st("switch", "power");
    const fan = this._st("switch", "fan");
    const scentSw = this._st("switch", "scent");
    const gate = this._st("sensor", "scent_status");
    const gated = !!(gate && gate.attributes.hvac_fan_entity);
    const pumpOn = power && power.state === "on";
    const on = scentSw ? scentSw.state === "on" : pumpOn;
    const fanOn = fan && fan.state === "on";
    const level = parseFloat(this._st("sensor", "oil_level")?.state);
    const remaining = this._st("sensor", "oil_remaining")?.state;
    const bottle = this._st("sensor", "bottle_size")?.state;
    const hours = parseFloat(this._st("sensor", "run_time_remaining")?.state);
    const rate = this._st("sensor", "consumption_rate")?.state;
    const scent = this._st("text", "scent")?.state;
    const daysLeft = parseFloat(this._st("sensor", "oil_days_left")?.state);
    const unavailable = power && power.state === "unavailable";

    const now = new Date();
    const today = hcDayIndex(now);
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const active = hcActiveMode(slots, now);
    const next = hcNextMode(slots, now);

    const nextTxt = next
      ? `next Mode ${next.slot.slot} ${next.offset === 0 ? "today" : next.offset === 1 ? "tomorrow" : HC_DAYS[next.day]} ${hcEsc(next.start)}`
      : "no modes enabled";
    let status;
    if (unavailable) status = `<span class="dot off"></span>Diffuser offline`;
    else if (!on) status = `<span class="dot off"></span>Off${gated ? " — HVAC pause won't turn it on until you do" : ""}`;
    else if (gated && gate.state === "waiting_for_hvac")
      status = `<span class="dot idle"></span>Paused · HVAC fan is off${active ? ` (Mode ${active.slot} scheduled)` : ""}`;
    else if (gated && gate.state === "starting")
      status = `<span class="dot idle"></span>Starting · waiting for airflow in the ducts`;
    else if (gated && gate.state === "outside_schedule")
      status = `<span class="dot idle"></span>Idle · ${nextTxt}`;
    else if (active)
      status = `<span class="dot run"></span>Mode ${active.slot} running · ${hcEsc(active.start)}–${hcEsc(active.end)} · ${active.work_s} s on / ${active.pause_s} s off`;
    else if (gated && !pumpOn) status = `<span class="dot idle"></span>Idle · ${nextTxt}`;
    else if (next) status = `<span class="dot idle"></span>Idle · ${nextTxt}`;
    else status = `<span class="dot idle"></span>No modes enabled`;

    const rows = HC_DAYS.map((label, d) => {
      const bars = hcBarsForDay(slots, d)
        .map((b) => {
          const left = (b.startMin / 1440) * 100;
          const width = ((b.endMin - b.startMin) / 1440) * 100;
          const isActive = active && d === today && b.slot === active.slot && on && pumpOn;
          const cls = ["bar", b.enabled ? "" : "disabled", isActive ? "active" : ""].join(" ");
          const tip = `Mode ${b.slot}: ${b.start}–${b.end}, ${b.work_s} s on / ${b.pause_s} s off${b.enabled ? "" : " (off)"}`;
          return `<div class="${cls}" data-bar="${b.slot}" style="left:${left}%;width:${width}%" title="${hcEsc(tip)} — tap to edit"><span>${b.slot}</span></div>`;
        })
        .join("");
      const marker = d === today ? `<div class="now" style="left:${(nowMin / 1440) * 100}%"></div>` : "";
      return `<div class="row ${d === today ? "today" : ""}"><div class="day">${label}</div><div class="track">${bars}${marker}</div></div>`;
    }).join("");

    const levelPct = isNaN(level) ? 0 : Math.max(0, Math.min(100, level));
    const lowOil = !isNaN(level) && level <= 10;
    const remMl = parseFloat(remaining);
    const capMl = parseFloat(bottle);
    const maxFill = isNaN(capMl) ? NaN : Math.floor(capMl * 0.9);
    const toFill = isNaN(maxFill) || isNaN(remMl) ? NaN : Math.max(0, maxFill - remMl);

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head { display:flex; align-items:center; gap:12px; }
        .title { font-size: 1.15rem; font-weight: 500; flex: 1; min-width: 0; }
        .scent { color: var(--secondary-text-color); font-size: .9rem; cursor: pointer; }
        .btns { display:flex; gap:8px; }
        button { border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color);
                 border-radius: 18px; padding: 6px 12px; font: inherit; cursor: pointer; display:flex; align-items:center; gap:6px; }
        button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
        button:disabled { opacity: .5; cursor: default; }
        ha-icon { --mdc-icon-size: 18px; }
        .status { margin: 12px 0 14px; font-size: .95rem; display:flex; align-items:center; }
        .dot { width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:8px; }
        .dot.run { background: var(--success-color, #43a047); }
        .dot.idle { background: var(--warning-color, #ffa000); }
        .dot.off { background: var(--disabled-text-color, #9e9e9e); }
        .grid { display:flex; flex-direction:column; gap:4px; }
        .row { display:flex; align-items:center; gap:8px; }
        .day { width: 32px; font-size: .8rem; color: var(--secondary-text-color); }
        .row.today .day { color: var(--primary-text-color); font-weight: 600; }
        .track { position:relative; flex:1; height: 20px; border-radius: 4px;
                 background: var(--secondary-background-color, rgba(127,127,127,.12)); overflow:hidden; }
        .bar { position:absolute; top:2px; bottom:2px; border-radius:3px; background: var(--primary-color); opacity:.55;
               display:flex; align-items:center; justify-content:center; font-size:.7rem; color: var(--text-primary-color, #fff); }
        .bar.disabled { opacity:.2; background: var(--disabled-text-color, #9e9e9e); }
        .bar.active { opacity:1; box-shadow: 0 0 0 2px var(--primary-text-color) inset; }
        .bar span { overflow:hidden; }
        .now { position:absolute; top:0; bottom:0; width:2px; background: var(--error-color, #db4437); }
        .axis { display:flex; margin-left:40px; font-size:.7rem; color: var(--secondary-text-color); justify-content: space-between; margin-top:2px; }
        .oil { margin-top: 16px; display:grid; grid-template-columns: 1fr auto; gap: 6px 12px; align-items:center; cursor:pointer; }
        .meter { position:relative; height: 10px; border-radius: 5px; background: var(--secondary-background-color, rgba(127,127,127,.12)); overflow:hidden; }
        .tick { position:absolute; top:-1px; bottom:-1px; width:2px; }
        .tick.max { background: var(--primary-text-color); opacity:.7; }
        .tick.low { background: var(--error-color, #db4437); opacity:.7; }
        .fill { height:100%; background: ${lowOil ? "var(--error-color, #db4437)" : "var(--primary-color)"}; }
        .num { font-size:.9rem; }
        .sub { grid-column: 1 / -1; font-size:.8rem; color: var(--secondary-text-color); line-height:1.4; }
        .warn { padding: 8px; color: var(--error-color); }
        .link { text-decoration: underline dotted; cursor: pointer; }
        .bar { cursor: pointer; }
        .list { margin-top: 14px; display:flex; flex-direction:column; gap:4px; }
        .lhead, .ehead { font-size:.85rem; color: var(--secondary-text-color); margin-bottom:2px; display:flex; align-items:center; justify-content:space-between; }
        .ehead span { color: var(--primary-text-color); font-weight:500; font-size:.95rem; }
        .mrow { display:flex; align-items:center; gap:10px; padding:6px 4px; border-radius:8px; }
        .mrow:hover { background: var(--secondary-background-color, rgba(127,127,127,.08)); }
        .mrow.off .mtxt { opacity:.5; }
        .mnum { width:22px; height:22px; border-radius:50%; background: var(--primary-color); color: var(--text-primary-color,#fff);
                display:flex; align-items:center; justify-content:center; font-size:.75rem; flex:none; }
        .mrow.off .mnum { background: var(--disabled-text-color, #9e9e9e); }
        .mtxt { flex:1; font-size:.9rem; min-width:0; }
        .msub { font-size:.75rem; color: var(--secondary-text-color); }
        button.icon { border:none; padding:4px; border-radius:50%; }
        .sw { position:relative; width:34px; height:20px; flex:none; display:inline-block; }
        .sw input { opacity:0; width:0; height:0; }
        .sw span { position:absolute; inset:0; border-radius:10px; background: var(--disabled-text-color,#9e9e9e); transition:.15s; cursor:pointer; }
        .sw span::before { content:""; position:absolute; width:16px; height:16px; left:2px; top:2px; border-radius:50%; background:#fff; transition:.15s; }
        .sw input:checked + span { background: var(--primary-color); }
        .sw input:checked + span::before { transform: translateX(14px); }
        .editor { margin-top:14px; padding:12px; border:1px solid var(--divider-color); border-radius:10px; display:flex; flex-direction:column; gap:12px; }
        .chips { display:flex; gap:6px; flex-wrap:wrap; }
        .chip { padding:4px 10px; border-radius:14px; }
        .chip.sel { background: var(--primary-color); color: var(--text-primary-color,#fff); border-color: var(--primary-color); }
        .fields { display:grid; grid-template-columns: repeat(auto-fit, minmax(110px,1fr)); gap:10px; }
        .fields label { display:flex; flex-direction:column; gap:4px; font-size:.8rem; color: var(--secondary-text-color); }
        .fields input { font: inherit; padding:6px 8px; border-radius:6px; border:1px solid var(--divider-color);
                        background: var(--card-background-color, transparent); color: var(--primary-text-color); color-scheme: light dark; }
        .eact { display:flex; justify-content:flex-end; gap:8px; }
        .err { color: var(--error-color, #db4437); font-size:.85rem; }
        .hint { color: var(--secondary-text-color); font-size:.8rem; }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${hcEsc(this._config.name || "Villa")}
            ${scent && scent !== "unknown" ? `<div class="scent" id="scent">${hcEsc(scent)}</div>` : ""}</div>
          <div class="btns">
            <button id="power" class="${on ? "on" : ""}" ${unavailable ? "disabled" : ""} title="${scentSw ? "Scent on/off (the HVAC pause follows this)" : "Power"}"><ha-icon icon="mdi:power"></ha-icon>${on ? "On" : "Off"}</button>
            <button id="fan" class="${fanOn ? "on" : ""}" ${unavailable ? "disabled" : ""} title="Fan"><ha-icon icon="mdi:fan"></ha-icon>Fan</button>
          </div>
        </div>
        <div class="status">${status}</div>
        <div class="grid">${rows}</div>
        <div class="axis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
        ${this._edit ? this._editorHtml() : this._listHtml(slots)}
        <div class="oil" id="oil">
          <div class="meter"><div class="fill" style="width:${levelPct}%"></div>
            <div class="tick low" style="left:10%" title="Low oil (10 %)"></div>
            <div class="tick max" style="left:90%" title="Max fill (90 %)"></div></div>
          <div class="num">${isNaN(level) ? "–" : Math.round(level) + " %"}</div>
          <div class="sub"><b>${remaining ?? "–"} mL</b> (${hcOz(remMl)} oz) in the bottle · bottle size ${bottle ?? "–"} mL (${hcOz(capMl)} oz)${isNaN(daysLeft) ? "" : ` · about <b>${Math.round(daysLeft)} days</b> left on this schedule`}</div>
          <div class="sub">Fill to 90 %: ${isNaN(maxFill) ? "–" : maxFill} mL (${hcOz(maxFill)} oz) · <b>room for ${isNaN(toFill) ? "–" : Math.round(toFill)} mL (${hcOz(toFill)} oz)</b> · ${isNaN(hours) ? "–" : Math.round(hours) + " h"} of spraying at <span class="link" id="rate">${rate ?? "–"} mL/h</span></div>
        </div>
      </ha-card>`;

    const $ = (id) => this.shadowRoot.getElementById(id);
    $("power")?.addEventListener("click", () => this._toggle(scentSw ? "scent" : "power"));
    $("fan")?.addEventListener("click", () => this._toggle("fan"));
    $("oil")?.addEventListener("click", () => this._more("number", "oil_remaining_setting"));
    $("rate")?.addEventListener("click", (ev) => { ev.stopPropagation(); this._more("number", "consumption_rate_setting"); });
    $("scent")?.addEventListener("click", () => this._more("text", "scent"));
    const root = this.shadowRoot;
    root.querySelectorAll("[data-bar]").forEach((el) => el.addEventListener("click", () => this._openEditor(Number(el.dataset.bar))));
    root.querySelectorAll("[data-edit]").forEach((el) => el.addEventListener("click", () => this._openEditor(Number(el.dataset.edit))));
    root.querySelectorAll("[data-toggle]").forEach((el) =>
      el.addEventListener("change", () => this._quickToggle(Number(el.dataset.toggle), el.checked)));
    if (this._edit) {
      const e = this._edit;
      root.querySelectorAll("[data-day]").forEach((el) => el.addEventListener("click", () => {
        const d = el.dataset.day;
        e.days = e.days.includes(d) ? e.days.filter((x) => x !== d) : HC_DAYS.filter((x) => x === d || e.days.includes(x));
        el.classList.toggle("sel", e.days.includes(d));
      }));
      $("e-en")?.addEventListener("change", (ev) => { e.enabled = ev.target.checked; });
      $("e-start")?.addEventListener("change", (ev) => { e.start = ev.target.value; });
      $("e-end")?.addEventListener("change", (ev) => { e.end = ev.target.value; });
      $("e-work")?.addEventListener("input", (ev) => { e.work_s = Number(ev.target.value); });
      $("e-pause")?.addEventListener("input", (ev) => { e.pause_s = Number(ev.target.value); });
      $("e-cancel")?.addEventListener("click", () => this._closeEditor());
      $("e-save")?.addEventListener("click", () => this._saveEditor());
    }
  }
}

if (!customElements.get("hotelcollection-card")) {
  customElements.define("hotelcollection-card", HotelCollectionCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "hotelcollection-card",
    name: "Hotel Collection diffuser",
    description: "Weekly schedule (editable), current mode, oil level and power/fan for a Hotel Collection diffuser.",
    preview: false,
    documentationURL: "https://github.com/dthomas946/ha-hotelcollection",
  });
}

if (typeof module !== "undefined") {
  module.exports = { hcDaySummary, hcBarsForDay, hcActiveMode, hcNextMode, hcDayIndex, hcMinutes };
}
