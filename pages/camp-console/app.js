/** 应用入口只装配功能与导航；业务、展示和通信各自独立。 */
import { ready } from "./lib/api.js";
import { byId, errorText, hydrateIcons, showToast } from "./lib/dom.js";
import { initAccounts } from "./features/accounts.js";
import { initAliases } from "./features/aliases.js";
import { initLogin } from "./features/login.js";
import { initQuery } from "./features/query.js";

async function main() {
  hydrateIcons();
  const aliases = initAliases(() => accounts.reload());
  const accounts = initAccounts((data) =>
    aliases.render({ list: data.aliases || [] }),
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
    true,
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
