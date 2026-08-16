/* Throughline.
 *
 * Two rules shape this file. The front door contains no decisions: the
 * app opens on the project last worked in and names one action. And
 * nothing here ever counts undone work - the map shows what is alive,
 * never what is owed.
 */

const PHASES = ["problem", "analysis", "design", "code"];
const COLUMN_X = [8, 32, 58, 82];
const NODE_HALF_X = 8.8;
const NODE_HALF_Y = 6;

const LEAD = {
  empty: "Start →",
  drafted: "Read →",
  in_progress: "Continue →",
};

const el = (id) => document.getElementById(id);
const SCREENS = ["front", "map", "setup", "reading", "editing", "tasks", "failure"];

let project = null;
let projects = [];
let openTask = null;
let openNode = null;
let loadedVersion = null;
let theirText = null;
let history = [];
let future = [];

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) return null;
  return response.json();
}

function esc(text) {
  return String(text).replace(/[&<>]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])
  );
}

/* Markdown, for exactly the subset these artifacts use. A full parser
 * would be a megabyte of dependency for tables, headings and fences. */
function inline(text) {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
}

function cells(line) {
  return line.split("|").slice(1, -1).map((c) => c.trim());
}

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
      const body = esc(buf.join("\n"));
      out.push(
        lang === "mermaid"
          ? `<pre class="mermaid">${body}</pre>`
          : `<pre><code>${body}</code></pre>`
      );
      continue;
    }

    if (/^\|.*\|$/.test(line) && /^\|[\s:|-]+\|$/.test(lines[i + 1] || "")) {
      const head = cells(line);
      i += 2;
      const body = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i])) body.push(cells(lines[i++]));
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

/* Mermaid is 3.5MB, vendored so the app works offline. It is fetched the
 * first time a diagram is on screen and never at startup. */
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
        theme: dark ? "dark" : "neutral",
        securityLevel: "strict",
      });
      resolve(window.mermaid);
    };
    tag.onerror = () => reject(new Error("mermaid failed to load"));
    document.head.appendChild(tag);
  });
  return mermaidLoading;
}

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
  // The editor needs the source, and reading it back out of rendered
  // HTML would be lossy. Keep it beside the textarea instead.
  el("source").dataset.text = markdown;
  const target = el("rendered");
  target.innerHTML = render(markdown);
  drawDiagrams(target);
}

/* Navigation ------------------------------------------------------ */

function snapshot() {
  return { screen: current(), node: openNode, task: openTask, path: project && project.path };
}

function current() {
  return SCREENS.find((name) => !el(name).hidden) || "front";
}

function show(screen) {
  SCREENS.forEach((name) => {
    el(name).hidden = name !== screen;
  });
  el("go-front").classList.toggle("on", screen === "front");
  el("go-map").classList.toggle("on", screen === "map");
  el("go-tasks").classList.toggle("on", screen === "tasks");
  el("go-setup").classList.toggle("on", screen === "setup");
  el("switcher").hidden = true;
}

function goTo(screen, record = true) {
  if (record) {
    history.push(snapshot());
    future = [];
  }
  show(screen);
  updateChevrons();
}

function updateChevrons() {
  el("back").classList.toggle("on", history.length > 0);
  el("forward").classList.toggle("on", future.length > 0);
}

async function restore(state) {
  if (state.path && (!project || project.path !== state.path)) await openProject(state.path, false);
  if (state.screen === "reading" && state.node) {
    await showArtifact(state.node, state.task, false);
  } else {
    if (state.screen === "map") drawMap();
    if (state.screen === "tasks") await drawTasks();
    if (state.screen === "setup") await drawSetup();
    show(state.screen);
  }
  updateChevrons();
}

el("back").onclick = async () => {
  if (!history.length) return;
  const here = snapshot();
  const previous = history.pop();
  future.unshift(here);
  await restore(previous);
};

el("forward").onclick = async () => {
  if (!future.length) return;
  const here = snapshot();
  const next = future.shift();
  history.push(here);
  await restore(next);
};

/* The rail and the switcher --------------------------------------- */

el("switch").onclick = () => {
  const box = el("switcher");
  box.hidden = !box.hidden;
  if (!box.hidden) drawSwitcher();
};

function drawSwitcher() {
  const box = el("switcher");
  box.innerHTML = "";
  projects.forEach((entry) => {
    const row = document.createElement("button");
    row.className = "sw-row";
    const tag = entry.missing ? "missing" : entry.task_only ? "task-only" : "";
    row.innerHTML = `<span>${esc(entry.project || entry.name)}</span><span class="tag">${tag}</span>`;
    row.onclick = () => openProject(entry.path);
    box.appendChild(row);
  });
}

el("go-front").onclick = () => goTo("front");
el("go-map").onclick = () => { drawMap(); goTo("map"); };
el("go-tasks").onclick = async () => { await drawTasks(); goTo("tasks"); };
el("go-setup").onclick = async () => { await drawSetup(); goTo("setup"); };

/* The front door -------------------------------------------------- */

function drawFront() {
  el("front-project").textContent = project.project || project.name;
  el("front-reminder").textContent = project.note || "";

  const action = el("front-action");
  const sub = el("front-sub");

  if (project.next) {
    const verb = project.task ? "Continue" : "Next";
    action.hidden = false;
    action.textContent = `${verb}: ${project.next_title}`;
    sub.textContent = `→ opens Claude in ${project.name}/`;
  } else {
    action.hidden = true;
    sub.textContent = project.task_only
      ? "No task in flight. Start one when a ticket arrives."
      : "Nothing waiting — every document is written.";
  }
}

el("front-action").onclick = (event) => startNode(project.next, event.currentTarget, project.task);

/* The map --------------------------------------------------------- */

function layout(nodes) {
  const placed = {};
  PHASES.forEach((phase, column) => {
    const inPhase = nodes.filter((n) => n.phase === phase);
    if (!inPhase.length) return;
    const spacing = Math.min(18, 84 / inPhase.length);
    const start = Math.max(4, (100 - (inPhase.length - 1) * spacing - 12) / 2);
    inPhase.forEach((node, index) => {
      placed[node.id] = { x: COLUMN_X[column], y: start + index * spacing };
    });
  });
  return placed;
}

function drawMap() {
  el("map-lede").textContent =
    `${project.project || project.name} — how the documents depend on each other.`;

  el("phases").innerHTML = PHASES.map((p) => `<span>${p}</span>`).join("");

  const nodes = project.nodes || [];
  const placed = layout(nodes);
  const svg = el("edges");
  const box = el("map-nodes");
  svg.innerHTML = "";
  box.innerHTML = "";

  nodes.forEach((node) => {
    (node.deps || []).forEach((dep) => {
      if (!placed[dep] || !placed[node.id]) return;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", placed[dep].x + NODE_HALF_X);
      line.setAttribute("y1", placed[dep].y + NODE_HALF_Y);
      line.setAttribute("x2", placed[node.id].x + NODE_HALF_X);
      line.setAttribute("y2", placed[node.id].y + NODE_HALF_Y);
      line.setAttribute("stroke", "var(--divider)");
      line.setAttribute("stroke-width", "0.3");
      svg.appendChild(line);
    });
  });

  nodes.forEach((node) => {
    const spot = placed[node.id];
    const button = document.createElement("button");
    button.className = `mnode ${node.status}`;
    button.style.left = `${spot.x}%`;
    button.style.top = `${spot.y}%`;
    const lead = LEAD[node.status];
    button.innerHTML =
      `<span>${esc(node.title)}</span>` + (lead ? `<span class="lead">${lead}</span>` : "");
    button.onclick = () => showArtifact(node.id);
    box.appendChild(button);
  });
}

/* Documents ------------------------------------------------------- */

function nodeById(id) {
  return (project.nodes || []).find((n) => n.id === id);
}

async function showArtifact(nodeId, slug = null, record = true) {
  openNode = nodeId;
  openTask = slug;
  clearConflict();

  const query = new URLSearchParams({ repo: project.path, node: nodeId });
  if (slug) query.set("slug", slug);
  const data = await api(`/api/artifact?${query}`);
  loadedVersion = data ? data.version : null;

  const node = slug ? { title: titleOf(nodeId), phase: "task", status: data ? "current" : "empty" } : nodeById(nodeId);
  const title = node ? node.title : nodeId;

  el("doc-kicker").textContent = slug ? `Task · ${title}` : `${node.phase} · ${title}`;
  el("doc-title").textContent = title;

  const status = node ? node.status : "empty";
  const unwritten = !data;
  el("doc-empty").hidden = !unwritten;
  el("rendered").hidden = unwritten;
  el("edit").hidden = unwritten;

  if (unwritten) {
    const mid = status === "in_progress";
    el("doc-empty-text").textContent = mid ? "Mid-interview." : "Not started yet.";
    el("doc-start").textContent = mid ? "Continue — hands to Claude" : "Start — hands to Claude";
    el("gaps").hidden = true;
    el("drafted-note").hidden = true;
    el("stale-note").hidden = true;
  } else {
    setRendered(data.text);
    el("drafted-note").hidden = status !== "drafted";
    await drawStale(nodeId, slug);
    await drawGaps(nodeId, slug);
  }

  if (record) goTo("reading");
  else show("reading");
}

function titleOf(nodeId) {
  const words = { understand: "Understand", analyze: "Analyze", design: "Design", verify: "Verify" };
  return words[nodeId] || nodeId;
}

/* Rule 5: staleness is asked for one document at a time, never
 * broadcast, and one word dismisses it. */
async function drawStale(nodeId, slug) {
  const note = el("stale-note");
  note.hidden = true;
  if (slug) return;
  const found = await api(
    `/api/stale?repo=${encodeURIComponent(project.path)}&node=${nodeId}`
  );
  if (!found || !found.stale) return;
  const names = found.changed.map((id) => {
    const node = nodeById(id);
    return node ? node.title : id;
  });
  el("stale-text").textContent =
    `${names.join(" and ")} changed since this was written.`;
  note.hidden = false;
}

el("dismiss-stale").onclick = () => { el("stale-note").hidden = true; };

async function drawGaps(nodeId, slug) {
  const box = el("gaps");
  const rows = el("gap-rows");
  rows.innerHTML = "";
  box.hidden = true;
  if (slug) return;

  const found = await api(
    `/api/gaps?repo=${encodeURIComponent(project.path)}&node=${nodeId}`
  );
  if (!found || !found.length) return;

  found.forEach((gap) => {
    const row = document.createElement("div");
    row.className = "gap";

    const what = document.createElement("div");
    what.className = "what";
    const first = (gap.text || "").split("\n").find((line) => line.trim());
    what.innerHTML =
      `<div>${esc(gap.title || "the target side")}</div>` +
      (first ? `<div><span class="lbl">Should be:</span> ${esc(first)}</div>` : "");

    const button = document.createElement("button");
    button.textContent = "→ Task";
    button.onclick = async () => {
      button.disabled = true;
      button.textContent = "Creating…";
      const query = new URLSearchParams({
        repo: project.path,
        node: gap.node,
        title: gap.title,
      });
      const response = await fetch(`/api/promote?${query}`, { method: "POST" });
      button.textContent = response.ok ? "Added to tasks" : "Could not create it";
      if (response.ok) await refresh();
    };

    row.append(what, button);
    rows.appendChild(row);
  });
  box.hidden = false;
}

el("doc-start").onclick = (event) => startNode(openNode, event.currentTarget, openTask);
el("edit").onclick = () => {
  el("edit-title").textContent = el("doc-title").textContent;
  el("source").value = el("source").dataset.text || "";
  goTo("editing");
};

/* Editing, and two writers ---------------------------------------- */

function showConflict(text) {
  theirText = text;
  el("conflict").hidden = false;
}

function clearConflict() {
  el("conflict").hidden = true;
  theirText = null;
}

async function saveArtifact() {
  const query = new URLSearchParams({ repo: project.path, node: openNode });
  if (openTask) query.set("slug", openTask);
  if (loadedVersion) query.set("version", loadedVersion);

  const response = await fetch(`/api/artifact?${query}`, {
    method: "PUT",
    body: el("source").value,
  });

  if (response.status === 409) {
    const theirs = await response.json();
    loadedVersion = theirs.version;
    showConflict(theirs.text);
    return false;
  }

  const saved = await response.json().catch(() => ({}));
  loadedVersion = saved.version || null;
  clearConflict();
  return true;
}

el("save").onclick = async () => {
  if (await saveArtifact()) await showArtifact(openNode, openTask);
};

el("cancel").onclick = () => showArtifact(openNode, openTask);

el("keep-mine").onclick = async () => {
  if (await saveArtifact()) await showArtifact(openNode, openTask);
};

el("take-theirs").onclick = () => {
  el("source").value = theirText || "";
  clearConflict();
};

/* Tasks ----------------------------------------------------------- */

async function drawTasks() {
  el("tasks-lede").textContent = project.project || project.name;
  const rows = el("task-rows");
  rows.innerHTML = "";

  const list = await api(`/api/tasks?repo=${encodeURIComponent(project.path)}`);
  if (!list || !list.length) {
    rows.innerHTML = '<p class="muted">No tasks in this project yet.</p>';
    return;
  }

  list.forEach((task) => {
    const row = document.createElement("button");
    row.className = `task ${task.status}`;

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = task.title;

    const steps = document.createElement("div");
    steps.className = "steps";
    task.nodes.forEach((node, index) => {
      const dot = document.createElement("span");
      const done = node.status === "current";
      const here = task.status !== "abandoned" && node.id === task.next;
      dot.className = `dot${done ? " filled" : here ? " current" : ""}`;
      dot.title = node.title;
      steps.appendChild(dot);
      if (index < task.nodes.length - 1) {
        const link = document.createElement("span");
        link.className = "link";
        steps.appendChild(link);
      }
    });

    row.append(name, steps);
    row.onclick = () => showArtifact(task.next || task.nodes[0].id, task.slug);
    rows.appendChild(row);
  });
}

/* Setup, for a repo tracked only for task work -------------------- */

async function drawSetup() {
  el("setup-title").textContent = project.project || project.name;
  const data = await api(`/api/setup?repo=${encodeURIComponent(project.path)}`);
  el("setup-body").innerHTML = data
    ? render(data.text)
    : '<p class="muted">No setup written yet — ask Claude to set this repo up when it earns it.</p>';
}

/* Handing off ----------------------------------------------------- */

async function startNode(nodeId, button, slug = null) {
  if (!nodeId) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Opening Claude…";

  const query = new URLSearchParams({ repo: project.path, node: nodeId });
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

/* Loading a project ----------------------------------------------- */

async function openProject(path, record = true) {
  const data = await api(`/api/project?repo=${encodeURIComponent(path)}`);
  if (!data) return;
  project = data;
  el("tb-project").textContent = `— ${data.project || data.name}`;
  el("go-map").hidden = !!data.task_only;
  el("go-setup").hidden = !data.task_only;
  drawFront();
  if (record) goTo("front");
  else show("front");
}

async function refresh() {
  if (!project) return;
  await openProject(project.path, false);
  projects = (await api("/api/projects")) || [];
}

function fail(reason) {
  el("failure-text").textContent = reason;
  el("failure-list").innerHTML = [
    "Another Throughline window may already be running.",
    "The <code>throughline</code> command needs to be on your PATH.",
    "Run <code>throughline status</code> in a terminal to check.",
  ]
    .map((line) => `<li>${line}</li>`)
    .join("");
  show("failure");
}

el("retry").onclick = () => start();

async function start() {
  try {
    const home = await api("/api/home");
    projects = (await api("/api/projects")) || [];
    if (!home || !home.path) {
      el("front-project").textContent = "No projects yet";
      el("front-reminder").textContent =
        "Run throughline init in a repository, then throughline add to track it.";
      el("front-action").hidden = true;
      el("front-sub").textContent = "";
      show("front");
      return;
    }
    await openProject(home.path, false);
  } catch (problem) {
    fail("The background process that reads your files didn't respond. Nothing you've written was touched.");
  }
}

start();
