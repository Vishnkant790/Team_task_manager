const app = document.querySelector("#app");

const state = {
  user: null,
  projects: [],
  selectedProjectId: null,
  selectedProject: null,
  members: [],
  tasks: [],
  dashboard: null,
  view: "dashboard",
};

function statusText(status) {
  return {
    TODO: "Todo",
    IN_PROGRESS: "In Progress",
    DONE: "Done",
  }[status] || status;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || "Request failed");
  }
  return body;
}

function setError(message) {
  const errorBox = document.querySelector("[data-error]");
  if (!errorBox) return;
  errorBox.textContent = message || "";
  errorBox.classList.toggle("show", Boolean(message));
}

async function boot() {
  const { user } = await api("/api/me");
  state.user = user;
  if (!user) {
    renderAuth();
    return;
  }
  await loadAppData();
  renderApp();
}

function renderAuth(mode = "login") {
  app.innerHTML = `
    <section class="auth-layout">
      <div class="auth-card">
        <div class="brand">
          <h1>Team Task Manager</h1>
          <p>Projects, team roles, assignments, and progress in one workspace.</p>
        </div>
        <div class="tabs">
          <button class="tab ${mode === "login" ? "active" : ""}" data-auth-tab="login">Login</button>
          <button class="tab ${mode === "signup" ? "active" : ""}" data-auth-tab="signup">Signup</button>
        </div>
        <p class="error" data-error></p>
        <form class="form" data-auth-form>
          ${mode === "signup" ? `
            <label class="field">
              <span>Name</span>
              <input name="name" autocomplete="name" required minlength="2">
            </label>
          ` : ""}
          <label class="field">
            <span>Email</span>
            <input name="email" type="email" autocomplete="email" required>
          </label>
          <label class="field">
            <span>Password</span>
            <input name="password" type="password" autocomplete="${mode === "login" ? "current-password" : "new-password"}" required minlength="6">
          </label>
          <button class="btn" type="submit">${mode === "login" ? "Login" : "Create Account"}</button>
        </form>
      </div>
    </section>
  `;

  document.querySelectorAll("[data-auth-tab]").forEach((button) => {
    button.addEventListener("click", () => renderAuth(button.dataset.authTab));
  });

  document.querySelector("[data-auth-form]").addEventListener("submit", async (event) => {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/signup";
      const { user } = await api(endpoint, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.user = user;
      await loadAppData();
      renderApp();
    } catch (error) {
      setError(error.message);
    }
  });
}

async function loadAppData() {
  const [dashboard, projects] = await Promise.all([
    api("/api/dashboard"),
    api("/api/projects"),
  ]);
  state.dashboard = dashboard;
  state.projects = projects.projects;
  if (!state.selectedProjectId && state.projects.length) {
    state.selectedProjectId = state.projects[0].id;
  }
  if (state.selectedProjectId) {
    await loadProject(state.selectedProjectId);
  }
}

async function loadProject(projectId) {
  const detail = await api(`/api/projects/${projectId}`);
  state.selectedProjectId = projectId;
  state.selectedProject = detail.project;
  state.members = detail.members;
  state.tasks = detail.tasks;
}

function renderApp() {
  app.innerHTML = `
    <section class="layout">
      <aside class="sidebar">
        <h1>Team Task Manager</h1>
        <p>Role-based project execution</p>
        <div class="sidebar-actions">
          <button class="nav-btn ${state.view === "dashboard" ? "active" : ""}" data-view="dashboard">Dashboard</button>
          <button class="nav-btn ${state.view === "projects" ? "active" : ""}" data-view="projects">Projects</button>
        </div>
        <div class="user-box">
          <strong>${escapeHtml(state.user.name)}</strong>
          <span>${escapeHtml(state.user.email)}</span>
          <button class="btn secondary small" data-logout style="margin-top: 14px;">Logout</button>
        </div>
      </aside>
      <section class="content">
        ${state.view === "dashboard" ? dashboardView() : projectsView()}
      </section>
    </section>
  `;

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      renderApp();
    });
  });
  document.querySelector("[data-logout]").addEventListener("click", logout);
  bindCurrentView();
}

function dashboardView() {
  const summary = state.dashboard.summary;
  return `
    <header class="topbar">
      <div>
        <h2>Dashboard</h2>
        <p>Track workload, completion, and overdue items.</p>
      </div>
    </header>
    <section class="grid stats-grid">
      ${statCard("Projects", summary.projects)}
      ${statCard("Total Tasks", summary.tasks)}
      ${statCard("Completed", summary.done)}
      ${statCard("Overdue", summary.overdue)}
    </section>
    <section class="panel" style="margin-top: 16px;">
      <h3>Upcoming Tasks</h3>
      ${state.dashboard.upcoming.length ? `
        <div class="project-list">
          ${state.dashboard.upcoming.map((task) => `
            <article class="task-card">
              <div class="meta-row">
                <span class="badge ${task.status.toLowerCase()}">${statusText(task.status)}</span>
                <span class="badge ${task.priority.toLowerCase()}">${task.priority}</span>
                ${task.overdue ? `<span class="badge overdue">Overdue</span>` : ""}
              </div>
              <h4>${escapeHtml(task.title)}</h4>
              <p>${escapeHtml(task.project_name)} · Due ${escapeHtml(task.due_date)} · ${escapeHtml(task.assignee_name || "Unassigned")}</p>
            </article>
          `).join("")}
        </div>
      ` : `<div class="empty">No tasks yet. Create a project and add your first task.</div>`}
    </section>
  `;
}

function statCard(label, value) {
  return `
    <article class="stat">
      <span>${label}</span>
      <strong>${value}</strong>
    </article>
  `;
}

function projectsView() {
  const selected = state.selectedProject;
  return `
    <header class="topbar">
      <div>
        <h2>Projects</h2>
        <p>Create projects, add team members, assign tasks, and update progress.</p>
      </div>
    </header>
    <p class="error" data-error></p>
    <section class="split">
      <div class="grid">
        <div class="panel">
          <h3>Create Project</h3>
          <form class="form" data-project-form>
            <label class="field">
              <span>Project Name</span>
              <input name="name" required minlength="3">
            </label>
            <label class="field">
              <span>Description</span>
              <textarea name="description"></textarea>
            </label>
            <button class="btn" type="submit">Create Project</button>
          </form>
        </div>
        <div class="panel">
          <h3>Your Projects</h3>
          ${state.projects.length ? `
            <div class="project-list">
              ${state.projects.map(projectCard).join("")}
            </div>
          ` : `<div class="empty">No projects yet. Create one to become its Admin.</div>`}
        </div>
      </div>
      <div class="grid">
        ${selected ? projectDetailView(selected) : `<div class="empty">Select or create a project.</div>`}
      </div>
    </section>
  `;
}

function projectCard(project) {
  const active = project.id === state.selectedProjectId;
  return `
    <article class="project-card">
      <div class="meta-row">
        <span class="badge ${project.role.toLowerCase()}">${project.role}</span>
        <span class="badge">${project.member_count} members</span>
        <span class="badge">${project.task_count} tasks</span>
      </div>
      <h3>${escapeHtml(project.name)}</h3>
      <p>${escapeHtml(project.description || "No description")}</p>
      <button class="btn ${active ? "" : "secondary"} small" data-open-project="${project.id}">
        ${active ? "Selected" : "Open"}
      </button>
    </article>
  `;
}

function projectDetailView(project) {
  const isAdmin = project.role === "ADMIN";
  return `
    <div class="panel">
      <div class="meta-row">
        <span class="badge ${project.role.toLowerCase()}">${project.role}</span>
        <span class="badge">Owner: ${escapeHtml(project.owner_name)}</span>
      </div>
      <h3 style="margin-top: 12px;">${escapeHtml(project.name)}</h3>
      <p style="color: var(--muted);">${escapeHtml(project.description || "No description")}</p>
    </div>
    <div class="panel">
      <h3>Team</h3>
      <div class="project-list">
        ${state.members.map((member) => `
          <article class="project-card">
            <div class="meta-row">
              <span class="badge ${member.role.toLowerCase()}">${member.role}</span>
            </div>
            <strong>${escapeHtml(member.name)}</strong>
            <p>${escapeHtml(member.email)}</p>
          </article>
        `).join("")}
      </div>
      ${isAdmin ? `
        <form class="form" data-member-form style="margin-top: 14px;">
          <label class="field">
            <span>Add Existing User By Email</span>
            <input name="email" type="email" required>
          </label>
          <label class="field">
            <span>Role</span>
            <select name="role">
              <option value="MEMBER">Member</option>
              <option value="ADMIN">Admin</option>
            </select>
          </label>
          <button class="btn" type="submit">Add Member</button>
        </form>
      ` : ""}
    </div>
    <div class="panel">
      <h3>Tasks</h3>
      ${isAdmin ? taskForm() : ""}
      ${tasksTable()}
    </div>
  `;
}

function taskForm() {
  return `
    <form class="form form-grid" data-task-form style="margin-bottom: 16px;">
      <label class="field full">
        <span>Title</span>
        <input name="title" required minlength="3">
      </label>
      <label class="field full">
        <span>Description</span>
        <textarea name="description"></textarea>
      </label>
      <label class="field">
        <span>Assignee</span>
        <select name="assignee_id">
          <option value="">Unassigned</option>
          ${state.members.map((member) => `<option value="${member.id}">${escapeHtml(member.name)}</option>`).join("")}
        </select>
      </label>
      <label class="field">
        <span>Due Date</span>
        <input name="due_date" type="date" required>
      </label>
      <label class="field">
        <span>Priority</span>
        <select name="priority">
          <option value="LOW">Low</option>
          <option value="MEDIUM" selected>Medium</option>
          <option value="HIGH">High</option>
        </select>
      </label>
      <label class="field">
        <span>Status</span>
        <select name="status">
          <option value="TODO">Todo</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="DONE">Done</option>
        </select>
      </label>
      <button class="btn full" type="submit">Create Task</button>
    </form>
  `;
}

function tasksTable() {
  if (!state.tasks.length) {
    return `<div class="empty">No tasks in this project yet.</div>`;
  }
  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Task</th>
            <th>Assignee</th>
            <th>Due</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${state.tasks.map((task) => `
            <tr>
              <td>
                <strong>${escapeHtml(task.title)}</strong>
                <p>${escapeHtml(task.description || "")}</p>
              </td>
              <td>${escapeHtml(task.assignee_name || "Unassigned")}</td>
              <td>
                ${escapeHtml(task.due_date)}
                ${task.overdue ? `<span class="badge overdue">Overdue</span>` : ""}
              </td>
              <td>
                ${task.can_update ? `
                  <select data-status-task="${task.id}">
                    ${["TODO", "IN_PROGRESS", "DONE"].map((status) => `
                      <option value="${status}" ${task.status === status ? "selected" : ""}>${statusText(status)}</option>
                    `).join("")}
                  </select>
                ` : `<span class="badge ${task.status.toLowerCase()}">${statusText(task.status)}</span>`}
              </td>
              <td><span class="badge ${task.priority.toLowerCase()}">${task.priority}</span></td>
              <td class="actions">
                ${task.can_delete ? `<button class="btn danger small" data-delete-task="${task.id}">Delete</button>` : ""}
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function bindCurrentView() {
  if (state.view !== "projects") return;

  document.querySelector("[data-project-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError("");
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const { project } = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.selectedProjectId = project.id;
      await loadAppData();
      state.view = "projects";
      renderApp();
    } catch (error) {
      setError(error.message);
    }
  });

  document.querySelectorAll("[data-open-project]").forEach((button) => {
    button.addEventListener("click", async () => {
      setError("");
      await loadProject(button.dataset.openProject);
      renderApp();
    });
  });

  document.querySelector("[data-member-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError("");
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const { members } = await api(`/api/projects/${state.selectedProjectId}/members`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.members = members;
      await loadAppData();
      renderApp();
    } catch (error) {
      setError(error.message);
    }
  });

  document.querySelector("[data-task-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError("");
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const { tasks } = await api(`/api/projects/${state.selectedProjectId}/tasks`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.tasks = tasks;
      await loadAppData();
      renderApp();
    } catch (error) {
      setError(error.message);
    }
  });

  document.querySelectorAll("[data-status-task]").forEach((select) => {
    select.addEventListener("change", async () => {
      setError("");
      try {
        const { tasks } = await api(`/api/tasks/${select.dataset.statusTask}`, {
          method: "PATCH",
          body: JSON.stringify({ status: select.value }),
        });
        state.tasks = tasks;
        await loadAppData();
        renderApp();
      } catch (error) {
        setError(error.message);
      }
    });
  });

  document.querySelectorAll("[data-delete-task]").forEach((button) => {
    button.addEventListener("click", async () => {
      setError("");
      try {
        await api(`/api/tasks/${button.dataset.deleteTask}`, { method: "DELETE" });
        await loadAppData();
        renderApp();
      } catch (error) {
        setError(error.message);
      }
    });
  });
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  state.user = null;
  state.projects = [];
  state.selectedProjectId = null;
  state.selectedProject = null;
  state.members = [];
  state.tasks = [];
  state.dashboard = null;
  state.view = "dashboard";
  renderAuth();
}

boot().catch((error) => {
  app.innerHTML = `
    <section class="auth-layout">
      <div class="auth-card">
        <div class="brand">
          <h1>Team Task Manager</h1>
          <p>${escapeHtml(error.message)}</p>
        </div>
      </div>
    </section>
  `;
});

