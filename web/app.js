import { loadBurndownHistory, recordPendingCount, renderBurndownChart } from "./burndown.js";
import {
  isTickSoundEnabled,
  requestNotificationPermission,
  setTickSoundEnabled,
  startPomodoro,
  stopPomodoro,
} from "./pomodoro.js";
import {
  collectTags,
  computeStats,
  filterTasks,
  focusQueue,
  formatMinutes,
  groupByStatus,
  isTaskBlocked,
  normaliseTask,
  parseTagsInput,
  taskSummary,
} from "./tasks.js";

const taskBoard = document.querySelector("[data-task-board]");
const taskForm = document.querySelector("[data-task-form]");
const quickForm = document.querySelector("[data-quick-form]");
const quickPreview = document.querySelector("[data-quick-preview]");
const statusText = document.querySelector("[data-status]");
const template = document.querySelector("[data-task-template]");
const searchInput = document.querySelector("[data-search]");
const tagFilter = document.querySelector("[data-tag-filter]");
const dueTodayFilter = document.querySelector("[data-due-today-filter]");
const themeToggle = document.querySelector("[data-theme-toggle]");
const statsPanel = document.querySelector("[data-stats]");
const emptyState = document.querySelector("[data-empty-state]");
const exportButton = document.querySelector("[data-export-tasks]");
const importInput = document.querySelector("[data-import-tasks]");
const blockedBySelect = document.querySelector("[data-blocked-by-select]");
const recurrenceCheckbox = document.querySelector("[data-recurrence-checkbox]");
const burndownChart = document.querySelector("[data-burndown-chart]");
const pomodoroTickToggle = document.querySelector("[data-pomodoro-tick]");
const presencePill = document.querySelector("[data-presence-pill]");
const focusOverlay = document.querySelector("[data-focus-overlay]");
const focusTitle = document.querySelector("[data-focus-title]");
const focusMeta = document.querySelector("[data-focus-meta]");
const focusTimer = document.querySelector("[data-focus-timer]");
const focusQueueLabel = document.querySelector("[data-focus-queue]");
const focusCompleteButton = document.querySelector("[data-focus-complete]");
const focusSkipButton = document.querySelector("[data-focus-skip]");
const focusExitButton = document.querySelector("[data-focus-exit]");
const modeButtons = document.querySelectorAll("[data-mode]");

let allTasks = [];
let socket = null;
let reconnectTimer = null;
let parsedQuickTask = null;
let focusTasks = [];
let focusIndex = 0;
let focusInterval = null;
let focusRemaining = 0;
let onlineClerks = [];

const THEME_KEY = "taskpulse-theme";
const API_KEY_STORAGE = "taskpulse-api-key";

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = saved || (prefersDark ? "dark" : "light");
  applyTheme(theme);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeToggle.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  themeToggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
}

function toggleTheme() {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, nextTheme);
  applyTheme(nextTheme);
}

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = localStorage.getItem(API_KEY_STORAGE);
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: apiHeaders(options.headers || {}),
  });

  if (response.status === 401) {
    const key = window.prompt("API key required. Enter X-API-Key:");
    if (key) {
      localStorage.setItem(API_KEY_STORAGE, key.trim());
      return fetch(url, {
        ...options,
        headers: apiHeaders(options.headers || {}),
      });
    }
  }

  return response;
}

function setComposerMode(mode) {
  const isQuick = mode === "quick";
  taskForm.hidden = isQuick;
  quickForm.hidden = !isQuick;
  for (const button of modeButtons) {
    button.classList.toggle("is-active", button.dataset.mode === mode);
  }
}

function renderQuickPreview(parsed) {
  if (!parsed) {
    quickPreview.hidden = true;
    quickPreview.replaceChildren();
    return;
  }

  quickPreview.hidden = false;
  quickPreview.innerHTML = `
    <p><strong>Title:</strong> ${parsed.title}</p>
    <p><strong>Owner:</strong> ${parsed.owner}</p>
    <p><strong>Priority:</strong> ${parsed.priority}</p>
    <p><strong>Minutes:</strong> ${parsed.minutes}</p>
    <p><strong>Due:</strong> ${parsed.due_date || "—"}</p>
    <p><strong>Tags:</strong> ${(parsed.tags || []).join(", ") || "—"}</p>
  `;
}

async function parseQuickText(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    parsedQuickTask = null;
    renderQuickPreview(null);
    return;
  }

  try {
    const response = await apiFetch("/api/tasks/parse", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: trimmed }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Could not parse task.");
    }
    const data = await response.json();
    parsedQuickTask = data.parsed;
    renderQuickPreview(parsedQuickTask);
  } catch (error) {
    parsedQuickTask = null;
    renderQuickPreview(null);
    setStatus(error.message);
  }
}

function renderPresence() {
  const count = onlineClerks.length;
  if (count === 0) {
    presencePill.hidden = true;
    return;
  }

  presencePill.hidden = false;
  const label = count === 1 ? "1 clerk online" : `${count} clerks online`;
  presencePill.textContent = label;
  presencePill.title = onlineClerks.join(", ");
}

async function loadTasks() {
  setStatus("Loading tasks...");

  try {
    const response = await fetch("/api/tasks");
    const data = await response.json();
    allTasks = data.tasks.map(normaliseTask);
    renderTasks();
    setStatus("Ready");
  } catch (error) {
    setStatus(`Could not load tasks: ${error.message}`);
  }
}

async function createTask(event) {
  event.preventDefault();
  const formData = new FormData(taskForm);

  const payload = {
    title: formData.get("title"),
    owner: formData.get("owner"),
    priority: formData.get("priority"),
    minutes: Number(formData.get("minutes")),
    due_date: formData.get("due_date") || null,
    tags: parseTagsInput(formData.get("tags")),
    blocked_by: formData.get("blocked_by") ? [Number(formData.get("blocked_by"))] : [],
    recurrence: recurrenceCheckbox.checked ? "daily" : null,
  };

  try {
    const response = await apiFetch("/api/tasks", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be created.");
    }

    taskForm.reset();
    recurrenceCheckbox.checked = false;
    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
}

async function createQuickTask(event) {
  event.preventDefault();
  const text = quickForm.querySelector("[name='quick_text']").value.trim();
  if (!text) {
    setStatus("Enter task text to parse.");
    return;
  }

  if (!parsedQuickTask) {
    await parseQuickText(text);
  }
  if (!parsedQuickTask) {
    return;
  }

  try {
    const response = await apiFetch("/api/tasks", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(parsedQuickTask),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be created.");
    }

    quickForm.reset();
    parsedQuickTask = null;
    renderQuickPreview(null);
    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
}

async function updateTask(taskId, fields) {
  try {
    const response = await apiFetch(`/api/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(fields),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be updated.");
    }

    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
}

async function deleteTask(taskId) {
  try {
    const response = await apiFetch(`/api/tasks/${taskId}`, { method: "DELETE" });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be deleted.");
    }

    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
}

async function exportTasks() {
  try {
    const response = await fetch("/api/tasks/export");
    if (!response.ok) {
      throw new Error("Export failed.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "tasks.json";
    link.click();
    URL.revokeObjectURL(url);
    setStatus("Tasks exported.");
  } catch (error) {
    setStatus(error.message);
  }
}

async function importTasks(file) {
  if (!file) {
    return;
  }

  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const response = await apiFetch("/api/tasks/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Import failed.");
    }

    await loadTasks();
    setStatus("Tasks imported.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    importInput.value = "";
  }
}

function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

  socket.addEventListener("open", () => {
    setStatus("Live sync connected");
  });

  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.event === "presence_changed") {
        onlineClerks = payload.clerks || [];
        renderPresence();
        return;
      }
    } catch {
      // Fall through to task reload.
    }
    loadTasks();
  });

  socket.addEventListener("close", () => {
    onlineClerks = [];
    renderPresence();
    setStatus("Live sync disconnected — retrying...");
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connectWebSocket, 2000);
  });
}

function renderStats(tasks) {
  const stats = computeStats(tasks);

  statsPanel.querySelector("[data-stat-total]").textContent = String(stats.total);
  statsPanel.querySelector("[data-stat-completed]").textContent = String(stats.completed);
  statsPanel.querySelector("[data-stat-pending]").textContent = String(stats.pending);

  for (const priority of ["high", "medium", "low"]) {
    const node = statsPanel.querySelector(`[data-stat-minutes-${priority}]`);
    node.textContent = formatMinutes(stats.minutesByPriority[priority]);
  }

  const history = recordPendingCount(stats.pending);
  renderBurndownChart(burndownChart, history);
}

function renderBlockedByOptions(tasks) {
  const current = blockedBySelect.value;
  blockedBySelect.replaceChildren();

  const noneOption = document.createElement("option");
  noneOption.value = "";
  noneOption.textContent = "None";
  blockedBySelect.append(noneOption);

  for (const task of tasks) {
    const option = document.createElement("option");
    option.value = String(task.id);
    option.textContent = `#${task.id} ${task.title}`;
    blockedBySelect.append(option);
  }

  blockedBySelect.value = tasks.some((task) => String(task.id) === current) ? current : "";
}

function renderTagFilterOptions(tasks) {
  const current = tagFilter.value;
  const tags = collectTags(tasks);

  tagFilter.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "All tags";
  tagFilter.append(allOption);

  for (const tag of tags) {
    const option = document.createElement("option");
    option.value = tag;
    option.textContent = tag;
    tagFilter.append(option);
  }

  tagFilter.value = tags.includes(current) ? current : "";
}

function formatCountdown(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function stopFocusTimer() {
  if (focusInterval) {
    clearInterval(focusInterval);
    focusInterval = null;
  }
}

function renderFocusTask() {
  const task = focusTasks[focusIndex];
  if (!task) {
    exitFocusMode();
    return;
  }

  focusTitle.textContent = task.title;
  focusMeta.textContent = `${task.owner} · ${task.priority} priority · ${formatMinutes(task.minutes)}`;
  focusQueueLabel.textContent = `Task ${focusIndex + 1} of ${focusTasks.length}`;
  focusRemaining = task.minutes * 60;
  focusTimer.textContent = formatCountdown(focusRemaining);

  stopFocusTimer();
  focusInterval = setInterval(() => {
    focusRemaining -= 1;
    focusTimer.textContent = formatCountdown(Math.max(0, focusRemaining));
    if (focusRemaining <= 0) {
      stopFocusTimer();
      if (window.confirm(`Time's up for "${task.title}". Mark it done?`)) {
        updateTask(task.id, { status: "done", done: true }).then(() => nextFocusTask());
      }
    }
  }, 1000);
}

function enterFocusMode(startTaskId = null) {
  focusTasks = focusQueue(allTasks).filter((task) => !isTaskBlocked(task, allTasks));
  if (!focusTasks.length) {
    setStatus("No pending tasks available for focus mode.");
    return;
  }

  if (startTaskId) {
    const index = focusTasks.findIndex((task) => task.id === startTaskId);
    focusIndex = index >= 0 ? index : 0;
  } else {
    focusIndex = 0;
  }

  focusOverlay.hidden = false;
  document.body.classList.add("is-focus-mode");
  renderFocusTask();
}

function nextFocusTask() {
  focusIndex += 1;
  if (focusIndex >= focusTasks.length) {
    exitFocusMode();
    setStatus("Focus queue complete.");
    return;
  }
  renderFocusTask();
}

function exitFocusMode() {
  stopFocusTimer();
  focusOverlay.hidden = true;
  document.body.classList.remove("is-focus-mode");
}

function createTaskCard(task) {
  const taskNode = template.content.firstElementChild.cloneNode(true);
  const blocked = isTaskBlocked(task, allTasks);

  taskNode.dataset.priority = task.priority;
  taskNode.dataset.status = task.status;
  taskNode.dataset.taskId = String(task.id);
  taskNode.draggable = true;
  taskNode.classList.toggle("is-done", task.done);
  taskNode.classList.toggle("is-blocked", blocked);

  const titleNode = taskNode.querySelector("[data-task-title]");
  titleNode.textContent = task.title;
  titleNode.addEventListener("click", () => startInlineEdit(titleNode, task));

  taskNode.querySelector("[data-task-owner]").textContent = task.owner;
  taskNode.querySelector("[data-task-summary]").textContent = taskSummary(task);

  const blockedNode = taskNode.querySelector("[data-task-blocked]");
  if (task.blockedBy.length) {
    const labels = task.blockedBy.map((id) => `#${id}`).join(", ");
    blockedNode.textContent = blocked ? `🔒 Blocked by ${labels}` : `Depends on ${labels}`;
    blockedNode.hidden = false;
  }

  const tagsNode = taskNode.querySelector("[data-task-tags]");
  tagsNode.replaceChildren();
  for (const tag of task.tags) {
    const pill = document.createElement("span");
    pill.className = "tag-pill";
    pill.textContent = tag;
    tagsNode.append(pill);
  }
  if (task.recurrence) {
    const pill = document.createElement("span");
    pill.className = "tag-pill tag-pill--recurrence";
    pill.textContent = `↻ ${task.recurrence}`;
    tagsNode.append(pill);
  }

  const dueNode = taskNode.querySelector("[data-task-due]");
  if (task.dueDate) {
    dueNode.textContent = `Due ${task.dueDate}`;
    dueNode.hidden = false;
  } else {
    dueNode.hidden = true;
  }

  const doingButton = taskNode.querySelector('[data-set-status="doing"]');
  const doingLabel = doingButton.querySelector("[data-doing-label]");
  if (blocked) {
    doingButton.disabled = true;
    doingLabel.textContent = "🔒 Doing";
    doingButton.title = "Complete blocking tasks first";
  }

  for (const button of taskNode.querySelectorAll("[data-set-status]")) {
    const status = button.dataset.setStatus;
    button.classList.toggle("is-active", task.status === status);
    button.addEventListener("click", () => updateTask(task.id, { status }));
  }

  taskNode.querySelector("[data-delete-task]").addEventListener("click", () => deleteTask(task.id));

  taskNode.querySelector("[data-start-pomodoro]").addEventListener("click", () => {
    requestNotificationPermission();
    startPomodoro({
      task,
      card: taskNode,
      onStart: (activeTask) => {
        if (activeTask.status !== "doing") {
          updateTask(activeTask.id, { status: "doing" });
        }
      },
      onComplete: (activeTask) => {
        if (window.confirm(`Pomodoro finished for "${activeTask.title}". Mark it done?`)) {
          updateTask(activeTask.id, { status: "done", done: true });
        }
      },
    });
  });

  taskNode.querySelector("[data-enter-focus]").addEventListener("click", () => {
    enterFocusMode(task.id);
  });

  taskNode.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/task-id", String(task.id));
    taskNode.classList.add("is-dragging");
  });

  taskNode.addEventListener("dragend", () => {
    taskNode.classList.remove("is-dragging");
  });

  return taskNode;
}

function startInlineEdit(titleNode, task) {
  if (titleNode.isContentEditable) {
    return;
  }

  titleNode.contentEditable = "true";
  titleNode.classList.add("is-editing");
  titleNode.focus();

  const range = document.createRange();
  range.selectNodeContents(titleNode);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);

  const finish = async () => {
    titleNode.contentEditable = "false";
    titleNode.classList.remove("is-editing");
    const nextTitle = titleNode.textContent.trim();
    if (!nextTitle) {
      titleNode.textContent = task.title;
      return;
    }
    if (nextTitle !== task.title) {
      await updateTask(task.id, { title: nextTitle });
    }
  };

  titleNode.addEventListener(
    "blur",
    () => {
      finish();
    },
    { once: true },
  );

  titleNode.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      titleNode.blur();
    }
    if (event.key === "Escape") {
      titleNode.textContent = task.title;
      titleNode.blur();
    }
  });
}

function setupColumnDropZones() {
  for (const column of taskBoard.querySelectorAll("[data-status-column]")) {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("is-drop-target");
    });

    column.addEventListener("dragleave", () => {
      column.classList.remove("is-drop-target");
    });

    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("is-drop-target");
      const taskId = Number(event.dataTransfer.getData("text/task-id"));
      const status = column.dataset.statusColumn;
      if (!taskId || !status) {
        return;
      }
      const task = allTasks.find((item) => item.id === taskId);
      if (task && task.status !== status) {
        await updateTask(taskId, { status });
      }
    });
  }
}

function renderTasks() {
  const query = searchInput.value;
  const visibleTasks = filterTasks(allTasks, query, {
    tag: tagFilter.value,
    dueToday: dueTodayFilter.checked,
  });
  renderStats(allTasks);
  renderTagFilterOptions(allTasks);
  renderBlockedByOptions(allTasks);

  for (const column of taskBoard.querySelectorAll("[data-status-column]")) {
    const list = column.querySelector("[data-column-list]");
    list.replaceChildren();
    column.querySelector("[data-column-count]").textContent = "0";
  }

  if (visibleTasks.length === 0) {
    emptyState.hidden = false;
    emptyState.textContent = query || tagFilter.value || dueTodayFilter.checked
      ? "No tasks match your filters."
      : "No tasks yet. Add one to get started.";
    return;
  }

  emptyState.hidden = true;
  const groups = groupByStatus(visibleTasks);

  for (const status of ["todo", "doing", "done"]) {
    const column = taskBoard.querySelector(`[data-status-column="${status}"]`);
    const list = column.querySelector("[data-column-list]");
    column.querySelector("[data-column-count]").textContent = String(groups[status].length);

    for (const task of groups[status]) {
      list.append(createTaskCard(task));
    }
  }
}

function setStatus(message) {
  statusText.textContent = message;
}

initTheme();
themeToggle.addEventListener("click", toggleTheme);
searchInput.addEventListener("input", renderTasks);
tagFilter.addEventListener("change", renderTasks);
dueTodayFilter.addEventListener("change", renderTasks);
taskForm.addEventListener("submit", createTask);
quickForm.addEventListener("submit", createQuickTask);
quickForm.querySelector("[name='quick_text']").addEventListener("input", (event) => {
  parseQuickText(event.target.value);
});
for (const button of modeButtons) {
  button.addEventListener("click", () => setComposerMode(button.dataset.mode));
}
exportButton.addEventListener("click", exportTasks);
importInput.addEventListener("change", () => importTasks(importInput.files[0]));
pomodoroTickToggle.checked = isTickSoundEnabled();
pomodoroTickToggle.addEventListener("change", () => {
  setTickSoundEnabled(pomodoroTickToggle.checked);
});
focusCompleteButton.addEventListener("click", async () => {
  const task = focusTasks[focusIndex];
  if (task) {
    await updateTask(task.id, { status: "done", done: true });
  }
  nextFocusTask();
});
focusSkipButton.addEventListener("click", () => nextFocusTask());
focusExitButton.addEventListener("click", exitFocusMode);
focusOverlay.addEventListener("click", (event) => {
  if (event.target === focusOverlay) {
    exitFocusMode();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !focusOverlay.hidden) {
    exitFocusMode();
  }
});
setupColumnDropZones();
renderBurndownChart(burndownChart, loadBurndownHistory());
requestNotificationPermission();
loadTasks();
connectWebSocket();