/** Subscription snapshots, poll clocks and per-session delivery selections. */
import { get, post } from "../lib/api.js";
import {
  byId,
  html,
  escapeHtml as e,
  empty,
  errorText,
  showToast,
  icon,
} from "../lib/dom.js";
import { askConfirm, openModal } from "../lib/dialogs.js";

export function initSubscriptions() {
  const root = byId("panel-subscriptions");
  let data = { modules: {}, sessions: [] },
    timer = null,
    generation = 0,
    loading = false,
    changing = false,
    closeEditor = null;
  const time = (value) =>
    value
      ? new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        }).format(new Date(value * 1000))
      : "—";
  function render(next) {
    data = next;
    for (const kind of ["status", "battle"]) {
      const module = data.modules[kind] || {},
        rows = module.targets || [],
        active = module.active_count > 0,
        intervalText =
          module.jitter > 0
            ? `每 ${module.interval_min}～${module.interval_max} 秒随机检查（基础 ${module.interval} 秒，±${module.jitter} 秒）`
            : `每 ${module.interval} 秒检查`;
      byId(`${kind}-running`).textContent = module.running
        ? "轮询中"
        : active
          ? "运行中"
          : "已暂停";
      byId(`${kind}-running`).classList.toggle("active", active);
      byId(`${kind}-poll-times`).innerHTML = html`<div>
          <span>上次轮询</span><strong>${e(time(module.last_poll_at))}</strong>
        </div>
        <div>
          <span>下次轮询</span
          ><strong>${active ? e(time(module.next_poll_at)) : "暂停"}</strong>
        </div>
        <p>
          ${e(intervalText)} · ${e(module.active_count || 0)}
          个订阅正在轮询
        </p>
        ${module.error ? html`<p class="danger">${e(module.error)}</p>` : ""}`;
      byId(`${kind}-subscription-list`).innerHTML = rows.length
        ? rows
            .map((row) => {
              const snapshot = row.snapshot || {},
                match = snapshot.match;
              return html`<article class="subscription-row">
                <div class="subscription-row-main">
                  <div class="subscription-row-title">
                    <strong>${e(row.nickname || `营地 ${row.camp_id}`)}</strong
                    >${kind === "status" ? html`<span class="subscription-badge ${snapshot.game_online === 0 ? "" : snapshot.game_online === 1 || snapshot.game_online === 2 ? "active" : ""}">${e(snapshot.game_status || "待检查")}</span>` : ""}
                  </div>
                  <p class="subscription-meta">
                    营地 ID ${e(row.camp_id)} ·
                    ${row.session_count ? `关联 ${e(row.session_count)} 个会话` : "未关联会话，已暂停"}
                  </p>
                  ${kind === "status" ? html`<p class="subscription-meta">段位：${e(snapshot.rank || "—")} · 最近检查：${e(time(row.last_poll_at))}</p>` : match ? html`<div class="subscription-match"><span class="${match.result === "win" ? "success" : "danger"}">${e(match.result_text)}</span> · ${e(match.hero_name)} · ${e(match.kills)}/${e(match.deaths)}/${e(match.assists)}<small>${e(match.mode_name)} · ${e(match.played_at)} · ${e(match.honor_text || "无荣誉")}</small></div>` : html`<p class="subscription-meta">尚未读取已完成对局</p>`}${row.error ? html`<p class="subscription-error">${e(row.error)}</p>` : ""}
                </div>
                <button
                  class="button text icon-button danger"
                  type="button"
                  data-remove-target="${e(row.camp_id)}"
                  data-kind="${kind}"
                  aria-label="删除${kind === "status" ? "状态" : "战绩"}订阅 ${e(row.camp_id)}"
                >
                  ${icon("trash")}
                </button>
              </article>`;
            })
            .join("")
        : empty("还没有订阅，添加营地 ID 后关联推送会话");
    }
    byId("push-session-list").innerHTML = data.sessions.length
      ? data.sessions
          .map(
            (session) =>
              html`<article class="session-row">
                <div class="session-main">
                  <strong class="session-id">${e(session.session_id)}</strong>
                  <div class="session-chips">
                    ${session.subscriptions.length ? session.subscriptions.map((item) => html`<span class="session-chip">${item.kind === "status" ? "状态" : "战绩"} · ${e(item.camp_id)}</span>`).join("") : '<span class="subscription-meta">尚未选择订阅</span>'}
                  </div>
                  <p class="subscription-meta">
                    最近推送：${e(time(session.last_sent_at))}
                  </p>
                  ${session.error ? html`<p class="subscription-error">${e(session.error)}</p>` : ""}
                </div>
                <div class="session-actions">
                  <button
                    class="button outline small"
                    type="button"
                    data-edit-session="${e(session.session_id)}"
                  >
                    编辑订阅</button
                  ><button
                    class="button text small danger"
                    type="button"
                    data-remove-session="${e(session.session_id)}"
                  >
                    删除会话
                  </button>
                </div>
              </article>`,
          )
          .join("")
      : empty("添加会话，为订阅选择消息接收位置");
  }
  async function reload() {
    if (loading || changing) return;
    loading = true;
    const version = ++generation;
    try {
      const next = await get("subscriptions/list");
      if (version !== generation) return;
      render(next);
      byId("subscription-notice").hidden = true;
    } catch (error) {
      if (version !== generation) return;
      const notice = byId("subscription-notice");
      notice.hidden = false;
      notice.textContent = errorText(error);
    } finally {
      loading = false;
    }
  }
  async function mutate(payload, button) {
    if (changing) throw new Error("正在保存，请稍候");
    changing = true;
    ++generation;
    if (button) button.disabled = true;
    try {
      render(await post("subscriptions/update", payload));
      byId("subscription-notice").hidden = true;
    } finally {
      changing = false;
      if (button?.isConnected) button.disabled = false;
    }
  }
  for (const kind of ["status", "battle"]) {
    byId(`add-${kind}-subscription`).addEventListener(
      "submit",
      async (event) => {
        event.preventDefault();
        const form = event.currentTarget,
          input = form.elements.camp_id;
        try {
          await mutate(
            { action: "add_target", kind, camp_id: input.value.trim() },
            form.querySelector("button"),
          );
          input.value = "";
          showToast("已添加订阅，请在会话推送中选择接收位置");
        } catch (error) {
          showToast(errorText(error), "error");
        }
      },
    );
  }
  function editSession(session = null) {
    byId("session-edit-title").textContent = session
      ? "编辑会话订阅"
      : "添加推送会话";
    const input = byId("push-session-id");
    input.value = session?.session_id || "";
    input.readOnly = Boolean(session);
    const chosen = new Set(
      (session?.subscriptions || []).map((row) => `${row.kind}:${row.camp_id}`),
    );
    byId("session-subscription-options").innerHTML = ["status", "battle"]
      .map(
        (kind) =>
          html`<fieldset>
            <legend>${kind === "status" ? "订阅状态" : "订阅战绩"}</legend>
            ${
              (data.modules[kind]?.targets || []).length
                ? data.modules[kind].targets
                    .map(
                      (row) =>
                        html`<label class="session-choice"
                          ><input
                            type="checkbox"
                            name="${kind}_ids"
                            value="${e(row.camp_id)}"
                            ${chosen.has(`${kind}:${row.camp_id}`) ? "checked" : ""}
                          /><span
                            >${e(row.nickname || "待检查玩家")}<small
                              >${e(row.camp_id)}</small
                            ></span
                          ></label
                        >`,
                    )
                    .join("")
                : '<p class="subscription-hint">请先添加营地 ID</p>'
            }
          </fieldset>`,
      )
      .join("");
    closeEditor = openModal("session-edit-mask");
  }
  byId("add-push-session").addEventListener("click", () => editSession());
  const cancel = () => {
    closeEditor?.();
    closeEditor = null;
  };
  byId("cancel-push-session").addEventListener("click", cancel);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") cancel();
  });
  byId("session-edit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await mutate(
        {
          action: "save_session",
          session_id: byId("push-session-id").value.trim(),
          status_ids: [
            ...form.querySelectorAll('[name="status_ids"]:checked'),
          ].map((el) => el.value),
          battle_ids: [
            ...form.querySelectorAll('[name="battle_ids"]:checked'),
          ].map((el) => el.value),
        },
        byId("save-push-session"),
      );
      cancel();
      showToast("会话订阅已保存");
    } catch (error) {
      showToast(errorText(error), "error");
    }
  });
  root.addEventListener("click", async (event) => {
    const remove = event.target.closest("[data-remove-target]"),
      edit = event.target.closest("[data-edit-session]"),
      removeSession = event.target.closest("[data-remove-session]");
    if (edit)
      editSession(
        data.sessions.find(
          (row) => row.session_id === edit.dataset.editSession,
        ),
      );
    if (
      remove &&
      (await askConfirm(
        "删除订阅",
        "将删除该营地 ID 的订阅及所有会话关联。",
        "删除",
      ))
    ) {
      try {
        await mutate(
          {
            action: "delete_target",
            kind: remove.dataset.kind,
            camp_id: remove.dataset.removeTarget,
          },
          remove,
        );
      } catch (error) {
        showToast(errorText(error), "error");
      }
    }
    if (
      removeSession &&
      (await askConfirm(
        "删除推送会话",
        "该会话将停止接收推送，没有其他接收会话的订阅会暂停轮询。",
        "删除",
      ))
    ) {
      try {
        await mutate(
          {
            action: "delete_session",
            session_id: removeSession.dataset.removeSession,
          },
          removeSession,
        );
      } catch (error) {
        showToast(errorText(error), "error");
      }
    }
  });
  byId("refresh-subscriptions").addEventListener("click", reload);
  document.addEventListener("gok:pagechange", (event) => {
    clearInterval(timer);
    if (event.detail.page === "subscriptions") {
      reload();
      timer = setInterval(() => {
        if (!document.hidden) reload();
      }, 5000);
    }
  });
  window.addEventListener("beforeunload", () => clearInterval(timer));
}
