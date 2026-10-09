/** 资料和战绩只使用后端公开模型，页面不再次解释营地原始字段。 */
import {
  html,
  escapeHtml as e,
  icon,
  image,
  numberText as n,
  safeImageUrl,
} from "../lib/dom.js";

export function playerIdentity(profile = {}, showGameStatus = false) {
  const rank =
    profile.rank_label && profile.rank_label !== "未知"
      ? profile.rank_label
      : "段位未返回";
  return html`<div class="player-identity">
    ${image(profile.avatar, profile.nickname, "avatar")}
    <div>
      <div class="player-name-row">
        <div class="player-name text-wrap">${e(profile.nickname)}</div>
        ${showGameStatus ? html`<span class="game-status ${{ 0: "offline", 1: "online", 2: "playing" }[profile.game_online] || "unknown"}">游戏状态 · ${e(profile.game_status || "未知")}</span>` : ""}
      </div>
      <div class="player-meta">
        营地 ID
        ${e(profile.camp_id)}${profile.area_name ? ` · ${e(profile.area_name)}` : ""}
      </div>
    </div>
    <div class="player-ranks">
      <div class="rank-block">
        ${profile.rank_icon ? image(profile.rank_icon, "", "rank-image") : ""}
        <div>
          <div class="rank-value">
            ${e(rank)}${rank !== "段位未返回" ? ` <span class="number">${n(profile.current_stars)}</span> 星` : ""}
          </div>
        </div>
      </div>
      <div class="rank-block">
        <div>
          <div class="rank-label">巅峰积分</div>
          <div class="rank-value number">
            ${profile.peak_score > 0 ? n(profile.peak_score) : "—"}
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

export function profileView(data) {
  const profile = data.profile || {},
    heroes = data.season_heroes || [];
  const metrics = [
    ["赛季场次", profile.season_games],
    ["赛季胜率", profile.season_games > 0 ? `${n(profile.win_rate)}%` : "—"],
    ["排位评分", profile.rank_score > 0 ? profile.rank_score : null],
    ["巅峰评分", profile.peak_rating > 0 ? profile.peak_rating : null],
    ["赛季胜场", profile.season_wins],
    ["全场最佳", profile.mvp_count],
    ["金牌次数", profile.gold_count],
    ["区服", profile.server_name || profile.area_name],
  ];
  return html`${playerIdentity(profile, true)}${profile.hide_match ? '<div class="inline-notice">该玩家隐藏了个人战绩。</div>' : ""}
    <dl class="profile-stats">
      ${metrics
        .map(
          ([label, value]) =>
            html`<div>
              <dt>${label}</dt>
              <dd>${typeof value === "string" ? e(value) : n(value)}</dd>
            </div>`,
        )
        .join("")}
    </dl>
    <div class="section-heading">
      <h2>赛季常用英雄</h2>
      <span class="muted">${e(data.season_name)}</span>
    </div>
    ${
      heroes.length
        ? html`<div class="hero-stat-row header">
              <span>英雄</span><span>场次</span><span>胜率</span
              ><span>战力</span>
            </div>
            ${heroes
              .map(
                (hero) =>
                  html`<div class="hero-stat-row">
                    <div class="match-hero">
                      ${image(hero.hero_icon, hero.hero_name)}<span
                        >${e(hero.hero_name)}</span
                      >
                    </div>
                    <span class="number">${n(hero.games)}</span
                    ><span class="number">${n(hero.win_rate)}%</span
                    ><span class="number">${n(hero.fight_power)}</span>
                  </div>`,
              )
              .join("")}`
        : '<div class="empty-state">营地暂未返回本赛季英雄统计</div>'
    }`;
}

export function battleView(data, option, limit) {
  const summary = data.summary || {},
    rows = data.list || [];
  const cells = [
    [`最近 ${summary.total ?? rows.length} 场`, ""],
    ["胜率", `${n(summary.win_rate)}%`],
    ["场均 KDA", n(summary.avg_kda)],
    ["平均评分", summary.avg_score > 0 ? n(summary.avg_score) : "—"],
  ];
  return html`${playerIdentity(data.profile)}
    <div class="summary-strip">
      ${cells
        .map(
          ([label, value], index) =>
            html`<div class="summary-cell">
              ${
                index
                  ? html`<div class="label">${label}</div>
                      <div class="value">${value}</div>`
                  : html`<div class="value">${label}</div>`
              }
            </div>`,
        )
        .join("")}
    </div>
    <div class="match-toolbar">
      <h2>近期对局</h2>
      <div class="match-controls">
        <div class="segmented" role="group" aria-label="战绩模式">
          ${[
            [0, "全部"],
            [1, "排位"],
            [4, "巅峰"],
          ]
            .map(
              ([value, label]) =>
                html`<button
                  type="button"
                  data-option="${value}"
                  class="${option === value ? "active" : ""}"
                  aria-pressed="${option === value}"
                >
                  ${label}
                </button>`,
            )
            .join("")}
        </div>
        <select id="query-limit" aria-label="战绩场数">
          ${[5, 10, 15, 25].map((value) => html`<option value="${value}" ${value === limit ? "selected" : ""}>${value} 场</option>`).join("")}
        </select>
      </div>
    </div>
    <div class="match-list">
      <div class="match-labels">
        <span>英雄</span><span>对局</span><span>KDA</span
        ><span>评分 / 荣誉</span><span>时长</span><span></span>
      </div>
      ${rows
        .map(
          (row, index) =>
            html`<button
              type="button"
              class="match-row ${row.result === "win" ? "win" : row.result === "lose" ? "lose" : "unknown"}"
              data-match="${e(row.game_seq)}"
              data-index="${index + 1}"
              aria-label="查看 ${e(row.hero_name)} ${e(row.played_at)} 的对局详情"
            >
              <div class="match-hero">
                ${image(row.hero_icon, row.hero_name)}
                <div>
                  <div class="match-hero-name">${e(row.hero_name)}</div>
                  <div class="match-mode">
                    ${e(row.mode_name)}${row.kill_streaks?.length ? ` · ${row.kill_streaks.map((item) => e(item.label)).join(" / ")}` : ""}${row.first_blood ? " · 一血" : ""}${row.rank_name ? ` · ${e(row.rank_name)} ${row.stars}星` : ""}
                  </div>
                </div>
              </div>
              <div class="match-info">
                <span class="match-time">${e(row.played_at)}</span
                ><span
                  class="match-result ${row.result === "win" ? "success" : row.result === "lose" ? "danger" : "muted"}"
                  >${e(row.result_text)}</span
                >
              </div>
              <div class="match-kda">
                ${row.kills} / ${row.deaths} / ${row.assists}
              </div>
              <div class="match-score">
                ${row.score > 0 ? n(row.score) : "—"}${row.mvp_type ? (safeImageUrl(row.mvp_icon) ? image(row.mvp_icon, row.mvp_type === "svp" ? "SVP" : "MVP", "honor-image") : html`<span class="honor-label">${row.mvp_type === "svp" ? "SVP" : "MVP"}</span>`) : row.medal ? (safeImageUrl(row.medal_icon) ? image(row.medal_icon, row.medal, "honor-image") : html`<span class="honor-label">${e(row.medal)}</span>`) : ""}
              </div>
              <div class="match-duration">
                ${row.duration_sec > 0 ? e(row.duration_text) : "—"}${row.peak_delta != null ? html`<span class="metric-small">巅峰 ${row.peak_delta > 0 ? "+" : ""}${n(row.peak_delta)}</span>` : ""}
              </div>
              ${icon("arrow")}
            </button>`,
        )
        .join("")}
    </div>
    <p class="list-note">
      显示 ${rows.length} 场 · 本次统计 ${summary.total ?? rows.length}
      场。点击对局查看双方表现与对局回放。
    </p>`;
}

export function selectionView(data) {
  return html`<h2>选择要查询的玩家</h2>
    <p class="muted">
      找到多个同名用户，选择营地 ID 后继续查询。候选在 60 秒后过期。
    </p>
    <div class="selection-list">
      ${(data.candidates || [])
        .map(
          (row) =>
            html`<button
              class="selection-row"
              data-candidate="${e(row.uid)}"
              type="button"
            >
              ${image(row.avatar, row.name, "avatar")}
              <div class="selection-main">
                <div class="selection-name">${e(row.name)}</div>
                <div class="selection-meta">
                  ${e(row.region)} · ${e(row.dw)} · 营地 ID ${e(row.uid)}
                </div>
              </div>
              ${icon("arrow")}
            </button>`,
        )
        .join("")}
    </div>
    <button class="button text" id="cancel-selection" type="button">
      取消选择
    </button>`;
}
