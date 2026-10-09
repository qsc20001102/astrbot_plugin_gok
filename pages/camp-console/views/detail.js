/** 单局概览：双方面板与可切换玩家的营地表现数据。 */
import {
  html,
  escapeHtml as e,
  image,
  icon,
  numberText as n,
} from "../lib/dom.js";

/** 占比使用同一队伍的公开模型；空值不画成零，宽度只接受有限数字。 */
function shareMeter(value) {
  if (value == null || !Number.isFinite(Number(value))) return "";
  const percent = Math.min(100, Math.max(0, Number(value)));
  return html`<span class="damage-share">
    <span
      class="share-track"
      role="meter"
      aria-label="队伍占比"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow="${percent}"
      ><span style="width:${percent}%"></span
    ></span>
    <span class="share-value">${n(value)}%</span>
  </span>`;
}

export function detailShell(data) {
  const match = data.match || {};
  return html`<header class="page-heading">
      <div>
        <h1>单局详情</h1>
        <p>双方表现与对局回放</p>
      </div>
      <button class="button outline" id="back-to-battles" type="button">
        ${icon("back")}返回战绩
      </button>
    </header>
    <div class="detail-heading">
      <span class="detail-result ${match.result === "lose" ? "lose" : ""}"
        >${e(match.result_text)}</span
      >
      <div class="match-hero">
        ${image(match.hero_icon, match.hero_name)}
        <div>
          <strong>${e(match.hero_name)}</strong>
          <div class="metric-small">${e(data.profile?.nickname)}</div>
        </div>
      </div>
      <div class="detail-fact">
        ${e(match.mode_name)}<small>对局模式</small>
      </div>
      <div class="detail-fact">
        ${e(match.played_at)}<small>对局时间</small>
      </div>
      <div class="detail-fact">
        ${match.duration_sec > 0 ? e(match.duration_text) : "—"}<small
          >对局时长</small
        >
      </div>
      <div class="detail-analysis-actions" aria-label="AI 对局分析操作">
        <button
          id="analyze-match"
          class="button primary"
          type="button"
          aria-controls="detail-analysis"
          aria-expanded="false"
          disabled
        >
          分析本场
        </button>
        <button
          id="view-analysis"
          class="button outline"
          type="button"
          aria-controls="detail-analysis"
          aria-expanded="false"
          disabled
        >
          分析结果
        </button>
        <button
          id="clear-analysis"
          class="button outline"
          type="button"
          disabled
        >
          清除缓存
        </button>
      </div>
    </div>
    <section
      id="detail-analysis"
      class="analysis-panel"
      aria-label="AI 对局分析结果"
      hidden
    ></section>
    <div class="detail-tabs" role="tablist" aria-label="详情内容">
      <button
        class="active"
        data-detail-tab="overview"
        role="tab"
        aria-selected="true"
        type="button"
      >
        对局概览</button
      ><button
        data-detail-tab="replay"
        role="tab"
        aria-selected="false"
        type="button"
      >
        对局回放
      </button>
    </div>
    <div id="detail-overview" role="tabpanel">${overview(data)}</div>
    <div id="detail-replay" role="tabpanel" hidden></div>`;
}

function overview(data) {
  if (!data.has_detail)
    return '<div class="empty-state">这场对局的玩家详情暂未返回，稍后可重新查询。</div>';
  const team = (side, label) => {
    const rows = data[side] || [],
      summary = data[`${side}_summary`] || {};
    return html`<section class="team-section team-${side}">
      <div class="team-title">
        <h3><span class="team-dot ${side}"></span>${label}</h3>
        <span class="team-meta"
          >${n(summary.kills)} 击杀 · ${n(summary.money)}
          经济${summary.complete === false ? " · 玩家数据未完整返回" : ""}</span
        >
      </div>
      <div class="table-scroll">
        <table class="detail-table">
          <colgroup>
            <col class="detail-col-player" />
            <col class="detail-col-kda" />
            <col class="detail-col-score" />
            <col class="detail-col-equipment" />
            <col class="detail-col-skill" />
            <col class="detail-col-money" />
            <col class="detail-col-damage" />
            <col class="detail-col-damage" />
          </colgroup>
          <thead>
            <tr>
              <th>玩家 / 英雄</th>
              <th>KDA</th>
              <th>评分</th>
              <th>出装</th>
              <th>召唤师技能</th>
              <th>经济</th>
              <th>英雄伤害</th>
              <th>英雄承伤</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) =>
                  html`<tr class="${row.is_target ? "target-row" : ""}">
                    <td>
                      <div class="player-cell">
                        ${image(row.hero_icon, row.hero_name)}
                        <div>
                          <strong title="${e(row.nickname || row.hero_name)}"
                            >${e(row.nickname || row.hero_name)}</strong
                          ><small
                            >${e(row.hero_name)} · ${n(row.level)} 级</small
                          >
                        </div>
                      </div>
                    </td>
                    <td>${row.kills}/${row.deaths}/${row.assists}</td>
                    <td>
                      ${n(row.score)}${row.mvp ? html`<span class="metric-small honor-label">${row.mvp_type === "svp" ? "SVP" : row.mvp_type === "mvp" ? "MVP" : "最佳"}</span>` : ""}
                    </td>
                    <td>
                      <div class="equipment-build">
                        ${(row.equipment || [])
                          .slice(0, 6)
                          .map((item) =>
                            image(
                              item.icon,
                              item.name || item.id,
                              "equipment-icon",
                            ),
                          )
                          .join("")}
                      </div>
                    </td>
                    <td>
                      ${row.skill?.icon ? html`<div class="summoner-skill">${image(row.skill.icon, row.skill.name, "skill-icon")}<span>${e(row.skill.name)}</span></div>` : "—"}
                    </td>
                    <td>${n(row.money)}</td>
                    <td>
                      ${n(row.hero_damage)}${shareMeter(row.hero_damage_percent)}
                    </td>
                    <td>
                      ${n(row.damage_taken)}${shareMeter(row.damage_taken_percent)}
                    </td>
                  </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </section>`;
  };
  const players = [...(data.blue || []), ...(data.red || [])];
  return `${team("blue", "蓝方")}${team("red", "红方")}<section class="performance-section"><div class="performance-controls"><h2>本场表现</h2><select id="detail-player" aria-label="查看玩家表现">${players.map((row) => html`<option value="${e(row.player_key || row.role_id)}" ${row.is_target ? "selected" : ""}>${e(row.nickname || row.hero_name)} · ${e(row.hero_name)}</option>`).join("")}</select></div><div id="player-performance"></div><p class="list-note">伤害与承伤进度条表示队伍占比。未返回的统计显示为“—”。</p></section>`;
}

export function performanceView(row = {}) {
  const delta = row.fight_power_delta;
  const metrics = [
    ["总伤害", row.total_damage, ""],
    ["总承伤", row.total_damage_taken, ""],
    ["参团率", row.participation, "%"],
    ["控制时长", row.control_seconds, " 秒"],
    ["补刀", row.minions, ""],
    ["治疗量", row.healing, ""],
    ["建筑伤害", row.building_damage, ""],
    ["推塔数", row.tower_count, ""],
    ["野怪经济", row.jungle_economy, ""],
    ["英雄战力", row.fight_power || null, ""],
    [
      "战力变化",
      delta == null ? "—" : `${delta > 0 ? "+" : ""}${n(delta)}`,
      "",
    ],
  ];
  return html`<div class="performance-metrics">
      ${metrics
        .map(
          ([label, value, suffix]) =>
            html`<div>
              <div class="metric-label">${label}</div>
              <div class="metric-value">
                ${typeof value === "string" ? e(value) : n(value, suffix)}
              </div>
            </div>`,
        )
        .join("")}
    </div>
    <div class="ratings">
      ${(row.ratings || []).map((item) => html`<span class="rating">${e(item.label)}<strong>${e(item.grade)}</strong></span>`).join("")}
    </div>
    ${(row.performance || [])
      .map(
        (group) =>
          html`<div class="performance-group">
            <h3>${e(group.title)}</h3>
            ${group.items.map((item) => html`<div class="performance-item"><span class="label">${e(item.name)}</span><span class="${item.highlight ? "success" : ""}">${e(item.value)}</span>${item.note ? html`<span class="performance-note ${item.note_highlight ? "success" : ""}">${e(item.note_text || item.note)}</span>` : ""}</div>`).join("")}
          </div>`,
      )
      .join(
        "",
      )}${row.honors?.length ? html`<div class="stat-honors">${row.honors.map(e).join(" · ")}</div>` : ""}`;
}
