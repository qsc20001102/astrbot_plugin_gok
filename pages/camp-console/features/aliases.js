/** 角色昵称只读，人工别名可编辑；与搜索候选保持同一份名称映射。 */
import { get, post } from "../lib/api.js";
import { askConfirm, openModal } from "../lib/dialogs.js";
import {
  html,
  byId,
  empty,
  errorText,
  escapeHtml,
  icon,
  showToast,
} from "../lib/dom.js";

export function initAliases(onChange) {
  let rows = [],
    editingId = "",
    closeModal = null;
  function render(data = {}) {
    rows = data.list || [];
    byId("alias-list").innerHTML = rows.length
      ? html`<div class="alias-row header">
            <span>游戏昵称</span><span class="alias-id">营地 ID</span
            ><span>别名</span><span></span>
          </div>
          ${rows
            .map(
              (row) =>
                html`<div class="alias-row">
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
                </div>`,
            )
            .join("")}`
      : empty("暂无角色记录，查询成功后会自动保存");
    byId("query-mappings").innerHTML = rows
      .map(
        (row) =>
          html`<option
            value="${escapeHtml(row.alias || row.role_name || row.gokid)}"
          >
            ${escapeHtml(row.role_name)} · ${escapeHtml(row.gokid)}
          </option>`,
      )
      .join("");
  }
  async function search() {
    try {
      render(
        await get("aliases/list", {
          keyword: byId("alias-search").value.trim(),
        }),
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
    const edit = event.target.closest("[data-alias-edit]"),
      remove = event.target.closest("[data-alias-delete]");
    if (edit) {
      const row = rows.find(
        (item) => String(item.gokid) === edit.dataset.aliasEdit,
      );
      if (!row) return;
      editingId = String(row.gokid);
      byId("alias-edit-meta").textContent =
        `${row.role_name || "未获取昵称"} · ${row.gokid}`;
      byId("alias-edit-name").value = row.alias || "";
      closeModal = openModal("alias-edit-mask");
      byId("alias-edit-name").focus();
    }
    if (
      remove &&
      (await askConfirm(
        "删除角色映射",
        "下次查询成功会重新记录游戏昵称，当前设置的别名将被删除。",
        "删除",
      ))
    ) {
      try {
        await post("aliases/delete", {
          gokid: Number(remove.dataset.aliasDelete),
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
        alias: byId("alias-edit-name").value.trim(),
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
