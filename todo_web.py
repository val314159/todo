import os
import re
import uuid
from datetime import datetime, timezone

import bottle
import psycopg2
from psycopg2.extras import Json, RealDictCursor


WORKFLOW_ID = os.environ.get("TODO_WORKFLOW_ID", "personal_todo_list")
WORKFLOW_NAME = os.environ.get("TODO_WORKFLOW_NAME", "personal TODO list")
PRIORITIES = ("low", "medium", "high")
TASK_STATES = ("IDLE", "WAITING", "RUNNING", "BLOCKED", "DONE")

app = bottle.Bottle()
_schema_ready = False


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Todo</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
          },
        },
      },
    };
  </script>
  <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
</head>
<body class="min-h-screen bg-zinc-100 text-zinc-950 antialiased">
  <div class="min-h-screen lg:flex">
    <aside class="border-b border-zinc-200 bg-white lg:min-h-screen lg:w-[24rem] lg:border-b-0 lg:border-r">
      <div class="mx-auto flex max-w-6xl flex-col gap-5 p-4 sm:p-6 lg:max-w-none">
        <div>
          <p class="text-xs font-semibold uppercase text-zinc-500">Postgres workflow</p>
          <div class="mt-1 flex items-center justify-between gap-3">
            <h1 class="text-3xl font-semibold text-zinc-950">Todo</h1>
            <button id="reloadButton" type="button" title="Reload tasks" class="grid h-10 w-10 place-items-center rounded-lg border border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900">
              <i data-lucide="refresh-cw" class="h-4 w-4"></i>
            </button>
          </div>
        </div>

        <form id="taskForm" class="space-y-4">
          <input id="editingId" type="hidden">
          <div>
            <label for="titleInput" class="text-sm font-medium text-zinc-800">Task</label>
            <input id="titleInput" name="title" required maxlength="180" autocomplete="off" class="mt-1 h-11 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200" placeholder="Add something concrete">
          </div>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1">
            <div>
              <label for="priorityInput" class="text-sm font-medium text-zinc-800">Priority</label>
              <select id="priorityInput" name="priority" class="mt-1 h-11 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200">
                <option value="high">High</option>
                <option value="medium" selected>Medium</option>
                <option value="low">Low</option>
              </select>
            </div>

            <div>
              <label for="dueInput" class="text-sm font-medium text-zinc-800">Due</label>
              <input id="dueInput" name="due_at" type="datetime-local" class="mt-1 h-11 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200">
            </div>
          </div>

          <div>
            <label for="notesInput" class="text-sm font-medium text-zinc-800">Notes</label>
            <textarea id="notesInput" name="notes" rows="4" maxlength="1200" class="mt-1 w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200" placeholder="Optional details"></textarea>
          </div>

          <div class="flex gap-2">
            <button id="submitButton" type="submit" class="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-zinc-950 px-4 text-sm font-semibold text-white hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2">
              <i data-lucide="plus" class="h-4 w-4"></i>
              <span>Add task</span>
            </button>
            <button id="cancelEditButton" type="button" hidden class="h-11 rounded-lg border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </aside>

    <main class="min-w-0 flex-1">
      <div class="mx-auto flex max-w-6xl flex-col gap-4 p-4 sm:p-6">
        <div id="errorBox" hidden class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"></div>

        <section class="flex flex-col gap-3 border-b border-zinc-200 pb-4">
          <div class="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto]">
            <label class="relative block">
              <span class="sr-only">Search tasks</span>
              <i data-lucide="search" class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"></i>
              <input id="searchInput" type="search" autocomplete="off" class="h-11 w-full rounded-lg border border-zinc-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200" placeholder="Search tasks">
            </label>
            <select id="priorityFilter" class="h-11 rounded-lg border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200">
              <option value="all">All priorities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select id="sortSelect" class="h-11 rounded-lg border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200">
              <option value="due">Sort by due date</option>
              <option value="priority">Sort by priority</option>
              <option value="created">Sort by newest</option>
              <option value="title">Sort by title</option>
            </select>
          </div>

          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="inline-flex w-full rounded-lg border border-zinc-300 bg-white p-1 sm:w-auto" role="tablist" aria-label="Task filters">
              <button type="button" data-filter="all" class="filter-tab h-9 flex-1 rounded-md px-3 text-sm font-medium sm:flex-none">All <span id="allCount" class="tabular-nums"></span></button>
              <button type="button" data-filter="active" class="filter-tab h-9 flex-1 rounded-md px-3 text-sm font-medium sm:flex-none">Active <span id="activeCount" class="tabular-nums"></span></button>
              <button type="button" data-filter="completed" class="filter-tab h-9 flex-1 rounded-md px-3 text-sm font-medium sm:flex-none">Done <span id="doneCount" class="tabular-nums"></span></button>
            </div>

            <button id="clearCompletedButton" type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-800 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-zinc-900">
              <i data-lucide="list-x" class="h-4 w-4"></i>
              <span>Clear done</span>
            </button>
          </div>
        </section>

        <section>
          <div id="summaryLine" class="mb-3 text-sm text-zinc-600"></div>
          <ul id="taskList" class="grid gap-3"></ul>
          <div id="emptyState" hidden class="flex min-h-[18rem] flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-white px-6 text-center">
            <i data-lucide="clipboard-check" class="h-8 w-8 text-zinc-400"></i>
            <h2 class="mt-3 text-lg font-semibold text-zinc-950">No tasks here</h2>
            <p class="mt-1 max-w-sm text-sm text-zinc-600">Add a task or adjust the current filters.</p>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    const state = {
      tasks: [],
      filter: "all",
      priority: "all",
      sort: "due",
      query: "",
    };

    const els = {
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

    function showError(message) {
      els.error.textContent = message;
      els.error.hidden = false;
    }

    function clearError() {
      els.error.hidden = true;
      els.error.textContent = "";
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

    function matchesTask(task) {
      if (state.filter === "active" && task.completed) return false;
      if (state.filter === "completed" && !task.completed) return false;
      if (state.priority !== "all" && task.priority !== state.priority) return false;
      const query = state.query.trim().toLowerCase();
      if (!query) return true;
      return `${task.title} ${task.notes || ""}`.toLowerCase().includes(query);
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
      els.allCount.textContent = state.tasks.length;
      els.activeCount.textContent = active;
      els.doneCount.textContent = done;
      els.clearCompleted.disabled = done === 0;
      els.clearCompleted.classList.toggle("opacity-50", done === 0);
      els.clearCompleted.classList.toggle("cursor-not-allowed", done === 0);
    }

    function renderTabs() {
      document.querySelectorAll(".filter-tab").forEach((button) => {
        const selected = button.dataset.filter === state.filter;
        button.className = `filter-tab h-9 flex-1 rounded-md px-3 text-sm font-medium sm:flex-none ${selected ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-100"}`;
      });
    }

    function taskRow(task) {
      const checked = task.completed ? "checked" : "";
      const titleClass = task.completed ? "text-zinc-500 line-through" : "text-zinc-950";
      const priority = escapeHtml(task.priority || "medium");
      const notes = task.notes ? `<p class="mt-2 whitespace-pre-wrap break-words text-sm text-zinc-600">${escapeHtml(task.notes)}</p>` : "";
      return `
        <li class="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm" data-id="${escapeHtml(task.id)}">
          <div class="flex gap-3">
            <input type="checkbox" title="Toggle complete" class="task-toggle mt-1 h-5 w-5 rounded border-zinc-300 text-zinc-950 focus:ring-zinc-900" ${checked}>
            <div class="min-w-0 flex-1">
              <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <h3 class="break-words text-base font-semibold ${titleClass}">${escapeHtml(task.title)}</h3>
                  <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span class="inline-flex h-6 items-center rounded-md border px-2 font-semibold ${priorityClass[task.priority] || priorityClass.medium}">${priority}</span>
                    <span class="${dueClass(task)}">${escapeHtml(dueLabel(task.due_at))}</span>
                    <span class="text-zinc-400">${escapeHtml(task.state)}</span>
                  </div>
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
              ${notes}
            </div>
          </div>
        </li>
      `;
    }

    function render() {
      renderCounts();
      renderTabs();
      const visible = sortTasks(state.tasks.filter(matchesTask));
      els.list.innerHTML = visible.map(taskRow).join("");
      els.empty.hidden = visible.length > 0;
      const active = state.tasks.filter((task) => !task.completed).length;
      els.summary.textContent = `${visible.length} shown, ${active} active`;
      if (window.lucide) lucide.createIcons();
    }

    function formPayload() {
      return {
        title: els.title.value.trim(),
        priority: els.priority.value,
        due_at: els.due.value ? new Date(els.due.value).toISOString() : null,
        notes: els.notes.value.trim(),
      };
    }

    function resetForm() {
      els.form.reset();
      els.priority.value = "medium";
      els.editingId.value = "";
      els.submit.querySelector("span").textContent = "Add task";
      els.cancelEdit.hidden = true;
      if (window.lucide) lucide.createIcons();
    }

    function editTask(task) {
      els.editingId.value = task.id;
      els.title.value = task.title;
      els.priority.value = task.priority || "medium";
      els.due.value = dateForInput(task.due_at);
      els.notes.value = task.notes || "";
      els.submit.querySelector("span").textContent = "Save task";
      els.cancelEdit.hidden = false;
      els.title.focus();
      if (window.lucide) lucide.createIcons();
    }

    els.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearError();
      const id = els.editingId.value;
      const payload = formPayload();
      if (!payload.title) {
        showError("Task title is required.");
        return;
      }
      els.submit.disabled = true;
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
        els.submit.disabled = false;
      }
    });

    els.list.addEventListener("click", async (event) => {
      const row = event.target.closest("li[data-id]");
      if (!row) return;
      const task = state.tasks.find((item) => item.id === row.dataset.id);
      if (!task) return;

      if (event.target.closest(".task-edit")) {
        editTask(task);
        return;
      }

      if (event.target.closest(".task-delete")) {
        if (!confirm("Delete this task?")) return;
        clearError();
        try {
          await api(`/api/tasks/${encodeURIComponent(task.id)}`, { method: "DELETE" });
          if (els.editingId.value === task.id) resetForm();
          await loadTasks();
        } catch (error) {
          showError(error.message);
        }
      }
    });

    els.list.addEventListener("change", async (event) => {
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

    document.querySelectorAll(".filter-tab").forEach((button) => {
      button.addEventListener("click", () => {
        state.filter = button.dataset.filter;
        render();
      });
    });

    els.search.addEventListener("input", () => {
      state.query = els.search.value;
      render();
    });

    els.priorityFilter.addEventListener("change", () => {
      state.priority = els.priorityFilter.value;
      render();
    });

    els.sort.addEventListener("change", () => {
      state.sort = els.sort.value;
      render();
    });

    els.clearCompleted.addEventListener("click", async () => {
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

    els.reload.addEventListener("click", loadTasks);
    els.cancelEdit.addEventListener("click", resetForm);

    resetForm();
    loadTasks();
  </script>
</body>
</html>
"""


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect():
    return psycopg2.connect(cursor_factory=RealDictCursor)


def require_json():
    payload = bottle.request.json
    if payload is None:
        raise bottle.HTTPError(400, {"error": "Expected a JSON request body."})
    if not isinstance(payload, dict):
        raise bottle.HTTPError(400, {"error": "Expected a JSON object."})
    return payload


def json_response(payload, status=200):
    bottle.response.status = status
    bottle.response.content_type = "application/json"
    return payload


def normalize_title(value):
    title = str(value or "").strip()
    if not title:
        raise bottle.HTTPError(400, {"error": "Task title is required."})
    if len(title) > 180:
        raise bottle.HTTPError(400, {"error": "Task title must be 180 characters or less."})
    return title


def normalize_priority(value):
    priority = str(value or "medium").strip().lower()
    if priority not in PRIORITIES:
        raise bottle.HTTPError(400, {"error": "Priority must be low, medium, or high."})
    return priority


def normalize_notes(value):
    notes = str(value or "").strip()
    if len(notes) > 1200:
        raise bottle.HTTPError(400, {"error": "Notes must be 1200 characters or less."})
    return notes


def normalize_due_at(value):
    if value in (None, ""):
        return None
    due_at = str(value).strip()
    if len(due_at) > 80:
        raise bottle.HTTPError(400, {"error": "Due date is too long."})
    return due_at


def task_id_for(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:48].strip("-") or "task"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def ensure_schema(cursor):
    global _schema_ready
    if _schema_ready:
        return
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_state') THEN
                CREATE TYPE task_state AS ENUM (
                    'IDLE',
                    'WAITING',
                    'RUNNING',
                    'BLOCKED',
                    'DONE'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS workflows (
            id text PRIMARY KEY,
            display_name text,
            frozen bool NOT NULL DEFAULT FALSE,
            meta jsonb NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS tasks (
            workflow_id text NOT NULL
                REFERENCES workflows(id) ON DELETE CASCADE,
            id text NOT NULL,
            display_name text,
            python_class text,
            task_state task_state NOT NULL DEFAULT 'IDLE',
            meta jsonb NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (workflow_id, id)
        );
        """
    )
    _schema_ready = True


def ensure_workflow(cursor):
    ensure_schema(cursor)
    cursor.execute(
        """
        INSERT INTO workflows (id, display_name, meta)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            meta = workflows.meta || EXCLUDED.meta
        """,
        (
            WORKFLOW_ID,
            WORKFLOW_NAME,
            Json({"kind": "todo-list", "source": "todo_web.py"}),
        ),
    )


def row_to_task(row):
    meta = row.get("meta") or {}
    state = row.get("task_state") or "IDLE"
    priority = meta.get("priority") if meta.get("priority") in PRIORITIES else "medium"
    return {
        "id": row["id"],
        "title": row.get("display_name") or row["id"],
        "state": state,
        "completed": state == "DONE",
        "priority": priority,
        "due_at": meta.get("due_at"),
        "notes": meta.get("notes") or "",
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
    }


def fetch_task(cursor, task_id):
    cursor.execute(
        """
        SELECT id, display_name, task_state::text AS task_state, meta
        FROM tasks
        WHERE workflow_id = %s AND id = %s
        """,
        (WORKFLOW_ID, task_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise bottle.HTTPError(404, {"error": "Task not found."})
    return row


@app.error(400)
@app.error(404)
@app.error(500)
def error_json(error):
    bottle.response.content_type = "application/json"
    body = error.body
    if isinstance(body, dict):
        return body
    return {"error": str(body or error.status)}


@app.get("/")
def index():
    bottle.response.content_type = "text/html; charset=utf-8"
    return INDEX_HTML


@app.get("/api/tasks")
def list_tasks():
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                ensure_workflow(cursor)
                cursor.execute(
                    """
                    SELECT id, display_name, task_state::text AS task_state, meta
                    FROM tasks
                    WHERE workflow_id = %s
                    ORDER BY
                        task_state = 'DONE',
                        NULLIF(meta->>'due_at', '') ASC NULLS LAST,
                        CASE meta->>'priority'
                            WHEN 'high' THEN 0
                            WHEN 'medium' THEN 1
                            WHEN 'low' THEN 2
                            ELSE 3
                        END,
                        display_name
                    """,
                    (WORKFLOW_ID,),
                )
                return json_response({"tasks": [row_to_task(row) for row in cursor.fetchall()]})
    except psycopg2.Error as exc:
        raise bottle.HTTPError(500, {"error": f"Database error: {exc.pgerror or exc}"})


@app.post("/api/tasks")
def create_task():
    payload = require_json()
    title = normalize_title(payload.get("title"))
    priority = normalize_priority(payload.get("priority"))
    notes = normalize_notes(payload.get("notes"))
    due_at = normalize_due_at(payload.get("due_at"))
    stamp = now_iso()
    meta = {
        "priority": priority,
        "notes": notes,
        "created_at": stamp,
        "updated_at": stamp,
        "source": "todo_web.py",
    }
    if due_at:
        meta["due_at"] = due_at

    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                ensure_workflow(cursor)
                cursor.execute(
                    """
                    INSERT INTO tasks (
                        workflow_id,
                        id,
                        display_name,
                        python_class,
                        task_state,
                        meta
                    )
                    VALUES (%s, %s, %s, 'ManualTask', 'IDLE', %s)
                    RETURNING id, display_name, task_state::text AS task_state, meta
                    """,
                    (WORKFLOW_ID, task_id_for(title), title, Json(meta)),
                )
                return json_response({"task": row_to_task(cursor.fetchone())}, status=201)
    except psycopg2.Error as exc:
        raise bottle.HTTPError(500, {"error": f"Database error: {exc.pgerror or exc}"})


@app.patch("/api/tasks/<task_id>")
def update_task(task_id):
    payload = require_json()
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                ensure_workflow(cursor)
                row = fetch_task(cursor, task_id)
                meta = dict(row.get("meta") or {})
                title = row.get("display_name") or row["id"]
                state = row.get("task_state") or "IDLE"

                if "title" in payload:
                    title = normalize_title(payload.get("title"))
                if "priority" in payload:
                    meta["priority"] = normalize_priority(payload.get("priority"))
                if "notes" in payload:
                    meta["notes"] = normalize_notes(payload.get("notes"))
                if "due_at" in payload:
                    due_at = normalize_due_at(payload.get("due_at"))
                    if due_at:
                        meta["due_at"] = due_at
                    else:
                        meta.pop("due_at", None)
                if "completed" in payload:
                    state = "DONE" if bool(payload.get("completed")) else "IDLE"
                if "state" in payload:
                    requested_state = str(payload.get("state") or "").upper()
                    if requested_state not in TASK_STATES:
                        raise bottle.HTTPError(400, {"error": "Invalid task state."})
                    state = requested_state

                meta["updated_at"] = now_iso()
                cursor.execute(
                    """
                    UPDATE tasks
                    SET display_name = %s,
                        task_state = %s::task_state,
                        meta = %s
                    WHERE workflow_id = %s AND id = %s
                    RETURNING id, display_name, task_state::text AS task_state, meta
                    """,
                    (title, state, Json(meta), WORKFLOW_ID, task_id),
                )
                return json_response({"task": row_to_task(cursor.fetchone())})
    except psycopg2.Error as exc:
        raise bottle.HTTPError(500, {"error": f"Database error: {exc.pgerror or exc}"})


@app.delete("/api/tasks/<task_id>")
def delete_task(task_id):
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                ensure_workflow(cursor)
                cursor.execute(
                    """
                    DELETE FROM tasks
                    WHERE workflow_id = %s AND id = %s
                    RETURNING id
                    """,
                    (WORKFLOW_ID, task_id),
                )
                if cursor.fetchone() is None:
                    raise bottle.HTTPError(404, {"error": "Task not found."})
                return json_response({"deleted": task_id})
    except psycopg2.Error as exc:
        raise bottle.HTTPError(500, {"error": f"Database error: {exc.pgerror or exc}"})


@app.post("/api/tasks/clear-completed")
def clear_completed():
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                ensure_workflow(cursor)
                cursor.execute(
                    """
                    DELETE FROM tasks
                    WHERE workflow_id = %s AND task_state = 'DONE'
                    RETURNING id
                    """,
                    (WORKFLOW_ID,),
                )
                deleted = [row["id"] for row in cursor.fetchall()]
                return json_response({"deleted": deleted})
    except psycopg2.Error as exc:
        raise bottle.HTTPError(500, {"error": f"Database error: {exc.pgerror or exc}"})


def main():
    host = os.environ.get("TODO_HOST", "127.0.0.1")
    port = int(os.environ.get("TODO_PORT", "8080"))
    bottle.run(app=app, host=host, port=port, debug=True, reloader=False)


if __name__ == "__main__":
    main()
