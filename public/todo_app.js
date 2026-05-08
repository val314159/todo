const state = {
  tasks: [],
  filter: "all",
  priority: "all",
  sort: "due",
  query: "",
};

const elts = {
  form: document.getElementById("taskForm"),
  editingId: document.getElementById("editingId"),
  title: document.getElementById("titleInput"),
  priority: document.getElementById("priorityInput"),
  due: document.getElementById("dueInput"),
  notes: document.getElementById("notesInput"),
  submit: document.getElementById("submitButton"),
  cancelEdit: document.getElementById("cancelEditButton"),
  reload: document.getElementById("reloadButton"),
  error: document.getElementById("errorBox"),
  search: document.getElementById("searchInput"),
  priorityFilter: document.getElementById("priorityFilter"),
  sort: document.getElementById("sortSelect"),
  clearCompleted: document.getElementById("clearCompletedButton"),
  list: document.getElementById("taskList"),
  empty: document.getElementById("emptyState"),
  summary: document.getElementById("summaryLine"),
  allCount: document.getElementById("allCount"),
  activeCount: document.getElementById("activeCount"),
  doneCount: document.getElementById("doneCount"),
};

const priorityRank = { high: 0, medium: 1, low: 2 };
const priorityClass = {
  high: "border-red-200 bg-red-50 text-red-700",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-emerald-200 bg-emerald-50 text-emerald-700",
};
const stateCycle = ["IDLE", "WAITING", "RUNNING", "BLOCKED", "DONE"];
const stateClass = {
  IDLE: "border-zinc-200 bg-white text-zinc-500",
  WAITING: "border-sky-200 bg-sky-50 text-sky-700",
  RUNNING: "border-emerald-200 bg-emerald-50 text-emerald-700",
  BLOCKED: "border-red-200 bg-red-50 text-red-700",
  DONE: "border-zinc-300 bg-zinc-100 text-zinc-500",
};

function showError(message) {
  elts.error.textContent = message;
  elts.error.hidden = false;
}

function clearError() {
  elts.error.hidden = true;
  elts.error.textContent = "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed with ${response.status}`);
  }
  return data;
}

async function loadTasks() {
  clearError();
  try {
    const data = await api("/api/tasks");
    state.tasks = data.tasks || [];
    render();
  } catch (error) {
    showError(error.message);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function dateForInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  const pad = (num) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function dueLabel(value) {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function dueClass(task) {
  if (task.completed || !task.due_at) return "text-zinc-500";
  const time = new Date(task.due_at).getTime();
  if (Number.isNaN(time)) return "text-zinc-500";
  return time < Date.now() ? "text-red-700" : "text-zinc-500";
}

function titleClass(task) {
  if (task.state === "DONE") return "font-normal text-zinc-500 line-through";
  if (task.state === "RUNNING" || task.state === "BLOCKED") return "font-bold text-zinc-950";
  if (task.state === "WAITING") return "font-normal text-zinc-700";
  return "font-normal text-zinc-950";
}

function nextState(value) {
  const index = stateCycle.indexOf(value);
  return stateCycle[(index + 1) % stateCycle.length];
}

function matchesTask(task) {
  if (state.filter === "active" && task.completed) return false;
  if (state.filter === "completed" && !task.completed) return false;
  if (state.priority !== "all" && task.priority !== state.priority) return false;
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  const dependencies = (task.dependencies || [])
    .map((dependency) => `${dependency.title} ${dependency.state}`)
    .join(" ");
  return `${task.title} ${task.notes || ""} ${dependencies}`.toLowerCase().includes(query);
}

function sortTasks(tasks) {
  return [...tasks].sort((a, b) => {
    if (state.sort === "priority") {
      return (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9)
        || String(a.title).localeCompare(String(b.title));
    }
    if (state.sort === "created") {
      return String(b.created_at || "").localeCompare(String(a.created_at || ""));
    }
    if (state.sort === "title") {
      return String(a.title).localeCompare(String(b.title));
    }
    return String(a.due_at || "9999").localeCompare(String(b.due_at || "9999"))
      || (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9);
  });
}

function renderCounts() {
  const done = state.tasks.filter((task) => task.completed).length;
  const active = state.tasks.length - done;
  elts.allCount.textContent = state.tasks.length;
  elts.activeCount.textContent = active;
  elts.doneCount.textContent = done;
  elts.clearCompleted.disabled = done === 0;
  elts.clearCompleted.classList.toggle("opacity-50", done === 0);
  elts.clearCompleted.classList.toggle("cursor-not-allowed", done === 0);
}

function renderTabs() {
  document.querySelectorAll(".filter-tab").forEach((button) => {
    const selected = button.dataset.filter === state.filter;
    button.className = `filter-tab h-9 flex-1 rounded-md px-3 text-sm font-medium sm:flex-none ${selected ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-100"}`;
  });
}

function taskRow(task) {
  const checked = task.completed ? "checked" : "";
  const priority = escapeHtml(task.priority || "medium");
  const notes = task.notes ? `<p class="mt-2 whitespace-pre-wrap break-words text-sm text-zinc-600">${escapeHtml(task.notes)}</p>` : "";
  const dependencies = task.dependencies || [];
  const dependencyLine = dependencies.length ? `
    <p class="mt-2 text-xs text-zinc-500">
      depends on ${dependencies.map((dependency) => {
        const label = `${dependency.title} (${dependency.state})`;
        return `<span class="mr-2 whitespace-nowrap">${escapeHtml(label)}</span>`;
      }).join("")}
    </p>
  ` : "";
  return `
    <li class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm" data-id="${escapeHtml(task.id)}">
      <div class="flex gap-3">
        <input type="checkbox" title="Mark done" class="task-toggle mt-1 h-5 w-5 rounded border-zinc-300 text-zinc-950 focus:ring-zinc-900" ${checked}>
        <div class="min-w-0 flex-1">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <h3 class="break-words text-base ${titleClass(task)}">${escapeHtml(task.title)}</h3>
              <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <button type="button" title="Cycle task state" class="task-state inline-flex h-6 items-center rounded-md border px-2 font-semibold ${stateClass[task.state] || stateClass.IDLE}">
                  ${escapeHtml(task.state)}
                </button>
                <span class="inline-flex h-6 items-center rounded-md border px-2 font-semibold ${priorityClass[task.priority] || priorityClass.medium}">${priority}</span>
                <span class="${dueClass(task)}">${escapeHtml(dueLabel(task.due_at))}</span>
              </div>
              ${notes}
              ${dependencyLine}
            </div>
            <div class="flex shrink-0 gap-1">
              <button type="button" title="Edit task" class="task-edit grid h-9 w-9 place-items-center rounded-lg border border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900">
                <i data-lucide="pencil" class="h-4 w-4"></i>
              </button>
              <button type="button" title="Delete task" class="task-delete grid h-9 w-9 place-items-center rounded-lg border border-zinc-300 bg-white text-zinc-700 hover:bg-red-50 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-red-700">
                <i data-lucide="trash-2" class="h-4 w-4"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </li>
  `;
}

function render() {
  renderCounts();
  renderTabs();
  const visible = sortTasks(state.tasks.filter(matchesTask));
  elts.list.innerHTML = visible.map(taskRow).join("");
  elts.empty.hidden = visible.length > 0;
  const active = state.tasks.filter((task) => !task.completed).length;
  elts.summary.textContent = `${visible.length} shown, ${active} active`;
  if (window.lucide) lucide.createIcons();
}

function formPayload() {
  return {
    title: elts.title.value.trim(),
    priority: elts.priority.value,
    due_at: elts.due.value ? new Date(elts.due.value).toISOString() : null,
    notes: elts.notes.value.trim(),
  };
}

function resetForm() {
  elts.form.reset();
  elts.priority.value = "medium";
  elts.editingId.value = "";
  elts.submit.querySelector("span").textContent = "Add task";
  elts.cancelEdit.hidden = true;
  if (window.lucide) lucide.createIcons();
}

function editTask(task) {
  elts.editingId.value = task.id;
  elts.title.value = task.title;
  elts.priority.value = task.priority || "medium";
  elts.due.value = dateForInput(task.due_at);
  elts.notes.value = task.notes || "";
  elts.submit.querySelector("span").textContent = "Save task";
  elts.cancelEdit.hidden = false;
  elts.title.focus();
  if (window.lucide) lucide.createIcons();
}

elts.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const id = elts.editingId.value;
  const payload = formPayload();
  if (!payload.title) {
    showError("Task title is required.");
    return;
  }
  elts.submit.disabled = true;
  try {
    if (id) {
      await api(`/api/tasks/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    } else {
      await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    }
    resetForm();
    await loadTasks();
  } catch (error) {
    showError(error.message);
  } finally {
    elts.submit.disabled = false;
  }
});

elts.list.addEventListener("change", async (event) => {
  if (!event.target.classList.contains("task-toggle")) return;
  const row = event.target.closest("li[data-id]");
  if (!row) return;
  clearError();
  try {
    await api(`/api/tasks/${encodeURIComponent(row.dataset.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ completed: event.target.checked }),
    });
    await loadTasks();
  } catch (error) {
    event.target.checked = !event.target.checked;
    showError(error.message);
  }
});

elts.list.addEventListener("click", async (event) => {
  const row = event.target.closest("li[data-id]");
  if (!row) return;
  const task = state.tasks.find((item) => item.id === row.dataset.id);
  if (!task) return;

  if (event.target.closest(".task-edit")) {
    editTask(task);
    return;
  }

  if (event.target.closest(".task-state")) {
    clearError();
    try {
      await api(`/api/tasks/${encodeURIComponent(task.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ state: nextState(task.state) }),
      });
      await loadTasks();
    } catch (error) {
      showError(error.message);
    }
    return;
  }

  if (event.target.closest(".task-delete")) {
    if (!confirm("Delete this task?")) return;
    clearError();
    try {
      await api(`/api/tasks/${encodeURIComponent(task.id)}`, { method: "DELETE" });
      if (elts.editingId.value === task.id) resetForm();
      await loadTasks();
    } catch (error) {
      showError(error.message);
    }
  }
});

document.querySelectorAll(".filter-tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    render();
  });
});

elts.search.addEventListener("input", () => {
  state.query = elts.search.value;
  render();
});

elts.priorityFilter.addEventListener("change", () => {
  state.priority = elts.priorityFilter.value;
  render();
});

elts.sort.addEventListener("change", () => {
  state.sort = elts.sort.value;
  render();
});

elts.clearCompleted.addEventListener("click", async () => {
  const done = state.tasks.filter((task) => task.completed).length;
  if (!done || !confirm(`Delete ${done} completed task${done === 1 ? "" : "s"}?`)) return;
  clearError();
  try {
    await api("/api/tasks/clear-completed", { method: "POST", body: "{}" });
    resetForm();
    await loadTasks();
  } catch (error) {
    showError(error.message);
  }
});

elts.reload.addEventListener("click", loadTasks);
elts.cancelEdit.addEventListener("click", resetForm);

resetForm();
loadTasks();
