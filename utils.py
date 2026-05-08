import psycopg2
from psycopg2.extras import Json


def task_meta(due_at, priority, notes):
    return {
        "due_at": due_at.isoformat(),
        "priority": priority,
        "notes": notes,
    }


def upsert_workflow(cursor, workflow_id, workflow_name):
    cursor.execute(
        """
        INSERT INTO workflows (id, display_name, meta)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            meta = workflows.meta || EXCLUDED.meta
        """,
        (
            workflow_id, workflow_name,
            Json({"kind": "todo-list", "source": "create_todo_list.py"}),
        ),
    )


def upsert_tasks(cursor, workflow_id, tasks):
    for task in tasks:
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
            VALUES (%s, %s, %s, %s, 'IDLE', %s)
            ON CONFLICT (workflow_id, id) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                python_class = EXCLUDED.python_class,
                meta = tasks.meta || EXCLUDED.meta
            """,
            (
                workflow_id,
                task["id"],
                task["display_name"],
                task["python_class"],
                Json(task["meta"]),
            ),
        )


def print_workflow(cursor, workflow_id):
    cursor.execute(
        """
        SELECT id, display_name
        FROM workflows
        WHERE id = %s
        """,
        (workflow_id,)
    )
    workflow_id, display_name = cursor.fetchone()
    print(f"workflow: {workflow_id} ({display_name})")

    cursor.execute(
        """
        SELECT id, display_name, task_state, meta->>'due_at' AS due_at
        FROM tasks
        WHERE workflow_id = %s
        ORDER BY meta->>'due_at', id
        """, 
        (workflow_id,)
    )
    for task_id, display_name, task_state, due_at in cursor.fetchall():
        print(f"- {task_id}: {display_name}")
        print(f"  state: {task_state}  due: {due_at}")
