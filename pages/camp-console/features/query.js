/** 实时查询、同名选择和单局导航；通过对局标识定位，避免序号变化误查。 */
import { get } from "../lib/api.js";
import {
  html,
  byId,
  empty,
  errorText,
  escapeHtml as e,
  loading,
  showToast,
} from "../lib/dom.js";
import { battleView, profileView, selectionView } from "../views/player.js";
import { detailShell, performanceView } from "../views/detail.js";
import { renderReplay } from "../views/replay.js";
import { mountAnalysis } from "./analysis.js";

export function initQuery(onData) {
  const root = byId("query-result");
  const state = {
    keyword: "",
    kind: "battle",
    option: 0,
    limit: 10,
    busy: false,
    generation: 0,
    selectionTimer: null,
    replayCleanup: null,
    analysisCleanup: null,
  };
  function cleanup() {
    clearTimeout(state.selectionTimer);
    state.analysisCleanup?.();
    state.analysisCleanup = null;
    const pause = state.replayCleanup;
    state.replayCleanup = null;
    pause?.();
  }
  function busy(value) {
    state.busy = value;
    byId("btn-query-profile").disabled = value;
    byId("btn-query-battle").disabled = value;
  }
  function detailMode(active) {
    byId("panel-query").classList.toggle("detail-mode", active);
    byId("query-form").hidden = active;
    document.querySelector("#panel-query > .page-heading").hidden = active;
  }
  function queryError(error, retry) {
    root.innerHTML = html`<div class="error-state">
      <h2>这次查询没有完成</h2>
      <p>${e(errorText(error))}</p>
      <button id="retry-query" class="button outline" type="button">
        重新查询
      </button>
    </div>`;
    byId("retry-query").addEventListener("click", retry);
  }
  async function run(
    kind = "battle",
    keyword = byId("query-keyword").value.trim(),
  ) {
    if (state.busy) return;
    if (!keyword) {
      byId("query-keyword").focus();
      showToast("请输入营地 ID、游戏昵称或别名");
      return;
    }
    cleanup();
    detailMode(false);
    busy(true);
    state.keyword = keyword;
    state.kind = kind;
    const generation = ++state.generation;
    root.innerHTML = loading();
    try {
      const response = await get("query", {
        keyword,
        type: kind,
        limit: state.limit,
        option: state.option,
      });
      if (generation !== state.generation) return;
      const data = response.data;
      if (response.type === "selection") {
        root.innerHTML = selectionView(data);
        state.selectionTimer = setTimeout(() => {
          state.generation += 1;
          root.innerHTML = empty("候选已过期，请重新查询");
        }, 60000);
        root.querySelectorAll("[data-candidate]").forEach((button) =>
          button.addEventListener("click", () => {
            byId("query-keyword").value = button.dataset.candidate;
            run(kind, button.dataset.candidate);
          }),
        );
        byId("cancel-selection").addEventListener("click", () => {
          cleanup();
          root.innerHTML = empty("已取消选择");
        });
        return;
      }
      root.innerHTML =
        kind === "profile"
          ? profileView(data)
          : battleView(data, state.option, state.limit);
      onData?.();
      root.querySelectorAll("[data-option]").forEach((button) =>
        button.addEventListener("click", () => {
          state.option = Number(button.dataset.option);
          run("battle", state.keyword);
        }),
      );
      root
        .querySelector("#query-limit")
        ?.addEventListener("change", (event) => {
          state.limit = Number(event.target.value);
          run("battle", state.keyword);
        });
      root
        .querySelectorAll("[data-match]")
        .forEach((button) =>
          button.addEventListener("click", () =>
            openDetail(button.dataset.match, Number(button.dataset.index)),
          ),
        );
    } catch (error) {
      if (generation === state.generation)
        queryError(error, () => run(kind, keyword));
    } finally {
      if (generation === state.generation) busy(false);
    }
  }
  async function openDetail(gameSeq, index) {
    if (state.busy) return;
    cleanup();
    busy(true);
    root.innerHTML = loading("正在读取单局详情…");
    const generation = ++state.generation;
    try {
      const response = await get("query", {
        keyword: state.keyword,
        type: "detail",
        game_seq: gameSeq,
        index,
      });
      if (generation !== state.generation) return;
      detailMode(true);
      root.innerHTML = detailShell(response.data);
      state.analysisCleanup = mountAnalysis(root, {
        keyword: state.keyword,
        gameSeq,
        index,
      });
      const players = [
        ...(response.data.blue || []),
        ...(response.data.red || []),
      ];
      const selectPlayer = () => {
        const select = byId("detail-player");
        const row =
          players.find(
            (player) => (player.player_key || player.role_id) === select?.value,
          ) ||
          response.data.target ||
          players[0];
        if (byId("player-performance"))
          byId("player-performance").innerHTML = performanceView(row);
      };
      selectPlayer();
      byId("detail-player")?.addEventListener("change", selectPlayer);
      byId("back-to-battles").addEventListener("click", () =>
        run("battle", state.keyword),
      );
      let replayLoaded = false,
        replayBusy = false;
      root.querySelectorAll("[data-detail-tab]").forEach((button) =>
        button.addEventListener("click", async () => {
          const isReplay = button.dataset.detailTab === "replay";
          root.querySelectorAll("[data-detail-tab]").forEach((tab) => {
            const active = tab === button;
            tab.classList.toggle("active", active);
            tab.setAttribute("aria-selected", String(active));
          });
          byId("detail-overview").hidden = isReplay;
          byId("detail-replay").hidden = !isReplay;
          if (!isReplay) {
            state.replayCleanup?.();
            return;
          }
          if (replayLoaded || replayBusy) return;
          replayBusy = true;
          byId("detail-replay").innerHTML = loading("正在读取对局回放…");
          try {
            const replay = await get("query", {
              keyword: state.keyword,
              type: "replay",
              game_seq: gameSeq,
              index,
            });
            if (generation !== state.generation) return;
            state.replayCleanup = renderReplay(
              byId("detail-replay"),
              replay.data,
            );
            replayLoaded = true;
          } catch (error) {
            if (generation === state.generation)
              byId("detail-replay").innerHTML = html`<div class="replay-state">
                <h3>对局回放暂不可用</h3>
                <p>${e(errorText(error))}</p>
                <button id="retry-replay" class="button outline" type="button">
                  重试
                </button>
              </div>`;
            byId("retry-replay")?.addEventListener("click", () =>
              button.click(),
            );
          } finally {
            replayBusy = false;
          }
        }),
      );
    } catch (error) {
      if (generation === state.generation)
        queryError(error, () => openDetail(gameSeq, index));
    } finally {
      if (generation === state.generation) busy(false);
    }
  }
  byId("query-form").addEventListener("submit", (event) => {
    event.preventDefault();
    run("battle");
  });
  byId("btn-query-profile").addEventListener("click", () => run("profile"));
  window.addEventListener("beforeunload", cleanup);
  return { run, pauseReplay: () => state.replayCleanup?.() };
}
