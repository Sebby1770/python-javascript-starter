import assert from "node:assert/strict";
import test from "node:test";

import {
  computeStats,
  filterTasks,
  formatMinutes,
  groupByPriority,
  normaliseTask,
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

test("formatMinutes pluralises minute labels", () => {
  assert.equal(formatMinutes(1), "1 minute");
  assert.equal(formatMinutes(45), "45 minutes");
  assert.equal(formatMinutes(0), "0 minutes");
});

test("taskSummary uses formatMinutes", () => {
  assert.equal(
    taskSummary({ id: 1, title: "Fast", priority: "high", minutes: 1 }),
    "high priority · 1 minute",
  );
  assert.equal(
    taskSummary({ id: 2, title: "Deep work", priority: "low", minutes: 45 }),
    "low priority · 45 minutes",
  );
});

test("filterTasks matches title owner and priority", () => {
  const tasks = [
    { id: 1, title: "Write docs", owner: "Seb", priority: "high" },
    { id: 2, title: "Ship UI", owner: "Frontend", priority: "medium" },
  ];

  assert.equal(filterTasks(tasks, "docs").length, 1);
  assert.equal(filterTasks(tasks, "frontend")[0].title, "Ship UI");
  assert.equal(filterTasks(tasks, "HIGH")[0].title, "Write docs");
  assert.equal(filterTasks(tasks, "").length, 2);
  assert.equal(filterTasks(tasks, "missing").length, 0);
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