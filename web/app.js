import { groupByPriority, normaliseTask, taskSummary } from "./tasks.js";

const taskList = document.querySelector("[data-task-list]");
const taskForm = document.querySelector("[data-task-form]");
const statusText = document.querySelector("[data-status]");
const template = document.querySelector("[data-task-template]");

async function loadTasks() {
  setStatus("Loading tasks...");

  try {
    const response = await fetch("/api/tasks");
    const data = await response.json();
    renderTasks(data.tasks.map(normaliseTask));
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

function renderTasks(tasks) {
  taskList.replaceChildren();
  const groups = groupByPriority(tasks);

  for (const priority of ["high", "medium", "low"]) {
    for (const task of groups[priority]) {
      const taskNode = template.content.firstElementChild.cloneNode(true);
      taskNode.dataset.priority = task.priority;
      taskNode.querySelector("[data-task-title]").textContent = task.title;
      taskNode.querySelector("[data-task-owner]").textContent = task.owner;
      taskNode.querySelector("[data-task-summary]").textContent = taskSummary(task);
      taskList.append(taskNode);
    }
  }
}

function setStatus(message) {
  statusText.textContent = message;
}

taskForm.addEventListener("submit", createTask);
loadTasks();
