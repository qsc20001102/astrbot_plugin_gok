/** 页面弹窗支持 Escape、焦点返回和 Tab 循环，兼容宿主 iframe。 */
import { byId } from "./dom.js";

export function openModal(id) {
  const mask = byId(id),
    previous = document.activeElement;
  mask.hidden = false;
  const focusable = () => [
    ...mask.querySelectorAll("button:not(:disabled), input, select"),
  ];
  const onKey = (event) => {
    if (event.key === "Tab") {
      const elements = focusable(),
        first = elements[0],
        last = elements.at(-1);
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

export function askConfirm(title, text, okLabel = "确定") {
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
    const yes = () => finish(true),
      no = () => finish(false),
      key = (event) => {
        if (event.key === "Escape") no();
      };
    byId("confirm-yes").addEventListener("click", yes);
    byId("confirm-no").addEventListener("click", no);
    document.addEventListener("keydown", key);
    byId("confirm-no").focus();
  });
}
