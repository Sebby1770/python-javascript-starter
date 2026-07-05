const priorityOrder = {
  high: 0,
  medium: 1,
  low: 2,
};

export function normaliseTask(task) {
  return {
    id: Number(task.id),
    title: String(task.title || "Untitled task"),
    owner: String(task.owner || "Unassigned"),
    priority: priorityOrder[task.priority] === undefined ? "medium" : task.priority,
    minutes: Math.max(1, Number(task.minutes || 25)),
    done: Boolean(task.done),
  };
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

export function formatMinutes(minutes) {
  const value = Math.max(0, Number(minutes) || 0);
  return `${value} ${value === 1 ? "minute" : "minutes"}`;
}

export function taskSummary(task) {
  const cleanTask = normaliseTask(task);
  return `${cleanTask.priority} priority · ${formatMinutes(cleanTask.minutes)}`;
}

export function filterTasks(tasks, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) {
    return tasks.map(normaliseTask);
  }

  return tasks
    .map(normaliseTask)
    .filter((task) => {
      const haystack = [task.title, task.owner, task.priority].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
}

export function computeStats(tasks) {
  const normalised = tasks.map(normaliseTask);
  const minutesByPriority = { high: 0, medium: 0, low: 0 };

  for (const task of normalised) {
    minutesByPriority[task.priority] += task.minutes;
  }

  const completed = normalised.filter((task) => task.done).length;

  return {
    total: normalised.length,
    completed,
    pending: normalised.length - completed,
    minutesByPriority,
  };
}