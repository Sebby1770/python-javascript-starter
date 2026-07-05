const HISTORY_KEY = "taskpulse-burndown-history";

function todayKey(referenceDate = new Date()) {
  return referenceDate.toISOString().slice(0, 10);
}

export function loadBurndownHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveBurndownHistory(history) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-30)));
}

export function recordPendingCount(pendingCount, referenceDate = new Date()) {
  const key = todayKey(referenceDate);
  const history = loadBurndownHistory().filter((entry) => entry.date !== key);
  history.push({ date: key, pending: Math.max(0, Number(pendingCount) || 0) });
  history.sort((first, second) => first.date.localeCompare(second.date));
  saveBurndownHistory(history);
  return history;
}

export function lastSevenDays(history = loadBurndownHistory(), referenceDate = new Date()) {
  const days = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = new Date(referenceDate);
    day.setDate(day.getDate() - offset);
    const key = todayKey(day);
    const existing = history.find((entry) => entry.date === key);
    days.push({
      date: key,
      label: day.toLocaleDateString(undefined, { weekday: "short" }),
      pending: existing ? existing.pending : null,
    });
  }
  return days;
}

export function renderBurndownChart(container, history, referenceDate = new Date()) {
  if (!container) {
    return;
  }

  const days = lastSevenDays(history, referenceDate);
  const known = days.filter((day) => day.pending !== null);
  const maxPending = Math.max(1, ...known.map((day) => day.pending), 1);

  container.replaceChildren();

  const chart = document.createElement("div");
  chart.className = "burndown-chart";
  chart.setAttribute("role", "img");
  chart.setAttribute(
    "aria-label",
    "Burndown chart showing pending tasks over the last seven days",
  );

  for (const day of days) {
    const bar = document.createElement("div");
    bar.className = "burndown-bar";

    const fill = document.createElement("div");
    fill.className = "burndown-bar-fill";
    if (day.pending === null) {
      fill.style.height = "0%";
      fill.dataset.empty = "true";
    } else {
      fill.style.height = `${Math.round((day.pending / maxPending) * 100)}%`;
      fill.title = `${day.pending} pending`;
    }

    const label = document.createElement("span");
    label.className = "burndown-bar-label";
    label.textContent = day.label;

    const value = document.createElement("span");
    value.className = "burndown-bar-value";
    value.textContent = day.pending === null ? "—" : String(day.pending);

    bar.append(fill, label, value);
    chart.append(bar);
  }

  container.append(chart);
}