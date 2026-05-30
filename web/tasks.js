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

export function taskSummary(task) {
  const cleanTask = normaliseTask(task);
  const minuteLabel = cleanTask.minutes === 1 ? "minute" : "minutes";
  return `${cleanTask.priority} priority - ${cleanTask.minutes} ${minuteLabel}`;
}
