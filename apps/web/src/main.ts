import "./styles.css";

type HealthResponse = {
  status: string;
  environment?: string;
  ai_device?: string;
  llm_backend?: string;
  llm_model?: string;
  model_backend?: string;
  dependencies?: Record<string, unknown>;
};

type ProjectResponse = {
  id: string;
  name: string;
  description: string;
  file_count: number;
};

type ProjectFile = {
  path: string;
  content: string;
  language: string;
};

type RagIngestResponse = {
  project_id: string;
  collection: string;
  indexed_count: number;
  document_ids: string[];
};

type OptimizeResponse = {
  summary: string;
  risk_level: string;
  bottleneck: string;
  explanation: string;
  patch: string;
  expected_effect: string;
  test_command: string;
  benchmark_command: string;
  checks: string[];
  notes: string[];
  rag_context: string[];
  llm_backend: string;
};

type BenchmarkResponse = {
  job_id: string;
  status: string;
  checks: string[];
};

type AppState = {
  project: ProjectResponse | null;
  files: ProjectFile[];
  selectedPath: string | null;
  ready: HealthResponse | null;
  rag: RagIngestResponse | null;
  optimize: OptimizeResponse | null;
  benchmark: BenchmarkResponse | null;
};

const state: AppState = {
  project: null,
  files: [
    {
      path: "src/service.py",
      language: "python",
      content: `def total(items):
    result = 0
    for item in items:
        result = result + item
    return result
`,
    },
  ],
  selectedPath: "src/service.py",
  ready: null,
  rag: null,
  optimize: null,
  benchmark: null,
};

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("App root not found");
}

app.innerHTML = `
  <main class="app-shell">
    <header class="app-header">
      <div>
        <p class="eyebrow">Local Code Optimization</p>
        <h1>AI Code Optimizer</h1>
      </div>
      <div class="header-status">
        <span id="api-status" class="status-pill">API 확인 중</span>
        <span id="model-status" class="status-pill">모델 대기</span>
      </div>
    </header>

    <section class="workflow-strip" aria-label="워크플로우">
      <span data-step="project">프로젝트 선택</span>
      <span data-step="upload">파일 업로드</span>
      <span data-step="rag">RAG 인덱싱</span>
      <span data-step="analyze">AI 분석</span>
      <span data-step="diff">diff 확인</span>
      <span data-step="test">테스트/벤치</span>
      <span data-step="apply">적용 결정</span>
    </section>

    <section class="main-grid">
      <aside class="left-rail">
        <section class="panel">
          <div class="panel-head">
            <h2>프로젝트</h2>
            <span id="project-id" class="mini-text">생성 전</span>
          </div>
          <label>
            프로젝트 이름
            <input id="project-name" value="local-upload" autocomplete="off">
          </label>
          <label>
            설명
            <input id="project-description" value="CPU-only MVP 최적화 테스트" autocomplete="off">
          </label>
          <label>
            Mode
            <select id="optimize-mode">
              <option value="hybrid" selected>hybrid</option>
              <option value="deterministic">deterministic</option>
              <option value="local_llm">local_llm</option>
            </select>
          </label>
          <div class="button-row">
            <button id="create-project" type="button">프로젝트 생성</button>
            <label class="file-button">
              파일 추가
              <input id="file-input" type="file" multiple>
            </label>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>파일 트리</h2>
            <span id="file-count" class="mini-text">1개</span>
          </div>
          <div id="file-tree" class="file-tree"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>AI 채팅 / 요청</h2>
            <span id="request-language" class="mini-text">python</span>
          </div>
          <label>
            목표
            <textarea id="goal" class="goal-box">속도 개선, 메모리 개선, 가독성 유지. 동작은 바꾸지 말고 unified diff로 제안해줘.</textarea>
          </label>
          <div class="button-row">
            <button id="ingest-rag" type="button">RAG 인덱싱</button>
            <button id="run-optimize" type="button">AI 분석 실행</button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>상태</h2>
            <span id="rag-status" class="status-pill">RAG 대기</span>
          </div>
          <ol class="status-list">
            <li id="state-project">프로젝트 생성 대기</li>
            <li id="state-files">파일 업로드 대기</li>
            <li id="state-rag">RAG 인덱싱 대기</li>
            <li id="state-ai">AI 분석 대기</li>
            <li id="state-test">테스트/벤치 대기</li>
          </ol>
        </section>
      </aside>

      <section class="work-area">
        <nav class="tabs" aria-label="결과 화면">
          <button class="tab active" data-tab="code" type="button">코드</button>
          <button class="tab" data-tab="result" type="button">최적화 결과</button>
          <button class="tab" data-tab="diff" type="button">diff 비교</button>
          <button class="tab" data-tab="tests" type="button">테스트 결과</button>
          <button class="tab" data-tab="bench" type="button">벤치마크</button>
          <button class="tab" data-tab="settings" type="button">모델/환경</button>
        </nav>

        <section id="tab-code" class="tab-panel active">
          <div class="panel-head">
            <h2>코드 뷰어</h2>
            <span id="selected-file" class="mini-text">src/service.py</span>
          </div>
          <textarea id="code-editor" class="code-editor" spellcheck="false"></textarea>
        </section>

        <section id="tab-result" class="tab-panel">
          <div class="result-grid">
            <article class="metric-card">
              <span>요약</span>
              <strong id="result-summary">아직 결과 없음</strong>
            </article>
            <article class="metric-card">
              <span>위험도</span>
              <strong id="risk-level">대기</strong>
            </article>
            <article class="metric-card">
              <span>백엔드</span>
              <strong id="backend-name">대기</strong>
            </article>
          </div>
          <section class="panel embedded">
            <h3>병목 추정</h3>
            <p id="bottleneck">AI 분석을 실행하면 표시됩니다.</p>
            <h3>예상 효과</h3>
            <p id="expected-effect">테스트와 벤치마크로 확인해야 합니다.</p>
            <h3>RAG 근거</h3>
            <ul id="rag-context" class="evidence-list"></ul>
          </section>
        </section>

        <section id="tab-diff" class="tab-panel">
          <div class="diff-layout">
            <section>
              <div class="panel-head">
                <h2>원본</h2>
                <span class="mini-text">현재 파일</span>
              </div>
              <pre id="original-view" class="code-view"></pre>
            </section>
            <section>
              <div class="panel-head">
                <h2>패치</h2>
                <span class="mini-text">unified diff</span>
              </div>
              <pre id="patch-view" class="code-view"></pre>
            </section>
          </div>
        </section>

        <section id="tab-tests" class="tab-panel">
          <div class="panel-head">
            <h2>테스트 결과</h2>
            <span id="job-status" class="status-pill">미실행</span>
          </div>
          <div class="button-row narrow">
            <button id="run-benchmark" type="button">테스트/벤치마크 job 생성</button>
          </div>
          <div id="checks" class="check-list"></div>
          <pre id="job-output" class="code-view small">테스트 실행 전입니다.</pre>
        </section>

        <section id="tab-bench" class="tab-panel">
          <div class="panel-head">
            <h2>벤치마크 결과</h2>
            <span class="mini-text">제안 단계</span>
          </div>
          <div class="bar-chart">
            <div>
              <span>현재 코드</span>
              <i style="--bar: 82%"></i>
            </div>
            <div>
              <span>제안 패치</span>
              <i style="--bar: 58%"></i>
            </div>
            <div>
              <span>목표</span>
              <i style="--bar: 45%"></i>
            </div>
          </div>
          <p class="muted">실제 수치는 `/optimize/benchmark` job과 프로젝트 테스트가 연결되면 갱신됩니다.</p>
        </section>

        <section id="tab-settings" class="tab-panel">
          <div class="settings-grid">
            <article class="metric-card">
              <span>AI 장치</span>
              <strong id="setting-device">확인 중</strong>
            </article>
            <article class="metric-card">
              <span>LLM 백엔드</span>
              <strong id="setting-llm">확인 중</strong>
            </article>
            <article class="metric-card">
              <span>모델</span>
              <strong id="setting-model">확인 중</strong>
            </article>
            <article class="metric-card">
              <span>환경</span>
              <strong id="setting-env">확인 중</strong>
            </article>
          </div>
          <pre id="ready-json" class="code-view small"></pre>
        </section>
      </section>
    </section>
  </main>
`;

const $ = <T extends HTMLElement>(selector: string) => {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`Missing element: ${selector}`);
  return node;
};

const apiStatus = $("#api-status");
const modelStatus = $("#model-status");
const projectId = $("#project-id");
const projectName = $("#project-name") as HTMLInputElement;
const projectDescription = $("#project-description") as HTMLInputElement;
const fileInput = $("#file-input") as HTMLInputElement;
const fileTree = $("#file-tree");
const fileCount = $("#file-count");
const requestLanguage = $("#request-language");
const goal = $("#goal") as HTMLTextAreaElement;
const optimizeMode = $("#optimize-mode") as HTMLSelectElement;
const codeEditor = $("#code-editor") as HTMLTextAreaElement;
const selectedFile = $("#selected-file");
const ragStatus = $("#rag-status");
const patchView = $("#patch-view");
const originalView = $("#original-view");
const resultSummary = $("#result-summary");
const riskLevel = $("#risk-level");
const backendName = $("#backend-name");
const bottleneck = $("#bottleneck");
const expectedEffect = $("#expected-effect");
const ragContext = $("#rag-context");
const checks = $("#checks");
const jobStatus = $("#job-status");
const jobOutput = $("#job-output");
const settingDevice = $("#setting-device");
const settingLlm = $("#setting-llm");
const settingModel = $("#setting-model");
const settingEnv = $("#setting-env");
const readyJson = $("#ready-json");

$("#create-project").addEventListener("click", () => void createProject());
$("#ingest-rag").addEventListener("click", () => void ingestRag());
$("#run-optimize").addEventListener("click", () => void runOptimize());
$("#run-benchmark").addEventListener("click", () => void runBenchmark());
codeEditor.addEventListener("input", syncSelectedFile);
fileInput.addEventListener("change", () => void addFilesFromInput());

document.querySelectorAll<HTMLButtonElement>(".tab").forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab ?? "code"));
});

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

async function checkReady() {
  try {
    const payload = await api<HealthResponse>("/ready");
    state.ready = payload;
    apiStatus.textContent = payload.status === "ready" ? "API ready" : `API ${payload.status}`;
    apiStatus.classList.toggle("ready", payload.status === "ready");
    modelStatus.textContent = `${payload.ai_device ?? "cpu"} · ${payload.llm_backend ?? "llm"}`;
    modelStatus.classList.add("ready");
    settingDevice.textContent = payload.ai_device ?? "-";
    settingLlm.textContent = payload.llm_backend ?? "-";
    settingModel.textContent = payload.llm_model ?? "-";
    settingEnv.textContent = payload.environment ?? "-";
    readyJson.textContent = JSON.stringify(payload, null, 2);
  } catch {
    apiStatus.textContent = "API 연결 대기";
    apiStatus.classList.remove("ready");
    modelStatus.textContent = "모델 대기";
  }
}

async function createProject() {
  state.project = await api<ProjectResponse>("/projects", {
    method: "POST",
    body: JSON.stringify({
      name: projectName.value.trim() || "local-upload",
      description: projectDescription.value.trim(),
    }),
  });
  await uploadAllFiles();
  render();
}

async function addFilesFromInput() {
  const files = Array.from(fileInput.files ?? []);
  const loaded = await Promise.all(files.map(readBrowserFile));
  state.files = mergeFiles(state.files, loaded);
  state.selectedPath = loaded[0]?.path ?? state.selectedPath;
  if (state.project) {
    await uploadAllFiles();
  }
  fileInput.value = "";
  render();
}

function readBrowserFile(file: File): Promise<ProjectFile> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      resolve({
        path: file.webkitRelativePath || file.name,
        content: String(reader.result ?? ""),
        language: languageFromPath(file.name),
      });
    };
    reader.readAsText(file);
  });
}

async function uploadAllFiles() {
  if (!state.project) return;
  for (const file of state.files) {
    await api(`/projects/${state.project.id}/files`, {
      method: "POST",
      body: JSON.stringify(file),
    });
  }
}

async function ingestRag() {
  if (!state.project) {
    await createProject();
  }
  if (!state.project) return;
  state.rag = await api<RagIngestResponse>("/rag/ingest", {
    method: "POST",
    body: JSON.stringify({
      project_id: state.project.id,
      paths: state.files.map((file) => file.path),
      collection: "project_code_chunks",
    }),
  });
  render();
}

async function runOptimize() {
  if (!state.project) {
    await createProject();
  }
  if (!state.rag) {
    await ingestRag();
  }
  const file = selectedProjectFile();
  if (!file || !state.project) return;
  state.optimize = await api<OptimizeResponse>("/optimize/patch", {
    method: "POST",
    body: JSON.stringify({
      project_id: state.project.id,
      path: file.path,
      language: file.language,
      mode: optimizeMode.value,
      goal: goal.value,
      code: file.content,
    }),
  });
  activateTab("result");
  render();
}

async function runBenchmark() {
  if (!state.project) {
    await createProject();
  }
  const file = selectedProjectFile();
  if (!file || !state.project) return;
  state.benchmark = await api<BenchmarkResponse>("/optimize/benchmark", {
    method: "POST",
    body: JSON.stringify({
      project_id: state.project.id,
      language: file.language,
      command: state.optimize?.test_command ?? "pytest",
    }),
  });
  activateTab("tests");
  render();
}

function syncSelectedFile() {
  const file = selectedProjectFile();
  if (!file) return;
  file.content = codeEditor.value;
  originalView.textContent = file.content;
}

function render() {
  const file = selectedProjectFile();
  projectId.textContent = state.project?.id.slice(0, 8) ?? "생성 전";
  fileCount.textContent = `${state.files.length}개`;
  selectedFile.textContent = file?.path ?? "파일 없음";
  requestLanguage.textContent = file?.language ?? "-";
  codeEditor.value = file?.content ?? "";
  originalView.textContent = file?.content ?? "";

  fileTree.innerHTML = state.files
    .map(
      (item) => `
        <button class="file-node ${item.path === state.selectedPath ? "active" : ""}" data-path="${escapeHtml(item.path)}" type="button">
          <span>${escapeHtml(item.path)}</span>
          <em>${item.language}</em>
        </button>
      `,
    )
    .join("");

  fileTree.querySelectorAll<HTMLButtonElement>(".file-node").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedPath = node.dataset.path ?? state.selectedPath;
      render();
    });
  });

  ragStatus.textContent = state.rag ? `${state.rag.indexed_count}개 청크` : "RAG 대기";
  ragStatus.classList.toggle("ready", Boolean(state.rag));
  patchView.textContent = state.optimize?.patch || "패치가 아직 없습니다.";
  resultSummary.textContent = state.optimize?.summary || "아직 결과 없음";
  riskLevel.textContent = state.optimize?.risk_level || "대기";
  backendName.textContent = state.optimize?.llm_backend || "대기";
  bottleneck.textContent = state.optimize?.bottleneck || "AI 분석을 실행하면 표시됩니다.";
  expectedEffect.textContent = state.optimize?.expected_effect || "테스트와 벤치마크로 확인해야 합니다.";
  ragContext.innerHTML = (state.optimize?.rag_context ?? [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  checks.innerHTML = (state.optimize?.checks ?? [])
    .map((item) => `<code>${escapeHtml(item)}</code>`)
    .join("");
  jobStatus.textContent = state.benchmark?.status ?? "미실행";
  jobStatus.classList.toggle("ready", Boolean(state.benchmark));
  jobOutput.textContent = state.benchmark
    ? `job_id=${state.benchmark.job_id}\nstatus=${state.benchmark.status}\nchecks=\n${state.benchmark.checks.map((item) => `- ${item}`).join("\n")}`
    : "테스트 실행 전입니다.";

  setStep("project", Boolean(state.project));
  setStep("upload", state.files.length > 0);
  setStep("rag", Boolean(state.rag));
  setStep("analyze", Boolean(state.optimize));
  setStep("diff", Boolean(state.optimize?.patch));
  setStep("test", Boolean(state.benchmark));
  $("#state-project").classList.toggle("done", Boolean(state.project));
  $("#state-files").classList.toggle("done", state.files.length > 0);
  $("#state-rag").classList.toggle("done", Boolean(state.rag));
  $("#state-ai").classList.toggle("done", Boolean(state.optimize));
  $("#state-test").classList.toggle("done", Boolean(state.benchmark));
}

function selectedProjectFile() {
  return state.files.find((file) => file.path === state.selectedPath) ?? state.files[0] ?? null;
}

function mergeFiles(current: ProjectFile[], added: ProjectFile[]) {
  const map = new Map(current.map((file) => [file.path, file]));
  for (const file of added) {
    map.set(file.path, file);
  }
  return Array.from(map.values());
}

function languageFromPath(path: string) {
  const suffix = path.split(".").pop()?.toLowerCase() ?? "";
  return (
    {
      py: "python",
      ts: "typescript",
      tsx: "typescript",
      js: "javascript",
      jsx: "javascript",
      java: "java",
      go: "go",
      rs: "rust",
      md: "markdown",
      txt: "text",
    } as Record<string, string>
  )[suffix] ?? "text";
}

function activateTab(name: string) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", (tab as HTMLElement).dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

function setStep(step: string, done: boolean) {
  const node = document.querySelector(`[data-step="${step}"]`);
  node?.classList.toggle("done", done);
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

render();
void checkReady();
setInterval(checkReady, 10000);
