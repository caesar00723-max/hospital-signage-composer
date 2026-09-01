// 병원 간판 합성 웹 폼 — GitHub Contents API + Actions API 연동
// 토큰은 localStorage에만 저장되며 이 브라우저 밖으로 전송되지 않는다
// (GitHub API 호출 시 Authorization 헤더로만 사용).

const LS_KEY = "signage_composer_settings_v1";

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveSettings(s) {
  localStorage.setItem(LS_KEY, JSON.stringify(s));
}

function $(id) { return document.getElementById(id); }

function setStatus(text, cls) {
  const el = $("status");
  el.textContent = text;
  el.className = "status" + (cls ? " " + cls : "");
}

function appendStatus(text) {
  $("status").textContent += "\n" + text;
}

// ---- 초기 로드: 저장된 설정 채워넣기 ----
window.addEventListener("DOMContentLoaded", () => {
  const s = loadSettings();
  if (s.owner) $("owner").value = s.owner;
  if (s.repo) $("repo").value = s.repo;
  if (s.token) $("token").value = s.token;
  if (!s.owner || !s.repo || !s.token) {
    $("settingsBox").open = true;
  }

  $("panelColorPicker").addEventListener("input", (e) => {
    $("panelColor").value = e.target.value.toUpperCase();
  });
  $("panelColor").addEventListener("input", (e) => {
    const v = e.target.value;
    if (/^#[0-9a-fA-F]{6}$/.test(v)) $("panelColorPicker").value = v;
  });

  $("ledColorPicker").addEventListener("input", (e) => {
    $("ledColor").value = e.target.value.toUpperCase();
  });
  $("ledColor").addEventListener("input", (e) => {
    const v = e.target.value;
    if (/^#[0-9a-fA-F]{6}$/.test(v)) $("ledColorPicker").value = v;
  });
});

$("saveSettings").addEventListener("click", () => {
  const s = {
    owner: $("owner").value.trim(),
    repo: $("repo").value.trim(),
    token: $("token").value.trim(),
  };
  saveSettings(s);
  $("saveMsg").textContent = "저장됨";
  setTimeout(() => ($("saveMsg").textContent = ""), 2000);
});

// ---- 유틸 ----
function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result.split(",")[1]);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function timestampName(originalName) {
  const ext = (originalName.split(".").pop() || "png").toLowerCase();
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  return `${stamp}.${ext}`;
}

async function gh(path, { owner, repo, token }, opts = {}) {
  const res = await fetch(`https://api.github.com/repos/${owner}/${repo}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API 오류 (${res.status}): ${body.slice(0, 300)}`);
  }
  return res.status === 204 ? null : res.json();
}

// ---- 메인 흐름 ----
$("composeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const settings = loadSettings();
  if (!settings.owner || !settings.repo || !settings.token) {
    setStatus("먼저 상단 '저장소 연결 설정'을 채우고 저장하세요.", "error");
    $("settingsBox").open = true;
    return;
  }

  const fileInput = $("imageFile");
  if (!fileInput.files.length) {
    setStatus("이미지 파일을 선택하세요.", "error");
    return;
  }
  const file = fileInput.files[0];
  const nameKr = $("nameKr").value.trim();
  const nameEn = $("nameEn").value.trim();
  const panelColor = $("panelColor").value.trim();
  const weight = $("weight").value;
  const material = $("material").value;
  const ledColor = $("ledColor").value.trim();
  const depth = $("depth").value.trim() || "auto";
  const vertical = $("vertical").checked;

  const btn = $("submitBtn");
  btn.disabled = true;

  try {
    setStatus("① 기본 브랜치 확인 중...");
    const repoInfo = await gh("", settings);
    const branch = repoInfo.default_branch || "main";

    setStatus("② 이미지를 저장소에 업로드하는 중...");
    const base64 = await fileToBase64(file);
    const remoteName = timestampName(file.name);
    const remotePath = `inputs/${remoteName}`;

    await gh(`/contents/${remotePath}`, settings, {
      method: "PUT",
      body: JSON.stringify({
        message: `chore: add input image ${remoteName}`,
        content: base64,
        branch,
      }),
    });

    appendStatus(`   업로드 완료 → ${remotePath}`);
    setStatus($("status").textContent); // keep accumulated text

    appendStatus("③ GitHub Actions 워크플로우 실행 요청 중...");
    const dispatchAt = Date.now();
    await gh(`/actions/workflows/compose-signage.yml/dispatches`, settings, {
      method: "POST",
      body: JSON.stringify({
        ref: branch,
        inputs: {
          image_path: remotePath,
          name_kr: nameKr,
          name_en: nameEn,
          panel_color: panelColor,
          material: material,
          led_color: ledColor,
          depth: depth,
          weight: weight,
          vertical: vertical ? "true" : "false",
        },
      }),
    });

    const actionsUrl = `https://github.com/${settings.owner}/${settings.repo}/actions`;
    appendStatus("④ 실행 요청 완료. 워크플로우 실행을 자동으로 기다리는 중...");
    setStatus($("status").textContent);

    const run = await findTriggeredRun(settings, dispatchAt);
    appendStatus(`   실행 확인됨 (run #${run.run_number}) — 완료될 때까지 기다립니다...`);
    setStatus($("status").textContent);

    const finished = await pollRunUntilDone(settings, run.id, (s) => {
      appendStatus(`   상태: ${translateStatus(s)}`);
      setStatus($("status").textContent);
    });

    if (finished.conclusion !== "success") {
      appendStatus(`⚠️ 실행이 실패로 종료됐습니다 (${finished.conclusion}).`);
      appendStatus(`   로그 확인: ${finished.html_url}`);
      setStatus($("status").textContent, "error");
      return;
    }

    appendStatus("⑤ 결과물을 불러오는 중...");
    setStatus($("status").textContent);

    const outPath = `outputs/composed_${remoteName}`;
    const dataUrl = await fetchImageAsDataUrl(settings, outPath, branch);

    appendStatus("완료!");
    setStatus($("status").textContent, "ok");
    renderResult(dataUrl, remoteName);
  } catch (err) {
    console.error(err);
    setStatus("오류 발생: " + err.message, "error");
  } finally {
    btn.disabled = false;
  }
});

// ---- 실행 완료 대기 ----
async function findTriggeredRun(settings, sinceMs, maxTries = 8) {
  for (let i = 0; i < maxTries; i++) {
    await sleep(1500);
    const data = await gh(
      `/actions/workflows/compose-signage.yml/runs?event=workflow_dispatch&per_page=5`,
      settings
    );
    const candidate = (data.workflow_runs || []).find(
      (r) => new Date(r.created_at).getTime() >= sinceMs - 5000
    );
    if (candidate) return candidate;
  }
  throw new Error("실행된 워크플로우를 찾지 못했습니다. Actions 탭에서 직접 확인해주세요.");
}

async function pollRunUntilDone(settings, runId, onStatus, maxTries = 40) {
  for (let i = 0; i < maxTries; i++) {
    const run = await gh(`/actions/runs/${runId}`, settings);
    onStatus(run.status);
    if (run.status === "completed") return run;
    await sleep(4000);
  }
  throw new Error("실행이 예상보다 오래 걸립니다. Actions 탭에서 직접 확인해주세요.");
}

function translateStatus(s) {
  return { queued: "대기 중", in_progress: "실행 중", completed: "완료" }[s] || s;
}

async function fetchImageAsDataUrl(settings, path, branch) {
  const data = await gh(
    `/contents/${path}?ref=${encodeURIComponent(branch)}`,
    settings
  );
  // Contents API는 1MB 넘는 파일이면 content를 비워서 돌려준다(encoding: "none").
  // 이 프로젝트의 합성 결과물은 보통 2~4MB라 항상 이 경로를 탄다.
  // sha로 Blob API(최대 100MB 지원)를 통해 실제 내용을 가져온다.
  if (!data.content || data.encoding === "none") {
    const blob = await gh(`/git/blobs/${data.sha}`, settings);
    return `data:image/png;base64,${blob.content.replace(/\n/g, "")}`;
  }
  return `data:image/png;base64,${data.content.replace(/\n/g, "")}`;
}

function renderResult(dataUrl, filename) {
  const box = document.createElement("div");
  box.className = "resultBox";
  const img = document.createElement("img");
  img.src = dataUrl;
  img.alt = "합성 결과";
  const dl = document.createElement("a");
  dl.href = dataUrl;
  dl.download = `composed_${filename}`;
  dl.textContent = "⬇ 결과 이미지 다운로드";
  dl.className = "downloadLink";
  box.appendChild(img);
  box.appendChild(dl);
  $("status").appendChild(box);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
