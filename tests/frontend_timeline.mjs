/** 回顾通知的时间边界回归，使用 Node 内置断言，不访问网络或浏览器。 */
import assert from "node:assert/strict";
import { replayEventsAtTime } from "../pages/camp-console/views/replay.js";

const events = [
  { id: "second", time_seconds: 12 },
  { id: "first", time_seconds: 10 },
  { id: "same-time", time_seconds: 12 },
  { id: "missing", time_seconds: null },
];
const original = JSON.stringify(events);
assert.deepEqual(replayEventsAtTime(events, 9), []);
assert.deepEqual(
  replayEventsAtTime(events, 10).map((event) => event.id),
  ["first"],
);
assert.deepEqual(
  replayEventsAtTime(events, 12).map((event) => event.id),
  ["first", "second", "same-time"],
);
assert.deepEqual(
  replayEventsAtTime(events, 16).map((event) => event.id),
  ["second", "same-time"],
);
assert.deepEqual(replayEventsAtTime(events, 18), []);
assert.deepEqual(
  replayEventsAtTime(events, 100, "first").map((event) => event.id),
  ["first"],
);
assert.deepEqual(replayEventsAtTime(events, NaN), []);
assert.equal(JSON.stringify(events), original);
console.log("回顾通知时间边界、同时事件、手动固定和数据不可变检查通过");
