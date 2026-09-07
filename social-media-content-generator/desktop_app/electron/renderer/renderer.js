// Renderer: talks to the local FastAPI backend over HTTP.
const BACKEND = window.studio.backendUrl;

const $ = (id) => document.getElementById(id);
const log = (msg) => {
  $("log").textContent += msg + "\n";
  $("log").scrollTop = $("log").scrollHeight;
};

async function checkHealth() {
  try {
    const r = await fetch(`${BACKEND}/api/health`);
    const h = await r.json();
    const badges = Object.entries(h.integrations)
      .map(([k, v]) => `<span class="badge ${v ? "ok" : "off"}">${k}${v ? " ✓" : " ✗"}</span>`)
      .join("");
    $("health").innerHTML = badges;
  } catch (e) {
    $("health").innerHTML = `<span class="badge off">backend offline</span>`;
  }
}

// ---- Step 1: script ----
$("genScript").addEventListener("click", async () => {
  const goal = $("goal").value.trim();
  if (!goal) return alert("Enter a goal first.");
  $("genScript").disabled = true;
  $("genScript").textContent = "Writing…";
  try {
    const form = new FormData();
    form.append("goal", goal);
    form.append("platform", $("platform").value);
    form.append("tone", $("tone").value);
    form.append("seconds", $("seconds").value);
    const r = await fetch(`${BACKEND}/api/script`, { method: "POST", body: form });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const { script, review } = await r.json();
    fillScript(script);
    $("scriptFields").classList.remove("hidden");
    $("genVideo").disabled = false;
    log(`Script ready (review score ${review.score}/10).`);
  } catch (e) {
    log("Script error: " + e.message);
  } finally {
    $("genScript").disabled = false;
    $("genScript").textContent = "Generate script";
  }
});

function fillScript(s) {
  $("f_title").value = s.title || "";
  $("f_hook").value = s.hook || "";
  $("f_body").value = s.body || "";
  $("f_cta").value = s.call_to_action || "";
  $("f_narration").value = s.narration || "";
  $("f_caption").value = s.caption || "";
  $("f_hashtags").value = (s.hashtags || []).join(", ");
}

function scriptFromForm() {
  return {
    title: $("f_title").value,
    hook: $("f_hook").value,
    body: $("f_body").value,
    call_to_action: $("f_cta").value,
    narration: $("f_narration").value,
    caption: $("f_caption").value,
    hashtags: $("f_hashtags").value.split(",").map((s) => s.trim()).filter(Boolean),
  };
}

// ---- Step 2: video ----
$("genVideo").addEventListener("click", async () => {
  const script = scriptFromForm();
  if (!script.narration.trim()) return alert("Narration is empty.");
  $("genVideo").disabled = true;
  $("preview").classList.add("hidden");

  const form = new FormData();
  form.append("goal", $("goal").value.trim());
  form.append("script_json", JSON.stringify(script));
  form.append("seconds", $("seconds").value);
  form.append("compose", $("compose").checked ? "true" : "false");
  form.append("max_frame_revisions", $("frameRev").value);
  if ($("face").files[0]) form.append("face_image", $("face").files[0]);
  for (const f of $("products").files) form.append("product_images", f);

  try {
    const r = await fetch(`${BACKEND}/api/generate`, { method: "POST", body: form });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    const { job_id } = await r.json();
    log(`Job started: ${job_id}`);
    pollJob(job_id);
  } catch (e) {
    log("Generate error: " + e.message);
    $("genVideo").disabled = false;
  }
});

async function pollJob(jobId) {
  let seen = 0;
  const timer = setInterval(async () => {
    let job;
    try {
      job = await (await fetch(`${BACKEND}/api/jobs/${jobId}`)).json();
    } catch {
      return;
    }
    for (; seen < job.events.length; seen++) {
      const ev = job.events[seen];
      log("  • " + ev.stage + (ev.payload?.name ? `: ${ev.payload.name}` : ""));
    }
    if (job.status === "done") {
      clearInterval(timer);
      $("genVideo").disabled = false;
      const rel = job.result?.video_rel;
      if (rel) {
        const v = $("preview");
        v.src = `${BACKEND}/api/files/${jobId}/${rel}`;
        v.classList.remove("hidden");
        log("Done. Video ready below.");
      } else {
        log("Done, but no video file was produced (script-only?).");
      }
    } else if (job.status === "error") {
      clearInterval(timer);
      $("genVideo").disabled = false;
      log("FAILED: " + job.error);
    }
  }, 1500);
}

checkHealth();
