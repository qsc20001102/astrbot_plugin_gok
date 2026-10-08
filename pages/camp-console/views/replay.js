/** 用统一回顾模型绘制官方地图、每秒轨迹与事件；返回清理函数停止播放。 */
import {
  html,
  clockText,
  empty,
  escapeHtml as e,
  icon,
  safeImageUrl,
} from "../lib/dom.js";

/** 当前画面显示最近六秒的事件，手动点选时保留指定事件，原始数组不变。 */
export function replayEventsAtTime(events, seconds, pinnedId = "") {
  if (!Number.isFinite(seconds)) return [];
  if (pinnedId) return events.filter((event) => event.id === pinnedId);
  return events
    .filter(
      (event) =>
        Number.isFinite(event.time_seconds) &&
        event.time_seconds <= seconds &&
        seconds - event.time_seconds < 6,
    )
    .sort((first, second) => first.time_seconds - second.time_seconds);
}

export function renderReplay(root, data) {
  if (!data.available) {
    root.innerHTML = html`<div class="replay-state">
      <h3>暂无地图回顾</h3>
      <p>${e(data.message || "这场对局的回顾数据暂未返回")}</p>
    </div>`;
    return () => {};
  }
  const players = data.players || [],
    events = data.events || [],
    towers = data.towers || [];
  let selected =
    players.find((player) => player.is_target)?.player_id ||
    players[0]?.player_id ||
    "";
  let seconds = 0,
    filter = "all",
    selectedEvent = "",
    pinnedEvent = "",
    liveSignature = "",
    playing = false,
    frameId = null,
    previousTime = null;
  const duration = Number(data.duration_seconds) || 0;
  root.innerHTML = html`<div class="replay-layout">
    <section class="replay-map-panel">
      <div class="replay-map-tools">
        <select id="replay-player" aria-label="选择轨迹玩家">
          ${players.map((player) => html`<option value="${e(player.player_id)}" ${player.player_id === selected ? "selected" : ""}>${e(player.nickname || player.hero_name)} · ${e(player.hero_name)}</option>`).join("")}
        </select>
        <div class="replay-trail-tools">
          <label
            ><input id="replay-show-trail" type="checkbox" checked />
            显示轨迹</label
          >
          <select
            id="replay-trail-window"
            class="trail-window"
            aria-label="轨迹范围"
          >
            <option value="30">近 30 秒</option>
            <option value="60">近 60 秒</option>
            <option value="0">全部轨迹</option>
          </select>
        </div>
      </div>
      <div class="replay-map">
        <img
          id="replay-map-image"
          src="${e(safeImageUrl(data.map_image))}"
          alt="营地官方回顾地图"
        /><svg
          id="replay-overlay"
          class="replay-overlay"
          viewBox="0 0 100 100"
          role="img"
          aria-label="玩家位置与移动轨迹"
        ></svg>
        <div
          id="replay-live-event"
          class="replay-live-event"
          role="status"
          aria-live="polite"
          hidden
        ></div>
      </div>
      <div class="replay-controls">
        <button
          id="replay-play"
          class="replay-play"
          type="button"
          aria-label="播放回顾"
        >
          ${icon("play")}</button
        ><span id="replay-time" class="replay-time"
          >0:00 / ${clockText(duration)}</span
        ><input
          id="replay-slider"
          class="replay-slider"
          type="range"
          min="0"
          max="${duration}"
          value="0"
          step="1"
          aria-label="对局回顾时间"
        /><select id="replay-speed" class="replay-speed" aria-label="播放速度">
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4" selected>4×</option>
        </select>
      </div>
      <div class="map-legend">
        <span class="map-key"><i></i>蓝方</span
        ><span class="map-key enemy"><i></i>红方</span
        ><span class="map-key event"><i></i>事件位置</span>
      </div>
      <div class="map-message" id="map-message">
        点击事件，在地图定位；也可拖动时间轴查看位置。
      </div>
    </section>
    <section class="replay-events-panel">
      <h2>关键事件</h2>
      <div class="event-filters" role="group" aria-label="事件类型">
        ${[
          ["all", "全部"],
          ["kill", "击杀"],
          ["battle", "战斗"],
          ["tower", "推塔"],
          ["resource", "资源"],
        ]
          .map(
            ([value, label]) =>
              html`<button
                class="event-filter ${value === filter ? "active" : ""}"
                type="button"
                data-event-filter="${value}"
                aria-pressed="${value === filter}"
              >
                ${label}
              </button>`,
          )
          .join("")}
      </div>
      <div id="event-list" class="event-list"></div>
      <p class="event-list-note">
        点选事件查看参与英雄。建筑记录可能重复，不按记录条数计算摧毁次数。
      </p>
    </section>
  </div>`;
  const overlay = root.querySelector("#replay-overlay"),
    slider = root.querySelector("#replay-slider"),
    playButton = root.querySelector("#replay-play"),
    message = root.querySelector("#map-message");
  const valid = (point) =>
    point &&
    Number.isFinite(point.x) &&
    Number.isFinite(point.y) &&
    point.x >= 0 &&
    point.x <= 100 &&
    point.y >= 0 &&
    point.y <= 100;
  const alive = (player, time) => {
    if (!player?.has_revive_data) return true;
    const lastDeath = Math.max(
      -1,
      ...(player.deaths || [])
        .filter((item) => item.time_seconds <= time)
        .map((item) => item.time_seconds),
    );
    const lastRevive = Math.max(
      -1,
      ...(player.revives || [])
        .filter((item) => item.time_seconds <= time)
        .map((item) => item.time_seconds),
    );
    return lastDeath < 0 || lastRevive >= lastDeath;
  };
  // 头像只创建一次，播放时移动节点，避免每帧替换图片导致加载中断。
  overlay.innerHTML = html`<defs
      >${players.map((player, index) => html`<clipPath id="replay-face-${index}"><circle r="2.3" /></clipPath>`).join("")}</defs
    >
    <g id="replay-towers"
      >${towers
        .filter((tower) => valid(tower.position))
        .map(
          (tower) =>
            html`<g
              class="tower-marker"
              data-replay-tower="${e(tower.id)}"
              transform="translate(${tower.position.x} ${tower.position.y})"
              style="color:${tower.camp === 2 ? "#e86d73" : "#5d94ff"}"
              ><title>${e(tower.name)}</title
              ><circle
                r="2.2"
                fill="#142235"
                fill-opacity=".85"
                stroke="currentColor"
                stroke-width=".35" /><path
                d="M-1.2-1.4h.6v.6h.6v-.6h.6v.6h.6v-.6h.6v1.2h-.4v1.7h-2.2V-.2h-.4z"
                fill="currentColor"
                stroke="white"
                stroke-width=".13"
            /></g>`,
        )
        .join("")}</g
    >
    <g id="replay-trails"></g
    ><g id="replay-members"
      >${players.map((member, index) => html`<g class="player-marker" data-replay-player="${e(member.player_id)}" style="color:${member.camp === 2 ? "#e86d73" : "#5d94ff"}" role="button" aria-label="查看${e(member.hero_name)}轨迹"><title>${e(member.nickname)} · ${e(member.hero_name)}</title><circle r="2.5" fill="currentColor" stroke="white" stroke-width=".4" /><text text-anchor="middle" y=".8" font-size="2.4" fill="white">${e(member.hero_name?.slice(0, 1) || "?")}</text>${safeImageUrl(member.hero_icon) ? html`<image href="${e(safeImageUrl(member.hero_icon))}" x="-2.3" y="-2.3" width="4.6" height="4.6" preserveAspectRatio="xMidYMid slice" clip-path="url(#replay-face-${index})" />` : ""}<circle r="2.5" fill="none" stroke="currentColor" stroke-width=".45" /><circle class="player-selection" r="3.1" fill="none" stroke="currentColor" stroke-width=".5" /></g>`).join("")}</g
    ><g id="replay-event-position"></g>`;
  const towerNodes = new Map(
    [...overlay.querySelectorAll("[data-replay-tower]")].map((node) => [
      node.dataset.replayTower,
      node,
    ]),
  );
  const playerNodes = new Map(
    [...overlay.querySelectorAll("[data-replay-player]")].map((node) => [
      node.dataset.replayPlayer,
      node,
    ]),
  );
  const playerLayer = overlay.querySelector("#replay-members");
  function draw() {
    const currentEvents = replayEventsAtTime(events, seconds, pinnedEvent);
    const latest = currentEvents[currentEvents.length - 1];
    const nextSelected = latest?.id || "";
    if (selectedEvent !== nextSelected) {
      selectedEvent = nextSelected;
      renderEvents();
      if (playing) {
        // 只滚动事件列表，不把整个 iframe 或页面带离地图播放画面。
        const list = root.querySelector("#event-list");
        const active = list.querySelector(".event-row.active");
        if (active) {
          const bounds = list.getBoundingClientRect(),
            item = active.getBoundingClientRect();
          if (item.top < bounds.top) list.scrollTop += item.top - bounds.top;
          else if (item.bottom > bounds.bottom)
            list.scrollTop += item.bottom - bounds.bottom;
        }
      }
    }
    const signature = currentEvents.map((event) => event.id).join("|");
    if (signature !== liveSignature) {
      liveSignature = signature;
      const banner = root.querySelector("#replay-live-event");
      banner.hidden = currentEvents.length === 0;
      banner.innerHTML =
        currentEvents
          .slice(-3)
          .map(
            (event) =>
              html`<div class="live-event-row" data-live-event="${e(event.id)}">
                <time>${clockText(event.time_seconds)}</time>
                <div>
                  <strong>${e(event.title)}</strong
                  >${event.description ? html`<span>${e(event.description)}</span>` : ""}
                </div>
              </div>`,
          )
          .join("") +
        (currentEvents.length > 3
          ? html`<div class="live-event-more">
              另有 ${currentEvents.length - 3} 条事件，见事件列表
            </div>`
          : "");
    }
    const player = players.find((item) => item.player_id === selected),
      trail = player?.points || [];
    const parts = [];
    if (root.querySelector("#replay-show-trail").checked) {
      let segment = [];
      const flush = () => {
        if (segment.length > 1)
          parts.push(
            html`<polyline
              points="${segment.join(" ")}"
              fill="none"
              stroke="#e8b85c"
              stroke-width=".6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />`,
          );
        segment = [];
      };
      const windowSeconds = Number(
        root.querySelector("#replay-trail-window").value,
      );
      for (const point of trail) {
        if (point.time_seconds > seconds) break;
        if (windowSeconds && point.time_seconds < seconds - windowSeconds)
          continue;
        if (!valid(point.position) || !alive(player, point.time_seconds))
          flush();
        else segment.push(`${point.position.x},${point.position.y}`);
      }
      flush();
    }
    for (const tower of towers) {
      const node = towerNodes.get(tower.id);
      if (node)
        node.style.display =
          tower.destroyed_at != null && seconds >= tower.destroyed_at
            ? "none"
            : "";
    }
    for (const member of players) {
      const node = playerNodes.get(member.player_id);
      const point =
        member.points?.[Math.min(Math.floor(seconds), member.points.length - 1)]
          ?.position;
      const visible = valid(point) && alive(member, seconds);
      node.style.display = visible ? "" : "none";
      if (!visible) continue;
      const chosen = member.player_id === selected;
      node.classList.toggle("selected", chosen);
      node.setAttribute(
        "transform",
        `translate(${point.x} ${point.y}) scale(${chosen ? 1.2 : 1})`,
      );
      if (chosen) playerLayer.appendChild(node);
    }
    overlay.querySelector("#replay-trails").innerHTML = parts.join("");
    const eventParts = [];
    const event = events.find((item) => item.id === selectedEvent);
    if (event && valid(event.position))
      eventParts.push(
        html`<g
          ><title>${e(event.title)}</title
          ><circle
            cx="${event.position.x}"
            cy="${event.position.y}"
            r="2.6"
            fill="none"
            stroke="#f6cf76"
            stroke-width=".6" /><circle
            cx="${event.position.x}"
            cy="${event.position.y}"
            r=".8"
            fill="#f6cf76"
        /></g>`,
      );
    overlay.querySelector("#replay-event-position").innerHTML =
      eventParts.join("");
    root.querySelector("#replay-time").textContent =
      `${clockText(seconds)} / ${clockText(duration)}`;
    slider.value = String(seconds);
    message.textContent = event
      ? event.position
        ? `${clockText(event.time_seconds)} · ${event.title}`
        : `${clockText(event.time_seconds)} · 此事件未返回位置，可查看当时玩家轨迹。`
      : data.has_trajectory
        ? "点击事件，在地图定位；也可拖动时间轴查看位置。"
        : "这场回顾有事件记录，暂未返回玩家轨迹。";
  }
  function renderEvents() {
    const shown = events.filter(
      (item) => filter === "all" || item.type === filter,
    );
    root.querySelector("#event-list").innerHTML = shown.length
      ? shown
          .map(
            (item) =>
              html`<button
                class="event-row ${item.id === selectedEvent ? "active" : ""}"
                data-event="${e(item.id)}"
                type="button"
                aria-expanded="${item.id === selectedEvent && Boolean(item.details_lines?.length)}"
              >
                <span class="event-dot ${e(item.type)}"></span
                ><span class="event-time">${clockText(item.time_seconds)}</span>
                <div class="event-body">
                  <div class="event-title">${e(item.title)}</div>
                  ${item.description ? html`<div class="event-description">${e(item.description)}</div>` : item.camp ? html`<div class="event-description">${item.camp === 1 ? "蓝方" : "红方"}</div>` : ""}
                  ${item.id === selectedEvent && item.details_lines?.length ? html`<div class="event-context">${item.details_lines.map((line) => html`<div>${e(line)}</div>`).join("")}</div>` : ""}
                </div>
                ${icon("arrow")}
              </button>`,
          )
          .join("")
      : empty("此分类暂无事件");
  }
  function pause() {
    playing = false;
    cancelAnimationFrame(frameId);
    frameId = null;
    previousTime = null;
    playButton.innerHTML = icon("play");
    playButton.setAttribute("aria-label", "播放回顾");
  }
  function advance(now) {
    if (!playing) return;
    if (!root.isConnected) return pause();
    if (previousTime !== null)
      seconds = Math.min(
        duration,
        seconds +
          Math.min((now - previousTime) / 1000, 0.25) *
            Number(root.querySelector("#replay-speed").value),
      );
    previousTime = now;
    draw();
    if (seconds >= duration) pause();
    else frameId = requestAnimationFrame(advance);
  }
  root.querySelector("#replay-play").addEventListener("click", () => {
    if (playing) return pause();
    if (seconds >= duration) seconds = 0;
    pinnedEvent = "";
    playing = true;
    root.querySelector("#replay-play").innerHTML = icon("pause");
    root.querySelector("#replay-play").setAttribute("aria-label", "暂停回顾");
    frameId = requestAnimationFrame(advance);
  });
  slider.addEventListener("input", () => {
    pause();
    seconds = Number(slider.value);
    pinnedEvent = "";
    draw();
  });
  root.querySelector("#replay-player").addEventListener("change", (event) => {
    selected = event.target.value;
    draw();
  });
  root.querySelector("#replay-show-trail").addEventListener("change", draw);
  root.querySelector("#replay-trail-window").addEventListener("change", draw);
  root.querySelector("#event-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-event]");
    if (!button) return;
    const item = events.find((row) => row.id === button.dataset.event);
    if (!item) return;
    pause();
    seconds = Math.min(duration, item.time_seconds);
    pinnedEvent = item.id;
    draw();
  });
  root.querySelector(".event-filters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-event-filter]");
    if (!button) return;
    filter = button.dataset.eventFilter;
    root.querySelectorAll("[data-event-filter]").forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    renderEvents();
  });
  overlay.addEventListener("click", (event) => {
    const marker = event.target.closest("[data-replay-player]");
    if (!marker) return;
    selected = marker.dataset.replayPlayer;
    root.querySelector("#replay-player").value = selected;
    draw();
  });
  root.querySelector("#replay-map-image").addEventListener("error", () => {
    message.textContent = "地图底图暂时无法加载，请稍后重试。";
  });
  renderEvents();
  draw();
  return pause;
}
