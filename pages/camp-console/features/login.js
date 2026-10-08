/** 微信与 QQ 共用页面会话状态；服务端负责授权、持久化与资源回收。 */
import { get, post } from "../lib/api.js";
import { byId, clockText, errorText, icon, showToast } from "../lib/dom.js";

export function initLogin(onSuccess) {
  const state = {
    platform: "wechat",
    taskId: "",
    generation: 0,
    pollTimer: null,
    countdownTimer: null,
    expiresAt: 0,
    imageReady: false,
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
    byId("login-note").textContent =
      `请使用账号对应的${state.platform === "qq" ? " QQ " : "微信"}扫码并在手机上确认。`;
  }
  function reset() {
    state.imageReady = false;
    byId("qr-image").hidden = true;
    byId("qr-image").removeAttribute("src");
    byId("qr-placeholder").hidden = false;
    byId("qr-placeholder").innerHTML =
      `${icon("qr")}<span>获取二维码后扫码登录</span>`;
    byId("qr-countdown").textContent = "";
    byId("btn-cancel").disabled = true;
  }
  function setImage(session) {
    if (!session.qrcode_base64) return;
    const mime = [
      "image/jpeg",
      "image/png",
      "image/gif",
      "image/webp",
    ].includes(session.qrcode_mime)
      ? session.qrcode_mime
      : "image/png";
    byId("qr-image").src = `data:${mime};base64,${session.qrcode_base64}`;
    byId("qr-image").hidden = false;
    byId("qr-placeholder").hidden = true;
    state.imageReady = true;
    state.expiresAt =
      Date.now() + Math.max(0, session.expires_in ?? 180) * 1000;
  }
  function countdown() {
    if (!state.taskId) return;
    byId("qr-countdown").textContent = state.imageReady
      ? clockText((state.expiresAt - Date.now()) / 1000)
      : "";
    state.countdownTimer = setTimeout(countdown, 1000);
  }
  async function pollLogin() {
    const generation = state.generation,
      taskId = state.taskId;
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
      state.pollTimer = setTimeout(pollLogin, 2000);
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
  document.querySelectorAll("[data-platform]").forEach((button) =>
    button.addEventListener("click", async () => {
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
    }),
  );
  byId("btn-qrcode").addEventListener("click", requestQrcode);
  byId("btn-cancel").addEventListener("click", () =>
    cancelLogin().catch((error) => showToast(errorText(error), "error")),
  );
  window.addEventListener("beforeunload", stopPolling);
  return { resumeSession, stopPolling };
}
