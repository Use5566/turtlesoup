"use strict";
const $ = id => document.getElementById(id);
const apiBase = (window.TURTLESOUP_CONFIG?.apiBase || "").replace(/\/$/, "");
let token = "", game = null, mode = "mock", pending = null, busy = false, generation = 0;
const syncLabels = { local: "已保存 · 試算表未啟用", pending: "尚未完成雲端儲存 · 請保留頁面", synced: "已儲存至試算表" };

function show(view) {
  for (const name of ["login", "activities", "game"]) $(name + "-view").hidden = name !== view;
}
function clearIdentity() {
  token = ""; game = null; pending = null; busy = false; generation++;
  $("identity").textContent = ""; $("logout").hidden = true; $("password").value = "";
  $("messages").replaceChildren(); delete $("messages").dataset.signature; $("question").value = ""; $("game-error").textContent = "";
  show("login");
}
async function api(path, options = {}) {
  if (!apiBase && location.hostname.endsWith("github.io")) throw new Error("老師尚未設定遊戲服務網址，請稍後再試。");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(apiBase + path, { ...options, signal: controller.signal, cache: "no-store",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) } });
    let data;
    try { data = await response.json(); } catch { throw new Error("服務暫時無法連線，請稍後再試。"); }
    if (!response.ok) {
      if (response.status === 401 && token) { clearIdentity(); $("login-error").textContent = data.message; }
      const error = new Error(data.message || "服務暫時無法處理，請稍後再試。"); error.status = response.status; throw error;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("連線等待較久，請重新確認這次提問的結果。");
    if (error instanceof TypeError) throw new Error("目前無法連線，請檢查網路後再試。");
    throw error;
  } finally { clearTimeout(timer); }
}
async function setup() {
  for (let i = 1; i <= 99; i++) $("seat").add(new Option(String(i).padStart(2, "0"), String(i)));
  try {
    const data = await api("/api/config"); mode = data.mode;
    $("mode").hidden = mode !== "mock";
    $("classroom").replaceChildren(new Option("選擇班級", ""));
    data.classes.forEach(value => $("classroom").add(new Option(value + " 班", value)));
  } catch (e) { $("classroom").replaceChildren(new Option("暫時無法載入", "")); $("login-error").textContent = e.message + " 請重新整理。"; }
}
$("login-form").addEventListener("submit", async event => {
  event.preventDefault(); $("login-error").textContent = ""; $("login-button").disabled = true;
  try {
    const data = await api("/api/login", { method: "POST", body: JSON.stringify({ classroom: $("classroom").value, seat: $("seat").value, password: $("password").value }) });
    token = data.token; generation++; $("password").value = "";
    $("identity").textContent = data.classroom + " 班 · " + data.seat + " 號"; $("logout").hidden = false;
    await activities();
  } catch (e) { $("login-error").textContent = e.message; }
  finally { $("login-button").disabled = false; }
});
$("logout").addEventListener("click", async () => {
  $("logout").disabled = true;
  try {
    if (busy || pending) throw new Error("請先確認目前提問結果，再登出。");
    await saveDraft();
    await api("/api/logout", { method: "POST" }); clearIdentity();
  }
  catch(e) { $("game-error").textContent = e.message; $("activity-error").textContent = e.message; }
  finally { $("logout").disabled = false; }
});
async function activities() {
  const epoch = generation;
  show("activities"); $("activity-error").textContent = ""; $("activity-list").replaceChildren();
  try {
    const data = await api("/api/activities");
    if (epoch !== generation || !token) return;
    if (!data.activities.length) $("activity-error").textContent = "目前沒有開放的活動，請等候老師。";
    for (const [i, item] of data.activities.entries()) {
      const button = document.createElement("button"); button.className = "activity-card";
      const label = document.createElement("small"); label.textContent = "謎題 " + String(i + 1).padStart(2, "0");
      const title = document.createElement("strong"); title.textContent = item.title;
      const action = document.createElement("span"); action.textContent = "開始／接續探索 →";
      button.append(label, title, action);
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await api("/api/games", { method: "POST", body: JSON.stringify({ activity: item.id }) });
          if (epoch !== generation || !token) return;
          game = result;
          pending = null; $("question").value = game.draft || "";
          updateCount(); $("game-error").textContent = "";
          renderGame(); show("game");
        } catch (e) { $("activity-error").textContent = e.message; } finally { button.disabled = false; }
      });
      $("activity-list").append(button);
    }
  } catch(e) { $("activity-error").textContent = e.message; }
}
function renderGame() {
  if (!game) return;
  $("story-title").textContent = game.title; $("story-surface").textContent = game.surface;
  $("sync-status").textContent = syncLabels[game.sync]; $("turn-count").textContent = "已提問 " + game.turns.length + " / " + game.max_turns + " 次";
  $("finished").hidden = game.state !== "finished";
  $("question-form").hidden = game.state === "finished";
  $("finish").disabled = busy || !!pending || game.state === "finished" || game.turns.some(t => t.status === "processing");
  $("send").disabled = busy || !!pending || game.turns.length >= game.max_turns || game.turns.some(t => t.status === "processing");
  $("question").disabled = busy || !!pending;
  $("retry").hidden = !pending; $("retry").disabled = busy;
  $("mock-help").hidden = mode !== "mock"; $("mock-examples").replaceChildren();
  for (const example of game.mock_examples || []) {
    const button = document.createElement("button"); button.textContent = example.question;
    button.disabled = busy || !!pending || game.state === "finished";
    button.addEventListener("click", () => { $("question").value = example.question; updateCount(); $("question").focus(); });
    $("mock-examples").append(button);
  }
  const container = $("messages"), oldScroll = container.scrollTop, nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  if (game.turns.length >= game.max_turns && game.state === "active") $("game-error").textContent = "已達提問上限，可以結束本次探索。";
  const messageSignature = game.id + JSON.stringify(game.turns.map(t => [t.request_id, t.status, t.answer]));
  if (container.dataset.signature === messageSignature) return;
  container.dataset.signature = messageSignature;
  container.replaceChildren();
  if (!game.turns.length) {
    const empty = document.createElement("div"); empty.className = "empty-state";
    const icon = document.createElement("img"); icon.src = "./turtle.svg"; icon.alt = "";
    const strong = document.createElement("strong"); strong.textContent = "你的第一個猜想是什麼？";
    const caption = document.createElement("span"); caption.textContent = "讀讀左邊的故事，用一個問題開始探索。";
    empty.append(icon, strong, caption); container.append(empty);
  }
  for (const turn of game.turns) {
    const article = document.createElement("article"); article.className = "message";
    const meta = document.createElement("div"); meta.className = "question-meta"; meta.textContent = "第 " + turn.sequence + " 次提問";
    const question = document.createElement("div"); question.className = "question-bubble"; question.textContent = turn.question;
    const reply = document.createElement("div"); reply.className = "reply";
    const icon = document.createElement("img"); icon.src = "./turtle.svg"; icon.alt = "主持人"; icon.className = "reply-icon";
    const text = document.createElement("div"); text.className = "reply-body" + (turn.answer ? "" : " system");
    text.textContent = turn.answer || "系統：" + turn.message;
    reply.append(icon, text); article.append(meta, question, reply); container.append(article);
  }
  container.scrollTop = nearBottom || busy ? container.scrollHeight : oldScroll;
  if (game.turns.length >= game.max_turns && game.state === "active") $("game-error").textContent = "已達提問上限，可以結束本次探索。";
}
function updateCount() { $("char-count").textContent = Array.from($("question").value).length + " / 300"; }
$("question").addEventListener("input", updateCount);
$("question-form").addEventListener("submit", async event => {
  event.preventDefault(); if (busy || pending || !game || !$("question").value.trim()) return;
  if (saving) { try { await saving; } catch { /* Submission retries the cloud save. */ } }
  if (!game || !token || busy || pending) return;
  pending = { request_id: crypto.randomUUID(), question: $("question").value.trim() };
  await sendPending();
});
async function sendPending() {
  if (!pending || !game || busy) return;
  const currentGeneration = generation, uid = game.id;
  busy = true; $("game-error").textContent = ""; renderGame();
  try {
    const turn = await api("/api/games/" + uid + "/questions", { method: "POST", body: JSON.stringify(pending) });
    if (currentGeneration !== generation || !game || game.id !== uid) return;
    if (turn.status !== "processing") { pending = null; $("question").value = ""; updateCount(); }
    const refreshed = await api("/api/games/" + uid);
    if (currentGeneration === generation && game?.id === uid) game = refreshed;
  } catch(e) {
    $("game-error").textContent = e.message;
    if (e.status && e.status < 500 && e.status !== 429) pending = null;
  } finally { busy = false; renderGame(); }
}
$("retry").addEventListener("click", sendPending);
$("back").addEventListener("click", async () => {
  if (busy || pending) { $("game-error").textContent = "請先確認目前提問的結果。"; return; }
  try { await saveDraft(); game = null; activities(); }
  catch(e) { $("game-error").textContent = e.message; }
});
$("finish").addEventListener("click", () => $("finish-dialog").showModal());
$("cancel-finish").addEventListener("click", () => $("finish-dialog").close());
$("confirm-finish").addEventListener("click", async () => {
  $("confirm-finish").disabled = true;
  const epoch = generation;
  try { const result = await api("/api/games/" + game.id + "/finish", { method: "POST" }); if (epoch === generation && token) { game = result; renderGame(); } }
  catch(e) { $("game-error").textContent = e.message; }
  finally { $("finish-dialog").close(); $("confirm-finish").disabled = false; }
});
let polling = false;
setInterval(async () => {
  if (!game || !token || busy || polling || document.hidden) return;
  const uid = game.id, epoch = generation; polling = true;
  try {
    const updated = await api("/api/games/" + uid);
    if (generation !== epoch || game?.id !== uid || busy) return;
    game = updated;
    if (pending && game.turns.some(t => t.request_id === pending.request_id && t.status !== "processing")) {
      pending = null; $("question").value = ""; updateCount();
    }
    renderGame();
  } catch { /* Keep saved content visible during transient network failures. */ }
  finally { polling = false; }
}, 5000);
setup();

let saving = null;
function saveDraft() {
  if (saving) return saving.then(() => saveDraft());
  if (!game || !token || game.state !== "active" || busy || pending) return Promise.resolve();
  const uid = game.id, epoch = generation;
  const body = JSON.stringify({question: $("question").value});
  saving = api("/api/games/" + uid + "/save", {method: "POST", body})
    .then(result => {
      if (epoch === generation && game?.id === uid) {
        $("sync-status").textContent = syncLabels[result.sync] + " · 每35秒自動儲存";
      }
    }).finally(() => { saving = null; });
  return saving;
}
setInterval(() => {
  saveDraft().catch(e => { $("game-error").textContent = e.message; });
}, 35000);
window.addEventListener("beforeunload", event => {
  if (game && (busy || pending || $("question").value)) {
    event.preventDefault(); event.returnValue = "";
  }
});
