# Team Task Manager

A full-stack web app for managing projects, team members, task assignment, status tracking, and overdue work. It includes REST APIs, SQL database relationships, authentication, and role-based access control.

## Tech Stack

- Python HTTP server for backend APIs and frontend serving
- SQLite for local development
- PostgreSQL on Railway through `DATABASE_URL`
- Vanilla HTML, CSS, and JavaScript frontend
- Secure password hashing with PBKDF2
- Cookie-based sessions stored in the database

## Features

- Signup and login
- Project creation
- Project team members with `ADMIN` and `MEMBER` roles
- Task creation, assignment, due dates, priority, and status
- Dashboard with total tasks, completed tasks, overdue tasks, and upcoming work
- REST API endpoints for auth, projects, members, tasks, and dashboard

## Run Locally in PyCharm

1. Open PyCharm.
2. Select `File > Open`.
3. Open this folder:

   `team-task-manager`

4. Choose your Python interpreter.
5. Open the PyCharm terminal and run:

   ```bash
   python server.py
   ```

6. Open:

   `http://127.0.0.1:8000`

The app will create a local `data/team_task_manager.db` SQLite database automatically.

Optional smoke test:

```bash
python scripts/smoke_test.py
```

## Railway Deployment

1. Push this project to GitHub.
2. Open Railway and create a new project from the GitHub repo.
3. Add a PostgreSQL database service.
4. In the app service variables, set:

   ```txt
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   COOKIE_SECURE=1
   ```

5. Railway will use `python server.py` as the start command.
6. Open the generated Railway domain and test signup/login.

## Main API Routes

```txt
POST   /api/auth/signup
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/me
GET    /api/dashboard
GET    /api/projects
POST   /api/projects
GET    /api/projects/:id
PATCH  /api/projects/:id
DELETE /api/projects/:id
POST   /api/projects/:id/members
GET    /api/projects/:id/tasks
POST   /api/projects/:id/tasks
PATCH  /api/tasks/:id
DELETE /api/tasks/:id
```

## Role-Based Access

- The user who creates a project becomes `ADMIN`.
- `ADMIN` can add members, create tasks, assign tasks, update tasks, and delete tasks.
- `MEMBER` can view project tasks and update status only for tasks assigned to them.

