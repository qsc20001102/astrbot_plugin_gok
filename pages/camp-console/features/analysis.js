/** 地图回顾中的分析入口，轮询后台任务并以纯文本呈现模型结果。 */
import { get, post } from "../lib/api.js";
import { html, errorText } from "../lib/dom.js";

export function mountAnalysis(root, { keyword, gameSeq, index }) {
  const panel = document.createElement("section");
  panel.className = "analysis-panel";
  panel.innerHTML = html`<div class="analysis-heading">
      <div>
        <h2>AI 对局分析</h2>
        <p>结合双方表现、全员轨迹和关键事件，分析胜负原因与关键转折。</p>
      </div>
      <button class="button primary" type="button">分析本场</button>
    </div>
    <p class="analysis-status" role="status" aria-live="polite">
      点击分析本场，获取职业教练视角的对局复盘。
    </p>
    <pre class="analysis-result" hidden></pre>`;
  root.append(panel);
  const button = panel.querySelector("button"),
    status = panel.querySelector(".analysis-status"),
    output = panel.querySelector(".analysis-result");
  let disposed = false,
    timer = null,
    taskId = "";
  const current = () => !disposed && panel.isConnected;
  async function poll() {
    try {
      const job = await get("analysis/status", { task_id: taskId });
      if (!current()) return;
      status.textContent = job.message;
      status.classList.toggle("error", job.status === "error");
      if (job.status === "done") {
        // 模型生成的文字不能作为 HTML 插入页面。
        output.textContent = job.text;
        output.hidden = false;
        taskId = "";
        button.disabled = false;
        button.textContent = "重新分析";
      } else if (job.status === "error") {
        taskId = "";
        button.disabled = false;
        button.textContent = "重试分析";
      } else {
        timer = setTimeout(poll, 1500);
      }
    } catch (error) {
      if (!current()) return;
      status.textContent = errorText(error);
      status.classList.add("error");
      button.disabled = false;
      if (status.textContent.includes("分析任务已过期或不存在")) taskId = "";
      // 保留任务标识，网络恢复后继续读取，不重复付费调用模型。
      button.textContent = taskId ? "重试连接" : "重试分析";
    }
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "分析中…";
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
      taskId = job.task_id;
      await poll();
    } catch (error) {
      if (!current()) return;
      status.textContent = errorText(error);
      status.classList.add("error");
      button.disabled = false;
      button.textContent = "重试分析";
    }
  });
  return () => {
    disposed = true;
    clearTimeout(timer);
  };
}
