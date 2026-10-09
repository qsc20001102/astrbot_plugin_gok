/** 基础导航独立于功能脚本和接口初始化，功能加载失败时仍可切换页面。 */
(() => {
  const pages = new Set(["login", "query", "aliases", "subscriptions"]);
  function go(page) {
    if (!pages.has(page)) return;
    document.querySelectorAll("[data-page]").forEach((button) => {
      const active = button.dataset.page === page;
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    document.querySelectorAll(".page-panel").forEach((panel) => {
      panel.hidden = panel.id !== `panel-${page}`;
    });
    window.scrollTo(0, 0);
    // 先切换页面，再通知播放组件；组件清理错误不应阻断导航。
    document.dispatchEvent(
      new CustomEvent("gok:pagechange", { detail: { page } }),
    );
  }
  document
    .querySelectorAll("[data-page]")
    .forEach((button) =>
      button.addEventListener("click", () => go(button.dataset.page)),
    );
  document.querySelector(".brand")?.addEventListener("click", (event) => {
    event.preventDefault();
    go("login");
  });
  document
    .querySelectorAll("[data-go-login]")
    .forEach((button) => button.addEventListener("click", () => go("login")));
  document.querySelector("#page-app")?.addEventListener("error", () => {
    const notice = document.getElementById("app-status");
    notice.textContent = "页面功能脚本加载失败，请刷新页面或重新加载插件。";
    notice.hidden = false;
  });
})();
