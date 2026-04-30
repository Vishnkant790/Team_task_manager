Team Task Manager

Live Application URL:
teamtaskmanager-production-6d1b.up.railway.app

GitHub Repository:
https://github.com/Vishnkant790/Team_task_manager

Overview:
Team Task Manager is a full-stack web application where users can signup, login, create projects, add team members, assign tasks, and track progress. It includes REST APIs, SQL database relationships, validations, authentication, and role-based access control.

Tech Stack:
- Python backend
- REST APIs
- SQLite for local development
- PostgreSQL on Railway using DATABASE_URL
- HTML, CSS, JavaScript frontend
- PBKDF2 password hashing
- Database-backed sessions

Features:
- Signup and login
- Project creation and management
- Team member management
- Admin and Member roles
- Task creation and assignment
- Task status tracking: TODO, IN_PROGRESS, DONE
- Dashboard with total, completed, assigned, and overdue tasks

Role-Based Access Control:
- Project creator becomes Admin.
- Admin can add members, create tasks, assign tasks, update tasks, and delete tasks.
- Member can view project tasks and update status only for assigned tasks.

Run Locally:
1. Open PyCharm.
2. Open the team-task-manager folder.
3. Open terminal in PyCharm.
4. Run:
   python server.py
5. Open:
   http://127.0.0.1:8000

Local database file:
   data/team_task_manager.db

Optional Smoke Test:
Run:
   python scripts/smoke_test.py

Railway Deployment:
1. Push this folder to GitHub.
2. Create a new Railway project from the GitHub repo.
3. Add a PostgreSQL database service.
4. Set app service variables:
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   COOKIE_SECURE=1
5. Deploy and open the Railway live URL.

Important API Routes:
POST /api/auth/signup
POST /api/auth/login
POST /api/auth/logout
GET /api/me
GET /api/dashboard
GET /api/projects
POST /api/projects
GET /api/projects/:id
POST /api/projects/:id/members
GET /api/projects/:id/tasks
POST /api/projects/:id/tasks
PATCH /api/tasks/:id
DELETE /api/tasks/:id


