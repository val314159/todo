import os
import re
import uuid
from datetime import datetime, timezone

import bottle
import psycopg2
from psycopg2.extras import Json, RealDictCursor


ROOTPATH = os.getenv("ROOTPATH", "./public")

WORKFLOW_ID = os.environ.get("TODO_WORKFLOW_ID", "personal_todo_list")
WORKFLOW_NAME = os.environ.get("TODO_WORKFLOW_NAME", "personal TODO list")
PRIORITIES = ("low", "medium", "high")
TASK_STATES = ("IDLE", "WAITING", "RUNNING", "BLOCKED", "DONE")

app = bottle.Bottle()


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


def ensure_workflow(cursor):
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
@app.get("/<path:path>")
def index(path='index.html'):
    return bottle.static_file(path=ROOTPATH)


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
    bottle.run(app=app, host=host, port=port, debug=True, reloader=False)


if __name__ == "__main__":
    main()
