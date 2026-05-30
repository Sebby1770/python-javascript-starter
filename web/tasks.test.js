import assert from "node:assert/strict";
import test from "node:test";

import { groupByPriority, normaliseTask, taskSummary } from "./tasks.js";

test("normaliseTask applies safe defaults", () => {
  const task = normaliseTask({ id: "7", title: "", priority: "urgent" });

  assert.equal(task.id, 7);
  assert.equal(task.title, "Untitled task");
  assert.equal(task.owner, "Unassigned");
  assert.equal(task.priority, "medium");
  assert.equal(task.minutes, 25);
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

test("taskSummary pluralises minutes", () => {
  assert.equal(
    taskSummary({ id: 1, title: "Fast", priority: "high", minutes: 1 }),
    "high priority - 1 minute",
  );
  assert.equal(
    taskSummary({ id: 2, title: "Deep work", priority: "low", minutes: 45 }),
    "low priority - 45 minutes",
  );
});
