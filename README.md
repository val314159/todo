# Todo

A small Bottle web app for the local Postgres-backed todo workflow.

Run it with:

```bash
make web
```

Then open:

```text
http://127.0.0.1:8080
```

The app uses the existing `workflows` and `tasks` tables, creates the todo
workflow row if needed, and stores todo fields in `tasks.meta`.
