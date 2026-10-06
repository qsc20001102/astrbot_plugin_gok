/**
 * 王者营地查询控制台前端。
 *
 * 与后端通信的唯一通道是宿主注入的 bridge：
 *   bridge.apiGet(endpoint, params) / bridge.apiPost(endpoint, payload)
 * endpoint 是插件内相对路径，宿主会补全为
 *   /api/v1/plugins/extensions/<插件名>/<endpoint>
 *
 * 两个重要约束（都由宿主的 sandbox iframe 造成）：
 *   1. iframe 没有 allow-modals，window.confirm/alert 会被静默忽略（返回 false），
 *      因此确认操作一律用页面内的弹窗（askConfirm）。
 *   2. iframe 是不透明源，localStorage/sessionStorage 会抛异常，
 *      因此「进行中的扫码会话」只能存在服务端，页面刷新后通过 login/status 恢复。
 *
 * 本页面不做任何数据缓存，查询结果每次都来自实时请求。
 */

const bridge = window.AstrBotPluginPage;
const byId = (id) => document.getElementById(id);

const POLL_INTERVAL_MS = 2000;

const state = {
  pollTimer: null,
  countdownTimer: null,
  taskId: "",
  expiresAt: 0,
  pollGeneration: 0,
  queryBusy: false,
  queryKeyword: "",
  queryKind: "battle",
  editingId: "",
};

/* ------------------------------------------------------------------ 工具 */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

let toastTimer = null;
function showToast(message, kind = "") {
  const el = byId("toast");
  el.textContent = message;
  el.className = `toast ${kind}`.trim();
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2800);
}

function errorText(error) {
  if (!error) return "未知错误";
  if (typeof error === "string") return error;
  return error.message || error.msg || "请求失败";
}

function formatRemaining(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 页面内确认框（代替被 sandbox 禁用的 window.confirm）。 */
function askConfirm(title, text, okLabel = "确定") {
  return new Promise((resolve) => {
    byId("confirm-title").textContent = title;
    byId("confirm-text").textContent = text;
    byId("confirm-yes").textContent = okLabel;
    byId("confirm-mask").hidden = false;

    const cleanup = (result) => {
      byId("confirm-mask").hidden = true;
      byId("confirm-yes").removeEventListener("click", onYes);
      byId("confirm-no").removeEventListener("click", onNo);
      document.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const onYes = () => cleanup(true);
    const onNo = () => cleanup(false);
    const onKey = (e) => { if (e.key === "Escape") cleanup(false); };

    byId("confirm-yes").addEventListener("click", onYes);
    byId("confirm-no").addEventListener("click", onNo);
    document.addEventListener("keydown", onKey);
  });
}

/* ------------------------------------------------------------------ 标签页 */
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      byId(`panel-${tab.dataset.tab}`)?.classList.add("active");
    });
  });
}

/* ------------------------------------------------------------------ 总览 */
async function loadDashboard() {
  try {
    const data = await bridge.apiGet("dashboard");
    renderAccounts(data.accounts);
    renderAliases({ list: data.aliases || [] });
    return data;
  } catch (error) {
    showToast(`读取总览失败：${errorText(error)}`, "error");
    return null;
  }
}

function renderAccounts(accounts = {}) {
  const box = byId("account-list");
  const rows = accounts.accounts || [];
  if (!rows.length) {
    box.innerHTML = `<div class="empty">还没有登录任何营地账号，请先扫码登录</div>`;
    return;
  }

  box.innerHTML = rows.map((row) => {
    const badge = !row.ready || row.auth_invalid
      ? `<span class="badge off">需重新登录</span>`
      : row.available
        ? `<span class="badge ${row.validation_status === "valid" ? "ok" : "warn"}">${row.validation_status === "valid" ? "已验证有效" : row.validation_status === "error" ? "暂无法确认" : "待验证"}</span>`
        : `<span class="badge warn">冷却 ${formatRemaining(row.cooled_remaining)}</span>`;
    const avatar = row.avatar
      ? `<img class="avatar" src="${escapeHtml(row.avatar)}" alt="" />`
      : `<div class="avatar fallback">${escapeHtml((row.nickname || "?").slice(0, 1))}</div>`;
    const meta = [
      `ID ${escapeHtml(row.user_id)}`,
      row.last_login_at ? `登录于 ${escapeHtml(row.last_login_at)}` : "",
      row.expires && String(row.expires) !== "0" ? `有效期至 ${escapeHtml(row.expires)}` : "",
      row.last_skip_reason ? `最近状态：${escapeHtml(({ auth: "登录态已失效", rate_limit: "访问频繁" })[row.last_skip_reason] || "请求异常")}` : "",
      row.last_checked_at ? `检测于 ${escapeHtml(new Date(row.last_checked_at * 1000).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }))}` : "",
      row.validation_message ? escapeHtml(row.validation_message) : "",
    ].filter(Boolean).join(" · ");

    return `<div class="item">
      ${avatar}
      <div class="main">
        <div class="name">${escapeHtml(row.nickname)}</div>
        <div class="meta">${meta}</div>
      </div>
      ${badge}
      <div class="actions">
        <button class="btn tiny danger" data-account-delete="${escapeHtml(row.user_id)}" type="button">删除</button>
      </div>
    </div>`;
  }).join("");

  box.querySelectorAll("[data-account-delete]").forEach((btn) => {
    btn.addEventListener("click", () => deleteAccount(btn.dataset.accountDelete));
  });
}

async function deleteAccount(userId) {
  const ok = await askConfirm(
    "删除营地账号",
    `确定要删除账号 ${userId} 吗？删除后需要重新扫码登录才能查询。`,
    "删除",
  );
  if (!ok) return;
  try {
    await bridge.apiPost("accounts/delete", { user_id: userId });
    showToast("已删除账号", "success");
    await loadDashboard();
  } catch (error) {
    showToast(`删除失败：${errorText(error)}`, "error");
  }
}

async function clearAccounts() {
  const ok = await askConfirm(
    "清空全部账号",
    "确定要清空所有营地账号吗？清空后需要重新扫码登录。",
    "清空",
  );
  if (!ok) return;
  try {
    await bridge.apiPost("accounts/clear", {});
    showToast("已清空账号", "success");
    await loadDashboard();
  } catch (error) {
    showToast(`操作失败：${errorText(error)}`, "error");
  }
}

/* ------------------------------------------------------------------ 扫码登录 */
function stopPolling() {
  clearTimeout(state.pollTimer);
  clearTimeout(state.countdownTimer);
  state.pollTimer = null;
  state.countdownTimer = null;
  state.pollGeneration += 1;
}

function setQrStatus(text, kind = "") {
  const el = byId("qr-status");
  el.textContent = text;
  el.className = `status-line ${kind}`.trim();
}

function tickCountdown() {
  const remain = Math.max(0, (state.expiresAt - Date.now()) / 1000);
  byId("qr-countdown").textContent = remain > 0
    ? `二维码剩余有效时间 ${formatRemaining(remain)}`
    : "正在确认登录状态…";
  if (remain > 0) {
    state.countdownTimer = setTimeout(tickCountdown, 1000);
  }
}

function showQrImage(base64, mime) {
  byId("qr-image").src = `data:${mime || "image/jpeg"};base64,${base64}`;
  byId("qr-image").hidden = false;
  byId("qr-placeholder").hidden = true;
}

function resetQrBox() {
  byId("qr-image").hidden = true;
  byId("qr-image").removeAttribute("src");
  byId("qr-placeholder").hidden = false;
  byId("qr-placeholder").innerHTML = "<span>点击下方按钮获取二维码</span>";
  byId("qr-countdown").textContent = "";
}

/** 把服务端返回的会话应用到界面并开始轮询。 */
function adoptSession(session, message) {
  stopPolling();
  state.taskId = session.task_id;
  state.expiresAt = Date.now() + Math.max(0, session.expires_in ?? 180) * 1000;
  showQrImage(session.qrcode_base64, session.qrcode_mime);
  setQrStatus(message, "warn");
  byId("btn-cancel").disabled = false;
  tickCountdown();
  state.pollTimer = setTimeout(pollLogin, 0);
}

async function requestQrcode() {
  const oldTaskId = state.taskId;
  stopPolling();
  state.taskId = "";
  resetQrBox();
  byId("btn-qrcode").disabled = true;
  byId("btn-cancel").disabled = true;
  setQrStatus("正在获取二维码…");
  try {
    if (oldTaskId) {
      await bridge.apiPost("login/cancel", { task_id: oldTaskId });
    }
    const data = await bridge.apiPost("login/qrcode", {});
    adoptSession(data, "请用微信扫描二维码");
  } catch (error) {
    setQrStatus(`获取二维码失败：${errorText(error)}`, "err");
  } finally {
    byId("btn-qrcode").disabled = false;
  }
}

/** 页面加载/刷新后恢复进行中的扫码会话（浏览器不会通知 iframe 被刷新）。 */
async function resumeSession() {
  try {
    const data = await bridge.apiGet("login/status");
    if (data?.active) {
      adoptSession(data, "已恢复进行中的扫码会话，请用微信扫码");
      return true;
    }
  } catch (error) {
    // 恢复失败不影响正常使用
    console.warn("恢复扫码会话失败", error);
  }
  return false;
}

async function pollLogin() {
  const taskId = state.taskId;
  const generation = state.pollGeneration;
  if (!taskId) return;
  try {
    const data = await bridge.apiPost("login/poll", { task_id: taskId });
    if (taskId !== state.taskId || generation !== state.pollGeneration) return;
    switch (data.status) {
      case "waiting":
        setQrStatus("等待扫码…", "warn");
        break;
      case "scanned":
        setQrStatus("已扫码，请在微信中点击确认", "warn");
        break;
      case "success":
        stopPolling();
        state.taskId = "";
        byId("btn-cancel").disabled = true;
        resetQrBox();
        setQrStatus(`登录成功：${data.account?.nickname || ""}`, "ok");
        showToast("营地登录成功", "success");
        await loadDashboard();
        break;
      case "expired":
      case "canceled":
        stopPolling();
        state.taskId = "";
        byId("btn-cancel").disabled = true;
        resetQrBox();
        setQrStatus(data.message || "二维码已失效，请重新获取", "err");
        break;
      default:
        if (data.terminal) {
          stopPolling();
          state.taskId = "";
          byId("btn-cancel").disabled = true;
          resetQrBox();
        }
        setQrStatus(data.message || "登录出错，正在重试…", "err");
        break;
    }
  } catch (error) {
    if (taskId === state.taskId && generation === state.pollGeneration) {
      setQrStatus(`轮询失败，正在重试：${errorText(error)}`, "err");
    }
  } finally {
    // WeChat uses long polling; schedule another request only after this one
    // finishes, and ignore responses belonging to a canceled/replaced session.
    if (taskId === state.taskId && generation === state.pollGeneration) {
      state.pollTimer = setTimeout(pollLogin, POLL_INTERVAL_MS);
    }
  }
}

async function cancelLogin() {
  const taskId = state.taskId;
  stopPolling();
  state.taskId = "";
  byId("btn-cancel").disabled = true;
  resetQrBox();
  setQrStatus("已取消");
  if (taskId) {
    try { await bridge.apiPost("login/cancel", { task_id: taskId }); } catch { /* 忽略 */ }
  }
}

/* ------------------------------------------------------------------ Login checks */
async function checkAccounts() {
  const button = byId("btn-check-accounts");
  const box = byId("account-check-result");
  button.disabled = true;
  button.textContent = "正在逐个检测…";
  box.hidden = false;
  box.textContent = "正在使用每个账号自己的登录态请求营地，请稍候…";
  try {
    const result = await bridge.apiPost("accounts/check", {});
    box.textContent = result.checked
      ? `检测 ${result.checked} 个账号：${result.valid} 个有效，${result.invalid} 个失效，${result.uncertain} 个暂无法确认。`
      : "还没有保存登录账号，请先扫码登录。";
    await loadDashboard();
  } catch (error) {
    box.textContent = `检测失败：${errorText(error)}`;
  } finally {
    button.disabled = false;
    button.textContent = "检测全部登录态";
  }
}

/* ------------------------------------------------------------------ Camp media */
function nativeImage(url, name = "", className = "") {
  const valid = typeof url === "string" && /^https?:\/\//i.test(url);
  const fallback = className.startsWith("rank-") || className === "honor-image" ? "" : String(name || "王").slice(0, 1);
  return `<span class="native-image ${className}" title="${escapeHtml(name)}"><span class="image-fallback" aria-hidden="true">${escapeHtml(fallback)}</span>${valid ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(name)}" loading="lazy" data-camp-image />` : ""}</span>`;
}

function metric(label, value, tone = "") {
  return `<div class="report-metric"><strong class="${tone}">${escapeHtml(value ?? "—")}</strong><span>${escapeHtml(label)}</span></div>`;
}

function playerHeader(p) {
  const background = p.game_bg_img || p.bg_img;
  const cover = typeof background === "string" && /^https?:\/\//i.test(background)
    ? `<img class="player-cover" src="${escapeHtml(background)}" alt="" data-camp-image />` : "";
  return `<header class="report-player">${cover}${nativeImage(p.avatar, p.nickname, "player-portrait")}
    <div class="player-who"><h3>${escapeHtml(p.nickname || "未知角色")}</h3>
      <p>营地 ID ${escapeHtml(p.camp_id)} · ${escapeHtml(p.server_name || p.area_name || "")}</p>
      <p>${p.season_games ? `本赛季 ${escapeHtml(p.season_games)} 场 · 胜率 ${escapeHtml(p.win_rate)}%` : ""}</p>
    </div><div class="player-rank"><div class="rank-pictures">${p.rank_stars_icon ? nativeImage(p.rank_stars_icon, `${p.current_stars ?? 0} 星`, "rank-star-image") : `<span>${escapeHtml(p.current_stars ?? 0)} 星</span>`}
      ${p.rank_icon ? nativeImage(p.rank_icon, p.rank_label, "rank-emblem") : ""}<strong class="rank-name">${escapeHtml(p.rank_label || "未知段位")}</strong></div>${p.peak_score > 0 ? `<span>巅峰 ${escapeHtml(p.peak_score)}</span>` : ""}
    </div></header>`;
}

/* ------------------------------------------------------------------ Player results */
function renderQueryResult(result) {
  const box = byId("query-result");
  if (!result || !["profile", "battle", "detail"].includes(result.type) ||
      !result.data || typeof result.data !== "object" || Array.isArray(result.data)) {
    throw new Error("查询响应格式异常，请更新插件、重载后刷新页面");
  }
  const data = result.data;
  const p = data.profile || {};

  if (result.type === "profile") {
    const heroes = data.season_heroes || [];
    box.innerHTML = `<article class="camp-report">${playerHeader(p)}
      <div class="report-section-title"><h3>本赛季资料</h3><span>${escapeHtml(data.season_name || "")}</span></div>
      <div class="report-summary profile-summary">
        ${metric("赛季场次", p.season_games)}${metric("赛季胜场", p.season_wins, "tone-win")}
        ${metric("赛季胜率", p.season_games ? `${p.win_rate}%` : "—", "tone-gold")}${metric("金牌次数", p.gold_count)}
        ${metric("排位评分", p.rank_score || "—", "tone-gold")}${metric("巅峰评分", p.peak_rating || "—")}
        ${metric("巅峰积分", p.peak_score || "—", "tone-gold")}${metric("MVP 次数", p.mvp_count || "—")}
      </div>
      <div class="role-facts">${p.role_id ? `<span>角色 ID ${escapeHtml(p.role_id)}</span>` : ""}<span>${escapeHtml(p.area_name || "")}</span></div>
      <section class="report-section"><div class="report-section-title"><h3>本赛季常用英雄</h3><span>${heroes.length} 位英雄</span></div>
        ${heroes.length ? `<div class="season-heroes">${heroes.map(h => `<div class="season-hero">${nativeImage(h.hero_icon, h.hero_name, "hero-portrait")}<div><strong>${escapeHtml(h.hero_name)}</strong><p>${escapeHtml(h.games)} 场 · ${escapeHtml(h.wins)} 胜${h.fight_power != null ? ` · 战力 ${escapeHtml(h.fight_power)}` : ""}</p></div><strong class="hero-win-rate ${h.win_rate >= 50 ? "tone-win" : "tone-lose"}">${escapeHtml(h.win_rate)}%</strong></div>`).join("")}</div>` : `<p class="report-empty">本赛季暂无英雄统计</p>`}
      </section>${data.hide_match ? `<p class="report-notice">该玩家已在营地隐藏战绩，无法查询对局记录。</p>` : ""}
      <footer class="report-footer">实时查询 · 数据来源：王者营地</footer></article>`;
    return;
  }

  if (result.type === "detail") {
    const m = data.match || {};
    const teams = [["blue", "蓝方", data.blue || []], ["red", "红方", data.red || []]];
    const teamHtml = teams.map(([side, name, rows]) => {
      const winning = m.side ? (side === m.side ? m.win : !m.win) : null;
      return `<section class="detail-team ${side}"><div class="team-heading"><h3>${name}</h3><span>${winning === null ? "" : winning ? "胜利" : "失败"} · ${rows.length} 位玩家</span></div>
        <div class="team-scroll"><table class="team-table"><thead><tr><th>玩家 / 英雄</th><th>等级</th><th>KDA</th><th>出装</th><th>经济</th><th>输出 / 占比</th><th>承伤 / 占比</th><th>英雄战力</th></tr></thead><tbody>
          ${rows.map(r => `<tr class="${r.is_target ? "target-player" : ""}"><td><div class="detail-player">${nativeImage(r.hero_icon, r.hero_name, "hero-portrait")}<div><strong>${escapeHtml(r.nickname || "未知玩家")}${r.is_target ? `<span class="target-label">查询玩家</span>` : ""}</strong><p>${escapeHtml(r.hero_name || r.hero_id || "—")}</p></div>${r.avatar ? nativeImage(r.avatar, r.nickname, "tiny-portrait") : ""}</div></td>
            <td>${escapeHtml(r.level ?? "—")}</td><td class="kda-text">${r.kills}/${r.deaths}/${r.assists}</td><td><div class="equipment-build">${(r.equipment || []).map(item => nativeImage(item.icon, item.name || `装备 ${item.id}`, "equipment-icon")).join("") || `<span class="equipment-empty">未返回出装</span>`}</div>${r.skill?.icon ? `<div class="summoner-skill">${nativeImage(r.skill.icon, r.skill.name, "skill-icon")}<span>${escapeHtml(r.skill.name)}</span></div>` : ""}</td><td>${Number(r.money || 0).toLocaleString("zh-CN")}</td>
            <td>${Number(r.hurt || 0).toLocaleString("zh-CN")}${r.hurt_percent != null ? `<small>${escapeHtml(r.hurt_percent)}% 团队输出</small>` : ""}</td>
            <td>${Number(r.behurt || 0).toLocaleString("zh-CN")}${r.behurt_percent != null ? `<small>${escapeHtml(r.behurt_percent)}% 团队承伤</small>` : ""}</td><td>${escapeHtml(r.fight_power || "—")}</td></tr>`).join("")}
        </tbody></table></div></section>`;
    }).join("");
    box.innerHTML = `<article class="camp-report"><div class="detail-toolbar"><button id="btn-back-battle" class="report-back" type="button">‹ 返回战绩</button><span>对局详情</span></div>${playerHeader(p)}
      <div class="detail-match-head">${nativeImage(m.hero_icon, m.hero_name, "hero-portrait")}<div><h3>${escapeHtml(m.hero_name)} · ${escapeHtml(m.mode_name)}</h3><p>${escapeHtml(m.played_at)} · 时长 ${escapeHtml(m.duration_text)}</p></div><strong class="${m.win ? "tone-win" : "tone-lose"}">${escapeHtml(m.result_text)}</strong></div>
      <div class="report-summary">${metric("KDA", `${m.kills}/${m.deaths}/${m.assists}`)}${metric("评分", m.score_text, "tone-gold")}${metric("对局段位", `${m.rank_name || "—"}${m.rank_name ? ` ${m.stars ?? 0}星` : ""}`)}${metric("荣誉", m.honor_text || "—", "tone-gold")}</div>
      ${teamHtml}
      <footer class="report-footer">实时查询 · 数据来源：王者营地</footer></article>`;
    byId("btn-back-battle").addEventListener("click", () => runQuery("battle", state.queryKeyword));
    return;
  }

  if (!Array.isArray(data.list) || !data.list.length) throw new Error("营地没有返回对局记录");
  const list = data.list;
  const s = data.summary || {};
  box.innerHTML = `<article class="camp-report">${playerHeader(p)}
    <div class="report-section-title"><h3>近期战绩</h3><span>统计 ${s.total ?? list.length} 场 · 展示 ${list.length} 场</span></div>
    <div class="report-summary battle-summary">${metric("近期场次", s.total)}${metric("胜场", s.wins, "tone-win")}${metric("负场", s.loses, "tone-lose")}${metric("胜率", `${s.win_rate ?? 0}%`, "tone-win")}${metric("平均 KDA", s.avg_kda)}${metric("平均评分", s.avg_score, "tone-gold")}${metric("MVP / SVP", `${s.mvp_count ?? 0} / ${s.svp_count ?? 0}`)}${metric("金牌", s.gold_count, "tone-gold")}</div>
    <div class="battle-head"><span>英雄 / 模式</span><span>结果</span><span>KDA</span><span>评分</span><span>荣誉</span><span>时长 / 段位</span><span>对局时间</span><span></span></div>
    <div class="battle-list">${list.map((m, i) => `<button class="match-entry ${m.win ? "match-win" : "match-lose"}" data-match-index="${i}" type="button" ${m.game_seq ? "" : "disabled"} aria-label="查看第 ${i + 1} 场 ${escapeHtml(m.hero_name)} 的对局详情">
      <span class="match-main">${nativeImage(m.hero_icon, m.hero_name, "hero-portrait")}<span><strong>${escapeHtml(m.hero_name)}</strong><small>${escapeHtml(m.mode_name)}</small></span></span>
      <strong class="match-outcome ${m.win ? "tone-win" : "tone-lose"}">${escapeHtml(m.result_text)}</strong>
      <span class="match-kda kda-text">${m.kills}<i>/</i><b>${m.deaths}</b><i>/</i>${m.assists}</span>
      <strong class="match-score tone-gold">${escapeHtml(m.score_text)}</strong>
      <span class="match-honors"><span class="honor-images">${m.mvp_icon ? nativeImage(m.mvp_icon, m.mvp_type === "svp" ? "败方 MVP" : "MVP", "honor-image") : ""}${m.medal_icon ? nativeImage(m.medal_icon, m.medal, "honor-image") : ""}</span></span>
      <span class="match-context">${escapeHtml(m.duration_text)}<small>${escapeHtml(m.rank_name || "—")}${m.rank_name ? ` ${escapeHtml(m.stars ?? 0)}星` : ""}</small>${m.mode === "peak" && m.peak_delta != null ? `<small class="${m.peak_delta >= 0 ? "tone-win" : "tone-lose"}">巅峰 ${m.peak_delta >= 0 ? "+" : ""}${escapeHtml(m.peak_delta)} 分</small>` : ""}</span>
      <span class="match-time">${escapeHtml(m.played_at)}${m.economy != null ? `<small>经济 ${escapeHtml(m.economy)}</small>` : ""}${m.damage != null ? `<small>输出 ${escapeHtml(m.damage)}</small>` : ""}</span><span class="match-chevron" aria-hidden="true">›</span>
    </button>`).join("")}</div><footer class="report-footer">点击战绩查看对局详情 · 实时查询 · 王者营地</footer></article>`;
  box.querySelectorAll("[data-match-index]").forEach(button => {
    const match = list[Number(button.dataset.matchIndex)];
    button.addEventListener("click", () => runQuery("detail", p.camp_id || result.keyword, match.game_seq));
  });
}

async function runQuery(type = "battle", keyword = "", gameSeq = "") {
  if (state.queryBusy) return;
  keyword = keyword || byId("query-keyword").value.trim();
  if (!keyword) { showToast("请输入营地 ID 或角色名称", "error"); return; }
  state.queryBusy = true;
  state.queryKeyword = keyword;
  state.queryKind = type;
  byId("query-result").innerHTML = `<div class="empty">${type === "detail" ? "正在读取该场对局详情" : "正在实时查询王者营地"}…</div>`;
  byId("btn-query-profile").disabled = true;
  byId("btn-query-battle").disabled = true;
  try {
    const data = await bridge.apiGet("query", { keyword, type, limit: Math.min(25, Math.max(1, Number(byId("query-limit").value) || 10)), ...(gameSeq ? { game_seq: gameSeq } : {}) });
    renderQueryResult(data);
    await loadDashboard();
  } catch (error) {
    byId("query-result").innerHTML = `<div class="result-error">${escapeHtml(errorText(error))}${type === "detail" ? `<button id="btn-back-battle" class="btn ghost" type="button">返回战绩</button>` : ""}</div>`;
    if (type === "detail") byId("btn-back-battle").addEventListener("click", () => runQuery("battle", keyword));
  } finally {
    state.queryBusy = false;
    byId("btn-query-profile").disabled = false;
    byId("btn-query-battle").disabled = false;
  }
}

function initQuery() {
  byId("btn-query-profile").addEventListener("click", () => runQuery("profile"));
  byId("btn-query-battle").addEventListener("click", () => runQuery("battle"));
  byId("query-keyword").addEventListener("keydown", event => {
    if (event.key === "Enter") runQuery(state.queryKind === "profile" ? "profile" : "battle");
  });
  document.addEventListener("error", event => {
    if (event.target instanceof HTMLImageElement && event.target.hasAttribute("data-camp-image")) event.target.hidden = true;
  }, true);
  document.addEventListener("load", event => {
    if (event.target instanceof HTMLImageElement && event.target.hasAttribute("data-camp-image") && event.target.parentElement.classList.contains("native-image")) {
      event.target.parentElement.classList.add("image-loaded");
    }
  }, true);
}

/* ------------------------------------------------------------------ Role mappings */
function renderAliases(payload = {}) {
  const list = payload.list || [];
  byId("query-mappings").innerHTML = list.map(row => `<option value="${escapeHtml(row.gokid)}">${escapeHtml(row.name)}</option>`).join("");
  const box = byId("alias-list");
  if (!list.length) {
    box.innerHTML = `<div class="empty">${escapeHtml(payload.message || "还没有角色名称映射，先用营地 ID 查询资料或战绩即可自动保存")}</div>`;
    return;
  }
  box.innerHTML = list.map(row => `<div class="item mapping-item"><div class="main"><div class="name">${escapeHtml(row.name)}${row.manually_named ? `<span class="badge">已修改</span>` : ""}</div><div class="meta">营地 ID ${escapeHtml(row.gokid)}${row.role_name ? ` · 游戏角色 ${escapeHtml(row.role_name)}` : ""}</div></div><div class="actions"><button class="btn tiny" data-alias-edit="${row.gokid}" type="button">修改名称</button><button class="btn tiny danger" data-alias-delete="${row.gokid}" type="button">删除</button></div></div>`).join("");
  box.querySelectorAll("[data-alias-delete]").forEach(button => button.addEventListener("click", () => deleteAlias(button.dataset.aliasDelete)));
  box.querySelectorAll("[data-alias-edit]").forEach(button => button.addEventListener("click", () => {
    const row = list.find(item => String(item.gokid) === button.dataset.aliasEdit);
    state.editingId = String(row.gokid);
    byId("alias-edit-meta").textContent = `营地 ID ${row.gokid}${row.role_name ? ` · 游戏角色 ${row.role_name}` : ""}`;
    byId("alias-edit-name").value = row.name;
    byId("alias-edit-mask").hidden = false;
    byId("alias-edit-name").focus();
  }));
}

async function deleteAlias(gokid) {
  const confirmed = await askConfirm("删除角色名称映射", `确定删除营地 ID ${gokid} 的名称映射吗？下次使用此 ID 查询成功会重新保存。`, "删除");
  if (!confirmed) return;
  try {
    await bridge.apiPost("aliases/delete", { gokid: Number(gokid) });
    showToast("名称映射已删除", "success");
    await searchAliases();
  } catch (error) { showToast(`删除失败：${errorText(error)}`, "error"); }
}

async function searchAliases() {
  const keyword = byId("alias-search").value.trim();
  try { renderAliases(await bridge.apiGet("aliases/list", keyword ? { keyword } : {})); }
  catch (error) { showToast(`搜索失败：${errorText(error)}`, "error"); }
}

function initAliases() {
  byId("btn-alias-search").addEventListener("click", searchAliases);
  byId("alias-search").addEventListener("keydown", event => { if (event.key === "Enter") searchAliases(); });
  byId("alias-edit-cancel").addEventListener("click", () => { byId("alias-edit-mask").hidden = true; });
  byId("alias-edit-form").addEventListener("submit", async event => {
    event.preventDefault();
    const name = byId("alias-edit-name").value.trim();
    if (!name) { showToast("请输入显示名称", "error"); return; }
    byId("alias-edit-save").disabled = true;
    try {
      await bridge.apiPost("aliases/update", { gokid: Number(state.editingId), name });
      byId("alias-edit-mask").hidden = true;
      showToast("角色显示名称已保存", "success");
      await searchAliases();
    } catch (error) { showToast(`修改失败：${errorText(error)}`, "error"); }
    finally { byId("alias-edit-save").disabled = false; }
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") byId("alias-edit-mask").hidden = true; });
}

/* ------------------------------------------------------------------ Startup */
async function main() {
  initTabs();
  initQuery();
  initAliases();
  byId("btn-refresh").addEventListener("click", loadDashboard);
  byId("btn-qrcode").addEventListener("click", requestQrcode);
  byId("btn-cancel").addEventListener("click", cancelLogin);
  byId("btn-clear-accounts").addEventListener("click", clearAccounts);
  byId("btn-check-accounts").addEventListener("click", checkAccounts);
  window.addEventListener("beforeunload", stopPolling);
  if (bridge && typeof bridge.ready === "function") {
    try { await bridge.ready(); } catch { /* Standalone preview has no host context. */ }
  }
  await loadDashboard();
  await resumeSession();
}

main();
