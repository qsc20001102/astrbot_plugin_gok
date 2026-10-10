/** Exercise login polling through the host bridge's status=error rejection rule. */
import assert from "node:assert/strict";

const timers = new Map();
let nextTimer = 0;
globalThis.setTimeout = (callback, delay) => {
  const id = ++nextTimer;
  timers.set(id, { callback, delay });
  return id;
};
globalThis.clearTimeout = (id) => timers.delete(id);

function element(dataset = {}) {
  return {
    dataset,
    listeners: {},
    textContent: "",
    disabled: false,
    hidden: false,
    classList: { toggle() {} },
    setAttribute() {},
    removeAttribute() {},
    addEventListener(event, callback) {
      this.listeners[event] = callback;
    },
  };
}

const ids = new Map();
const platforms = [element({ platform: "wechat" }), element({ platform: "qq" })];
globalThis.document = {
  getElementById(id) {
    if (!ids.has(id)) ids.set(id, element());
    return ids.get(id);
  },
  querySelectorAll() {
    return platforms;
  },
};

let response;
let polls = 0;
globalThis.window = {
  addEventListener() {},
  AstrBotPluginPage: {
    async apiPost(endpoint) {
      if (endpoint === "login/qrcode") {
        return { task_id: "test-task", platform: "qq", expires_in: 180 };
      }
      assert.equal(endpoint, "login/poll");
      polls++;
      if (response instanceof Error) throw response;
      if (response.status === "error") throw new Error(response.message);
      return response;
    },
  },
};

const { initLogin } = await import("../pages/camp-console/features/login.js");
const byId = (id) => document.getElementById(id);

async function pollTimer(delay) {
  const entry = [...timers.entries()].find(([, timer]) => timer.delay === delay);
  assert.ok(entry, `Expected a polling timer with delay ${delay}`);
  timers.delete(entry[0]);
  await entry[1].callback();
}

async function begin(result) {
  timers.clear();
  response = result;
  polls = 0;
  const login = initLogin(() => {});
  await platforms[1].listeners.click();
  await byId("btn-qrcode").listeners.click();
  await pollTimer(0);
  return login;
}

const message = "QQ 登录浏览器缺少 Linux 系统依赖";
await begin({ status: "failed", terminal: true, message });
assert.equal(byId("qr-status").textContent, message);
assert.equal(byId("qr-status").className, "qr-status danger");
assert.equal(byId("btn-cancel").disabled, true);
assert.equal(byId("btn-qrcode").disabled, false);
assert.equal(timers.size, 0, "A terminal failure must stop polling and countdown");
assert.equal(polls, 1);

await begin({ status: "retrying", terminal: false, message: "保存失败，正在重试" });
assert.equal(byId("qr-status").textContent, "保存失败，正在重试");
assert.equal(byId("btn-cancel").disabled, false);
assert.ok([...timers.values()].some((timer) => timer.delay === 2000));
response = { status: "failed", terminal: true, message };
await pollTimer(2000);
assert.equal(timers.size, 0);
assert.equal(polls, 2);

await begin(new Error("网络暂时中断"));
assert.equal(byId("qr-status").textContent, "暂时无法确认：网络暂时中断");
assert.ok([...timers.values()].some((timer) => timer.delay === 2000));
response = { status: "failed", terminal: true, message };
await pollTimer(2000);
assert.equal(timers.size, 0);

console.log("登录终止错误停止轮询、重新获取可用、可恢复错误及网络异常继续重试检查通过");
