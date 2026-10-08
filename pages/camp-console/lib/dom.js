/** 页面通用的转义、图片、图标与数字格式，不依赖业务数据。 */
export const html = (strings, ...values) =>
  String.raw({ raw: strings }, ...values);
export const byId = (id) => document.getElementById(id);
export const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
export const errorText = (error) =>
  typeof error === "string"
    ? error
    : error?.message || error?.msg || "请求失败，请稍后重试";
export const numberText = (value, suffix = "") =>
  value == null || value === "" || !Number.isFinite(Number(value))
    ? "—"
    : `${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}${suffix}`;
export const clockText = (seconds) => {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
};
export const safeImageUrl = (value) => {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};
export function image(url, label = "", className = "hero-image") {
  const safe = safeImageUrl(url);
  return html`<span class="img-wrap ${className}" title="${escapeHtml(label)}"
    >${safe ? html`<img src="${escapeHtml(safe)}" alt="${escapeHtml(label)}" loading="lazy" referrerpolicy="no-referrer" />` : html`<span class="avatar-fallback">${escapeHtml(label.slice(0, 1) || "·")}</span>`}</span
  >`;
}

const paths = {
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
  pause: '<path d="M8 4v16M16 4v16"/>',
};
export const icon = (name) =>
  html`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
    ${paths[name] || paths.arrow}
  </svg>`;
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((element) => {
    element.innerHTML = icon(element.dataset.icon);
  });
}
let toastTimer;
export function showToast(message, kind = "") {
  const element = byId("toast");
  element.textContent = message;
  element.className = `toast ${kind}`;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 3200);
}
export function loading(message = "正在实时查询…") {
  return html`<div class="loading-state" role="status">
    <span class="spinner"></span>${escapeHtml(message)}
  </div>`;
}
export function empty(message) {
  return html`<div class="empty-state">${escapeHtml(message)}</div>`;
}
