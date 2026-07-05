import assert from "node:assert/strict";
import test from "node:test";

import {
  collectSprints,
  collectTags,
  computeStats,
  filterTasks,
  focusQueue,
  formatActivityTimestamp,
  formatDueDate,
  formatMinutes,
  formatTimeTracking,
  groupByPriority,
  groupByStatus,
  isDueToday,
  isOverdue,
  isStaleDoing,
  isTaskBlocked,
  isUntaggedHighPriority,
  normaliseTask,
  parseTagsInput,
  taskSummary,
  weeklyReviewItems,
} from "./tasks.js";
import { allTemplates, BUILTIN_TEMPLATES } from "./templates.js";

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

test("normaliseTask includes blockedBy and recurrence", () => {
  const task = normaliseTask({
    id: 1,
    title: "Blocked",
    blocked_by: [2, 2],
    recurrence: "daily",
  });

  assert.deepEqual(task.blockedBy, [2]);
  assert.equal(task.recurrence, "daily");
});

test("isTaskBlocked detects incomplete blockers", () => {
  const tasks = [
    { id: 1, title: "Blocker", status: "todo" },
    { id: 2, title: "Dependent", blocked_by: [1] },
  ];

  assert.equal(isTaskBlocked(tasks[1], tasks), true);

  tasks[0].status = "done";
  tasks[0].done = true;
  assert.equal(isTaskBlocked(tasks[1], tasks), false);
});

test("focusQueue returns pending tasks by priority", () => {
  const queue = focusQueue([
    { id: 1, title: "Low", priority: "low", status: "todo" },
    { id: 2, title: "High", priority: "high", status: "todo" },
    { id: 3, title: "Done", priority: "high", status: "done", done: true },
  ]);

  assert.deepEqual(queue.map((task) => task.title), ["High", "Low"]);
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

test("normaliseTask includes sprint and time tracking fields", () => {
  const task = normaliseTask({
    id: 1,
    title: "Tracked",
    sprint: "Sprint 3",
    actual_minutes: 12,
    started_at: "2026-07-05T10:00:00+00:00",
  });

  assert.equal(task.sprint, "Sprint 3");
  assert.equal(task.actualMinutes, 12);
  assert.equal(task.startedAt, "2026-07-05T10:00:00+00:00");
});

test("computeStats includes estimated and actual totals and sprint stats", () => {
  const stats = computeStats([
    { id: 1, title: "A", sprint: "Sprint 1", minutes: 30, actual_minutes: 10 },
    { id: 2, title: "B", sprint: "Sprint 1", minutes: 20, actual_minutes: 5 },
    { id: 3, title: "C", minutes: 15 },
  ]);

  assert.equal(stats.estimatedMinutes, 65);
  assert.equal(stats.actualMinutes, 15);
  assert.equal(stats.bySprint["Sprint 1"].total, 2);
  assert.equal(stats.bySprint["Sprint 1"].actualMinutes, 15);
  assert.equal(stats.bySprint.unassigned.total, 1);
});

test("filterTasks supports sprint and status filters", () => {
  const tasks = [
    { id: 1, title: "Todo", status: "todo", sprint: "Sprint 1" },
    { id: 2, title: "Doing", status: "doing", sprint: "Sprint 2" },
    { id: 3, title: "Done", status: "done", done: true, sprint: "Sprint 1" },
  ];

  assert.equal(filterTasks(tasks, "", { sprint: "Sprint 1" }).length, 2);
  assert.equal(filterTasks(tasks, "", { status: "doing" }).length, 1);
});

test("collectSprints returns sorted unique sprint names", () => {
  assert.deepEqual(
    collectSprints([
      { id: 1, sprint: "Sprint 2" },
      { id: 2, sprint: "Sprint 1" },
      { id: 3, sprint: "Sprint 2" },
    ]),
    ["Sprint 1", "Sprint 2"],
  );
});

test("weeklyReviewItems finds overdue stale and untagged high priority tasks", () => {
  const reference = new Date("2026-07-10T12:00:00");
  const review = weeklyReviewItems(
    [
      {
        id: 1,
        title: "Late",
        priority: "high",
        due_date: "2026-07-01",
        status: "todo",
      },
      {
        id: 2,
        title: "Stuck",
        status: "doing",
        created_at: "2026-07-01T10:00:00+00:00",
      },
      { id: 3, title: "No tags", priority: "high", status: "todo", tags: [] },
      { id: 4, title: "Fine", priority: "low", status: "todo", tags: ["ok"] },
    ],
    reference,
  );

  assert.equal(review.overdue.length, 1);
  assert.equal(review.staleDoing.length, 1);
  assert.equal(review.untaggedHighPriority.length, 2);
  assert.equal(isOverdue({ due_date: "2026-07-01" }, reference), true);
  assert.equal(
    isStaleDoing(
      { status: "doing", created_at: "2026-07-01T10:00:00+00:00" },
      reference,
    ),
    true,
  );
  assert.equal(isUntaggedHighPriority({ priority: "high", tags: [] }), true);
});

test("formatTimeTracking and formatActivityTimestamp render readable labels", () => {
  assert.match(formatTimeTracking({ minutes: 25, actual_minutes: 10 }), /10 minutes tracked/);
  assert.match(formatActivityTimestamp("2026-07-05T15:30:00+00:00"), /Jul/);
});

test("built-in templates are available", () => {
  assert.equal(BUILTIN_TEMPLATES.length, 4);
  assert.ok(allTemplates().some((template) => template.id === "bug-fix"));
});