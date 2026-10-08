/** 沿用宿主注入的页面桥接，端点均为本插件已注册的相对路由。 */
const bridge = window.AstrBotPluginPage;
export async function ready() {
  if (!bridge) throw new Error("请从 AstrBot 管理页打开营地页面");
  if (typeof bridge.ready === "function") await bridge.ready();
}
export const get = (endpoint, params = {}) => bridge.apiGet(endpoint, params);
export const post = (endpoint, payload = {}) =>
  bridge.apiPost(endpoint, payload);
