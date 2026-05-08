import os

import psycopg2
from psycopg2 import sql, connect


TABLES = ("workflows", "tasks", "relations", "jobs")


def fetch_one(cursor, query, params=None):
    cursor.execute(query, params or ())
    return cursor.fetchone()


def table_exists(cursor, table_name):
    exists, = fetch_one(
        cursor,
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    return exists


def count_table(cursor, table_name):
    cursor.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name))
    )
    count, = cursor.fetchone()
    return count


def print_rows(cursor, title, query, limit=5):
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    print(f"\n{title}:")
    if not rows:
        print("  none")
        return
    for row in rows:
        print(" ", row)


def main():
    with connect() as conn:
        with conn.cursor() as cursor:
            db, user, server = fetch_one(
                cursor,
                "SELECT current_database(), current_user, version()",
            )
            print(f"database: {db}")
            print(f"user:     {user}")
            print(f"server:   {server}")

            print("\ntables:")
            for table_name in TABLES:
                if table_exists(cursor, table_name):
                    print(f"  {table_name}: {count_table(cursor, table_name)} rows")
                else:
                    print(f"  {table_name}: missing")

            if table_exists(cursor, "workflows"):
                print_rows(
                    cursor,
                    "recent workflows",
                    """
                    SELECT id, display_name, frozen, meta
                    FROM workflows
                    ORDER BY id
                    LIMIT %s
                    """,
                )

            if table_exists(cursor, "tasks"):
                print_rows(
                    cursor,
                    "recent tasks",
                    """
                    SELECT workflow_id, id, display_name, task_state, meta
                    FROM tasks
                    ORDER BY workflow_id, id
                    LIMIT %s
                    """,
                )


if __name__ == "__main__":
    main()
