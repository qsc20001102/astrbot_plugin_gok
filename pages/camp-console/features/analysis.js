/** Shared battle analysis controls and persistent cache state. */
import { get, post } from "../lib/api.js";
import { html, errorText } from "../lib/dom.js";

export function mountAnalysis(root, { keyword, gameSeq, index }) {
  const panel = root.querySelector("#detail-analysis"),
    button = root.querySelector("#analyze-match"),
    resultButton = root.querySelector("#view-analysis"),
    clearButton = root.querySelector("#clear-analysis");
  panel.innerHTML = html`<div class="analysis-heading">
      <div>
        <h2>AI 对局分析</h2>
        <p>结合双方表现、全员轨迹和关键事件，分析胜负原因与关键转折。</p>
      </div>
    </div>
    <p class="analysis-status" role="status" aria-live="polite">
      点击分析本场，获取职业教练视角的对局复盘。
    </p>
    <button class="button outline" id="retry-analysis-cache" type="button" hidden>
      重新读取缓存
    </button>
    <pre class="analysis-result" hidden></pre>`;
  const status = panel.querySelector(".analysis-status"),
    output = panel.querySelector(".analysis-result"),
    retryButton = panel.querySelector("#retry-analysis-cache");
  let disposed = false,
    timer = null,
    taskId = "",
    available = false,
    cacheKnown = false,
    busy = false;
  const current = () => !disposed && panel.isConnected;
  const updateButtons = () => {
    button.disabled = busy || available || !cacheKnown;
    resultButton.disabled = busy || !available || !cacheKnown;
    clearButton.disabled = busy || !available || !cacheKnown;
    retryButton.disabled = busy;
  };
  const showError = (error) => {
    panel.hidden = false;
    status.textContent = errorText(error);
    status.classList.add("error");
  };
  async function readCache(show = false) {
    const cache = await get("analysis/cache", { game_seq: gameSeq });
    if (!current()) return;
    cacheKnown = true;
    available = cache.available;
    retryButton.hidden = true;
    button.textContent = "分析本场";
    if (!available) {
      output.hidden = true;
      output.textContent = "";
      button.textContent = "分析本场";
    }
    if (show || !panel.hidden) {
      if (show) {
        panel.hidden = false;
        resultButton.setAttribute("aria-expanded", "true");
      }
      status.classList.remove("error");
      status.textContent = available
        ? show || !output.hidden
          ? "已读取保存的分析结果。"
          : "本场已有分析缓存，点击分析结果查看。"
        : "本场暂无分析缓存，可以点击分析本场。";
      // Treat model output as text, including results read from the database.
      if (show || !output.hidden) {
        output.textContent = available ? cache.text : "";
        output.hidden = !available;
      }
    }
    updateButtons();
  }
  async function poll() {
    try {
      const job = await get("analysis/status", { task_id: taskId });
      if (!current()) return;
      status.textContent = job.message;
      status.classList.toggle("error", job.status === "error");
      if (job.status === "done") {
        output.textContent = job.text;
        output.hidden = false;
        taskId = "";
        busy = false;
        available = true;
        cacheKnown = true;
        button.textContent = "分析本场";
        updateButtons();
      } else if (job.status === "error") {
        taskId = "";
        busy = false;
        button.textContent = "重试分析";
        updateButtons();
      } else {
        timer = setTimeout(poll, 1500);
      }
    } catch (error) {
      if (!current()) return;
      showError(error);
      busy = false;
      if (status.textContent.includes("分析任务已过期或不存在")) taskId = "";
      // Resume an existing job after connection failures instead of generating twice.
      button.textContent = taskId ? "重试连接" : "重试分析";
      updateButtons();
    }
  }
  button.addEventListener("click", async () => {
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
    busy = true;
    button.textContent = "分析中…";
    updateButtons();
    status.classList.remove("error");
    if (taskId) {
      await poll();
      return;
    }
    output.hidden = true;
    output.textContent = "";
    status.textContent = "正在启动分析…";
    try {
      const job = await post("analysis/start", {
        keyword,
        game_seq: gameSeq,
        index,
      });
      if (!current()) return;
      if (job.status === "done") {
        output.textContent = job.text;
        output.hidden = false;
        status.textContent = "已读取保存的分析结果。";
        available = true;
        busy = false;
        button.textContent = "分析本场";
        updateButtons();
      } else {
        taskId = job.task_id;
        await poll();
      }
    } catch (error) {
      if (!current()) return;
      showError(error);
      busy = false;
      button.textContent = "重试分析";
      updateButtons();
    }
  });
  resultButton.addEventListener("click", async () => {
    busy = true;
    updateButtons();
    try {
      await readCache(true);
    } catch (error) {
      if (current()) showError(error);
    } finally {
      if (current()) {
        busy = false;
        updateButtons();
      }
    }
  });
  clearButton.addEventListener("click", async () => {
    busy = true;
    clearButton.textContent = "清除中…";
    updateButtons();
    try {
      await post("analysis/clear", { game_seq: gameSeq });
      if (!current()) return;
      available = false;
      cacheKnown = true;
      taskId = "";
      clearTimeout(timer);
      output.textContent = "";
      output.hidden = true;
      panel.hidden = false;
      status.classList.remove("error");
      status.textContent = "本场分析缓存已清除，可以重新分析。";
      resultButton.setAttribute("aria-expanded", "false");
      button.textContent = "分析本场";
    } catch (error) {
      if (current()) showError(error);
    } finally {
      if (current()) {
        busy = false;
        clearButton.textContent = "清除缓存";
        updateButtons();
      }
    }
  });
  const refreshCache = async () => {
    if (busy || taskId || !current()) return;
    busy = true;
    updateButtons();
    try {
      await readCache();
    } catch (error) {
      if (!current()) return;
      cacheKnown = false;
      showError(error);
      retryButton.hidden = false;
    } finally {
      if (current()) {
        busy = false;
        updateButtons();
      }
    }
  };
  retryButton.addEventListener("click", refreshCache);
  window.addEventListener("focus", refreshCache);
  refreshCache();
  return () => {
    disposed = true;
    clearTimeout(timer);
    window.removeEventListener("focus", refreshCache);
  };
}
