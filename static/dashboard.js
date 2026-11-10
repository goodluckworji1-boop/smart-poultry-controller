// Live dashboard: polls the Python backend every 2 seconds (asynchronous update).
const $ = (id) => document.getElementById(id);
const CLASSES = ["Optimal", "Heat Stress", "Cold Stress", "Poor Air Quality"];
let state = {};
let comfort = [24, 27];

async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}

function placeBand(key, value, min, max, okLo, okHi) {
  const pct = (v) => Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  $("ok-" + key).style.left = pct(okLo) + "%";
  $("ok-" + key).style.width = (pct(okHi) - pct(okLo)) + "%";
  $("d-" + key).style.left = pct(value) + "%";
}

function setReading(key, value, unit) {
  $("v-" + key).innerHTML = value + "<small> " + unit + "</small>";
}

function renderLatest(r) {
  if (!r) return;
  setReading("t", r.temperature, "°C");
  setReading("h", r.humidity, "%");
  setReading("a", r.ammonia, "ppm");
  setReading("l", Math.round(r.light), "lux");
  setReading("f", Math.round(r.feed_level), "%");
  placeBand("t", r.temperature, 12, 42, comfort[0], comfort[1]);
  placeBand("h", r.humidity, 30, 100, 50, 70);
  placeBand("a", r.ammonia, 0, 50, 0, 20);
  placeBand("l", r.light, 0, 500, 20, 500);
  placeBand("f", r.feed_level, 0, 100, 20, 100);
  $("n-t").textContent = `Comfort zone ${comfort[0]} to ${comfort[1]} °C for day ${r.bird_age}`;

  const cls = { "Heat Stress": "s-Heat", "Cold Stress": "s-Cold", "Poor Air Quality": "s-Poor" }[r.prediction] || "";
  $("house").className = "house " + cls;
  $("pred").textContent = r.prediction;
  $("conf").textContent = `DNN confidence ${r.confidence}%  |  Status: ${r.status}  |  Reading #${r.id} at ${r.created_at.slice(11)}`;
  $("action").textContent = r.action;
}

function renderProbs(probs) {
  $("probs").innerHTML = CLASSES.map((c) => {
    const p = probs && probs[c] !== undefined ? probs[c] : 0;
    return `<div class="row"><span>${c}</span><div class="bar"><i style="width:${p}%"></i></div><span>${p}%</span></div>`;
  }).join("");
}

function renderDevices(s) {
  const names = { fan: "Fans", heater: "Heater", feeder: "Feeder", lights: "Lights" };
  const manual = s.mode === "manual";
  $("devices").innerHTML = Object.keys(names).map((k) => {
    const on = s.actuators[k];
    return `<div class="dev"><b>${names[k]}</b><button class="pill ${on ? "on" : ""}" data-dev="${k}" ${manual ? "" : "disabled"} aria-label="${names[k]} ${on ? "on" : "off"}">${on ? "ON" : "OFF"}</button></div>`;
  }).join("");
  document.querySelectorAll("[data-dev]").forEach((b) => {
    b.onclick = async () => {
      await post("/api/control", { device: b.dataset.dev, value: s.actuators[b.dataset.dev] ? 0 : 1 });
      refresh();
    };
  });
}

function renderAlerts(list) {
  if (!list.length) return;
  $("alerts").innerHTML = list.map((a) =>
    `<div class="alert-item ${a.level}"><time>${a.created_at} | ${a.level}</time>${a.message}</div>`).join("");
}

function drawChart(hist) {
  const cv = $("chart");
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d");
  g.scale(dpr, dpr);
  g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const col = (n) => css.getPropertyValue(n).trim();
  const pad = { l: 34, r: 10, t: 10, b: 20 };
  const yMax = 100, yMin = 0;
  const Y = (v) => pad.t + (1 - (v - yMin) / (yMax - yMin)) * (h - pad.t - pad.b);
  const X = (i) => pad.l + (hist.length < 2 ? 0 : (i / (hist.length - 1)) * (w - pad.l - pad.r));

  g.font = "11px Segoe UI, Arial";
  g.fillStyle = col("--muted");
  g.strokeStyle = col("--line");
  for (let v = 0; v <= 100; v += 20) {
    g.beginPath(); g.moveTo(pad.l, Y(v)); g.lineTo(w - pad.r, Y(v)); g.stroke();
    g.fillText(v, 4, Y(v) + 4);
  }
  g.fillStyle = col("--ok"); g.globalAlpha = 0.15;
  g.fillRect(pad.l, Y(comfort[1]), w - pad.l - pad.r, Y(comfort[0]) - Y(comfort[1]));
  g.globalAlpha = 1;
  if (!hist.length) return;
  [["temperature", "--heat"], ["humidity", "--cold"], ["ammonia", "--air"]].forEach(([k, c]) => {
    g.strokeStyle = col(c); g.lineWidth = 2; g.beginPath();
    hist.forEach((r, i) => (i ? g.lineTo(X(i), Y(r[k])) : g.moveTo(X(i), Y(r[k]))));
    g.stroke();
  });
}

async function refresh() {
  try {
    const d = await (await fetch("/api/latest")).json();
    state = d.state;
    comfort = d.comfort;
    renderLatest(d.latest);
    renderProbs(d.latest ? (Object.keys(state.last_probs).length ? state.last_probs : null) : null);
    renderDevices(state);
    renderAlerts(d.alerts);
    drawChart(d.history);
    $("simBtn").textContent = state.simulating ? "Stop sensor simulation" : "Start sensor simulation";
    $("simBtn").className = state.simulating ? "btn stop" : "btn";
    $("modeBtn").textContent = state.mode === "manual" ? "Return to automatic (DNN) control" : "Switch to manual override";
    if (document.activeElement !== $("age")) $("age").value = state.bird_age;
    $("comfort").textContent = `Comfort zone: ${comfort[0]} to ${comfort[1]} °C`;
  } catch (e) { console.error(e); }
}

$("simBtn").onclick = async () => { await post("/api/control", { simulating: !state.simulating }); refresh(); };
$("modeBtn").onclick = async () => { await post("/api/control", { mode: state.mode === "manual" ? "auto" : "manual" }); refresh(); };
$("age").onchange = async () => { await post("/api/control", { bird_age: $("age").value }); refresh(); };
$("mBtn").onclick = async () => {
  await post("/api/manual-reading", {
    temperature: $("m-t").value, humidity: $("m-h").value, ammonia: $("m-a").value,
    light: $("m-l").value, feed_level: $("m-f").value, bird_age: state.bird_age,
  });
  refresh();
};
window.addEventListener("resize", refresh);
renderProbs(null);
refresh();
setInterval(refresh, 2000);
