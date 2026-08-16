/* Throughline.
 *
 * Two rules shape this file. The front door contains no decisions: the
 * app opens on the last project worked in and names one next action.
 * And nothing here ever counts undone work - the rail shows what is
 * alive, never what is owed.
 */

const PHASES = ["problem", "analysis", "design", "code"];
const STATE_WORDS = {
  empty: "not started",
  drafted: "drafted, not read yet",
  in_progress: "partway through",
  current: "written",
};

let current = null;

const el = (id) => document.getElementById(id);

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) return null;
  return response.json();
}

function esc(text) {
  return text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function inline(text) {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
}

function row(line) {
  return line.split("|").slice(1, -1).map((c) => c.trim());
}

/* A markdown renderer for exactly the subset these artifacts use.
 * Vendoring a full parser would be a megabyte of dependency for tables,
 * headings and fences. */
function render(md) {
  const lines = md.split("\n");
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i += 1;
      if (lang === "mermaid") {
        /* mermaid reads textContent, so the escaping here is undone
         * before it ever sees the source. */
        out.push(`<pre class="mermaid">${esc(buf.join("\n"))}</pre>`);
      } else {
        out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
      }
      continue;
    }

    if (/^\|.*\|$/.test(line) && /^\|[\s:|-]+\|$/.test(lines[i + 1] || "")) {
      const head = row(line);
      i += 2;
      const body = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i])) body.push(row(lines[i++]));
      const th = head.map((c) => `<th>${inline(c)}</th>`).join("");
      const tr = body
        .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (line.startsWith("> ")) {
      const buf = [];
      while (i < lines.length && lines[i].startsWith("> ")) buf.push(lines[i++].slice(2));
      out.push(`<blockquote>${inline(buf.join(" "))}</blockquote>`);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        buf.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      }
      out.push(`<ul>${buf.map((t) => `<li>${inline(t)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        buf.push(lines[i++].replace(/^\s*\d+\.\s+/, ""));
      }
      out.push(`<ol>${buf.map((t) => `<li>${inline(t)}</li>`).join("")}</ol>`);
      continue;
    }

    if (line.trim() === "" || line.trim() === "---") {
      i += 1;
      continue;
    }

    const buf = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^[#>|`-]/.test(lines[i])) {
      buf.push(lines[i++]);
    }
    if (buf.length) out.push(`<p>${inline(buf.join(" "))}</p>`);
    else i += 1;
  }

  return out.join("\n");
}

/* Mermaid is 3.5MB, vendored so the app works offline and under Tauri's
 * CSP. It is fetched the first time a diagram is actually on screen and
 * never on startup, so the front door stays instant. */
let mermaidLoading = null;

function loadMermaid() {
  if (mermaidLoading) return mermaidLoading;
  mermaidLoading = new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = "/vendor/mermaid.min.js";
    tag.onload = () => {
      const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      window.mermaid.initialize({
        startOnLoad: false,
        theme: dark ? "dark" : "default",
        securityLevel: "strict",
      });
      resolve(window.mermaid);
    };
    tag.onerror = () => reject(new Error("mermaid failed to load"));
    document.head.appendChild(tag);
  });
  return mermaidLoading;
}

/* A diagram that will not parse leaves its source on screen. That is the
 * honest fallback: the text is still the artifact. */
async function drawDiagrams(root) {
  const blocks = [...root.querySelectorAll("pre.mermaid")];
  if (!blocks.length) return;
  try {
    const mermaid = await loadMermaid();
    await mermaid.run({ nodes: blocks, suppressErrors: true });
  } catch (err) {
    console.warn("diagrams not rendered:", err.message);
  }
}

function setRendered(markdown) {
  const target = el("rendered");
  target.innerHTML = render(markdown);
  drawDiagrams(target);
}

function drawRail(projects) {
  const rail = el("projects");
  rail.innerHTML = "";
  projects.forEach((p) => {
    const button = document.createElement("button");
    button.className = "project" + (p.missing ? " missing" : "");
    button.setAttribute("aria-current", current && p.path === current.path);
    const bar = p.phases
      .map((ph) => "#".repeat(ph.filled) + ".".repeat(ph.total - ph.filled))
      .join(" ");
    button.innerHTML = `${esc(p.project || p.name)}<span class="bar">${
      p.missing ? "folder not found" : esc(bar)
    }</span>`;
    button.onclick = () => open(p.path);
    rail.appendChild(button);
  });
}

function drawGraph(nodes) {
  const graph = el("graph");
  graph.innerHTML = "";
  PHASES.forEach((phase) => {
    const inPhase = nodes.filter((n) => n.phase === phase);
    if (!inPhase.length) return;
    const column = document.createElement("div");
    column.innerHTML = `<div class="phase-title">${phase}</div>`;
    inPhase.forEach((node) => {
      const button = document.createElement("button");
      button.className =
        "node " + node.status + (node.id === current.next ? " next" : "");
      button.innerHTML = `${esc(node.title)}<span class="state">${
        STATE_WORDS[node.status] || node.status
      }</span>`;
      button.onclick = () => showArtifact(node);
      column.appendChild(button);
    });
    graph.appendChild(column);
  });
}

/* The task list is opened deliberately or not at all. Nothing renders it
 * on load, and no count of it appears anywhere. */
let openTask = null;

const TASK_WORDS = {
  open: "not started",
  in_progress: "in progress",
  done: "finished",
  abandoned: "dropped",
};

async function showTasks() {
  const list = await api(`/api/tasks?repo=${encodeURIComponent(current.path)}`);
  const target = el("tasks");
  target.innerHTML = "";
  if (!list || !list.length) {
    target.innerHTML = "<p>No tasks in this project yet.</p>";
  }
  (list || []).forEach((task) => {
    const box = document.createElement("div");
    box.className = "task " + task.status;
    box.innerHTML =
      `<div class="task-title">${esc(task.title)}` +
      `<span class="state">${TASK_WORDS[task.status] || task.status}` +
      `${task.reference ? " · " + esc(task.reference) : ""}</span></div>`;
    task.nodes.forEach((node) => {
      const button = document.createElement("button");
      button.className =
        "node " + node.status + (node.id === task.next ? " next" : "");
      button.innerHTML = `${esc(node.title)}<span class="state">${
        STATE_WORDS[node.status] || node.status
      }</span>`;
      button.onclick = () => showArtifact(node, task.slug);
      box.appendChild(button);
    });
    target.appendChild(box);
  });
  el("graph").hidden = true;
  el("artifact").hidden = true;
  target.hidden = false;
}

/* Gaps appear on the artifact that states them, never on a screen of
 * their own, and each one is promoted by its own deliberate click. A
 * screen listing every gap in the project is a backlog. */
async function drawGaps(nodeId) {
  const target = el("gaps");
  target.innerHTML = "";
  target.hidden = true;
  const found = await api(
    `/api/gaps?repo=${encodeURIComponent(current.path)}&node=${nodeId}`
  );
  if (!found || !found.length) return;

  const heading = document.createElement("h2");
  heading.textContent = "What this says should change";
  target.appendChild(heading);

  found.forEach((gap) => {
    const row = document.createElement("div");
    row.className = "gap";
    const label = document.createElement("span");
    label.textContent = gap.title || "the target side";
    const button = document.createElement("button");
    button.textContent = "Make this a task";
    button.onclick = async () => {
      button.disabled = true;
      button.textContent = "Creating…";
      const query = new URLSearchParams({
        repo: current.path,
        node: gap.node,
        title: gap.title,
      });
      const response = await fetch(`/api/promote?${query}`, { method: "POST" });
      button.textContent = response.ok ? "Task created" : "Could not create it";
      if (response.ok) await open(current.path);
    };
    row.append(label, button);
    target.appendChild(row);
  });
  target.hidden = false;
}

async function showArtifact(node, slug = null) {
  openTask = slug;
  const query = new URLSearchParams({ repo: current.path, node: node.id });
  if (slug) query.set("slug", slug);
  const url = `/api/artifact?${query}`;
  const data = await api(url);
  el("tasks").hidden = true;
  el("graph").hidden = true;
  el("artifact").hidden = false;
  el("source").value = data ? data.text : "";
  if (data) {
    setRendered(data.text);
  } else {
    el("rendered").innerHTML =
      `<p>Nothing written for <strong>${esc(node.title)}</strong> yet.</p>`;
  }
  el("artifact").dataset.node = node.id;
  setEditing(false);
  if (slug) {
    el("gaps").hidden = true;
  } else {
    drawGaps(node.id);
  }
}

function setEditing(on) {
  el("source").hidden = !on;
  el("rendered").hidden = on;
  if (on) el("gaps").hidden = true;
  el("edit").hidden = on;
  el("work").hidden = on;
  el("save").hidden = !on;
  el("cancel").hidden = !on;
}

function showGraph() {
  el("artifact").hidden = true;
  el("tasks").hidden = true;
  el("graph").hidden = false;
  openTask = null;
}

async function open(path) {
  const data = await api(`/api/project?repo=${encodeURIComponent(path)}`);
  if (!data) return;
  current = data;
  el("project-name").textContent = data.project || data.name;
  el("note").textContent = data.note || "";

  /* A live task owns the next action. You finish what you started. */
  const onTask = el("on-task");
  onTask.hidden = !data.task;
  onTask.textContent = data.task ? `On: ${data.task_title}` : "";

  const next = el("next-action");
  if (data.next) {
    next.hidden = false;
    next.textContent = `Next: ${data.next_title}`;
  } else {
    next.hidden = true;
  }
  drawGraph(data.nodes);
  showGraph();
  drawRail(await api("/api/projects"));
}

async function start() {
  const home = await api("/api/home");
  const projects = (await api("/api/projects")) || [];
  if (!home || !home.path) {
    el("empty").hidden = false;
    el("head").hidden = true;
    drawRail(projects);
    return;
  }
  await open(home.path);
}

/* The handoff. The sidecar spawns the session because a browser tab
 * cannot; under Tauri the same endpoint does the same thing. */
async function startNode(nodeId, button, slug = null) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Opening Claude…";
  const query = new URLSearchParams({ repo: current.path, node: nodeId });
  if (slug) query.set("slug", slug);
  const response = await fetch(`/api/start?${query}`, { method: "POST" });
  if (response.ok) {
    button.textContent = "Opened in Claude";
  } else {
    const problem = await response.json().catch(() => ({}));
    button.textContent = problem.error || "Could not open Claude";
  }
  setTimeout(() => {
    button.disabled = false;
    button.textContent = label;
  }, 4000);
}

el("back").onclick = showGraph;
el("edit").onclick = () => setEditing(true);
el("cancel").onclick = () => setEditing(false);

el("next-action").onclick = (event) =>
  startNode(current.next, event.currentTarget, current.task);

el("work").onclick = (event) =>
  startNode(el("artifact").dataset.node, event.currentTarget, openTask);

el("tasks-toggle").onclick = () =>
  el("tasks").hidden ? showTasks() : showGraph();

el("save").onclick = async () => {
  const node = el("artifact").dataset.node;
  const query = new URLSearchParams({ repo: current.path, node });
  if (openTask) query.set("slug", openTask);
  await fetch(`/api/artifact?${query}`, {
    method: "PUT",
    body: el("source").value,
  });
  setRendered(el("source").value);
  setEditing(false);
};

start();
