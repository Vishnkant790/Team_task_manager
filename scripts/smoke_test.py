import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PORT = "8123"
BASE_URL = f"http://127.0.0.1:{PORT}"


def make_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def request(opener, method, path, payload=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    with opener.open(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server():
    opener = make_opener()
    last_error = None
    for _ in range(40):
        try:
            return request(opener, "GET", "/health")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Server did not start: {last_error}")


def main():
    env = os.environ.copy()
    env["PORT"] = PORT
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SQLITE_PATH"] = str(ROOT / f"smoke_test_{uuid.uuid4().hex}.db")
    env.pop("DATABASE_URL", None)

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-B", "server.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        wait_for_server()
        suffix = uuid.uuid4().hex[:8]
        admin_email = f"admin-{suffix}@example.com"
        member_email = f"member-{suffix}@example.com"
        admin_client = make_opener()
        member_client = make_opener()

        admin = request(
            admin_client,
            "POST",
            "/api/auth/signup",
            {"name": "Admin User", "email": admin_email, "password": "password123"},
        )
        member = request(
            member_client,
            "POST",
            "/api/auth/signup",
            {"name": "Member User", "email": member_email, "password": "password123"},
        )
        project = request(
            admin_client,
            "POST",
            "/api/projects",
            {"name": "Demo Project", "description": "Smoke test project"},
        )
        project_id = project["project"]["id"]
        members = request(
            admin_client,
            "POST",
            f"/api/projects/{project_id}/members",
            {"email": member_email, "role": "MEMBER"},
        )
        tasks = request(
            admin_client,
            "POST",
            f"/api/projects/{project_id}/tasks",
            {
                "title": "Prepare demo video",
                "description": "Show auth, roles, tasks, dashboard",
                "assignee_id": member["user"]["id"],
                "due_date": "2026-05-02",
                "priority": "HIGH",
                "status": "TODO",
            },
        )
        task_id = tasks["tasks"][0]["id"]
        updated = request(member_client, "PATCH", f"/api/tasks/{task_id}", {"status": "IN_PROGRESS"})
        dashboard = request(admin_client, "GET", "/api/dashboard")

        print(
            json.dumps(
                {
                    "ok": True,
                    "admin": admin["user"]["email"],
                    "member": member["user"]["email"],
                    "project": project["project"]["name"],
                    "member_count": len(members["members"]),
                    "task_status": updated["tasks"][0]["status"],
                    "dashboard_tasks": dashboard["summary"]["tasks"],
                },
                indent=2,
            )
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()

