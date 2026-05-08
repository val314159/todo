from datetime import datetime, timedelta, timezone

from utils import *


WORKFLOW_ID = "personal_todo_list"
WORKFLOW_NAME = "personal TODO list"


def build_tasks():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return [
        {
            "id": "morning-reset",
            "display_name": "Morning reset: inbox zero, desk clear, plan the day",
            "python_class": "ManualTask",
            "meta": task_meta(
                now + timedelta(hours=16),
                "high",
                "Start with a clean surface and a short written plan.",
            ),
        },
        {
            "id": "ship-one-useful-thing",
            "display_name": "Ship one useful thing before lunch",
            "python_class": "ManualTask",
            "meta": task_meta(
                now + timedelta(days=1, hours=4),
                "high",
                "Small is fine; merged, sent, posted, or otherwise real.",
            ),
        },
        {
            "id": "deep-clean-downloads",
            "display_name": "Delete the ancient stuff in Downloads",
            "python_class": "ManualTask",
            "meta": task_meta(
                now + timedelta(days=2, hours=1),
                "medium",
                "Archive anything important, then be ruthless.",
            ),
        },
        {
            "id": "cook-something-new",
            "display_name": "Cook something new and actually write down the recipe",
            "python_class": "ManualTask",
            "meta": task_meta(
                now + timedelta(days=3, hours=2),
                "medium",
                "Bonus points for something freezer-friendly.",
            ),
        },
        {
            "id": "future-self-note",
            "display_name": "Write a note that future you will be glad exists",
            "python_class": "ManualTask",
            "meta": task_meta(
                now + timedelta(days=5),
                "low",
                "Document one setup, decision, or recurring pain point.",
            ),
        },
    ]


def main():
    tasks = build_tasks()
    with psycopg2.connect() as conn:
        with conn.cursor() as cursor:
            upsert_workflow(cursor,
                            WORKFLOW_ID,
                            WORKFLOW_NAME)
            upsert_tasks(cursor, WORKFLOW_ID, tasks)
            print_workflow(cursor, WORKFLOW_ID)


if __name__ == "__main__":
    main()
