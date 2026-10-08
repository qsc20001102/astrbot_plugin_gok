//本文件由tools/build_frontend.py自动生成，勿直接编辑；源码SHA256=445ca01ae5d419de165f3e456bf59e0f297431caa5799e3b70d6e8de7f664174
(() => {
  // pages/camp-console/lib/api.js
  var bridge = window.AstrBotPluginPage;
  async function ready() {
    if (!bridge) throw new Error("请从 AstrBot 管理页打开营地页面");
    if (typeof bridge.ready === "function") await bridge.ready();
  }
  var get = (endpoint, params = {}) => bridge.apiGet(endpoint, params);
  var post = (endpoint, payload = {}) => bridge.apiPost(endpoint, payload);

  // pages/camp-console/lib/dom.js
  var html = (strings, ...values) => String.raw({ raw: strings }, ...values);
  var byId = (id) => document.getElementById(id);
  var escapeHtml = (value) => String(value ?? "").replace(
    /[&<>"']/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );
  var errorText = (error) => typeof error === "string" ? error : error?.message || error?.msg || "请求失败，请稍后重试";
  var numberText = (value, suffix = "") => value == null || value === "" || !Number.isFinite(Number(value)) ? "—" : `${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}${suffix}`;
  var clockText = (seconds) => {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
  };
  var safeImageUrl = (value) => {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  };
  function image(url, label = "", className = "hero-image") {
    const safe = safeImageUrl(url);
    return html`<span class="img-wrap ${className}" title="${escapeHtml(label)}"
    >${safe ? html`<img src="${escapeHtml(safe)}" alt="${escapeHtml(label)}" loading="lazy" referrerpolicy="no-referrer" />` : html`<span class="avatar-fallback">${escapeHtml(label.slice(0, 1) || "·")}</span>`}</span
  >`;
  }
  var paths = {
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    user: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    tag: '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r=".7"/>',
    arrow: '<path d="m9 5 7 7-7 7"/>',
    back: '<path d="m15 5-7 7 7 7"/>',
    refresh: '<path d="M20 7a9 9 0 1 0 1 9M20 3v5h-5"/>',
    trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    edit: '<path d="m4 16 12-12 4 4-12 12-5 1zM14 6l4 4"/>',
    qr: '<path d="M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h3v3h3v3h-6v-3h-3v-3h3M12 3v6M3 12h6M12 12h9"/>',
    play: '<path d="m8 4 12 8-12 8z"/>',
    pause: '<path d="M8 4v16M16 4v16"/>'
  };
  var icon = (name) => html`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
    ${paths[name] || paths.arrow}
  </svg>`;
  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((element) => {
      element.innerHTML = icon(element.dataset.icon);
    });
  }
  var toastTimer;
  function showToast(message, kind = "") {
    const element = byId("toast");
    element.textContent = message;
    element.className = `toast ${kind}`;
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      element.hidden = true;
    }, 3200);
  }
  function loading(message = "正在实时查询…") {
    return html`<div class="loading-state" role="status">
    <span class="spinner"></span>${escapeHtml(message)}
  </div>`;
  }
  function empty(message) {
    return html`<div class="empty-state">${escapeHtml(message)}</div>`;
  }

  // pages/camp-console/lib/dialogs.js
  function openModal(id) {
    const mask = byId(id), previous = document.activeElement;
    mask.hidden = false;
    const focusable = () => [
      ...mask.querySelectorAll("button:not(:disabled), input, select")
    ];
    const onKey = (event) => {
      if (event.key === "Tab") {
        const elements = focusable(), first = elements[0], last = elements.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    mask.addEventListener("keydown", onKey);
    focusable()[0]?.focus();
    return () => {
      mask.hidden = true;
      mask.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }
  function askConfirm(title, text, okLabel = "确定") {
    return new Promise((resolve) => {
      byId("confirm-title").textContent = title;
      byId("confirm-text").textContent = text;
      byId("confirm-yes").textContent = okLabel;
      const close = openModal("confirm-mask");
      const finish = (result) => {
        close();
        byId("confirm-yes").removeEventListener("click", yes);
        byId("confirm-no").removeEventListener("click", no);
        document.removeEventListener("keydown", key);
        resolve(result);
      };
      const yes = () => finish(true), no = () => finish(false), key = (event) => {
        if (event.key === "Escape") no();
      };
      byId("confirm-yes").addEventListener("click", yes);
      byId("confirm-no").addEventListener("click", no);
      document.addEventListener("keydown", key);
      byId("confirm-no").focus();
    });
  }

  // pages/camp-console/features/accounts.js
  function initAccounts(onDashboard) {
    function render(summary = {}) {
      const rows = summary.accounts || [];
      byId("account-list").innerHTML = rows.length ? rows.map((row) => {
        const status = row.auth_invalid || !row.ready ? "需重新登录" : !row.available ? `冷却 ${clockText(row.cooled_remaining)}` : row.validation_status === "valid" ? "已验证" : "待验证";
        const platform = row.login_platform === "qq" ? "QQ" : "微信";
        return html`<div class="account-row">
              ${image(row.avatar, row.nickname, "avatar")}
              <div class="account-main">
                <div class="account-name text-wrap">
                  ${escapeHtml(row.nickname)}
                </div>
                <div class="account-meta">
                  ${platform} · ${escapeHtml(row.user_id)}
                </div>
                ${row.validation_message ? html`<div class="account-meta text-wrap">${escapeHtml(row.validation_message)}</div>` : ""}
              </div>
              <span
                class="account-status ${row.validation_status === "valid" && row.available ? "success" : ""}"
                >${escapeHtml(status)}</span
              ><button
                class="button text icon-button danger"
                type="button"
                data-account-delete="${escapeHtml(row.user_id)}"
                aria-label="删除账号 ${escapeHtml(row.nickname)}"
              >
                ${icon("trash")}
              </button>
            </div>`;
      }).join("") : empty("还没有登录账号，请先扫码授权");
    }
    async function reload() {
      try {
        const data = await get("dashboard");
        render(data.accounts);
        onDashboard(data);
        return data;
      } catch (error) {
        showToast(errorText(error), "error");
        return null;
      }
    }
    byId("account-list").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-account-delete]");
      if (!button || !await askConfirm(
        "删除营地账号",
        "删除后需要重新扫码授权，是否继续？",
        "删除"
      ))
        return;
      try {
        await post("accounts/delete", { user_id: button.dataset.accountDelete });
        await reload();
        showToast("账号已删除");
      } catch (error) {
        showToast(errorText(error), "error");
      }
    });
    byId("btn-clear-accounts").addEventListener("click", async () => {
      if (!await askConfirm(
        "清空全部账号",
        "所有账号的登录态都将被删除，需要重新扫码授权。",
        "清空账号"
      ))
        return;
      try {
        await post("accounts/clear");
        await reload();
        showToast("账号已清空");
      } catch (error) {
        showToast(errorText(error), "error");
      }
    });
    byId("btn-check-accounts").addEventListener("click", async () => {
      const button = byId("btn-check-accounts");
      button.disabled = true;
      button.textContent = "正在检测…";
      try {
        const data = await post("accounts/check");
        const result = byId("account-check-result");
        result.hidden = false;
        result.textContent = `检测完成：${data.valid ?? 0} 个有效，${data.invalid ?? 0} 个需重新登录，${data.uncertain ?? 0} 个暂无法确认。`;
        await reload();
      } catch (error) {
        showToast(errorText(error), "error");
      } finally {
        button.disabled = false;
        button.textContent = "检测登录态";
      }
    });
    byId("btn-refresh").addEventListener("click", reload);
    return { reload, render };
  }

  // pages/camp-console/features/aliases.js
  function initAliases(onChange) {
    let rows = [], editingId = "", closeModal = null;
    function render(data = {}) {
      rows = data.list || [];
      byId("alias-list").innerHTML = rows.length ? html`<div class="alias-row header">
            <span>游戏昵称</span><span class="alias-id">营地 ID</span
            ><span>别名</span><span></span>
          </div>
          ${rows.map(
        (row) => html`<div class="alias-row">
                  <span class="text-wrap"
                    >${escapeHtml(row.role_name || "尚未获取昵称")}</span
                  ><span class="alias-id">${escapeHtml(row.gokid)}</span
                  ><span class="text-wrap ${row.alias ? "" : "alias-empty"}"
                    >${escapeHtml(row.alias || "未设置")}</span
                  >
                  <div class="alias-actions">
                    <button
                      class="button text icon-button"
                      data-alias-edit="${escapeHtml(row.gokid)}"
                      aria-label="编辑 ${escapeHtml(row.role_name)} 的别名"
                      type="button"
                    >
                      ${icon("edit")}</button
                    ><button
                      class="button text icon-button danger"
                      data-alias-delete="${escapeHtml(row.gokid)}"
                      aria-label="删除 ${escapeHtml(row.role_name)} 的映射"
                      type="button"
                    >
                      ${icon("trash")}
                    </button>
                  </div>
                </div>`
      ).join("")}` : empty("暂无角色记录，查询成功后会自动保存");
      byId("query-mappings").innerHTML = rows.map(
        (row) => html`<option
            value="${escapeHtml(row.alias || row.role_name || row.gokid)}"
          >
            ${escapeHtml(row.role_name)} · ${escapeHtml(row.gokid)}
          </option>`
      ).join("");
    }
    async function search() {
      try {
        render(
          await get("aliases/list", {
            keyword: byId("alias-search").value.trim()
          })
        );
      } catch (error) {
        showToast(errorText(error), "error");
      }
    }
    byId("alias-search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      search();
    });
    byId("alias-list").addEventListener("click", async (event) => {
      const edit = event.target.closest("[data-alias-edit]"), remove = event.target.closest("[data-alias-delete]");
      if (edit) {
        const row = rows.find(
          (item) => String(item.gokid) === edit.dataset.aliasEdit
        );
        if (!row) return;
        editingId = String(row.gokid);
        byId("alias-edit-meta").textContent = `${row.role_name || "未获取昵称"} · ${row.gokid}`;
        byId("alias-edit-name").value = row.alias || "";
        closeModal = openModal("alias-edit-mask");
        byId("alias-edit-name").focus();
      }
      if (remove && await askConfirm(
        "删除角色映射",
        "下次查询成功会重新记录游戏昵称，当前设置的别名将被删除。",
        "删除"
      )) {
        try {
          await post("aliases/delete", {
            gokid: Number(remove.dataset.aliasDelete)
          });
          await onChange();
          showToast("角色映射已删除");
        } catch (error) {
          showToast(errorText(error), "error");
        }
      }
    });
    const cancel = () => {
      closeModal?.();
      closeModal = null;
    };
    byId("alias-edit-cancel").addEventListener("click", cancel);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") cancel();
    });
    byId("alias-edit-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = byId("alias-edit-save");
      button.disabled = true;
      try {
        await post("aliases/update", {
          gokid: Number(editingId),
          alias: byId("alias-edit-name").value.trim()
        });
        cancel();
        await onChange();
        showToast("别名已保存");
      } catch (error) {
        showToast(errorText(error), "error");
      } finally {
        button.disabled = false;
      }
    });
    return { render, search };
  }

  // pages/camp-console/features/login.js
  function initLogin(onSuccess) {
    const state = {
      platform: "wechat",
      taskId: "",
      generation: 0,
      pollTimer: null,
      countdownTimer: null,
      expiresAt: 0,
      imageReady: false
    };
    const status = (message, kind = "") => {
      byId("qr-status").textContent = message;
      byId("qr-status").className = `qr-status ${kind}`;
    };
    function stopPolling() {
      clearTimeout(state.pollTimer);
      clearTimeout(state.countdownTimer);
      state.generation += 1;
    }
    function platformView() {
      document.querySelectorAll("[data-platform]").forEach((button) => {
        const selected = button.dataset.platform === state.platform;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
      byId("login-note").textContent = `请使用账号对应的${state.platform === "qq" ? " QQ " : "微信"}扫码并在手机上确认。`;
    }
    function reset() {
      state.imageReady = false;
      byId("qr-image").hidden = true;
      byId("qr-image").removeAttribute("src");
      byId("qr-placeholder").hidden = false;
      byId("qr-placeholder").innerHTML = `${icon("qr")}<span>获取二维码后扫码登录</span>`;
      byId("qr-countdown").textContent = "";
      byId("btn-cancel").disabled = true;
    }
    function setImage(session) {
      if (!session.qrcode_base64) return;
      const mime = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp"
      ].includes(session.qrcode_mime) ? session.qrcode_mime : "image/png";
      byId("qr-image").src = `data:${mime};base64,${session.qrcode_base64}`;
      byId("qr-image").hidden = false;
      byId("qr-placeholder").hidden = true;
      state.imageReady = true;
      state.expiresAt = Date.now() + Math.max(0, session.expires_in ?? 180) * 1e3;
    }
    function countdown() {
      if (!state.taskId) return;
      byId("qr-countdown").textContent = state.imageReady ? clockText((state.expiresAt - Date.now()) / 1e3) : "";
      state.countdownTimer = setTimeout(countdown, 1e3);
    }
    async function pollLogin() {
      const generation = state.generation, taskId = state.taskId;
      if (!taskId) return;
      try {
        const result = await post("login/poll", { task_id: taskId });
        if (generation !== state.generation || taskId !== state.taskId) return;
        if (!state.imageReady) setImage(result);
        if (result.status === "success") {
          stopPolling();
          state.taskId = "";
          byId("btn-cancel").disabled = true;
          status("登录成功，账号已保存", "success");
          byId("qr-countdown").textContent = "";
          await onSuccess();
          showToast("营地账号已登录");
          return;
        }
        status(result.message || "等待扫码确认", result.terminal ? "danger" : "");
        if (result.terminal) {
          stopPolling();
          state.taskId = "";
          byId("btn-cancel").disabled = true;
          byId("qr-countdown").textContent = "";
          return;
        }
      } catch (error) {
        if (generation !== state.generation) return;
        status(`暂时无法确认：${errorText(error)}`);
      }
      if (generation === state.generation)
        state.pollTimer = setTimeout(pollLogin, 2e3);
    }
    function adopt(session) {
      stopPolling();
      state.taskId = session.task_id;
      state.platform = session.platform || "wechat";
      state.imageReady = false;
      platformView();
      setImage(session);
      byId("btn-cancel").disabled = false;
      status(session.qrcode_base64 ? "等待扫码确认" : "正在准备 QQ 登录二维码");
      countdown();
      state.pollTimer = setTimeout(pollLogin, 0);
    }
    async function cancelLogin() {
      if (state.taskId) await post("login/cancel", { task_id: state.taskId });
      stopPolling();
      state.taskId = "";
      reset();
      status("已取消登录");
    }
    async function requestQrcode() {
      const button = byId("btn-qrcode");
      button.disabled = true;
      document.querySelectorAll("[data-platform]").forEach((item) => {
        item.disabled = true;
      });
      try {
        if (state.taskId) await cancelLogin();
        reset();
        status("正在准备二维码…");
        adopt(await post("login/qrcode", { platform: state.platform }));
      } catch (error) {
        status(errorText(error), "danger");
      } finally {
        button.disabled = false;
        document.querySelectorAll("[data-platform]").forEach((item) => {
          item.disabled = false;
        });
      }
    }
    async function resumeSession() {
      try {
        const session = await get("login/status");
        if (session.active) adopt(session);
      } catch (error) {
        status(errorText(error), "danger");
      }
    }
    document.querySelectorAll("[data-platform]").forEach(
      (button) => button.addEventListener("click", async () => {
        const next = button.dataset.platform;
        if (next === state.platform) return;
        try {
          if (state.taskId) await cancelLogin();
          state.platform = next;
          platformView();
          reset();
          status("等待开始");
        } catch (error) {
          showToast(errorText(error), "error");
        }
      })
    );
    byId("btn-qrcode").addEventListener("click", requestQrcode);
    byId("btn-cancel").addEventListener(
      "click",
      () => cancelLogin().catch((error) => showToast(errorText(error), "error"))
    );
    window.addEventListener("beforeunload", stopPolling);
    return { resumeSession, stopPolling };
  }

  // pages/camp-console/views/player.js
  function playerIdentity(profile = {}) {
    const rank = profile.rank_label && profile.rank_label !== "未知" ? profile.rank_label : "段位未返回";
    return html`<div class="player-identity">
    ${image(profile.avatar, profile.nickname, "avatar")}
    <div>
      <div class="player-name text-wrap">${escapeHtml(profile.nickname)}</div>
      <div class="player-meta">
        营地 ID
        ${escapeHtml(profile.camp_id)}${profile.area_name ? ` · ${escapeHtml(profile.area_name)}` : ""}
      </div>
    </div>
    <div class="player-ranks">
      <div class="rank-block">
        ${profile.rank_icon ? image(profile.rank_icon, "", "rank-image") : ""}
        <div>
          <div class="rank-value">
            ${escapeHtml(rank)}${rank !== "段位未返回" ? ` <span class="number">${numberText(profile.current_stars)}</span> 星` : ""}
          </div>
        </div>
      </div>
      <div class="rank-block">
        <div>
          <div class="rank-label">巅峰积分</div>
          <div class="rank-value number">
            ${profile.peak_score > 0 ? numberText(profile.peak_score) : "—"}
          </div>
        </div>
      </div>
    </div>
  </div>`;
  }
  function profileView(data) {
    const profile = data.profile || {}, heroes = data.season_heroes || [];
    const metrics = [
      ["赛季场次", profile.season_games],
      ["赛季胜率", profile.season_games > 0 ? `${numberText(profile.win_rate)}%` : "—"],
      ["排位评分", profile.rank_score > 0 ? profile.rank_score : null],
      ["巅峰评分", profile.peak_rating > 0 ? profile.peak_rating : null],
      ["赛季胜场", profile.season_wins],
      ["全场最佳", profile.mvp_count],
      ["金牌次数", profile.gold_count],
      ["区服", profile.server_name || profile.area_name]
    ];
    return html`${playerIdentity(profile)}${profile.hide_match ? '<div class="inline-notice">该玩家隐藏了个人战绩。</div>' : ""}
    <dl class="profile-stats">
      ${metrics.map(
      ([label, value]) => html`<div>
              <dt>${label}</dt>
              <dd>${typeof value === "string" ? escapeHtml(value) : numberText(value)}</dd>
            </div>`
    ).join("")}
    </dl>
    <div class="section-heading">
      <h2>赛季常用英雄</h2>
      <span class="muted">${escapeHtml(data.season_name)}</span>
    </div>
    ${heroes.length ? html`<div class="hero-stat-row header">
              <span>英雄</span><span>场次</span><span>胜率</span
              ><span>战力</span>
            </div>
            ${heroes.map(
      (hero) => html`<div class="hero-stat-row">
                    <div class="match-hero">
                      ${image(hero.hero_icon, hero.hero_name)}<span
                        >${escapeHtml(hero.hero_name)}</span
                      >
                    </div>
                    <span class="number">${numberText(hero.games)}</span
                    ><span class="number">${numberText(hero.win_rate)}%</span
                    ><span class="number">${numberText(hero.fight_power)}</span>
                  </div>`
    ).join("")}` : '<div class="empty-state">营地暂未返回本赛季英雄统计</div>'}`;
  }
  function battleView(data, option, limit) {
    const summary = data.summary || {}, rows = data.list || [];
    const cells = [
      [`最近 ${summary.total ?? rows.length} 场`, ""],
      ["胜率", `${numberText(summary.win_rate)}%`],
      ["场均 KDA", numberText(summary.avg_kda)],
      ["平均评分", summary.avg_score > 0 ? numberText(summary.avg_score) : "—"]
    ];
    return html`${playerIdentity(data.profile)}
    <div class="summary-strip">
      ${cells.map(
      ([label, value], index) => html`<div class="summary-cell">
              ${index ? html`<div class="label">${label}</div>
                      <div class="value">${value}</div>` : html`<div class="value">${label}</div>`}
            </div>`
    ).join("")}
    </div>
    <div class="match-toolbar">
      <h2>近期对局</h2>
      <div class="match-controls">
        <div class="segmented" role="group" aria-label="战绩模式">
          ${[
      [0, "全部"],
      [1, "排位"],
      [4, "巅峰"]
    ].map(
      ([value, label]) => html`<button
                  type="button"
                  data-option="${value}"
                  class="${option === value ? "active" : ""}"
                  aria-pressed="${option === value}"
                >
                  ${label}
                </button>`
    ).join("")}
        </div>
        <select id="query-limit" aria-label="战绩场数">
          ${[5, 10, 15, 25].map((value) => html`<option value="${value}" ${value === limit ? "selected" : ""}>${value} 场</option>`).join("")}
        </select>
      </div>
    </div>
    <div class="match-list">
      <div class="match-labels">
        <span>英雄</span><span>对局</span><span>KDA</span
        ><span>评分 / 荣誉</span><span>时长</span><span></span>
      </div>
      ${rows.map(
      (row, index) => html`<button
              type="button"
              class="match-row ${row.result === "win" ? "win" : row.result === "lose" ? "lose" : "unknown"}"
              data-match="${escapeHtml(row.game_seq)}"
              data-index="${index + 1}"
              aria-label="查看 ${escapeHtml(row.hero_name)} ${escapeHtml(row.played_at)} 的对局详情"
            >
              <div class="match-hero">
                ${image(row.hero_icon, row.hero_name)}
                <div>
                  <div class="match-hero-name">${escapeHtml(row.hero_name)}</div>
                  <div class="match-mode">
                    ${escapeHtml(row.mode_name)}${row.kill_streaks?.length ? ` · ${row.kill_streaks.map((item) => escapeHtml(item.label)).join(" / ")}` : ""}${row.first_blood ? " · 一血" : ""}${row.rank_name ? ` · ${escapeHtml(row.rank_name)} ${row.stars}星` : ""}
                  </div>
                </div>
              </div>
              <div class="match-info">
                <span class="match-time">${escapeHtml(row.played_at)}</span
                ><span
                  class="match-result ${row.result === "win" ? "success" : row.result === "lose" ? "danger" : "muted"}"
                  >${escapeHtml(row.result_text)}</span
                >
              </div>
              <div class="match-kda">
                ${row.kills} / ${row.deaths} / ${row.assists}
              </div>
              <div class="match-score">
                ${row.score > 0 ? numberText(row.score) : "—"}${row.mvp_type ? safeImageUrl(row.mvp_icon) ? image(row.mvp_icon, row.mvp_type === "svp" ? "SVP" : "MVP", "honor-image") : html`<span class="honor-label">${row.mvp_type === "svp" ? "SVP" : "MVP"}</span>` : row.medal ? safeImageUrl(row.medal_icon) ? image(row.medal_icon, row.medal, "honor-image") : html`<span class="honor-label">${escapeHtml(row.medal)}</span>` : ""}
              </div>
              <div class="match-duration">
                ${row.duration_sec > 0 ? escapeHtml(row.duration_text) : "—"}${row.peak_delta != null ? html`<span class="metric-small">巅峰 ${row.peak_delta > 0 ? "+" : ""}${numberText(row.peak_delta)}</span>` : ""}
              </div>
              ${icon("arrow")}
            </button>`
    ).join("")}
    </div>
    <p class="list-note">
      显示 ${rows.length} 场 · 本次统计 ${summary.total ?? rows.length}
      场。点击对局查看双方表现与地图回顾。
    </p>`;
  }
  function selectionView(data) {
    return html`<h2>选择要查询的玩家</h2>
    <p class="muted">
      找到多个同名用户，选择营地 ID 后继续查询。候选在 60 秒后过期。
    </p>
    <div class="selection-list">
      ${(data.candidates || []).map(
      (row) => html`<button
              class="selection-row"
              data-candidate="${escapeHtml(row.uid)}"
              type="button"
            >
              ${image(row.avatar, row.name, "avatar")}
              <div class="selection-main">
                <div class="selection-name">${escapeHtml(row.name)}</div>
                <div class="selection-meta">
                  ${escapeHtml(row.region)} · ${escapeHtml(row.dw)} · 营地 ID ${escapeHtml(row.uid)}
                </div>
              </div>
              ${icon("arrow")}
            </button>`
    ).join("")}
    </div>
    <button class="button text" id="cancel-selection" type="button">
      取消选择
    </button>`;
  }

  // pages/camp-console/views/detail.js
  function shareMeter(value) {
    if (value == null || !Number.isFinite(Number(value))) return "";
    const percent = Math.min(100, Math.max(0, Number(value)));
    return html`<span class="damage-share">
    <span
      class="share-track"
      role="meter"
      aria-label="队伍占比"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow="${percent}"
      ><span style="width:${percent}%"></span
    ></span>
    <span class="share-value">${numberText(value)}%</span>
  </span>`;
  }
  function detailShell(data) {
    const match = data.match || {};
    return html`<button
      class="button text detail-back"
      id="back-to-battles"
      type="button"
    >
      ${icon("back")}返回战绩
    </button>
    <h1>单局详情</h1>
    <div class="detail-heading">
      <span class="detail-result ${match.result === "lose" ? "lose" : ""}"
        >${escapeHtml(match.result_text)}</span
      >
      <div class="match-hero">
        ${image(match.hero_icon, match.hero_name)}
        <div>
          <strong>${escapeHtml(match.hero_name)}</strong>
          <div class="metric-small">${escapeHtml(data.profile?.nickname)}</div>
        </div>
      </div>
      <div class="detail-fact">
        ${escapeHtml(match.mode_name)}<small>对局模式</small>
      </div>
      <div class="detail-fact">
        ${escapeHtml(match.played_at)}<small>对局时间</small>
      </div>
      <div class="detail-fact">
        ${match.duration_sec > 0 ? escapeHtml(match.duration_text) : "—"}<small
          >对局时长</small
        >
      </div>
    </div>
    <div class="detail-tabs" role="tablist" aria-label="详情内容">
      <button
        class="active"
        data-detail-tab="overview"
        role="tab"
        aria-selected="true"
        type="button"
      >
        对局概览</button
      ><button
        data-detail-tab="replay"
        role="tab"
        aria-selected="false"
        type="button"
      >
        地图回顾
      </button>
    </div>
    <div id="detail-overview" role="tabpanel">${overview(data)}</div>
    <div id="detail-replay" role="tabpanel" hidden></div>`;
  }
  function overview(data) {
    if (!data.has_detail)
      return '<div class="empty-state">这场对局的玩家详情暂未返回，稍后可重新查询。</div>';
    const team = (side, label) => {
      const rows = data[side] || [], summary = data[`${side}_summary`] || {};
      return html`<section class="team-section team-${side}">
      <div class="team-title">
        <h3><span class="team-dot ${side}"></span>${label}</h3>
        <span class="team-meta"
          >${numberText(summary.kills)} 击杀 · ${numberText(summary.money)}
          经济${summary.complete === false ? " · 玩家数据未完整返回" : ""}</span
        >
      </div>
      <div class="table-scroll">
        <table class="detail-table">
          <colgroup>
            <col class="detail-col-player" />
            <col class="detail-col-kda" />
            <col class="detail-col-score" />
            <col class="detail-col-equipment" />
            <col class="detail-col-skill" />
            <col class="detail-col-money" />
            <col class="detail-col-damage" />
            <col class="detail-col-damage" />
          </colgroup>
          <thead>
            <tr>
              <th>玩家 / 英雄</th>
              <th>KDA</th>
              <th>评分</th>
              <th>出装</th>
              <th>召唤师技能</th>
              <th>经济</th>
              <th>英雄伤害</th>
              <th>英雄承伤</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(
        (row) => html`<tr class="${row.is_target ? "target-row" : ""}">
                    <td>
                      <div class="player-cell">
                        ${image(row.hero_icon, row.hero_name)}
                        <div>
                          <strong title="${escapeHtml(row.nickname || row.hero_name)}"
                            >${escapeHtml(row.nickname || row.hero_name)}</strong
                          ><small
                            >${escapeHtml(row.hero_name)} · ${numberText(row.level)} 级</small
                          >
                        </div>
                      </div>
                    </td>
                    <td>${row.kills}/${row.deaths}/${row.assists}</td>
                    <td>
                      ${numberText(row.score)}${row.mvp ? html`<span class="metric-small honor-label">${row.mvp_type === "svp" ? "SVP" : row.mvp_type === "mvp" ? "MVP" : "最佳"}</span>` : ""}
                    </td>
                    <td>
                      <div class="equipment-build">
                        ${(row.equipment || []).slice(0, 6).map(
          (item) => image(
            item.icon,
            item.name || item.id,
            "equipment-icon"
          )
        ).join("")}
                      </div>
                    </td>
                    <td>
                      ${row.skill?.icon ? html`<div class="summoner-skill">${image(row.skill.icon, row.skill.name, "skill-icon")}<span>${escapeHtml(row.skill.name)}</span></div>` : "—"}
                    </td>
                    <td>${numberText(row.money)}</td>
                    <td>
                      ${numberText(row.hero_damage)}${shareMeter(row.hero_damage_percent)}
                    </td>
                    <td>
                      ${numberText(row.damage_taken)}${shareMeter(row.damage_taken_percent)}
                    </td>
                  </tr>`
      ).join("")}
          </tbody>
        </table>
      </div>
    </section>`;
    };
    const players = [...data.blue || [], ...data.red || []];
    return `${team("blue", "蓝方")}${team("red", "红方")}<section class="performance-section"><div class="performance-controls"><h2>本场表现</h2><select id="detail-player" aria-label="查看玩家表现">${players.map((row) => html`<option value="${escapeHtml(row.player_key || row.role_id)}" ${row.is_target ? "selected" : ""}>${escapeHtml(row.nickname || row.hero_name)} · ${escapeHtml(row.hero_name)}</option>`).join("")}</select></div><div id="player-performance"></div><p class="list-note">伤害与承伤进度条表示队伍占比。未返回的统计显示为“—”。</p></section>`;
  }
  function performanceView(row = {}) {
    const delta = row.fight_power_delta;
    const metrics = [
      ["总伤害", row.total_damage, ""],
      ["总承伤", row.total_damage_taken, ""],
      ["参团率", row.participation, "%"],
      ["控制时长", row.control_seconds, " 秒"],
      ["补刀", row.minions, ""],
      ["治疗量", row.healing, ""],
      ["建筑伤害", row.building_damage, ""],
      ["推塔数", row.tower_count, ""],
      ["野怪经济", row.jungle_economy, ""],
      ["英雄战力", row.fight_power || null, ""],
      [
        "战力变化",
        delta == null ? "—" : `${delta > 0 ? "+" : ""}${numberText(delta)}`,
        ""
      ]
    ];
    return html`<div class="performance-metrics">
      ${metrics.map(
      ([label, value, suffix]) => html`<div>
              <div class="metric-label">${label}</div>
              <div class="metric-value">
                ${typeof value === "string" ? escapeHtml(value) : numberText(value, suffix)}
              </div>
            </div>`
    ).join("")}
    </div>
    <div class="ratings">
      ${(row.ratings || []).map((item) => html`<span class="rating">${escapeHtml(item.label)}<strong>${escapeHtml(item.grade)}</strong></span>`).join("")}
    </div>
    ${(row.performance || []).map(
      (group) => html`<div class="performance-group">
            <h3>${escapeHtml(group.title)}</h3>
            ${group.items.map((item) => html`<div class="performance-item"><span class="label">${escapeHtml(item.name)}</span><span class="${item.highlight ? "success" : ""}">${escapeHtml(item.value)}</span>${item.note ? html`<span class="performance-note ${item.note_highlight ? "success" : ""}">${escapeHtml(item.note_text || item.note)}</span>` : ""}</div>`).join("")}
          </div>`
    ).join(
      ""
    )}${row.honors?.length ? html`<div class="stat-honors">${row.honors.map(escapeHtml).join(" · ")}</div>` : ""}`;
  }

  // pages/camp-console/views/replay.js
  function replayEventsAtTime(events, seconds, pinnedId = "") {
    if (!Number.isFinite(seconds)) return [];
    if (pinnedId) return events.filter((event) => event.id === pinnedId);
    return events.filter(
      (event) => Number.isFinite(event.time_seconds) && event.time_seconds <= seconds && seconds - event.time_seconds < 6
    ).sort((first, second) => first.time_seconds - second.time_seconds);
  }
  function renderReplay(root, data) {
    if (!data.available) {
      root.innerHTML = html`<div class="replay-state">
      <h3>暂无地图回顾</h3>
      <p>${escapeHtml(data.message || "这场对局的回顾数据暂未返回")}</p>
    </div>`;
      return () => {
      };
    }
    const players = data.players || [], events = data.events || [], towers = data.towers || [];
    let selected = players.find((player) => player.is_target)?.player_id || players[0]?.player_id || "";
    let seconds = 0, filter = "all", selectedEvent = "", pinnedEvent = "", liveSignature = "", playing = false, frameId = null, previousTime = null;
    const duration = Number(data.duration_seconds) || 0;
    root.innerHTML = html`<div class="replay-layout">
    <section class="replay-map-panel">
      <div class="replay-map-tools">
        <select id="replay-player" aria-label="选择轨迹玩家">
          ${players.map((player) => html`<option value="${escapeHtml(player.player_id)}" ${player.player_id === selected ? "selected" : ""}>${escapeHtml(player.nickname || player.hero_name)} · ${escapeHtml(player.hero_name)}</option>`).join("")}
        </select>
        <div class="replay-trail-tools">
          <label
            ><input id="replay-show-trail" type="checkbox" checked />
            显示轨迹</label
          >
          <select
            id="replay-trail-window"
            class="trail-window"
            aria-label="轨迹范围"
          >
            <option value="30">近 30 秒</option>
            <option value="60">近 60 秒</option>
            <option value="0">全部轨迹</option>
          </select>
        </div>
      </div>
      <div class="replay-map">
        <img
          id="replay-map-image"
          src="${escapeHtml(safeImageUrl(data.map_image))}"
          alt="营地官方回顾地图"
        /><svg
          id="replay-overlay"
          class="replay-overlay"
          viewBox="0 0 100 100"
          role="img"
          aria-label="玩家位置与移动轨迹"
        ></svg>
        <div
          id="replay-live-event"
          class="replay-live-event"
          role="status"
          aria-live="polite"
          hidden
        ></div>
      </div>
      <div class="replay-controls">
        <button
          id="replay-play"
          class="replay-play"
          type="button"
          aria-label="播放回顾"
        >
          ${icon("play")}</button
        ><span id="replay-time" class="replay-time"
          >0:00 / ${clockText(duration)}</span
        ><input
          id="replay-slider"
          class="replay-slider"
          type="range"
          min="0"
          max="${duration}"
          value="0"
          step="1"
          aria-label="对局回顾时间"
        /><select id="replay-speed" class="replay-speed" aria-label="播放速度">
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4" selected>4×</option>
        </select>
      </div>
      <div class="map-legend">
        <span class="map-key"><i></i>蓝方</span
        ><span class="map-key enemy"><i></i>红方</span
        ><span class="map-key event"><i></i>事件位置</span>
      </div>
      <div class="map-message" id="map-message">
        点击事件，在地图定位；也可拖动时间轴查看位置。
      </div>
    </section>
    <section class="replay-events-panel">
      <h2>关键事件</h2>
      <div class="event-filters" role="group" aria-label="事件类型">
        ${[
      ["all", "全部"],
      ["kill", "击杀"],
      ["battle", "战斗"],
      ["tower", "推塔"],
      ["resource", "资源"]
    ].map(
      ([value, label]) => html`<button
                class="event-filter ${value === filter ? "active" : ""}"
                type="button"
                data-event-filter="${value}"
                aria-pressed="${value === filter}"
              >
                ${label}
              </button>`
    ).join("")}
      </div>
      <div id="event-list" class="event-list"></div>
      <p class="event-list-note">
        点选事件查看参与英雄。建筑记录可能重复，不按记录条数计算摧毁次数。
      </p>
    </section>
  </div>`;
    const overlay = root.querySelector("#replay-overlay"), slider = root.querySelector("#replay-slider"), playButton = root.querySelector("#replay-play"), message = root.querySelector("#map-message");
    const valid = (point) => point && Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.x <= 100 && point.y >= 0 && point.y <= 100;
    const alive = (player, time) => {
      if (!player?.has_revive_data) return true;
      const lastDeath = Math.max(
        -1,
        ...(player.deaths || []).filter((item) => item.time_seconds <= time).map((item) => item.time_seconds)
      );
      const lastRevive = Math.max(
        -1,
        ...(player.revives || []).filter((item) => item.time_seconds <= time).map((item) => item.time_seconds)
      );
      return lastDeath < 0 || lastRevive >= lastDeath;
    };
    overlay.innerHTML = html`<defs
      >${players.map((player, index) => html`<clipPath id="replay-face-${index}"><circle r="2.3" /></clipPath>`).join("")}</defs
    >
    <g id="replay-towers"
      >${towers.filter((tower) => valid(tower.position)).map(
      (tower) => html`<g
              class="tower-marker"
              data-replay-tower="${escapeHtml(tower.id)}"
              transform="translate(${tower.position.x} ${tower.position.y})"
              style="color:${tower.camp === 2 ? "#e86d73" : "#5d94ff"}"
              ><title>${escapeHtml(tower.name)}</title
              ><circle
                r="2.2"
                fill="#142235"
                fill-opacity=".85"
                stroke="currentColor"
                stroke-width=".35" /><path
                d="M-1.2-1.4h.6v.6h.6v-.6h.6v.6h.6v-.6h.6v1.2h-.4v1.7h-2.2V-.2h-.4z"
                fill="currentColor"
                stroke="white"
                stroke-width=".13"
            /></g>`
    ).join("")}</g
    >
    <g id="replay-trails"></g
    ><g id="replay-members"
      >${players.map((member, index) => html`<g class="player-marker" data-replay-player="${escapeHtml(member.player_id)}" style="color:${member.camp === 2 ? "#e86d73" : "#5d94ff"}" role="button" aria-label="查看${escapeHtml(member.hero_name)}轨迹"><title>${escapeHtml(member.nickname)} · ${escapeHtml(member.hero_name)}</title><circle r="2.5" fill="currentColor" stroke="white" stroke-width=".4" /><text text-anchor="middle" y=".8" font-size="2.4" fill="white">${escapeHtml(member.hero_name?.slice(0, 1) || "?")}</text>${safeImageUrl(member.hero_icon) ? html`<image href="${escapeHtml(safeImageUrl(member.hero_icon))}" x="-2.3" y="-2.3" width="4.6" height="4.6" preserveAspectRatio="xMidYMid slice" clip-path="url(#replay-face-${index})" />` : ""}<circle r="2.5" fill="none" stroke="currentColor" stroke-width=".45" /><circle class="player-selection" r="3.1" fill="none" stroke="currentColor" stroke-width=".5" /></g>`).join("")}</g
    ><g id="replay-event-position"></g>`;
    const towerNodes = new Map(
      [...overlay.querySelectorAll("[data-replay-tower]")].map((node) => [
        node.dataset.replayTower,
        node
      ])
    );
    const playerNodes = new Map(
      [...overlay.querySelectorAll("[data-replay-player]")].map((node) => [
        node.dataset.replayPlayer,
        node
      ])
    );
    const playerLayer = overlay.querySelector("#replay-members");
    function draw() {
      const currentEvents = replayEventsAtTime(events, seconds, pinnedEvent);
      const latest = currentEvents[currentEvents.length - 1];
      const nextSelected = latest?.id || "";
      if (selectedEvent !== nextSelected) {
        selectedEvent = nextSelected;
        renderEvents();
        if (playing) {
          const list = root.querySelector("#event-list");
          const active = list.querySelector(".event-row.active");
          if (active) {
            const bounds = list.getBoundingClientRect(), item = active.getBoundingClientRect();
            if (item.top < bounds.top) list.scrollTop += item.top - bounds.top;
            else if (item.bottom > bounds.bottom)
              list.scrollTop += item.bottom - bounds.bottom;
          }
        }
      }
      const signature = currentEvents.map((event2) => event2.id).join("|");
      if (signature !== liveSignature) {
        liveSignature = signature;
        const banner = root.querySelector("#replay-live-event");
        banner.hidden = currentEvents.length === 0;
        banner.innerHTML = currentEvents.slice(-3).map(
          (event2) => html`<div class="live-event-row" data-live-event="${escapeHtml(event2.id)}">
                <time>${clockText(event2.time_seconds)}</time>
                <div>
                  <strong>${escapeHtml(event2.title)}</strong
                  >${event2.description ? html`<span>${escapeHtml(event2.description)}</span>` : ""}
                </div>
              </div>`
        ).join("") + (currentEvents.length > 3 ? html`<div class="live-event-more">
              另有 ${currentEvents.length - 3} 条事件，见事件列表
            </div>` : "");
      }
      const player = players.find((item) => item.player_id === selected), trail = player?.points || [];
      const parts = [];
      if (root.querySelector("#replay-show-trail").checked) {
        let segment = [];
        const flush = () => {
          if (segment.length > 1)
            parts.push(
              html`<polyline
              points="${segment.join(" ")}"
              fill="none"
              stroke="#e8b85c"
              stroke-width=".6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />`
            );
          segment = [];
        };
        const windowSeconds = Number(
          root.querySelector("#replay-trail-window").value
        );
        for (const point of trail) {
          if (point.time_seconds > seconds) break;
          if (windowSeconds && point.time_seconds < seconds - windowSeconds)
            continue;
          if (!valid(point.position) || !alive(player, point.time_seconds))
            flush();
          else segment.push(`${point.position.x},${point.position.y}`);
        }
        flush();
      }
      for (const tower of towers) {
        const node = towerNodes.get(tower.id);
        if (node)
          node.style.display = tower.destroyed_at != null && seconds >= tower.destroyed_at ? "none" : "";
      }
      for (const member of players) {
        const node = playerNodes.get(member.player_id);
        const point = member.points?.[Math.min(Math.floor(seconds), member.points.length - 1)]?.position;
        const visible = valid(point) && alive(member, seconds);
        node.style.display = visible ? "" : "none";
        if (!visible) continue;
        const chosen = member.player_id === selected;
        node.classList.toggle("selected", chosen);
        node.setAttribute(
          "transform",
          `translate(${point.x} ${point.y}) scale(${chosen ? 1.2 : 1})`
        );
        if (chosen) playerLayer.appendChild(node);
      }
      overlay.querySelector("#replay-trails").innerHTML = parts.join("");
      const eventParts = [];
      const event = events.find((item) => item.id === selectedEvent);
      if (event && valid(event.position))
        eventParts.push(
          html`<g
          ><title>${escapeHtml(event.title)}</title
          ><circle
            cx="${event.position.x}"
            cy="${event.position.y}"
            r="2.6"
            fill="none"
            stroke="#f6cf76"
            stroke-width=".6" /><circle
            cx="${event.position.x}"
            cy="${event.position.y}"
            r=".8"
            fill="#f6cf76"
        /></g>`
        );
      overlay.querySelector("#replay-event-position").innerHTML = eventParts.join("");
      root.querySelector("#replay-time").textContent = `${clockText(seconds)} / ${clockText(duration)}`;
      slider.value = String(seconds);
      message.textContent = event ? event.position ? `${clockText(event.time_seconds)} · ${event.title}` : `${clockText(event.time_seconds)} · 此事件未返回位置，可查看当时玩家轨迹。` : data.has_trajectory ? "点击事件，在地图定位；也可拖动时间轴查看位置。" : "这场回顾有事件记录，暂未返回玩家轨迹。";
    }
    function renderEvents() {
      const shown = events.filter(
        (item) => filter === "all" || item.type === filter
      );
      root.querySelector("#event-list").innerHTML = shown.length ? shown.map(
        (item) => html`<button
                class="event-row ${item.id === selectedEvent ? "active" : ""}"
                data-event="${escapeHtml(item.id)}"
                type="button"
                aria-expanded="${item.id === selectedEvent && Boolean(item.details_lines?.length)}"
              >
                <span class="event-dot ${escapeHtml(item.type)}"></span
                ><span class="event-time">${clockText(item.time_seconds)}</span>
                <div class="event-body">
                  <div class="event-title">${escapeHtml(item.title)}</div>
                  ${item.description ? html`<div class="event-description">${escapeHtml(item.description)}</div>` : item.camp ? html`<div class="event-description">${item.camp === 1 ? "蓝方" : "红方"}</div>` : ""}
                  ${item.id === selectedEvent && item.details_lines?.length ? html`<div class="event-context">${item.details_lines.map((line) => html`<div>${escapeHtml(line)}</div>`).join("")}</div>` : ""}
                </div>
                ${icon("arrow")}
              </button>`
      ).join("") : empty("此分类暂无事件");
    }
    function pause() {
      playing = false;
      cancelAnimationFrame(frameId);
      frameId = null;
      previousTime = null;
      playButton.innerHTML = icon("play");
      playButton.setAttribute("aria-label", "播放回顾");
    }
    function advance(now) {
      if (!playing) return;
      if (!root.isConnected) return pause();
      if (previousTime !== null)
        seconds = Math.min(
          duration,
          seconds + Math.min((now - previousTime) / 1e3, 0.25) * Number(root.querySelector("#replay-speed").value)
        );
      previousTime = now;
      draw();
      if (seconds >= duration) pause();
      else frameId = requestAnimationFrame(advance);
    }
    root.querySelector("#replay-play").addEventListener("click", () => {
      if (playing) return pause();
      if (seconds >= duration) seconds = 0;
      pinnedEvent = "";
      playing = true;
      root.querySelector("#replay-play").innerHTML = icon("pause");
      root.querySelector("#replay-play").setAttribute("aria-label", "暂停回顾");
      frameId = requestAnimationFrame(advance);
    });
    slider.addEventListener("input", () => {
      pause();
      seconds = Number(slider.value);
      pinnedEvent = "";
      draw();
    });
    root.querySelector("#replay-player").addEventListener("change", (event) => {
      selected = event.target.value;
      draw();
    });
    root.querySelector("#replay-show-trail").addEventListener("change", draw);
    root.querySelector("#replay-trail-window").addEventListener("change", draw);
    root.querySelector("#event-list").addEventListener("click", (event) => {
      const button = event.target.closest("[data-event]");
      if (!button) return;
      const item = events.find((row) => row.id === button.dataset.event);
      if (!item) return;
      pause();
      seconds = Math.min(duration, item.time_seconds);
      pinnedEvent = item.id;
      draw();
    });
    root.querySelector(".event-filters").addEventListener("click", (event) => {
      const button = event.target.closest("[data-event-filter]");
      if (!button) return;
      filter = button.dataset.eventFilter;
      root.querySelectorAll("[data-event-filter]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderEvents();
    });
    overlay.addEventListener("click", (event) => {
      const marker = event.target.closest("[data-replay-player]");
      if (!marker) return;
      selected = marker.dataset.replayPlayer;
      root.querySelector("#replay-player").value = selected;
      draw();
    });
    root.querySelector("#replay-map-image").addEventListener("error", () => {
      message.textContent = "地图底图暂时无法加载，请稍后重试。";
    });
    renderEvents();
    draw();
    return pause;
  }

  // pages/camp-console/features/analysis.js
  function mountAnalysis(root, { keyword, gameSeq, index }) {
    const panel = document.createElement("section");
    panel.className = "analysis-panel";
    panel.innerHTML = html`<div class="analysis-heading">
      <div>
        <h2>AI 对局分析</h2>
        <p>结合双方表现、全员轨迹和关键事件，分析胜负原因与关键转折。</p>
      </div>
      <button class="button primary" type="button">分析本场</button>
    </div>
    <p class="analysis-status" role="status" aria-live="polite">
      点击分析本场，获取职业教练视角的对局复盘。
    </p>
    <pre class="analysis-result" hidden></pre>`;
    root.append(panel);
    const button = panel.querySelector("button"), status = panel.querySelector(".analysis-status"), output = panel.querySelector(".analysis-result");
    let disposed = false, timer = null, taskId = "";
    const current = () => !disposed && panel.isConnected;
    async function poll() {
      try {
        const job = await get("analysis/status", { task_id: taskId });
        if (!current()) return;
        status.textContent = job.message;
        status.classList.toggle("error", job.status === "error");
        if (job.status === "done") {
          output.textContent = job.text;
          output.hidden = false;
          taskId = "";
          button.disabled = false;
          button.textContent = "重新分析";
        } else if (job.status === "error") {
          taskId = "";
          button.disabled = false;
          button.textContent = "重试分析";
        } else {
          timer = setTimeout(poll, 1500);
        }
      } catch (error) {
        if (!current()) return;
        status.textContent = errorText(error);
        status.classList.add("error");
        button.disabled = false;
        if (status.textContent.includes("分析任务已过期或不存在")) taskId = "";
        button.textContent = taskId ? "重试连接" : "重试分析";
      }
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "分析中…";
      status.classList.remove("error");
      if (taskId) {
        await poll();
        return;
      }
      output.hidden = true;
      output.textContent = "";
      status.textContent = "正在启动分析…";
      try {
        const job = await post("analysis/start", {
          keyword,
          game_seq: gameSeq,
          index
        });
        if (!current()) return;
        taskId = job.task_id;
        await poll();
      } catch (error) {
        if (!current()) return;
        status.textContent = errorText(error);
        status.classList.add("error");
        button.disabled = false;
        button.textContent = "重试分析";
      }
    });
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }

  // pages/camp-console/features/query.js
  function initQuery(onData) {
    const root = byId("query-result");
    const state = {
      keyword: "",
      kind: "battle",
      option: 0,
      limit: 10,
      busy: false,
      generation: 0,
      selectionTimer: null,
      replayCleanup: null,
      analysisCleanup: null
    };
    function cleanup() {
      clearTimeout(state.selectionTimer);
      state.analysisCleanup?.();
      state.analysisCleanup = null;
      const pause = state.replayCleanup;
      state.replayCleanup = null;
      pause?.();
    }
    function busy(value) {
      state.busy = value;
      byId("btn-query-profile").disabled = value;
      byId("btn-query-battle").disabled = value;
    }
    function detailMode(active) {
      document.querySelector(".main-content").classList.toggle("detail-mode", active && !byId("panel-query").hidden);
      byId("query-form").hidden = active;
      document.querySelector("#panel-query > .page-heading").hidden = active;
    }
    function queryError(error, retry) {
      root.innerHTML = html`<div class="error-state">
      <h2>这次查询没有完成</h2>
      <p>${escapeHtml(errorText(error))}</p>
      <button id="retry-query" class="button outline" type="button">
        重新查询
      </button>
    </div>`;
      byId("retry-query").addEventListener("click", retry);
    }
    async function run(kind = "battle", keyword = byId("query-keyword").value.trim()) {
      if (state.busy) return;
      if (!keyword) {
        byId("query-keyword").focus();
        showToast("请输入营地 ID、游戏昵称或别名");
        return;
      }
      cleanup();
      detailMode(false);
      busy(true);
      state.keyword = keyword;
      state.kind = kind;
      const generation = ++state.generation;
      root.innerHTML = loading();
      try {
        const response = await get("query", {
          keyword,
          type: kind,
          limit: state.limit,
          option: state.option
        });
        if (generation !== state.generation) return;
        const data = response.data;
        if (response.type === "selection") {
          root.innerHTML = selectionView(data);
          state.selectionTimer = setTimeout(() => {
            state.generation += 1;
            root.innerHTML = empty("候选已过期，请重新查询");
          }, 6e4);
          root.querySelectorAll("[data-candidate]").forEach(
            (button) => button.addEventListener("click", () => {
              byId("query-keyword").value = button.dataset.candidate;
              run(kind, button.dataset.candidate);
            })
          );
          byId("cancel-selection").addEventListener("click", () => {
            cleanup();
            root.innerHTML = empty("已取消选择");
          });
          return;
        }
        root.innerHTML = kind === "profile" ? profileView(data) : battleView(data, state.option, state.limit);
        onData?.();
        root.querySelectorAll("[data-option]").forEach(
          (button) => button.addEventListener("click", () => {
            state.option = Number(button.dataset.option);
            run("battle", state.keyword);
          })
        );
        root.querySelector("#query-limit")?.addEventListener("change", (event) => {
          state.limit = Number(event.target.value);
          run("battle", state.keyword);
        });
        root.querySelectorAll("[data-match]").forEach(
          (button) => button.addEventListener(
            "click",
            () => openDetail(button.dataset.match, Number(button.dataset.index))
          )
        );
      } catch (error) {
        if (generation === state.generation)
          queryError(error, () => run(kind, keyword));
      } finally {
        if (generation === state.generation) busy(false);
      }
    }
    async function openDetail(gameSeq, index) {
      if (state.busy) return;
      cleanup();
      busy(true);
      root.innerHTML = loading("正在读取单局详情…");
      const generation = ++state.generation;
      try {
        const response = await get("query", {
          keyword: state.keyword,
          type: "detail",
          game_seq: gameSeq,
          index
        });
        if (generation !== state.generation) return;
        detailMode(true);
        root.innerHTML = detailShell(response.data);
        const players = [
          ...response.data.blue || [],
          ...response.data.red || []
        ];
        const selectPlayer = () => {
          const select = byId("detail-player");
          const row = players.find(
            (player) => (player.player_key || player.role_id) === select?.value
          ) || response.data.target || players[0];
          if (byId("player-performance"))
            byId("player-performance").innerHTML = performanceView(row);
        };
        selectPlayer();
        byId("detail-player")?.addEventListener("change", selectPlayer);
        byId("back-to-battles").addEventListener(
          "click",
          () => run("battle", state.keyword)
        );
        let replayLoaded = false, replayBusy = false;
        root.querySelectorAll("[data-detail-tab]").forEach(
          (button) => button.addEventListener("click", async () => {
            const isReplay = button.dataset.detailTab === "replay";
            root.querySelectorAll("[data-detail-tab]").forEach((tab) => {
              const active = tab === button;
              tab.classList.toggle("active", active);
              tab.setAttribute("aria-selected", String(active));
            });
            byId("detail-overview").hidden = isReplay;
            byId("detail-replay").hidden = !isReplay;
            if (!isReplay) {
              state.replayCleanup?.();
              return;
            }
            if (replayLoaded || replayBusy) return;
            replayBusy = true;
            byId("detail-replay").innerHTML = loading("正在读取地图回顾…");
            try {
              const replay = await get("query", {
                keyword: state.keyword,
                type: "replay",
                game_seq: gameSeq,
                index
              });
              if (generation !== state.generation) return;
              state.replayCleanup = renderReplay(
                byId("detail-replay"),
                replay.data
              );
              state.analysisCleanup = mountAnalysis(byId("detail-replay"), {
                keyword: state.keyword,
                gameSeq,
                index
              });
              replayLoaded = true;
            } catch (error) {
              if (generation === state.generation)
                byId("detail-replay").innerHTML = html`<div class="replay-state">
                <h3>地图回顾暂不可用</h3>
                <p>${escapeHtml(errorText(error))}</p>
                <button id="retry-replay" class="button outline" type="button">
                  重试
                </button>
              </div>`;
              byId("retry-replay")?.addEventListener(
                "click",
                () => button.click()
              );
            } finally {
              replayBusy = false;
            }
          })
        );
      } catch (error) {
        if (generation === state.generation)
          queryError(error, () => openDetail(gameSeq, index));
      } finally {
        if (generation === state.generation) busy(false);
      }
    }
    byId("query-form").addEventListener("submit", (event) => {
      event.preventDefault();
      run("battle");
    });
    byId("btn-query-profile").addEventListener("click", () => run("profile"));
    window.addEventListener("beforeunload", cleanup);
    return { run, pauseReplay: () => state.replayCleanup?.() };
  }

  // pages/camp-console/app.js
  async function main() {
    hydrateIcons();
    const aliases = initAliases(() => accounts.reload());
    const accounts = initAccounts(
      (data) => aliases.render({ list: data.aliases || [] })
    );
    const login = initLogin(() => accounts.reload());
    const query = initQuery(() => accounts.reload());
    document.addEventListener("gok:pagechange", (event) => {
      if (event.detail.page !== "query") query.pauseReplay();
    });
    document.addEventListener(
      "error",
      (event) => {
        if (event.target instanceof HTMLImageElement)
          event.target.classList.add("image-missing");
      },
      true
    );
    try {
      await ready();
      await accounts.reload();
      await login.resumeSession();
    } catch (error) {
      showToast(errorText(error));
      byId("qr-status").textContent = errorText(error);
    }
  }
  main().catch((error) => {
    console.error("营地页面初始化失败", error);
    const notice = byId("app-status");
    notice.textContent = "页面初始化失败，请刷新页面或重新加载插件。";
    notice.hidden = false;
  });
})();
