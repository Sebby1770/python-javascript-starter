export const BUILTIN_TEMPLATES = [
  {
    id: "bug-fix",
    name: "Bug fix",
    title: "Fix: ",
    owner: "Unassigned",
    priority: "high",
    minutes: 30,
    tags: ["bug"],
    sprint: null,
  },
  {
    id: "feature",
    name: "Feature",
    title: "Feature: ",
    owner: "Unassigned",
    priority: "medium",
    minutes: 60,
    tags: ["feature"],
    sprint: null,
  },
  {
    id: "meeting",
    name: "Meeting",
    title: "Meeting: ",
    owner: "Unassigned",
    priority: "low",
    minutes: 30,
    tags: ["meeting"],
    sprint: null,
  },
  {
    id: "review",
    name: "Review",
    title: "Review: ",
    owner: "Unassigned",
    priority: "medium",
    minutes: 20,
    tags: ["review"],
    sprint: null,
  },
];

const CUSTOM_TEMPLATES_KEY = "taskpulse-custom-templates";

export function loadCustomTemplates() {
  try {
    const raw = localStorage.getItem(CUSTOM_TEMPLATES_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveCustomTemplates(templates) {
  localStorage.setItem(CUSTOM_TEMPLATES_KEY, JSON.stringify(templates));
}

export function allTemplates() {
  return [...BUILTIN_TEMPLATES, ...loadCustomTemplates()];
}

export function templateById(id) {
  return allTemplates().find((template) => template.id === id) || null;
}