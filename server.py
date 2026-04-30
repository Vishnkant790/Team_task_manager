import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from teamtask import db
from teamtask.config import COOKIE_SECURE, PORT, STATIC_DIR, TEMPLATE_DIR
from teamtask.security import (
    expires_iso,
    hash_password,
    is_valid_email,
    make_session_token,
    new_id,
    normalize_email,
    now_iso,
    today_iso,
    validate_due_date,
    verify_password,
)


VALID_STATUSES = {"TODO", "IN_PROGRESS", "DONE"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH"}
VALID_ROLES = {"ADMIN", "MEMBER"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class TeamTaskHandler(BaseHTTPRequestHandler):
    server_version = "TeamTaskManager/1.0"

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_PATCH(self):
        self.route()

    def do_DELETE(self):
        self.route()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/health":
                return self.send_json(HTTPStatus.OK, {"ok": True})
            if path.startswith("/static/"):
                return self.serve_static(path)
            if path == "/" and self.command == "GET":
                return self.serve_index()
            if not path.startswith("/api/"):
                return self.serve_index()

            if path == "/api/auth/signup" and self.command == "POST":
                return self.signup()
            if path == "/api/auth/login" and self.command == "POST":
                return self.login()
            if path == "/api/auth/logout" and self.command == "POST":
                return self.logout()
            if path == "/api/me" and self.command == "GET":
                return self.me()
            if path == "/api/dashboard" and self.command == "GET":
                return self.dashboard()
            if path == "/api/projects":
                if self.command == "GET":
                    return self.list_projects()
                if self.command == "POST":
                    return self.create_project()

            project_members_match = re.fullmatch(r"/api/projects/([^/]+)/members", path)
            if project_members_match and self.command == "POST":
                return self.add_member(project_members_match.group(1))

            project_tasks_match = re.fullmatch(r"/api/projects/([^/]+)/tasks", path)
            if project_tasks_match:
                if self.command == "GET":
                    return self.list_tasks(project_tasks_match.group(1))
                if self.command == "POST":
                    return self.create_task(project_tasks_match.group(1))

            project_match = re.fullmatch(r"/api/projects/([^/]+)", path)
            if project_match:
                project_id = project_match.group(1)
                if self.command == "GET":
                    return self.project_detail(project_id)
                if self.command == "PATCH":
                    return self.update_project(project_id)
                if self.command == "DELETE":
                    return self.delete_project(project_id)

            task_match = re.fullmatch(r"/api/tasks/([^/]+)", path)
            if task_match:
                task_id = task_match.group(1)
                if self.command == "PATCH":
                    return self.update_task(task_id)
                if self.command == "DELETE":
                    return self.delete_task(task_id)

            raise ApiError(HTTPStatus.NOT_FOUND, "Route not found.")
        except ApiError as exc:
            self.send_json(exc.status, {"error": exc.message})
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body."})
        except Exception as exc:
            print("Unhandled error:", repr(exc))
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Server error."})

    def serve_index(self):
        body = (TEMPLATE_DIR / "index.html").read_bytes()
        self.send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def serve_static(self, path: str):
        rel = unquote(path.removeprefix("/static/"))
        target = (STATIC_DIR / rel).resolve()
        static_root = STATIC_DIR.resolve()
        if target != static_root and static_root not in target.parents:
            raise ApiError(HTTPStatus.FORBIDDEN, "Invalid static path.")
        if not target.exists() or not target.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Static file not found.")
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_bytes(HTTPStatus.OK, target.read_bytes(), content_type)

    def send_bytes(self, status: int, body: bytes, content_type: str, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload, headers=None):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        final_headers = {"Cache-Control": "no-store"}
        if headers:
            final_headers.update(headers)
        self.send_bytes(status, body, "application/json; charset=utf-8", final_headers)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def cookie_header(self, token: str, max_age: int) -> str:
        secure = "; Secure" if COOKIE_SECURE else ""
        return f"session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}"

    def get_cookie(self, name: str):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "=" not in part:
                continue
            key, value = part.strip().split("=", 1)
            if key == name:
                return value
        return None

    def current_user(self, conn):
        token = self.get_cookie("session")
        if not token:
            return None
        session = db.fetch_one(
            conn,
            """
            SELECT s.token, s.expires_at, u.id, u.name, u.email, u.created_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        )
        if not session:
            return None
        if session["expires_at"] < now_iso():
            db.execute(conn, "DELETE FROM sessions WHERE token = ?", (token,))
            return None
        return {
            "id": session["id"],
            "name": session["name"],
            "email": session["email"],
            "created_at": session["created_at"],
        }

    def require_user(self, conn):
        user = self.current_user(conn)
        if not user:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Please login first.")
        return user

    def create_session(self, conn, user_id: str) -> str:
        token = make_session_token()
        db.execute(
            conn,
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now_iso(), expires_iso()),
        )
        return token

    def signup(self):
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        email = normalize_email(payload.get("email", ""))
        password = payload.get("password") or ""
        if len(name) < 2:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Name must be at least 2 characters.")
        if not is_valid_email(email):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid email.")
        if len(password) < 6:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Password must be at least 6 characters.")

        with db.connection() as conn:
            existing = db.fetch_one(conn, "SELECT id FROM users WHERE email = ?", (email,))
            if existing:
                raise ApiError(HTTPStatus.CONFLICT, "Email already registered.")
            user_id = new_id()
            db.execute(
                conn,
                "INSERT INTO users (id, name, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, email, hash_password(password), now_iso()),
            )
            token = self.create_session(conn, user_id)
            user = {"id": user_id, "name": name, "email": email}
        self.send_json(HTTPStatus.CREATED, {"user": user}, {"Set-Cookie": self.cookie_header(token, 604800)})

    def login(self):
        payload = self.read_json()
        email = normalize_email(payload.get("email", ""))
        password = payload.get("password") or ""
        with db.connection() as conn:
            user = db.fetch_one(conn, "SELECT * FROM users WHERE email = ?", (email,))
            if not user or not verify_password(password, user["password_hash"]):
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Invalid email or password.")
            token = self.create_session(conn, user["id"])
            body = {"user": {"id": user["id"], "name": user["name"], "email": user["email"]}}
        self.send_json(HTTPStatus.OK, body, {"Set-Cookie": self.cookie_header(token, 604800)})

    def logout(self):
        with db.connection() as conn:
            token = self.get_cookie("session")
            if token:
                db.execute(conn, "DELETE FROM sessions WHERE token = ?", (token,))
        self.send_json(HTTPStatus.OK, {"ok": True}, {"Set-Cookie": self.cookie_header("", 0)})

    def me(self):
        with db.connection() as conn:
            user = self.current_user(conn)
        self.send_json(HTTPStatus.OK, {"user": user})

    def dashboard(self):
        with db.connection() as conn:
            user = self.require_user(conn)
            projects = db.fetch_all(
                conn,
                """
                SELECT p.id, p.name, pm.role
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.id
                WHERE pm.user_id = ?
                ORDER BY p.created_at DESC
                """,
                (user["id"],),
            )
            tasks = db.fetch_all(
                conn,
                """
                SELECT t.*, p.name AS project_name, u.name AS assignee_name
                FROM tasks t
                JOIN projects p ON p.id = t.project_id
                JOIN project_members pm ON pm.project_id = t.project_id
                LEFT JOIN users u ON u.id = t.assignee_id
                WHERE pm.user_id = ?
                ORDER BY t.due_date ASC, t.created_at DESC
                """,
                (user["id"],),
            )
        today = today_iso()
        summary = {
            "projects": len(projects),
            "tasks": len(tasks),
            "todo": sum(1 for task in tasks if task["status"] == "TODO"),
            "in_progress": sum(1 for task in tasks if task["status"] == "IN_PROGRESS"),
            "done": sum(1 for task in tasks if task["status"] == "DONE"),
            "overdue": sum(1 for task in tasks if task["status"] != "DONE" and task["due_date"] < today),
            "assigned_to_me": sum(1 for task in tasks if task["assignee_id"] == user["id"]),
        }
        for task in tasks:
            task["overdue"] = task["status"] != "DONE" and task["due_date"] < today
        self.send_json(HTTPStatus.OK, {"summary": summary, "projects": projects, "upcoming": tasks[:8]})

    def list_projects(self):
        with db.connection() as conn:
            user = self.require_user(conn)
            projects = db.fetch_all(
                conn,
                """
                SELECT
                    p.id, p.name, p.description, p.owner_id, p.created_at,
                    pm.role,
                    owner.name AS owner_name,
                    (SELECT COUNT(*) FROM project_members m WHERE m.project_id = p.id) AS member_count,
                    (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id) AS task_count
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.id
                JOIN users owner ON owner.id = p.owner_id
                WHERE pm.user_id = ?
                ORDER BY p.created_at DESC
                """,
                (user["id"],),
            )
        self.send_json(HTTPStatus.OK, {"projects": projects})

    def create_project(self):
        payload = self.read_json()
        name = (payload.get("name") or "").strip()
        description = (payload.get("description") or "").strip()
        if len(name) < 3:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Project name must be at least 3 characters.")
        with db.connection() as conn:
            user = self.require_user(conn)
            project_id = new_id()
            db.execute(
                conn,
                "INSERT INTO projects (id, name, description, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, name, description, user["id"], now_iso()),
            )
            db.execute(
                conn,
                """
                INSERT INTO project_members (id, project_id, user_id, role, created_at)
                VALUES (?, ?, ?, 'ADMIN', ?)
                """,
                (new_id(), project_id, user["id"], now_iso()),
            )
            project = self.get_project(conn, project_id, user["id"])
        self.send_json(HTTPStatus.CREATED, {"project": project})

    def get_project(self, conn, project_id: str, user_id: str):
        project = db.fetch_one(
            conn,
            """
            SELECT p.*, pm.role, owner.name AS owner_name
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.id
            JOIN users owner ON owner.id = p.owner_id
            WHERE p.id = ? AND pm.user_id = ?
            """,
            (project_id, user_id),
        )
        if not project:
            raise ApiError(HTTPStatus.NOT_FOUND, "Project not found.")
        return project

    def project_detail(self, project_id: str):
        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            members = self.project_members(conn, project_id)
            tasks = self.project_tasks(conn, project_id)
        self.send_json(HTTPStatus.OK, {"project": project, "members": members, "tasks": self.decorate_tasks(tasks, user, project)})

    def update_project(self, project_id: str):
        payload = self.read_json()
        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            self.require_admin(project)
            name = (payload.get("name") or project["name"]).strip()
            description = (payload.get("description") if payload.get("description") is not None else project["description"]).strip()
            if len(name) < 3:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Project name must be at least 3 characters.")
            db.execute(
                conn,
                "UPDATE projects SET name = ?, description = ? WHERE id = ?",
                (name, description, project_id),
            )
            project = self.get_project(conn, project_id, user["id"])
        self.send_json(HTTPStatus.OK, {"project": project})

    def delete_project(self, project_id: str):
        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            self.require_admin(project)
            db.execute(conn, "DELETE FROM projects WHERE id = ?", (project_id,))
        self.send_json(HTTPStatus.OK, {"ok": True})

    def add_member(self, project_id: str):
        payload = self.read_json()
        email = normalize_email(payload.get("email", ""))
        role = (payload.get("role") or "MEMBER").strip().upper()
        if not is_valid_email(email):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Enter a valid member email.")
        if role not in VALID_ROLES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Role must be ADMIN or MEMBER.")
        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            self.require_admin(project)
            member_user = db.fetch_one(conn, "SELECT id, name, email FROM users WHERE email = ?", (email,))
            if not member_user:
                raise ApiError(HTTPStatus.NOT_FOUND, "User must signup before being added.")
            existing = db.fetch_one(
                conn,
                "SELECT id FROM project_members WHERE project_id = ? AND user_id = ?",
                (project_id, member_user["id"]),
            )
            if existing:
                raise ApiError(HTTPStatus.CONFLICT, "User is already in this project.")
            db.execute(
                conn,
                """
                INSERT INTO project_members (id, project_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_id(), project_id, member_user["id"], role, now_iso()),
            )
            members = self.project_members(conn, project_id)
        self.send_json(HTTPStatus.CREATED, {"members": members})

    def list_tasks(self, project_id: str):
        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            tasks = self.project_tasks(conn, project_id)
        self.send_json(HTTPStatus.OK, {"tasks": self.decorate_tasks(tasks, user, project)})

    def create_task(self, project_id: str):
        payload = self.read_json()
        title = (payload.get("title") or "").strip()
        description = (payload.get("description") or "").strip()
        status = (payload.get("status") or "TODO").strip().upper()
        priority = (payload.get("priority") or "MEDIUM").strip().upper()
        assignee_id = (payload.get("assignee_id") or "").strip() or None
        if len(title) < 3:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Task title must be at least 3 characters.")
        if status not in VALID_STATUSES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid task status.")
        if priority not in VALID_PRIORITIES:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid task priority.")
        try:
            due_date = validate_due_date(payload.get("due_date") or "")
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc

        with db.connection() as conn:
            user = self.require_user(conn)
            project = self.get_project(conn, project_id, user["id"])
            self.require_admin(project)
            if assignee_id:
                self.require_project_member(conn, project_id, assignee_id)
            task_id = new_id()
            timestamp = now_iso()
            db.execute(
                conn,
                """
                INSERT INTO tasks
                (id, project_id, title, description, status, priority, due_date, assignee_id, created_by_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, project_id, title, description, status, priority, due_date, assignee_id, user["id"], timestamp, timestamp),
            )
            tasks = self.project_tasks(conn, project_id)
        self.send_json(HTTPStatus.CREATED, {"tasks": self.decorate_tasks(tasks, user, project)})

    def update_task(self, task_id: str):
        payload = self.read_json()
        with db.connection() as conn:
            user = self.require_user(conn)
            task = self.task_with_membership(conn, task_id, user["id"])
            if not task:
                raise ApiError(HTTPStatus.NOT_FOUND, "Task not found.")
            is_admin = task["role"] == "ADMIN"
            is_assignee = task["assignee_id"] == user["id"]
            if not is_admin and not is_assignee:
                raise ApiError(HTTPStatus.FORBIDDEN, "Only admins or the assigned member can update this task.")

            allowed = {"status"} if not is_admin else {"title", "description", "status", "priority", "due_date", "assignee_id"}
            incoming_keys = {key for key in payload.keys() if key in {"title", "description", "status", "priority", "due_date", "assignee_id"}}
            blocked = incoming_keys - allowed
            if blocked:
                raise ApiError(HTTPStatus.FORBIDDEN, "Members can update only their task status.")

            updates = []
            values = []
            if "title" in allowed and "title" in payload:
                title = (payload.get("title") or "").strip()
                if len(title) < 3:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Task title must be at least 3 characters.")
                updates.append("title = ?")
                values.append(title)
            if "description" in allowed and "description" in payload:
                updates.append("description = ?")
                values.append((payload.get("description") or "").strip())
            if "status" in payload:
                status = (payload.get("status") or "").strip().upper()
                if status not in VALID_STATUSES:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid task status.")
                updates.append("status = ?")
                values.append(status)
            if "priority" in allowed and "priority" in payload:
                priority = (payload.get("priority") or "").strip().upper()
                if priority not in VALID_PRIORITIES:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid task priority.")
                updates.append("priority = ?")
                values.append(priority)
            if "due_date" in allowed and "due_date" in payload:
                try:
                    due_date = validate_due_date(payload.get("due_date") or "")
                except ValueError as exc:
                    raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                updates.append("due_date = ?")
                values.append(due_date)
            if "assignee_id" in allowed and "assignee_id" in payload:
                assignee_id = (payload.get("assignee_id") or "").strip() or None
                if assignee_id:
                    self.require_project_member(conn, task["project_id"], assignee_id)
                updates.append("assignee_id = ?")
                values.append(assignee_id)
            if not updates:
                raise ApiError(HTTPStatus.BAD_REQUEST, "No valid fields to update.")
            updates.append("updated_at = ?")
            values.append(now_iso())
            values.append(task_id)
            db.execute(conn, f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values)
            project = self.get_project(conn, task["project_id"], user["id"])
            tasks = self.project_tasks(conn, task["project_id"])
        self.send_json(HTTPStatus.OK, {"tasks": self.decorate_tasks(tasks, user, project)})

    def delete_task(self, task_id: str):
        with db.connection() as conn:
            user = self.require_user(conn)
            task = self.task_with_membership(conn, task_id, user["id"])
            if not task:
                raise ApiError(HTTPStatus.NOT_FOUND, "Task not found.")
            if task["role"] != "ADMIN":
                raise ApiError(HTTPStatus.FORBIDDEN, "Only project admins can delete tasks.")
            db.execute(conn, "DELETE FROM tasks WHERE id = ?", (task_id,))
        self.send_json(HTTPStatus.OK, {"ok": True})

    def project_members(self, conn, project_id: str):
        return db.fetch_all(
            conn,
            """
            SELECT u.id, u.name, u.email, pm.role
            FROM project_members pm
            JOIN users u ON u.id = pm.user_id
            WHERE pm.project_id = ?
            ORDER BY pm.role ASC, u.name ASC
            """,
            (project_id,),
        )

    def project_tasks(self, conn, project_id: str):
        return db.fetch_all(
            conn,
            """
            SELECT
                t.*,
                assignee.name AS assignee_name,
                assignee.email AS assignee_email,
                creator.name AS created_by_name
            FROM tasks t
            LEFT JOIN users assignee ON assignee.id = t.assignee_id
            JOIN users creator ON creator.id = t.created_by_id
            WHERE t.project_id = ?
            ORDER BY
                CASE t.status WHEN 'TODO' THEN 1 WHEN 'IN_PROGRESS' THEN 2 ELSE 3 END,
                t.due_date ASC,
                t.created_at DESC
            """,
            (project_id,),
        )

    def decorate_tasks(self, tasks, user, project):
        today = today_iso()
        is_admin = project["role"] == "ADMIN"
        for task in tasks:
            task["overdue"] = task["status"] != "DONE" and task["due_date"] < today
            task["can_update"] = is_admin or task["assignee_id"] == user["id"]
            task["can_delete"] = is_admin
        return tasks

    def task_with_membership(self, conn, task_id: str, user_id: str):
        return db.fetch_one(
            conn,
            """
            SELECT t.*, pm.role
            FROM tasks t
            JOIN project_members pm ON pm.project_id = t.project_id
            WHERE t.id = ? AND pm.user_id = ?
            """,
            (task_id, user_id),
        )

    def require_project_member(self, conn, project_id: str, user_id: str):
        member = db.fetch_one(
            conn,
            "SELECT id FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        )
        if not member:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Assignee must be a member of this project.")
        return member

    def require_admin(self, project):
        if project["role"] != "ADMIN":
            raise ApiError(HTTPStatus.FORBIDDEN, "Admin role required.")


def main():
    db.init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), TeamTaskHandler)
    print(f"Team Task Manager running on http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()

