// Logic tests for the dashboard card. Run: node --test tests/
const test = require("node:test");
const assert = require("node:assert");

globalThis.HTMLElement = class {};
globalThis.window = {};
globalThis.customElements = { get: () => undefined, define: () => {} };
const card = require("../custom_components/hotelcollection/www/hotelcollection-card.js");

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const WEEKEND = ["Sat", "Sun"];
// the Villa's schedule as read on 2026-11-15
const SLOTS = [
  { slot: 1, days: WEEKDAYS, start: "05:30", end: "12:00", enabled: true, work_s: 60, pause_s: 90 },
  { slot: 2, days: WEEKDAYS, start: "13:30", end: "16:00", enabled: true, work_s: 60, pause_s: 90 },
  { slot: 3, days: WEEKEND, start: "09:00", end: "13:00", enabled: true, work_s: 60, pause_s: 90 },
  { slot: 4, days: WEEKDAYS, start: "21:00", end: "22:00", enabled: true, work_s: 70, pause_s: 90 },
  { slot: 5, days: WEEKEND, start: "20:00", end: "23:59", enabled: true, work_s: 70, pause_s: 90 },
];

// 2026-11-15 is a Sunday, 2026-11-16 a Monday
const at = (d, hh, mm) => new Date(2026, 10, d, hh, mm);

test("weekday index is Monday-based", () => {
  assert.strictEqual(card.hcDayIndex(at(16, 9, 0)), 0);
  assert.strictEqual(card.hcDayIndex(at(15, 9, 0)), 6);
});

test("bars per day", () => {
  assert.deepStrictEqual(card.hcBarsForDay(SLOTS, 0).map((b) => b.slot), [1, 2, 4]);
  const sun = card.hcBarsForDay(SLOTS, 6);
  assert.deepStrictEqual(sun.map((b) => b.slot), [3, 5]);
  assert.strictEqual(sun[1].endMin, 1440); // 23:59 drawn to the end of the day
});

test("active mode", () => {
  assert.strictEqual(card.hcActiveMode(SLOTS, at(15, 21, 30)).slot, 5);
  assert.strictEqual(card.hcActiveMode(SLOTS, at(16, 6, 0)).slot, 1);
  assert.strictEqual(card.hcActiveMode(SLOTS, at(16, 12, 30)), null);
});

test("next mode", () => {
  const n = card.hcNextMode(SLOTS, at(15, 23, 59)); // Sunday night -> Monday 05:30
  assert.deepStrictEqual([n.slot.slot, n.offset, n.start], [1, 1, "05:30"]);
  const m = card.hcNextMode(SLOTS, at(16, 12, 30));
  assert.deepStrictEqual([m.slot.slot, m.offset], [2, 0]);
});

test("disabled modes are not active, but past-midnight windows carry over", () => {
  const off = SLOTS.map((s) => ({ ...s, enabled: false }));
  assert.strictEqual(card.hcActiveMode(off, at(16, 6, 0)), null);
  assert.strictEqual(card.hcNextMode(off, at(16, 6, 0)), null);
  const late = [{ slot: 1, days: ["Fri"], start: "22:00", end: "02:00", enabled: true, work_s: 1, pause_s: 1 }];
  assert.deepStrictEqual(card.hcBarsForDay(late, 5).map((b) => [b.startMin, b.endMin]), [[0, 120]]);
  assert.strictEqual(card.hcActiveMode(late, new Date(2026, 10, 21, 1, 0)).slot, 1); // Sat 01:00
});

test("day summaries", () => {
  assert.strictEqual(card.hcDaySummary(WEEKDAYS), "Mon–Fri");
  assert.strictEqual(card.hcDaySummary(WEEKEND), "Sat, Sun");
  assert.strictEqual(card.hcDaySummary(["Mon", "Wed", "Fri"]), "Mon, Wed, Fri");
  assert.strictEqual(card.hcDaySummary([...WEEKDAYS, ...WEEKEND]), "Every day");
  assert.strictEqual(card.hcDaySummary([]), "No days");
});
