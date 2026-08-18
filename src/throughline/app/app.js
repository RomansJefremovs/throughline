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

/* Which agent the hand-off opens. The server decides; this is only what
 * the buttons are allowed to say. */
const AGENT_LABELS = { claude: "Claude", opencode: "opencode" };
let agent = "claude";
const agentLabel = () => AGENT_LABELS[agent] || agent;

const el = (id) => document.getElementById(id);
const SCREENS = ["front", "map", "setup", "reading", "editing", "tasks", "adding", "starting", "failure"];

/* Human words for the flags. The list itself comes from the server so it
 * cannot drift; only the wording lives here, and an unknown flag falls
 * back to its own name rather than disappearing. */
const FLAG_WORDS = {
  has_db: "Database",
  has_ui: "User interface",
  has_state: "State",
  multi_service: "Multiple services",
};

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

async function goBack() {
  if (!history.length) return;
  const here = snapshot();
  const previous = history.pop();
  future.unshift(here);
  await restore(previous);
}

el("back").onclick = goBack;

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

  const more = document.createElement("button");
  more.className = "sw-row sw-add";
  more.innerHTML = "<span>+ Add a project…</span>";
  more.onclick = () => { el("switcher").hidden = true; openAdd(); };
  box.appendChild(more);

  /* The agent applies to every project, so it belongs beside the list of
   * them rather than inside any one. Named, not hidden behind a gear. */
  const who = document.createElement("button");
  who.className = "sw-row sw-agent";
  who.innerHTML = `<span>Agent</span><span class="tag">${esc(agentLabel())}</span>`;
  who.onclick = async () => {
    el("switcher").hidden = true;
    if (await pickAgent()) redrawForAgent();
  };
  box.appendChild(who);
}

/* Every place the agent is named, after it changes. */
function redrawForAgent() {
  if (project) drawFront();
  if (openNode) {
    const start = el("doc-start");
    if (!el("doc-empty").hidden) {
      start.textContent = start.textContent.startsWith("Continue")
        ? `Continue — hands to ${agentLabel()}`
        : `Start — hands to ${agentLabel()}`;
    }
  }
}

el("go-front").onclick = () => goTo("front");
el("go-map").onclick = () => { drawMap(); goTo("map"); };
el("go-tasks").onclick = async () => { await drawTasks(); goTo("tasks"); };
el("go-setup").onclick = async () => { await drawSetup(); goTo("setup"); };

/* The front door -------------------------------------------------- */

function drawFront() {
  el("front-project").textContent = project.project || project.name;
  el("front-reminder").textContent = project.note || "";
  el("front-add").hidden = true;
  el("front-setup").hidden = true;
  el("front-start").hidden = true;

  const action = el("front-action");
  const sub = el("front-sub");

  if (project.next) {
    const verb = project.task ? "Continue" : "Next";
    action.hidden = false;
    action.textContent = `${verb}: ${project.next_title}`;
    sub.textContent = `→ opens ${agentLabel()} in ${project.name}/`;
    return;
  }

  action.hidden = true;

  /* A task-only repo has no nodes, so `next` stays null until a task
   * exists - and nothing could create the first one. That left the one
   * screen which must always name something to do naming nothing. */
  if (project.task_only && !project.has_setup) {
    el("front-setup").hidden = false;
    sub.textContent = `→ opens ${agentLabel()} in ${project.name}/`;
  } else if (project.task_only) {
    el("front-start").hidden = false;
    sub.textContent = "A task is four short nodes, start to verified.";
  } else {
    sub.textContent = "Nothing waiting — every document is written.";
  }
}

el("front-action").onclick = (event) => startNode(project.next, event.currentTarget, project.task);
el("front-add").onclick = () => openAdd();

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
    el("doc-start").textContent = mid
      ? `Continue — hands to ${agentLabel()}`
      : `Start — hands to ${agentLabel()}`;
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

  /* Diagrams are drawn only once the screen is on.
   *
   * Mermaid measures the rendered text to lay a diagram out, and inside a
   * hidden screen every measurement comes back zero. It reports that as a
   * syntax error in the diagram - so a timing problem here reads to the
   * user as a broken document, and they go looking at their own markdown. */
  if (!unwritten) drawDiagrams(el("rendered"));
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

/* Adding a project ------------------------------------------------- */

let flagList = null;

async function drawFlags() {
  if (!flagList) {
    // api() turns a resolved-but-not-ok response into null, but it
    // rethrows when fetch() itself rejects - the sidecar not answering
    // at all, not answering no. Both have to end up here rather than
    // one of them escaping as an unhandled rejection and taking
    // openAdd() down with it before the screen ever changes.
    let fetched = null;
    try {
      fetched = await api("/api/flags");
    } catch (problem) {
      fetched = null;
    }
    // The cache is only ever filled with a real answer. Caching a
    // failure - or caching [] and calling that done - would make one
    // bad response (or one dead sidecar) permanent: every later
    // openAdd() would draw an "Extras" box holding nothing, with no
    // sign anything went wrong.
    if (!fetched) {
      addError("Could not load the available flags.");
      return;
    }
    flagList = fetched;
  }
  const box = el("add-flags");
  box.innerHTML = "";
  flagList.forEach((flag) => {
    const row = document.createElement("label");
    const tick = document.createElement("input");
    tick.type = "checkbox";
    tick.className = "flag";
    tick.value = flag.name;
    const words = document.createElement("span");
    words.innerHTML =
      `${esc(FLAG_WORDS[flag.name] || flag.name)} ` +
      `<span class="adds">${flag.adds ? `adds ${esc(flag.adds)}` : "adds nothing yet"}</span>`;
    row.append(tick, words);
    box.appendChild(row);
  });
}

function addError(text) {
  const box = el("add-error");
  box.textContent = text;
  box.hidden = !text;
}

async function openAdd() {
  el("add-path").value = "";
  el("add-name").value = "";
  delete el("add-name").dataset.touched;
  el("add-target").checked = false;
  document.querySelector('input[name="add-kind"][value="full"]').checked = true;
  addError("");
  await drawFlags();
  // The picker only exists inside the desktop shell. In a browser the
  // text field is the whole input, so the button is not offered.
  el("add-browse").hidden = !(window.__TAURI__ && window.__TAURI__.dialog);
  goTo("adding");
  el("add-path").focus();
}

/* The folder's own name is the project's name nine times out of ten,
 * so it is filled in until the moment someone types their own. */
el("add-path").oninput = () => {
  if (el("add-name").dataset.touched) return;
  const typed = el("add-path").value.trim().replace(/[\\/]+$/, "");
  el("add-name").value = typed.split(/[\\/]/).pop() || "";
};

el("add-name").oninput = () => { el("add-name").dataset.touched = "1"; };

el("add-browse").onclick = async () => {
  const chosen = await window.__TAURI__.dialog.open({
    directory: true,
    multiple: false,
  });
  if (typeof chosen !== "string") return;
  el("add-path").value = chosen;
  el("add-path").dispatchEvent(new Event("input"));
};

el("add-cancel").onclick = async () => {
  if (history.length) await goBack();
  else show("front");
};

async function said(response) {
  const problem = await response.json().catch(() => ({}));
  return problem.error || "That didn't work.";
}

/* Add first, and only create a pipeline if there is none.
 *
 * The two endpoints mirror the two CLI commands, and their refusals
 * compose: add writes nothing, so a mistyped path is turned away before
 * anything can be created. 404 from add means one thing only - the
 * folder is real and has no pipeline in it. */
async function submitAdd() {
  const path = el("add-path").value.trim();
  if (!path) return addError("Type or choose a folder.");

  const button = el("add-submit");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Adding…";
  addError("");

  const track = () =>
    fetch(`/api/add?path=${encodeURIComponent(path)}`, { method: "POST" });

  // Tracked across the try so a throw in catch can say how far this
  // actually got, instead of "nothing was created" being repeated for
  // a request that did write something before it broke.
  let pipelineMade = false;
  let pipelineTracked = false;

  try {
    let response = await track();

    if (response.status === 404) {
      // Flags are read only on this branch - the one that calls init
      // and creates a fresh pipeline. A folder that already has one
      // never reaches here, so refusing outright at the top of this
      // function would wrongly block that path too; refusing exactly
      // here blocks only the case flags actually matter for.
      //
      // flagList is null until drawFlags() has loaded a real list, so
      // this is also what stands between "the box rendered empty
      // because loading failed" and "init runs with flags: [] anyway" -
      // there is no way to fix a wrongly-flagged pipeline afterwards
      // short of hand-editing pipeline.yaml, so guessing here is not
      // an option.
      if (!flagList) {
        return addError(
          "The list of flags never loaded, so a new pipeline can't be created safely yet. Try again."
        );
      }
      const created = await fetch("/api/init", {
        method: "POST",
        body: JSON.stringify({
          path,
          project: el("add-name").value.trim(),
          flags: [...document.querySelectorAll("#add-flags input.flag:checked")]
            .map((tick) => tick.value),
          target_side: el("add-target").checked,
          task_only:
            document.querySelector('input[name="add-kind"]:checked').value === "task",
        }),
      });
      if (!created.ok) return addError(await said(created));
      pipelineMade = true;
      response = await track();
    }

    if (!response.ok) return addError(await said(response));

    // The write already happened server-side the moment response.ok
    // is true, whatever the parse below does with the body.
    pipelineTracked = true;
    const added = await response.json();
    // The project was genuinely created either way, so the switcher
    // and front door must learn about it regardless of what the user
    // did while this was in flight. Only the navigation is conditional:
    // nothing but the submit button is disabled during the request, so
    // Cancel (or the switcher) can move the screen on before this
    // resolves - and jumping back to "adding" then would yank the user
    // off wherever they went next for a request they no longer care
    // about.
    projects = (await api("/api/projects")) || [];
    if (current() === "adding") await openProject(added.path);
  } catch (problem) {
    // A throw means fetch() itself failed - the sidecar did not
    // answer at all - which the .ok checks above never see. Say
    // something true about how far this got rather than a generic
    // failure that would read as "nothing happened" when it did.
    if (pipelineTracked) {
      addError("Added, but the screen could not refresh. Reopen it from the switcher.");
    } else if (pipelineMade) {
      addError("The pipeline was created, but Throughline could not track it yet. Click Add again.");
    } else {
      addError("Throughline did not respond. Nothing was created.");
    }
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

el("add-submit").onclick = submitAdd;

/* Starting a task -------------------------------------------------- */

function taskError(text) {
  const box = el("task-error");
  box.textContent = text;
  box.hidden = !text;
}

function openStart() {
  el("start-project").textContent = project.project || project.name;
  el("task-title").value = "";
  el("task-reference").value = "";
  taskError("");
  goTo("starting");
  el("task-title").focus();
}

el("task-cancel").onclick = async () => {
  if (history.length) await goBack();
  else show("front");
};

/* Created here rather than handed over: a title is one line off a
 * ticket, not an interview. The work that follows is still the agent's - the
 * front door names it the moment this returns. */
async function submitTask() {
  const title = el("task-title").value.trim();
  if (!title) return taskError("Give the task a title.");

  const button = el("task-submit");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Starting…";
  taskError("");
  let started = false;

  try {
    const query = new URLSearchParams({ repo: project.path, title });
    const reference = el("task-reference").value.trim();
    if (reference) query.set("reference", reference);

    const response = await fetch(`/api/task?${query}`, { method: "POST" });
    if (!response.ok) return taskError(await said(response));
    started = true;
    await openProject(project.path);
  } catch {
    // Which half failed decides what is true. Saying the task was not
    // started when it was would send someone off to start it twice.
    taskError(
      started
        ? "The task was started, but the screen could not refresh. Open it from Tasks."
        : "Throughline did not respond. The task was not started."
    );
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

el("task-submit").onclick = submitTask;
el("front-start").onclick = () => openStart();

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
    : '<p class="muted">No setup written yet.</p>';
  el("setup-action").hidden = !!data;
}

/* Handing off ----------------------------------------------------- */

/* The server refuses to guess when both agents are installed, so the
 * choice is made here and stored. Also opened deliberately from the
 * switcher - a decision you can only make once is a trap, not a default.
 *
 * Resolves to the chosen name, or null if it was dismissed. */
function pickAgent() {
  return new Promise((resolve) => {
    const dialog = el("pick-agent");
    // Which one is live right now, so opening this on purpose shows you
    // where you are rather than asking you to remember.
    el("pick-claude").className = agent === "claude" ? "solid" : "hollow";
    el("pick-opencode").className = agent === "opencode" ? "solid" : "hollow";
    dialog.hidden = false;

    const close = (name) => {
      dialog.hidden = true;
      document.removeEventListener("keydown", onKey);
      resolve(name);
    };
    const onKey = (event) => {
      if (event.key === "Escape") close(null);
    };
    const pick = async (name) => {
      await fetch(`/api/agent?name=${name}`, { method: "POST" });
      agent = name;
      close(name);
    };

    document.addEventListener("keydown", onKey);
    el("pick-claude").onclick = () => pick("claude");
    el("pick-opencode").onclick = () => pick("opencode");
  });
}

/* One hand-off, two callers. The 409 retry lives here rather than in
 * both, because a dialog that only appears in one of them is the kind of
 * thing nobody notices until it matters.
 *
 * A new console that outlives the app, and a button that says what
 * happened for long enough to read. */
async function handOff(button, query) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = `Opening ${agentLabel()}…`;

  const send = () => fetch(`/api/start?${query}`, { method: "POST" });
  let response = await send();
  if (response.status === 409) {
    // Dismissed without choosing: nothing was asked for, so nothing opens.
    if (!(await pickAgent())) {
      button.disabled = false;
      button.textContent = label;
      return;
    }
    button.textContent = `Opening ${agentLabel()}…`;
    response = await send();
  }

  if (response.ok) {
    button.textContent = `Opened in ${agentLabel()}`;
  } else {
    const problem = await response.json().catch(() => ({}));
    button.textContent = problem.error || `Could not open ${agentLabel()}`;
  }
  setTimeout(() => {
    button.disabled = false;
    button.textContent = label;
  }, 4000);
}

async function startNode(nodeId, button, slug = null) {
  if (!nodeId) return;
  const query = new URLSearchParams({ repo: project.path, node: nodeId });
  if (slug) query.set("slug", slug);
  await handOff(button, query);
}

async function startSetup(button) {
  await handOff(
    button,
    new URLSearchParams({ repo: project.path, setup: "1" })
  );
}

el("front-setup").onclick = (event) => startSetup(event.currentTarget);
el("setup-action").onclick = (event) => startSetup(event.currentTarget);

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
    const picked = await api("/api/agent");
    if (picked && picked.chosen) agent = picked.chosen;
    if (!home || !home.path) {
      el("front-project").textContent = "No projects yet";
      el("front-reminder").textContent =
        "Throughline tracks repositories you have pointed it at.";
      el("front-action").hidden = true;
      el("front-add").hidden = false;
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
