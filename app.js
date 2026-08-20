// const STAGE_TITLES = {
//   ingest: "Ingest file",
//   tier1: "Tier 1 — Native PDF extraction",
//   validate1: "Validate Tier 1 extraction",
//   escalate1: "Escalation gate (Tier 1 → Tier 2)",
//   tier2: "Tier 2 — OCR + Text LLM",
//   validate2: "Validate Tier 2 extraction",
//   escalate2: "Escalation gate (Tier 2 → Tier 3)",
//   tier3: "Tier 3 — Vision LLM",
//   validate3: "Validate final extraction",
//   match: "PO matching engine",
//   decision: "Decision engine",
//   correspondence: "Vendor correspondence",
//   ledger: "Record to ledger / history",
// };
// const STAGE_ORDER = Object.keys(STAGE_TITLES);

// let selectedSample = null;
// let selectedFile = null;
// let currentRunId = null;
// let stageState = {};   // stage_id -> {status, detail, payload}
// let selectedStageId = null;
// let currentSourceFile = null;   // server-side path, needed for vendor-reply reprocessing

// // ---------------------------------------------------------------------- tabs
// document.querySelectorAll(".tab").forEach(btn => {
//   btn.addEventListener("click", () => {
//     document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
//     btn.classList.add("active");
//     const tab = btn.dataset.tab;
//     document.getElementById("view-run").style.display = tab === "run" ? "" : "none";
//     document.getElementById("view-dashboard").style.display = tab === "dashboard" ? "" : "none";
//     if (tab === "dashboard") loadDashboard();
//   });
// });

// // ---------------------------------------------------------------------- init
// init();
// async function init() {
//   await loadSamples();
//   await loadState();
//   resetStageList();
//   loadApiKeyBadge();
//   document.getElementById("runBtn").addEventListener("click", startRun);
//   document.getElementById("resetStateBtn").addEventListener("click", async () => {
//     await fetch("/api/state/reset", {method: "POST"});
//     await loadState();
//   });
//   document.getElementById("refreshRunsBtn").addEventListener("click", loadDashboard);
//   document.getElementById("modalClose").addEventListener("click", () => {
//     document.getElementById("modalOverlay").style.display = "none";
//   });

//   const dz = document.getElementById("dropzone");
//   // const fileInput = document.getElementById("fileInput");

// const dropzone = document.getElementById("dropzone");
// const fileInput = document.getElementById("fileInput");

//   // 1. Prevent click events on the hidden file input from bubbling up to #dropzone
//   fileInput.addEventListener("click", (e) => {
//     e.stopPropagation();
//   });

//   // 2. Trigger fileInput.click() ONLY when clicking dropzone areas (not the input itself)
//   dropzone.addEventListener("click", (e) => {
//     if (e.target !== fileInput) {
//       fileInput.click();
//     }
//   });

//   dz.addEventListener("click", () => fileInput.click());
//   dz.addEventListener("dragover", e => { e.preventDefault(); dz.style.borderColor = "var(--amber)"; });
//   dz.addEventListener("dragleave", () => { dz.style.borderColor = ""; });
//   dz.addEventListener("drop", e => {
//     e.preventDefault(); dz.style.borderColor = "";
//     if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; handleFileChosen(); }
//   });
//   fileInput.addEventListener("change", handleFileChosen);

//   function handleFileChosen() {
//     const f = fileInput.files[0];
//     if (!f) return;
//     selectedFile = f; selectedSample = null;
//     document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("selected"));
//     document.getElementById("dropzoneFile").textContent = f.name;
//     document.getElementById("runBtn").disabled = false;
//   }
// }

// async function loadApiKeyBadge() {
//   const res = await fetch("/api/apikey-status");
//   const data = await res.json();
//   const badge = document.getElementById("apiKeyBadge");
//   if (data.live) {
//     badge.textContent = "OpenAI key live — Tier 2/3 real calls";
//     badge.className = "badge badge-live";
//   } else {
//     badge.textContent = "No API key — offline fallback mode";
//     badge.className = "badge badge-offline";
//   }
// }

// // ------------------------------------------------------------- sample picker
// async function loadSamples() {
//   const res = await fetch("/api/samples");
//   const samples = await res.json();
//   const grid = document.getElementById("sampleGrid");
//   grid.innerHTML = "";
//   samples.forEach(s => {
//     const card = document.createElement("button");
//     card.className = "sample-card";
//     card.dataset.scenario = s.scenario;
//     card.innerHTML = `<span class="sc-tag">${s.scenario === "happy_path" ? "Happy path" : "Edge case"}</span>
//       <span class="sc-label">${s.label}</span>
//       <span class="sc-desc">${s.description}</span>`;
//     card.addEventListener("click", () => {
//       selectedSample = s.file; selectedFile = null;
//       document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("selected"));
//       card.classList.add("selected");
//       document.getElementById("dropzoneFile").textContent = "";
//       document.getElementById("runBtn").disabled = false;
//       showStaticPreview(s.file);
//     });
//     grid.appendChild(card);
//   });
// }

// function showStaticPreview(sampleFile) {
//   const frame = document.getElementById("previewFrame");
//   const empty = document.getElementById("previewEmpty");
//   empty.style.display = "none";
//   frame.style.display = "";
//   const url = `/samples/${sampleFile}`;
//   if (sampleFile.toLowerCase().endsWith(".pdf")) {
//     frame.innerHTML = `<object data="${url}" type="application/pdf"><p>PDF preview</p></object>`;
//   } else {
//     frame.innerHTML = `<img src="${url}" alt="invoice preview">`;
//   }
//   hideStamp();
// }

// // ------------------------------------------------------------- stage ledger
// function resetStageList() {
//   stageState = {};
//   STAGE_ORDER.forEach(id => stageState[id] = {status: "pending"});
//   renderStageList();
// }

// function renderStageList() {
//   const list = document.getElementById("stageList");
//   list.innerHTML = "";
//   STAGE_ORDER.forEach(id => {
//     const st = stageState[id];
//     const row = document.createElement("li");
//     row.className = "stage-row" + (id === selectedStageId ? " active-select" : "");
//     row.dataset.status = st.status;
//     row.dataset.stage = id;
//     row.innerHTML = `<span class="stage-dot"></span>
//       <span class="stage-row-text">
//         <span class="stage-row-title">${STAGE_TITLES[id]}</span>
//         <span class="stage-row-sub">${statusSub(st)}</span>
//       </span>`;
//     row.addEventListener("click", () => selectStage(id));
//     list.appendChild(row);
//   });
// }
// function statusSub(st) {
//   if (st.status === "pending") return "waiting";
//   if (st.status === "running") return "running…";
//   if (st.status === "skipped") return "skipped";
//   if (st.status === "done") return "complete";
//   return "";
// }

// function selectStage(id) {
//   selectedStageId = id;
//   renderStageList();
//   const st = stageState[id] || {status: "pending"};
//   document.getElementById("detailStageTitle").textContent = STAGE_TITLES[id];
//   const body = document.getElementById("detailBody");
//   if (st.status === "pending") {
//     body.innerHTML = `<p class="muted">Not reached yet.</p>`; return;
//   }
//   let html = "";
//   if (st.detail && st.detail.length) {
//     html += "<ul>" + st.detail.map(d => `<li class="${severityClass(d)}">${escapeHtml(d)}</li>`).join("") + "</ul>";
//   }
//   if (st.payload) html += renderPayload(id, st.payload);
//   body.innerHTML = html || `<p class="muted">No further detail.</p>`;
// }
// function severityClass(text) {
//   if (/^\[critical\]/i.test(text)) return "critical";
//   if (/^\[warning\]/i.test(text)) return "warning";
//   return "";
// }

// function renderPayload(stageId, payload) {
//   let html = "";
//   if (payload.extraction) {
//     const c = payload.extraction.core_fields || {};
//     html += `<div class="kv-grid">
//       <div><span class="k">Invoice #</span><span class="v">${val(c.invoice_number)}</span></div>
//       <div><span class="k">Vendor</span><span class="v">${val(c.vendor_name)}</span></div>
//       <div><span class="k">PO #</span><span class="v">${val(c.po_number)}</span></div>
//       <div><span class="k">Invoice date</span><span class="v">${val(c.invoice_date)}</span></div>
//       <div><span class="k">Subtotal</span><span class="v">${money(c.subtotal)}</span></div>
//       <div><span class="k">Tax</span><span class="v">${money(c.tax_amount)} (${val(payload.extraction.tax_mode)})</span></div>
//       <div><span class="k">Total</span><span class="v">${money(c.total_amount)}</span></div>
//       <div><span class="k">Line items</span><span class="v">${(c.line_items||[]).length}</span></div>
//     </div>`;
//   }
//   if (payload.validation) {
//     html += `<p class="muted small">Confidence <b style="color:var(--ink-text)">${payload.validation.confidence_score}</b>/100</p>`;
//   }
//   if (payload.decision) {
//     html += `<span class="decision-chip ${payload.decision.decision}">${payload.decision.decision.replaceAll("_"," ")}</span><br/>`;
//     (payload.decision.flags||[]).forEach(f => html += `<span class="flag-pill">${f}</span>`);
//   }
//   return html;
// }
// function val(v) { return (v === null || v === undefined || v === "") ? '<span class="muted">—</span>' : escapeHtml(String(v)); }
// function money(v) { return (v === null || v === undefined) ? '<span class="muted">—</span>' : `$${Number(v).toFixed(2)}`; }
// function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// // ------------------------------------------------------------------ run flow
// async function startRun() {
//   resetStageList();
//   selectedStageId = null;
//   document.getElementById("detailBody").innerHTML = `<p class="muted">Starting…</p>`;
//   document.getElementById("correspondencePanel").style.display = "none";
//   hideStamp();
//   document.getElementById("runBtn").disabled = true;
//   document.getElementById("runStatusLabel").textContent = "Running…";

//   const form = new FormData();
//   if (selectedSample) {
//     form.append("sample", selectedSample);
//     showStaticPreview(selectedSample);
//   } else if (selectedFile) {
//     form.append("file", selectedFile);
//     const reader = new FileReader();
//     reader.onload = () => {
//       const frame = document.getElementById("previewFrame");
//       document.getElementById("previewEmpty").style.display = "none";
//       frame.style.display = "";
//       if (selectedFile.type === "application/pdf") {
//         frame.innerHTML = `<object data="${reader.result}" type="application/pdf"></object>`;
//       } else {
//         frame.innerHTML = `<img src="${reader.result}">`;
//       }
//     };
//     reader.readAsDataURL(selectedFile);
//   } else {
//     return;
//   }

//   const res = await fetch("/api/run", {method: "POST", body: form});
//   const data = await res.json();
//   if (data.error) { alert(data.error); document.getElementById("runBtn").disabled = false; return; }
//   currentRunId = data.run_id;
//   streamRun(currentRunId);
// }

// function streamRun(runId) {
//   const es = new EventSource(`/api/stream/${runId}`);
//   es.onmessage = (e) => {
//     const evt = JSON.parse(e.data);
//     if (evt.type === "stage") {
//       stageState[evt.stage] = {status: evt.status, detail: evt.detail, payload: evt.payload};
//       renderStageList();
//       if (evt.status === "running" || (!selectedStageId)) selectStage(evt.stage);
//       if (selectedStageId === evt.stage) selectStage(evt.stage);
//     } else if (evt.type === "result") {
//       currentSourceFile = evt.payload.source_file;
//       onResult(evt.payload);
//     } else if (evt.type === "error") {
//       document.getElementById("runStatusLabel").textContent = "Error";
//       alert("Pipeline error: " + evt.message);
//     } else if (evt.type === "end") {
//       document.getElementById("runBtn").disabled = false;
//       document.getElementById("runStatusLabel").textContent = "Done";
//       es.close();
//       loadState();
//     }
//   };
//   es.onerror = () => { es.close(); document.getElementById("runBtn").disabled = false; };
// }

// function onResult(result) {
//   const decision = result.decision.decision;
//   showStamp(decision);
//   if (result.correspondence && decision === "AWAITING_VENDOR_INFO") {
//     showCorrespondence(result);
//   }
// }

// function showStamp(decision) {
//   const el = document.getElementById("stampEl");
//   const map = {
//     AUTO_APPROVE: ["APPROVED", "approve"],
//     APPROVE_WITH_NOTE: ["APPROVED*", "approve"],
//     HOLD_FOR_REVIEW: ["HOLD", "hold"],
//     REJECT_DUPLICATE: ["REJECTED", "reject"],
//     AWAITING_VENDOR_INFO: ["AWAITING VENDOR", "wait"],
//   };
//   const [text, cls] = map[decision] || ["REVIEW", "hold"];
//   el.textContent = text;
//   el.className = "stamp " + cls;
//   requestAnimationFrame(() => el.classList.add("show"));
// }
// function hideStamp() {
//   const el = document.getElementById("stampEl");
//   el.className = "stamp"; el.classList.remove("show");
// }

// // -------------------------------------------------------- vendor reply flow
// function showCorrespondence(result) {
//   const panel = document.getElementById("correspondencePanel");
//   panel.style.display = "";
//   const corr = result.correspondence;
//   const msg = corr.messages[0];
//   document.getElementById("corrEmail").textContent = `Subject: ${msg.subject}\n\n${msg.body}`;

//   const flags = result.decision.flags || [];
//   const fieldsNeeded = [];
//   if (flags.includes("missing_mandatory_core_fields")) fieldsNeeded.push("invoice_number", "po_number", "invoice_date");
//   if (flags.includes("no_po_match")) fieldsNeeded.push("po_number");
//   if (flags.includes("duplicate") || flags.includes("soft_duplicate")) fieldsNeeded.push("invoice_number");
//   if (!fieldsNeeded.length) fieldsNeeded.push("po_number");
//   const unique = [...new Set(fieldsNeeded)];

//   const container = document.getElementById("corrFields");
//   container.innerHTML = "";
//   unique.forEach(f => {
//     const wrap = document.createElement("div");
//     wrap.innerHTML = `<label class="field-label">${f.replaceAll("_"," ")}</label>
//       <input type="text" data-field="${f}" placeholder="e.g. ${placeholderFor(f)}">`;
//     container.appendChild(wrap);
//   });
//   document.getElementById("corrReplyBody").value =
//     "Thanks for flagging — apologies for the omission. Please see the corrected detail above; let me know if you need anything else to process this.";

//   document.getElementById("corrSendBtn").onclick = () => sendVendorReply(result);
// }
// function placeholderFor(f) {
//   if (f === "po_number") return "PO-90210";
//   if (f === "invoice_number") return "INV-30044";
//   if (f === "invoice_date") return "04/02/2026";
//   return "";
// }

// async function sendVendorReply(result) {
//   const corrected_fields = {};
//   document.querySelectorAll("#corrFields input").forEach(inp => {
//     if (inp.value.trim()) corrected_fields[inp.dataset.field] = inp.value.trim();
//   });
//   const reply_body = document.getElementById("corrReplyBody").value;

//   document.getElementById("runBtn").disabled = true;
//   document.getElementById("runStatusLabel").textContent = "Reprocessing…";

//   const res = await fetch("/api/vendor-reply", {
//     method: "POST", headers: {"Content-Type": "application/json"},
//     body: JSON.stringify({
//       source_file: currentSourceFile, corrected_fields, reply_body,
//       parent_run_id: currentRunId,
//     }),
//   });
//   const data = await res.json();
//   currentRunId = data.run_id;
//   streamRun(currentRunId);
// }

// // ------------------------------------------------------------ system state
// async function loadState() {
//   const res = await fetch("/api/state");
//   const state = await res.json();
//   const poBody = document.querySelector("#poTable tbody");
//   poBody.innerHTML = state.purchase_orders.map(po => `
//     <tr><td>${po.po_number}</td><td>${po.vendor_name}</td><td>$${po.amount.toFixed(2)}</td>
//         <td>$${po.amount_invoiced.toFixed(2)}</td><td>$${(po.amount - po.amount_invoiced).toFixed(2)}</td>
//         <td>${po.approved_vendor ? "yes" : "NO"}</td></tr>`).join("");

//   const corrBody = document.querySelector("#corrTable tbody");
//   corrBody.innerHTML = state.correspondence_threads.length
//     ? state.correspondence_threads.map(t => `
//       <tr><td>${t.correspondence_id}</td><td>${t.vendor_name||"—"}</td><td>${t.status}</td><td>${t.reason}</td></tr>`).join("")
//     : `<tr><td colspan="4" class="muted">No open threads.</td></tr>`;
// }

// // -------------------------------------------------------------- dashboard
// async function loadDashboard() {
//   const [statsRes, runsRes] = await Promise.all([fetch("/api/stats"), fetch("/api/runs")]);
//   const stats = await statsRes.json();
//   const runs = await runsRes.json();

//   const strip = document.getElementById("statStrip");
//   strip.innerHTML = `
//     <div class="stat-cell"><span class="stat-label">Total runs</span><span class="stat-value">${stats.total}</span></div>
//     <div class="stat-cell"><span class="stat-label">Avg confidence</span><span class="stat-value">${stats.avg_confidence ? stats.avg_confidence.toFixed(0) : "—"}</span></div>
//     <div class="stat-cell"><span class="stat-label">Avg latency</span><span class="stat-value">${stats.avg_duration_ms ? (stats.avg_duration_ms/1000).toFixed(1)+"s" : "—"}</span></div>
//     <div class="stat-cell"><span class="stat-label">Auto-approved</span><span class="stat-value">${stats.by_decision.AUTO_APPROVE||0}</span></div>
//     <div class="stat-cell"><span class="stat-label">Held for review</span><span class="stat-value">${stats.by_decision.HOLD_FOR_REVIEW||0}</span></div>
//   `;

//   const tbody = document.querySelector("#runsTable tbody");
//   tbody.innerHTML = runs.map(r => `
//     <tr data-id="${r.id}">
//       <td>${new Date(r.created_at).toLocaleString()}</td>
//       <td>${r.source_name}</td>
//       <td>${r.scenario_label}${r.parent_run_id ? " ↳ reprocessed" : ""}</td>
//       <td>${r.tier_used}</td>
//       <td>${r.confidence}</td>
//       <td>${r.match_status}</td>
//       <td class="decision-text ${r.decision}">${r.decision.replaceAll("_"," ")}</td>
//       <td>${r.requires_review ? "yes" : "no"}</td>
//     </tr>`).join("") || `<tr><td colspan="8" class="muted">No runs yet — go run something in Live Run.</td></tr>`;

//   tbody.querySelectorAll("tr[data-id]").forEach(tr => {
//     tr.addEventListener("click", () => openRunModal(tr.dataset.id));
//   });
// }

// async function openRunModal(runId) {
//   const res = await fetch(`/api/runs/${runId}`);
//   const data = await res.json();
//   document.getElementById("modalTitle").textContent = `${data.source_name} — ${data.decision}`;
//   const r = data.result;
//   let html = `<span class="decision-chip ${r.decision.decision}">${r.decision.decision.replaceAll("_"," ")}</span>`;
//   html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Reasoning trail</h4><ul>` +
//     r.decision.reasoning_trail.map(x => `<li>${escapeHtml(x)}</li>`).join("") + `</ul>`;
//   html += renderPayload("modal", {extraction: r.extraction, validation: r.validation});
//   html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Match reasoning</h4><ul>` +
//     r.match.reasoning.map(x => `<li>${escapeHtml(x)}</li>`).join("") + `</ul>`;
//   if (r.correspondence) {
//     html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Correspondence</h4>` +
//       `<div class="corr-email">${escapeHtml(r.correspondence.messages.map(m => `[${m.direction}] ${m.subject}\n${m.body}`).join("\n\n---\n\n"))}</div>`;
//   }
//   document.getElementById("modalBody").innerHTML = html;
//   document.getElementById("modalOverlay").style.display = "flex";
// }


const STAGE_TITLES = {
  ingest: "Ingest file",
  tier1: "Tier 1 — Native PDF extraction",
  validate1: "Validate Tier 1 extraction",
  escalate1: "Escalation gate (Tier 1 → Tier 2)",
  tier2: "Tier 2 — OCR + Text LLM",
  validate2: "Validate Tier 2 extraction",
  escalate2: "Escalation gate (Tier 2 → Tier 3)",
  tier3: "Tier 3 — Vision LLM",
  validate3: "Validate final extraction",
  match: "PO matching engine",
  decision: "Decision engine",
  correspondence: "Vendor correspondence",
  ledger: "Record to ledger / history",
};
const STAGE_ORDER = Object.keys(STAGE_TITLES);

let selectedSample = null;
let selectedFile = null;
let currentRunId = null;
let stageState = {};   // stage_id -> {status, detail, payload}
let selectedStageId = null;
let currentSourceFile = null;   // server-side path, needed for vendor-reply reprocessing

// ---------------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("view-run").style.display = tab === "run" ? "" : "none";
    document.getElementById("view-dashboard").style.display = tab === "dashboard" ? "" : "none";
    if (tab === "dashboard") loadDashboard();
  });
});

// ---------------------------------------------------------------------- init
init();
async function init() {
  await loadSamples();
  await loadState();
  resetStageList();
  loadApiKeyBadge();
  document.getElementById("runBtn").addEventListener("click", startRun);
  document.getElementById("resetStateBtn").addEventListener("click", async () => {
    await fetch("/api/state/reset", {method: "POST"});
    await loadState();
  });
  document.getElementById("refreshRunsBtn").addEventListener("click", loadDashboard);
  document.getElementById("modalClose").addEventListener("click", () => {
    document.getElementById("modalOverlay").style.display = "none";
  });

  const dz = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");

  // Prevent click events on the hidden file input from bubbling up to #dropzone
  fileInput.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  // Trigger fileInput.click() ONLY when clicking dropzone areas (not the input itself)
  dz.addEventListener("click", (e) => {
    if (e.target !== fileInput) {
      fileInput.click();
    }
  });

  dz.addEventListener("dragover", e => { e.preventDefault(); dz.style.borderColor = "var(--amber)"; });
  dz.addEventListener("dragleave", () => { dz.style.borderColor = ""; });
  dz.addEventListener("drop", e => {
    e.preventDefault(); dz.style.borderColor = "";
    if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; handleFileChosen(); }
  });
  fileInput.addEventListener("change", handleFileChosen);

  function handleFileChosen() {
    const f = fileInput.files[0];
    if (!f) return;
    selectedFile = f; selectedSample = null;
    document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("selected"));
    document.getElementById("dropzoneFile").textContent = f.name;
    document.getElementById("runBtn").disabled = false;
  }
}

async function loadApiKeyBadge() {
  const res = await fetch("/api/apikey-status");
  const data = await res.json();
  const badge = document.getElementById("apiKeyBadge");
  if (data.live) {
    badge.textContent = "OpenAI key live — Tier 2/3 real calls";
    badge.className = "badge badge-live";
  } else {
    badge.textContent = "No API key — offline fallback mode";
    badge.className = "badge badge-offline";
  }
}

// ------------------------------------------------------------- sample picker
async function loadSamples() {
  const res = await fetch("/api/samples");
  const samples = await res.json();
  const grid = document.getElementById("sampleGrid");
  grid.innerHTML = "";
  samples.forEach(s => {
    const card = document.createElement("button");
    card.className = "sample-card";
    card.dataset.scenario = s.scenario;
    card.innerHTML = `<span class="sc-tag">${s.scenario === "happy_path" ? "Happy path" : "Edge case"}</span>
      <span class="sc-label">${s.label}</span>
      <span class="sc-desc">${s.description}</span>`;
    card.addEventListener("click", () => {
      selectedSample = s.file; selectedFile = null;
      document.querySelectorAll(".sample-card").forEach(c => c.classList.remove("selected"));
      card.classList.add("selected");
      document.getElementById("dropzoneFile").textContent = "";
      document.getElementById("runBtn").disabled = false;
      showStaticPreview(s.file);
    });
    grid.appendChild(card);
  });
}

function showStaticPreview(sampleFile) {
  const frame = document.getElementById("previewFrame");
  const empty = document.getElementById("previewEmpty");
  empty.style.display = "none";
  frame.style.display = "";
  const url = `/samples/${sampleFile}`;
  if (sampleFile.toLowerCase().endsWith(".pdf")) {
    frame.innerHTML = `<object data="${url}" type="application/pdf"><p>PDF preview</p></object>`;
  } else {
    frame.innerHTML = `<img src="${url}" alt="invoice preview">`;
  }
  hideStamp();
}

// ------------------------------------------------------------- stage ledger
function resetStageList() {
  stageState = {};
  STAGE_ORDER.forEach(id => stageState[id] = {status: "pending"});
  renderStageList();
}

function renderStageList() {
  const list = document.getElementById("stageList");
  list.innerHTML = "";
  STAGE_ORDER.forEach(id => {
    const st = stageState[id];
    const row = document.createElement("li");
    row.className = "stage-row" + (id === selectedStageId ? " active-select" : "");
    row.dataset.status = st.status;
    row.dataset.stage = id;
    row.innerHTML = `<span class="stage-dot"></span>
      <span class="stage-row-text">
        <span class="stage-row-title">${STAGE_TITLES[id]}</span>
        <span class="stage-row-sub">${statusSub(st)}</span>
      </span>`;
    row.addEventListener("click", () => selectStage(id));
    list.appendChild(row);
  });
}
function statusSub(st) {
  if (st.status === "pending") return "waiting";
  if (st.status === "running") return "running…";
  if (st.status === "skipped") return "skipped";
  if (st.status === "done") return "complete";
  return "";
}

function selectStage(id) {
  selectedStageId = id;
  renderStageList();
  const st = stageState[id] || {status: "pending"};
  document.getElementById("detailStageTitle").textContent = STAGE_TITLES[id];
  const body = document.getElementById("detailBody");
  if (st.status === "pending") {
    body.innerHTML = `<p class="muted">Not reached yet.</p>`; return;
  }
  let html = "";
  if (st.detail && st.detail.length) {
    html += "<ul>" + st.detail.map(d => `<li class="${severityClass(d)}">${escapeHtml(d)}</li>`).join("") + "</ul>";
  }
  if (st.payload) html += renderPayload(id, st.payload);
  body.innerHTML = html || `<p class="muted">No further detail.</p>`;
}
function severityClass(text) {
  if (/^\[critical\]/i.test(text)) return "critical";
  if (/^\[warning\]/i.test(text)) return "warning";
  return "";
}

function renderPayload(stageId, payload) {
  let html = "";
  if (payload.extraction) {
    const c = payload.extraction.core_fields || {};
    html += `<div class="kv-grid">
      <div><span class="k">Invoice #</span><span class="v">${val(c.invoice_number)}</span></div>
      <div><span class="k">Vendor</span><span class="v">${val(c.vendor_name)}</span></div>
      <div><span class="k">PO #</span><span class="v">${val(c.po_number)}</span></div>
      <div><span class="k">Invoice date</span><span class="v">${val(c.invoice_date)}</span></div>
      <div><span class="k">Subtotal</span><span class="v">${money(c.subtotal)}</span></div>
      <div><span class="k">Tax</span><span class="v">${money(c.tax_amount)} (${val(payload.extraction.tax_mode)})</span></div>
      <div><span class="k">Total</span><span class="v">${money(c.total_amount)}</span></div>
      <div><span class="k">Line items</span><span class="v">${(c.line_items||[]).length}</span></div>
    </div>`;
  }
  if (payload.validation) {
    html += `<p class="muted small">Confidence <b style="color:var(--ink-text)">${payload.validation.confidence_score}</b>/100</p>`;
  }
  if (payload.decision) {
    html += `<span class="decision-chip ${payload.decision.decision}">${payload.decision.decision.replaceAll("_"," ")}</span><br/>`;
    (payload.decision.flags||[]).forEach(f => html += `<span class="flag-pill">${f}</span>`);
  }
  return html;
}
function val(v) { return (v === null || v === undefined || v === "") ? '<span class="muted">—</span>' : escapeHtml(String(v)); }
function money(v) { return (v === null || v === undefined) ? '<span class="muted">—</span>' : `$${Number(v).toFixed(2)}`; }
function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ------------------------------------------------------------------ run flow
async function startRun() {
  resetStageList();
  selectedStageId = null;
  document.getElementById("detailBody").innerHTML = `<p class="muted">Starting…</p>`;
  document.getElementById("correspondencePanel").style.display = "none";
  hideStamp();
  document.getElementById("runBtn").disabled = true;
  document.getElementById("runStatusLabel").textContent = "Running…";

  const form = new FormData();
  if (selectedSample) {
    form.append("sample", selectedSample);
    showStaticPreview(selectedSample);
  } else if (selectedFile) {
    form.append("file", selectedFile);
    const reader = new FileReader();
    reader.onload = () => {
      const frame = document.getElementById("previewFrame");
      document.getElementById("previewEmpty").style.display = "none";
      frame.style.display = "";
      if (selectedFile.type === "application/pdf") {
        frame.innerHTML = `<object data="${reader.result}" type="application/pdf"></object>`;
      } else {
        frame.innerHTML = `<img src="${reader.result}">`;
      }
    };
    reader.readAsDataURL(selectedFile);
  } else {
    return;
  }

  const res = await fetch("/api/run", {method: "POST", body: form});
  const data = await res.json();
  if (data.error) { alert(data.error); document.getElementById("runBtn").disabled = false; return; }
  currentRunId = data.run_id;
  streamRun(currentRunId);
}

function streamRun(runId) {
  const es = new EventSource(`/api/stream/${runId}`);
  es.onmessage = (e) => {
    const evt = JSON.parse(e.data);
    if (evt.type === "stage") {
      stageState[evt.stage] = {status: evt.status, detail: evt.detail, payload: evt.payload};
      renderStageList();
      if (evt.status === "running" || (!selectedStageId)) selectStage(evt.stage);
      if (selectedStageId === evt.stage) selectStage(evt.stage);
    } else if (evt.type === "result") {
      currentSourceFile = evt.payload.source_file;
      onResult(evt.payload);
    } else if (evt.type === "error") {
      document.getElementById("runStatusLabel").textContent = "Error";
      alert("Pipeline error: " + evt.message);
    } else if (evt.type === "end") {
      document.getElementById("runBtn").disabled = false;
      document.getElementById("runStatusLabel").textContent = "Done";
      es.close();
      loadState();
    }
  };
  es.onerror = () => { es.close(); document.getElementById("runBtn").disabled = false; };
}

function onResult(result) {
  const decision = result.decision.decision;
  showStamp(decision);
  if (result.correspondence && decision === "AWAITING_VENDOR_INFO") {
    showCorrespondence(result);
  }
}

function showStamp(decision) {
  const el = document.getElementById("stampEl");
  const map = {
    AUTO_APPROVE: ["APPROVED", "approve"],
    APPROVE_WITH_NOTE: ["APPROVED*", "approve"],
    HOLD_FOR_REVIEW: ["HOLD", "hold"],
    REJECT_DUPLICATE: ["REJECTED", "reject"],
    AWAITING_VENDOR_INFO: ["AWAITING VENDOR", "wait"],
  };
  const [text, cls] = map[decision] || ["REVIEW", "hold"];
  el.textContent = text;
  el.className = "stamp " + cls;
  requestAnimationFrame(() => el.classList.add("show"));
}
function hideStamp() {
  const el = document.getElementById("stampEl");
  el.className = "stamp"; el.classList.remove("show");
}

// -------------------------------------------------------- vendor reply flow
function showCorrespondence(result) {
  const panel = document.getElementById("correspondencePanel");
  panel.style.display = "";
  const corr = result.correspondence;
  const msg = corr.messages[0];
  document.getElementById("corrEmail").textContent = `Subject: ${msg.subject}\n\n${msg.body}`;

  const flags = result.decision.flags || [];
  const fieldsNeeded = [];
  if (flags.includes("missing_mandatory_core_fields")) fieldsNeeded.push("invoice_number", "po_number", "invoice_date");
  if (flags.includes("no_po_match")) fieldsNeeded.push("po_number");
  if (flags.includes("duplicate") || flags.includes("soft_duplicate")) fieldsNeeded.push("invoice_number");
  if (!fieldsNeeded.length) fieldsNeeded.push("po_number");
  const unique = [...new Set(fieldsNeeded)];

  const container = document.getElementById("corrFields");
  container.innerHTML = "";
  unique.forEach(f => {
    const wrap = document.createElement("div");
    wrap.innerHTML = `<label class="field-label">${f.replaceAll("_"," ")}</label>
      <input type="text" data-field="${f}" placeholder="e.g. ${placeholderFor(f)}">`;
    container.appendChild(wrap);
  });
  document.getElementById("corrReplyBody").value =
    "Thanks for flagging — apologies for the omission. Please see the corrected detail above; let me know if you need anything else to process this.";

  document.getElementById("corrSendBtn").onclick = () => sendVendorReply(result);
}
function placeholderFor(f) {
  if (f === "po_number") return "PO-90210";
  if (f === "invoice_number") return "INV-30044";
  if (f === "invoice_date") return "04/02/2026";
  return "";
}

async function sendVendorReply(result) {
  const corrected_fields = {};
  document.querySelectorAll("#corrFields input").forEach(inp => {
    if (inp.value.trim()) corrected_fields[inp.dataset.field] = inp.value.trim();
  });
  const reply_body = document.getElementById("corrReplyBody").value;

  document.getElementById("runBtn").disabled = true;
  document.getElementById("runStatusLabel").textContent = "Reprocessing…";

  const res = await fetch("/api/vendor-reply", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      source_file: currentSourceFile, corrected_fields, reply_body,
      parent_run_id: currentRunId,
    }),
  });
  const data = await res.json();
  currentRunId = data.run_id;
  streamRun(currentRunId);
}

// ------------------------------------------------------------ system state
async function loadState() {
  const res = await fetch("/api/state");
  const state = await res.json();
  const poBody = document.querySelector("#poTable tbody");
  poBody.innerHTML = state.purchase_orders.map(po => `
    <tr><td>${po.po_number}</td><td>${po.vendor_name}</td><td>$${po.amount.toFixed(2)}</td>
        <td>$${po.amount_invoiced.toFixed(2)}</td><td>$${(po.amount - po.amount_invoiced).toFixed(2)}</td>
        <td>${po.approved_vendor ? "yes" : "NO"}</td></tr>`).join("");

  const corrBody = document.querySelector("#corrTable tbody");
  corrBody.innerHTML = state.correspondence_threads.length
    ? state.correspondence_threads.map(t => `
      <tr><td>${t.correspondence_id}</td><td>${t.vendor_name||"—"}</td><td>${t.status}</td><td>${t.reason}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">No open threads.</td></tr>`;
}

// -------------------------------------------------------------- dashboard
async function loadDashboard() {
  const [statsRes, runsRes] = await Promise.all([fetch("/api/stats"), fetch("/api/runs")]);
  const stats = await statsRes.json();
  const runs = await runsRes.json();

  const strip = document.getElementById("statStrip");
  strip.innerHTML = `
    <div class="stat-cell"><span class="stat-label">Total runs</span><span class="stat-value">${stats.total}</span></div>
    <div class="stat-cell"><span class="stat-label">Avg confidence</span><span class="stat-value">${stats.avg_confidence ? stats.avg_confidence.toFixed(0) : "—"}</span></div>
    <div class="stat-cell"><span class="stat-label">Avg latency</span><span class="stat-value">${stats.avg_duration_ms ? (stats.avg_duration_ms/1000).toFixed(1)+"s" : "—"}</span></div>
    <div class="stat-cell"><span class="stat-label">Auto-approved</span><span class="stat-value">${stats.by_decision.AUTO_APPROVE||0}</span></div>
    <div class="stat-cell"><span class="stat-label">Held for review</span><span class="stat-value">${stats.by_decision.HOLD_FOR_REVIEW||0}</span></div>
  `;

  const tbody = document.querySelector("#runsTable tbody");
  tbody.innerHTML = runs.map(r => `
    <tr data-id="${r.id}">
      <td>${new Date(r.created_at).toLocaleString()}</td>
      <td>${r.source_name}</td>
      <td>${r.scenario_label}${r.parent_run_id ? " ↳ reprocessed" : ""}</td>
      <td>${r.tier_used}</td>
      <td>${r.confidence}</td>
      <td>${r.match_status}</td>
      <td class="decision-text ${r.decision}">${r.decision.replaceAll("_"," ")}</td>
      <td>${r.requires_review ? "yes" : "no"}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="muted">No runs yet — go run something in Live Run.</td></tr>`;

  tbody.querySelectorAll("tr[data-id]").forEach(tr => {
    tr.addEventListener("click", () => openRunModal(tr.dataset.id));
  });
}

async function openRunModal(runId) {
  const res = await fetch(`/api/runs/${runId}`);
  const data = await res.json();
  document.getElementById("modalTitle").textContent = `${data.source_name} — ${data.decision}`;
  const r = data.result;
  let html = `<span class="decision-chip ${r.decision.decision}">${r.decision.decision.replaceAll("_"," ")}</span>`;
  html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Reasoning trail</h4><ul>` +
    r.decision.reasoning_trail.map(x => `<li>${escapeHtml(x)}</li>`).join("") + `</ul>`;
  html += renderPayload("modal", {extraction: r.extraction, validation: r.validation});
  html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Match reasoning</h4><ul>` +
    r.match.reasoning.map(x => `<li>${escapeHtml(x)}</li>`).join("") + `</ul>`;
  if (r.correspondence) {
    html += `<h4 style="font-family:var(--font-display);margin:14px 0 6px;">Correspondence</h4>` +
      `<div class="corr-email">${escapeHtml(r.correspondence.messages.map(m => `[${m.direction}] ${m.subject}\n${m.body}`).join("\n\n---\n\n"))}</div>`;
  }
  document.getElementById("modalBody").innerHTML = html;
  document.getElementById("modalOverlay").style.display = "flex";
}