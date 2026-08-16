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

async function showArtifact(node) {
  const url = `/api/artifact?repo=${encodeURIComponent(current.path)}&node=${node.id}`;
  const data = await api(url);
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
}

function setEditing(on) {
  el("source").hidden = !on;
  el("rendered").hidden = on;
  el("edit").hidden = on;
  el("save").hidden = !on;
  el("cancel").hidden = !on;
}

function showGraph() {
  el("artifact").hidden = true;
  el("graph").hidden = false;
}

async function open(path) {
  const data = await api(`/api/project?repo=${encodeURIComponent(path)}`);
  if (!data) return;
  current = data;
  el("project-name").textContent = data.project || data.name;
  el("note").textContent = data.note || "";
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

el("back").onclick = showGraph;
el("edit").onclick = () => setEditing(true);
el("cancel").onclick = () => setEditing(false);

el("save").onclick = async () => {
  const node = el("artifact").dataset.node;
  const url = `/api/artifact?repo=${encodeURIComponent(current.path)}&node=${node}`;
  await fetch(url, { method: "PUT", body: el("source").value });
  setRendered(el("source").value);
  setEditing(false);
};

start();
