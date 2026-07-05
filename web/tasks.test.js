import assert from "node:assert/strict";
import test from "node:test";

import {
  collectTags,
  computeStats,
  filterTasks,
  formatDueDate,
  formatMinutes,
  groupByPriority,
  groupByStatus,
  isDueToday,
  normaliseTask,
  parseTagsInput,
  taskSummary,
} from "./tasks.js";

test("normaliseTask applies safe defaults", () => {
  const task = normaliseTask({ id: "7", title: "", priority: "urgent" });

  assert.equal(task.id, 7);
  assert.equal(task.title, "Untitled task");
  assert.equal(task.owner, "Unassigned");
  assert.equal(task.priority, "medium");
  assert.equal(task.minutes, 25);
  assert.equal(task.done, false);
  assert.equal(task.status, "todo");
  assert.deepEqual(task.tags, []);
});

test("normaliseTask maps done to done status", () => {
  const task = normaliseTask({ id: 1, title: "Done", done: true, status: "todo" });
  assert.equal(task.status, "done");
  assert.equal(task.done, true);
});

test("parseTagsInput splits comma-separated tags", () => {
  assert.deepEqual(parseTagsInput("API, frontend ,api"), ["api", "frontend"]);
});

test("groupByPriority sorts tasks into priority buckets", () => {
  const groups = groupByPriority([
    { id: 1, title: "C", priority: "low" },
    { id: 2, title: "A", priority: "high" },
    { id: 3, title: "B", priority: "medium" },
  ]);

  assert.deepEqual(
    Object.fromEntries(Object.entries(groups).map(([key, value]) => [key, value.length])),
    { high: 1, medium: 1, low: 1 },
  );
  assert.equal(groups.high[0].title, "A");
});

test("groupByStatus sorts tasks into kanban columns", () => {
  const groups = groupByStatus([
    { id: 1, title: "Todo", status: "todo" },
    { id: 2, title: "Doing", status: "doing" },
    { id: 3, title: "Done", status: "done", done: true },
  ]);

  assert.equal(groups.todo[0].title, "Todo");
  assert.equal(groups.doing[0].title, "Doing");
  assert.equal(groups.done[0].title, "Done");
});

test("formatMinutes pluralises minute labels", () => {
  assert.equal(formatMinutes(1), "1 minute");
  assert.equal(formatMinutes(45), "45 minutes");
  assert.equal(formatMinutes(0), "0 minutes");
});

test("formatDueDate renders readable dates", () => {
  assert.match(formatDueDate("2026-07-05"), /Jul/);
  assert.equal(formatDueDate(null), null);
});

test("isDueToday matches same calendar day", () => {
  const reference = new Date("2026-07-05T15:00:00");
  assert.equal(isDueToday("2026-07-05", reference), true);
  assert.equal(isDueToday("2026-07-06", reference), false);
});

test("taskSummary uses formatMinutes and due date", () => {
  assert.equal(
    taskSummary({ id: 1, title: "Fast", priority: "high", minutes: 1 }),
    "high priority · 1 minute",
  );
  assert.match(
    taskSummary({
      id: 2,
      title: "Deep work",
      priority: "low",
      minutes: 45,
      due_date: "2026-07-05",
    }),
    /low priority · 45 minutes · due .+2026/,
  );
});

test("filterTasks matches title owner priority tags and due today", () => {
  const tasks = [
    {
      id: 1,
      title: "Write docs",
      owner: "Seb",
      priority: "high",
      tags: ["docs"],
      due_date: "2026-07-05",
    },
    {
      id: 2,
      title: "Ship UI",
      owner: "Frontend",
      priority: "medium",
      tags: ["frontend"],
      due_date: "2026-08-01",
    },
  ];
  const reference = new Date("2026-07-05T12:00:00");

  assert.equal(filterTasks(tasks, "docs").length, 1);
  assert.equal(filterTasks(tasks, "frontend")[0].title, "Ship UI");
  assert.equal(filterTasks(tasks, "HIGH")[0].title, "Write docs");
  assert.equal(filterTasks(tasks, "", { tag: "docs" }).length, 1);
  assert.equal(
    filterTasks(tasks, "", { dueToday: true, referenceDate: reference }).length,
    1,
  );
  assert.equal(filterTasks(tasks, "").length, 2);
  assert.equal(filterTasks(tasks, "missing").length, 0);
});

test("collectTags returns sorted unique tags", () => {
  assert.deepEqual(
    collectTags([
      { id: 1, tags: ["api", "docs"] },
      { id: 2, tags: ["frontend", "api"] },
    ]),
    ["api", "docs", "frontend"],
  );
});

test("computeStats totals tasks and minutes by priority", () => {
  const stats = computeStats([
    { id: 1, title: "A", priority: "high", minutes: 30, done: true },
    { id: 2, title: "B", priority: "medium", minutes: 20 },
    { id: 3, title: "C", priority: "low", minutes: 10 },
  ]);

  assert.equal(stats.total, 3);
  assert.equal(stats.completed, 1);
  assert.equal(stats.pending, 2);
  assert.deepEqual(stats.minutesByPriority, { high: 30, medium: 20, low: 10 });
});