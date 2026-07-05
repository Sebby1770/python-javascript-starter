const priorityOrder = {
  high: 0,
  medium: 1,
  low: 2,
};

const statusOrder = {
  todo: 0,
  doing: 1,
  done: 2,
};

export function normaliseTask(task) {
  const done = Boolean(task.done);
  let status = String(task.status || (done ? "done" : "todo")).toLowerCase();
  if (statusOrder[status] === undefined) {
    status = done ? "done" : "todo";
  }
  if (done) {
    status = "done";
  }

  const tags = Array.isArray(task.tags)
    ? task.tags.map((tag) => String(tag).trim().toLowerCase()).filter(Boolean)
    : String(task.tags || "")
        .split(",")
        .map((tag) => tag.trim().toLowerCase())
        .filter(Boolean);

  const blockedBy = Array.isArray(task.blocked_by)
    ? [...new Set(task.blocked_by.map((id) => Number(id)).filter((id) => id > 0))]
    : [];

  return {
    id: Number(task.id),
    title: String(task.title || "Untitled task"),
    owner: String(task.owner || "Unassigned"),
    priority: priorityOrder[task.priority] === undefined ? "medium" : task.priority,
    minutes: Math.max(1, Number(task.minutes || 25)),
    done,
    status,
    dueDate: task.due_date || task.dueDate || null,
    tags: [...new Set(tags)],
    blockedBy,
    recurrence: task.recurrence || null,
    actualMinutes: Math.max(0, Number(task.actual_minutes ?? task.actualMinutes ?? 0)),
    startedAt: task.started_at || task.startedAt || null,
    sprint: task.sprint || null,
    createdAt: task.created_at || task.createdAt || null,
  };
}

export function isTaskBlocked(task, allTasks) {
  const clean = normaliseTask(task);
  if (!clean.blockedBy.length) {
    return false;
  }
  const byId = new Map(allTasks.map((item) => [normaliseTask(item).id, normaliseTask(item)]));
  return clean.blockedBy.some((blockerId) => {
    const blocker = byId.get(blockerId);
    return blocker && !blocker.done;
  });
}

export function focusQueue(tasks) {
  return tasks
    .map(normaliseTask)
    .filter((task) => !task.done && task.status !== "done")
    .sort((first, second) => priorityOrder[first.priority] - priorityOrder[second.priority]);
}

export function parseTagsInput(value) {
  const tags = [];
  const seen = new Set();
  for (const part of String(value || "").split(",")) {
    const tag = part.trim().toLowerCase();
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

export function groupByPriority(tasks) {
  return tasks
    .map(normaliseTask)
    .sort((first, second) => {
      return priorityOrder[first.priority] - priorityOrder[second.priority];
    })
    .reduce(
      (groups, task) => {
        groups[task.priority].push(task);
        return groups;
      },
      { high: [], medium: [], low: [] },
    );
}

export function groupByStatus(tasks) {
  return tasks
    .map(normaliseTask)
    .sort((first, second) => priorityOrder[first.priority] - priorityOrder[second.priority])
    .reduce(
      (groups, task) => {
        groups[task.status].push(task);
        return groups;
      },
      { todo: [], doing: [], done: [] },
    );
}

export function formatMinutes(minutes) {
  const value = Math.max(0, Number(minutes) || 0);
  return `${value} ${value === 1 ? "minute" : "minutes"}`;
}

export function formatDueDate(dueDate) {
  if (!dueDate) {
    return null;
  }
  const parsed = new Date(`${dueDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return dueDate;
  }
  return parsed.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function isDueToday(dueDate, referenceDate = new Date()) {
  if (!dueDate) {
    return false;
  }
  const due = new Date(`${dueDate}T00:00:00`);
  return (
    due.getFullYear() === referenceDate.getFullYear() &&
    due.getMonth() === referenceDate.getMonth() &&
    due.getDate() === referenceDate.getDate()
  );
}

export function taskSummary(task) {
  const cleanTask = normaliseTask(task);
  const parts = [`${cleanTask.priority} priority`, formatMinutes(cleanTask.minutes)];
  const dueLabel = formatDueDate(cleanTask.dueDate);
  if (dueLabel) {
    parts.push(`due ${dueLabel}`);
  }
  return parts.join(" · ");
}

export function filterTasks(tasks, query, options = {}) {
  const needle = String(query || "").trim().toLowerCase();
  const tagFilter = String(options.tag || "").trim().toLowerCase();
  const sprintFilter = String(options.sprint || "").trim();
  const statusFilter = String(options.status || "").trim().toLowerCase();
  const dueTodayOnly = Boolean(options.dueToday);
  const referenceDate = options.referenceDate || new Date();

  return tasks
    .map(normaliseTask)
    .filter((task) => {
      if (dueTodayOnly && !isDueToday(task.dueDate, referenceDate)) {
        return false;
      }

      if (tagFilter && !task.tags.includes(tagFilter)) {
        return false;
      }

      if (sprintFilter && (task.sprint || "") !== sprintFilter) {
        return false;
      }

      if (statusFilter && task.status !== statusFilter) {
        return false;
      }

      if (!needle) {
        return true;
      }

      const haystack = [
        task.title,
        task.owner,
        task.priority,
        task.status,
        task.sprint || "",
        ...task.tags,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
}

export function collectTags(tasks) {
  const tags = new Set();
  for (const task of tasks.map(normaliseTask)) {
    for (const tag of task.tags) {
      tags.add(tag);
    }
  }
  return [...tags].sort();
}

export function collectSprints(tasks) {
  const sprints = new Set();
  for (const task of tasks.map(normaliseTask)) {
    if (task.sprint) {
      sprints.add(task.sprint);
    }
  }
  return [...sprints].sort();
}

export function computeStats(tasks) {
  const normalised = tasks.map(normaliseTask);
  const minutesByPriority = { high: 0, medium: 0, low: 0 };
  let estimatedMinutes = 0;
  let actualMinutes = 0;
  const bySprint = {};

  for (const task of normalised) {
    minutesByPriority[task.priority] += task.minutes;
    estimatedMinutes += task.minutes;
    actualMinutes += task.actualMinutes;

    const sprintKey = task.sprint || "unassigned";
    if (!bySprint[sprintKey]) {
      bySprint[sprintKey] = {
        total: 0,
        completed: 0,
        pending: 0,
        estimatedMinutes: 0,
        actualMinutes: 0,
      };
    }
    bySprint[sprintKey].total += 1;
    if (task.done) {
      bySprint[sprintKey].completed += 1;
    } else {
      bySprint[sprintKey].pending += 1;
    }
    bySprint[sprintKey].estimatedMinutes += task.minutes;
    bySprint[sprintKey].actualMinutes += task.actualMinutes;
  }

  const completed = normalised.filter((task) => task.done).length;

  return {
    total: normalised.length,
    completed,
    pending: normalised.length - completed,
    minutesByPriority,
    estimatedMinutes,
    actualMinutes,
    bySprint,
  };
}

export function isOverdue(task, referenceDate = new Date()) {
  const clean = normaliseTask(task);
  if (clean.done || !clean.dueDate) {
    return false;
  }
  const due = new Date(`${clean.dueDate}T23:59:59`);
  return due < referenceDate;
}

export function isStaleDoing(task, referenceDate = new Date(), staleDays = 3) {
  const clean = normaliseTask(task);
  if (clean.status !== "doing" || clean.done) {
    return false;
  }
  const anchor = clean.startedAt || clean.createdAt;
  if (!anchor) {
    return false;
  }
  const started = new Date(anchor);
  const threshold = staleDays * 24 * 60 * 60 * 1000;
  return referenceDate.getTime() - started.getTime() > threshold;
}

export function isUntaggedHighPriority(task) {
  const clean = normaliseTask(task);
  return clean.priority === "high" && !clean.done && clean.tags.length === 0;
}

export function weeklyReviewItems(tasks, referenceDate = new Date()) {
  const normalised = tasks.map(normaliseTask);
  return {
    overdue: normalised.filter((task) => isOverdue(task, referenceDate)),
    staleDoing: normalised.filter((task) => isStaleDoing(task, referenceDate)),
    untaggedHighPriority: normalised.filter((task) => isUntaggedHighPriority(task)),
  };
}

export function formatActivityTimestamp(timestamp) {
  if (!timestamp) {
    return "";
  }
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatTimeTracking(task) {
  const clean = normaliseTask(task);
  if (clean.actualMinutes > 0) {
    return `${formatMinutes(clean.actualMinutes)} tracked · est ${clean.minutes}m`;
  }
  return `Est ${clean.minutes}m`;
}