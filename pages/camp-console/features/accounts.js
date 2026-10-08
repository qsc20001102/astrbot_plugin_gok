/** 登录账号列表与检测；前端只接收后端公开摘要。 */
import { get, post } from "../lib/api.js";
import { askConfirm } from "../lib/dialogs.js";
import {
  html,
  byId,
  clockText,
  empty,
  errorText,
  escapeHtml,
  icon,
  image,
  showToast,
} from "../lib/dom.js";

export function initAccounts(onDashboard) {
  function render(summary = {}) {
    const rows = summary.accounts || [];
    byId("account-list").innerHTML = rows.length
      ? rows
          .map((row) => {
            const status =
              row.auth_invalid || !row.ready
                ? "需重新登录"
                : !row.available
                  ? `冷却 ${clockText(row.cooled_remaining)}`
                  : row.validation_status === "valid"
                    ? "已验证"
                    : "待验证";
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
          })
          .join("")
      : empty("还没有登录账号，请先扫码授权");
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
    if (
      !button ||
      !(await askConfirm(
        "删除营地账号",
        "删除后需要重新扫码授权，是否继续？",
        "删除",
      ))
    )
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
    if (
      !(await askConfirm(
        "清空全部账号",
        "所有账号的登录态都将被删除，需要重新扫码授权。",
        "清空账号",
      ))
    )
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
