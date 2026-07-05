import {
  computeStats,
  filterTasks,
  formatMinutes,
  groupByPriority,
  normaliseTask,
  taskSummary,
} from "./tasks.js";

const taskList = document.querySelector("[data-task-list]");
const taskForm = document.querySelector("[data-task-form]");
const statusText = document.querySelector("[data-status]");
const template = document.querySelector("[data-task-template]");
const searchInput = document.querySelector("[data-search]");
const themeToggle = document.querySelector("[data-theme-toggle]");
const statsPanel = document.querySelector("[data-stats]");
const emptyState = document.querySelector("[data-empty-state]");

let allTasks = [];

const THEME_KEY = "taskpulse-theme";

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
  };

  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be created.");
    }

    taskForm.reset();
    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
}

async function toggleTask(taskId) {
  try {
    const response = await fetch(`/api/tasks/${taskId}`, { method: "PATCH" });

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
    const response = await fetch(`/api/tasks/${taskId}`, { method: "DELETE" });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Task could not be deleted.");
    }

    await loadTasks();
  } catch (error) {
    setStatus(error.message);
  }
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
}

function renderTasks() {
  const query = searchInput.value;
  const visibleTasks = filterTasks(allTasks, query);
  renderStats(allTasks);

  taskList.replaceChildren();

  if (visibleTasks.length === 0) {
    emptyState.hidden = false;
    emptyState.textContent = query
      ? "No tasks match your search."
      : "No tasks yet. Add one to get started.";
    return;
  }

  emptyState.hidden = true;
  const groups = groupByPriority(visibleTasks);

  for (const priority of ["high", "medium", "low"]) {
    for (const task of groups[priority]) {
      const taskNode = template.content.firstElementChild.cloneNode(true);
      taskNode.dataset.priority = task.priority;
      taskNode.classList.toggle("is-done", task.done);

      taskNode.querySelector("[data-task-title]").textContent = task.title;
      taskNode.querySelector("[data-task-owner]").textContent = task.owner;
      taskNode.querySelector("[data-task-summary]").textContent = taskSummary(task);

      const completeButton = taskNode.querySelector("[data-complete-task]");
      completeButton.textContent = task.done ? "Undo" : "Complete";
      completeButton.setAttribute("aria-label", task.done ? "Mark as pending" : "Mark as complete");
      completeButton.addEventListener("click", () => toggleTask(task.id));

      const deleteButton = taskNode.querySelector("[data-delete-task]");
      deleteButton.addEventListener("click", () => deleteTask(task.id));

      taskList.append(taskNode);
    }
  }
}

function setStatus(message) {
  statusText.textContent = message;
}

initTheme();
themeToggle.addEventListener("click", toggleTheme);
searchInput.addEventListener("input", renderTasks);
taskForm.addEventListener("submit", createTask);
loadTasks();