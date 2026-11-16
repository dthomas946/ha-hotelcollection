/*
 * Hotel Collection diffuser card (read-only schedule view)
 *   type: custom:hotelcollection-card
 *   device: villa          # entity prefix, e.g. switch.villa_power  (default "villa")
 *   name: Villa            # optional title
 *
 * Shows the diffuser's five modes on a weekly 24 h timeline with a "now" marker,
 * which mode is running, oil level, run time left, scent, and power/fan toggles.
 * Created with Claude.ai. MIT licence. Layout idea from the schedule overview in
 * jrx-code/hassio-integration-aroma-link (MIT).
 */

const HC_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

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
    return 6;
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
    const ids = [
      ["switch", "power"], ["switch", "fan"], ["sensor", "oil_level"], ["sensor", "oil_remaining"],
      ["sensor", "bottle_size"], ["sensor", "run_time_remaining"], ["sensor", "consumption_rate"],
      ["sensor", "active_schedule_slots"], ["text", "scent"],
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
    this._timer = setInterval(() => { this._lastKey = null; if (this._hass) this.hass = this._hass; }, 60000);
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
    const on = power && power.state === "on";
    const fanOn = fan && fan.state === "on";
    const level = parseFloat(this._st("sensor", "oil_level")?.state);
    const remaining = this._st("sensor", "oil_remaining")?.state;
    const bottle = this._st("sensor", "bottle_size")?.state;
    const hours = parseFloat(this._st("sensor", "run_time_remaining")?.state);
    const rate = this._st("sensor", "consumption_rate")?.state;
    const scent = this._st("text", "scent")?.state;
    const unavailable = power && power.state === "unavailable";

    const now = new Date();
    const today = hcDayIndex(now);
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const active = hcActiveMode(slots, now);
    const next = hcNextMode(slots, now);

    let status;
    if (unavailable) status = `<span class="dot off"></span>Diffuser offline`;
    else if (!on) status = `<span class="dot off"></span>Off`;
    else if (active)
      status = `<span class="dot run"></span>Mode ${active.slot} running · ${hcEsc(active.start)}–${hcEsc(active.end)} · ${active.work_s} s on / ${active.pause_s} s off`;
    else if (next)
      status = `<span class="dot idle"></span>Idle · next Mode ${next.slot.slot} ${next.offset === 0 ? "today" : next.offset === 1 ? "tomorrow" : HC_DAYS[next.day]} ${hcEsc(next.start)}`;
    else status = `<span class="dot idle"></span>No modes enabled`;

    const rows = HC_DAYS.map((label, d) => {
      const bars = hcBarsForDay(slots, d)
        .map((b) => {
          const left = (b.startMin / 1440) * 100;
          const width = ((b.endMin - b.startMin) / 1440) * 100;
          const isActive = active && d === today && b.slot === active.slot && on;
          const cls = ["bar", b.enabled ? "" : "disabled", isActive ? "active" : ""].join(" ");
          const tip = `Mode ${b.slot}: ${b.start}–${b.end}, ${b.work_s} s on / ${b.pause_s} s off${b.enabled ? "" : " (off)"}`;
          return `<div class="${cls}" style="left:${left}%;width:${width}%" title="${hcEsc(tip)}"><span>${b.slot}</span></div>`;
        })
        .join("");
      const marker = d === today ? `<div class="now" style="left:${(nowMin / 1440) * 100}%"></div>` : "";
      return `<div class="row ${d === today ? "today" : ""}"><div class="day">${label}</div><div class="track">${bars}${marker}</div></div>`;
    }).join("");

    const levelPct = isNaN(level) ? 0 : Math.max(0, Math.min(100, level));
    const lowOil = !isNaN(level) && level < 15;

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
        .meter { height: 10px; border-radius: 5px; background: var(--secondary-background-color, rgba(127,127,127,.12)); overflow:hidden; }
        .fill { height:100%; background: ${lowOil ? "var(--error-color, #db4437)" : "var(--primary-color)"}; }
        .num { font-size:.9rem; }
        .sub { grid-column: 1 / -1; font-size:.8rem; color: var(--secondary-text-color); }
        .warn { padding: 8px; color: var(--error-color); }
      </style>
      <ha-card>
        <div class="head">
          <div class="title">${hcEsc(this._config.name || "Villa")}
            ${scent && scent !== "unknown" ? `<div class="scent" id="scent">${hcEsc(scent)}</div>` : ""}</div>
          <div class="btns">
            <button id="power" class="${on ? "on" : ""}" ${unavailable ? "disabled" : ""} title="Power"><ha-icon icon="mdi:power"></ha-icon>${on ? "On" : "Off"}</button>
            <button id="fan" class="${fanOn ? "on" : ""}" ${unavailable ? "disabled" : ""} title="Fan"><ha-icon icon="mdi:fan"></ha-icon>Fan</button>
          </div>
        </div>
        <div class="status">${status}</div>
        <div class="grid">${rows}</div>
        <div class="axis"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
        <div class="oil" id="oil">
          <div class="meter"><div class="fill" style="width:${levelPct}%"></div></div>
          <div class="num">${isNaN(level) ? "–" : Math.round(level) + " %"}</div>
          <div class="sub">${remaining ?? "–"} of ${bottle ?? "–"} mL · ${rate ?? "–"} mL/h · ${isNaN(hours) ? "–" : Math.round(hours) + " h"} of spraying left</div>
        </div>
      </ha-card>`;

    const $ = (id) => this.shadowRoot.getElementById(id);
    $("power")?.addEventListener("click", () => this._toggle("power"));
    $("fan")?.addEventListener("click", () => this._toggle("fan"));
    $("oil")?.addEventListener("click", () => this._more("sensor", "oil_remaining"));
    $("scent")?.addEventListener("click", () => this._more("text", "scent"));
  }
}

if (!customElements.get("hotelcollection-card")) {
  customElements.define("hotelcollection-card", HotelCollectionCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "hotelcollection-card",
    name: "Hotel Collection diffuser",
    description: "Weekly schedule, current mode, oil level and power/fan for a Hotel Collection diffuser.",
    preview: false,
    documentationURL: "https://github.com/dthomas946/ha-hotelcollection",
  });
}

if (typeof module !== "undefined") {
  module.exports = { hcBarsForDay, hcActiveMode, hcNextMode, hcDayIndex, hcMinutes };
}
