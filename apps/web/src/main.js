const discoveredAis = Array.isArray(window.discoveredDotnetAis)
  ? window.discoveredDotnetAis
  : [];

const app = document.querySelector("#app");

const apiEndpoints = [
  "POST /api/chat",
  "POST /api/chat/stream",
  "POST /api/session/new",
  "GET  /api/models",
  "GET  /api/health",
  "POST /api/rag/search",
  "POST /api/tools/execute",
];

const wpfRoles = ["채팅창", "설정창", "모델 선택", "로그 뷰어", "파일 선택", "NAS 경로 설정"];

const winuiSituations = [
  "Windows 11 스타일 UI",
  "Microsoft Store 배포",
  "현대적인 XAML UI",
  "터치 친화적 UI",
];

const avaloniaSituations = [
  "Windows + Linux 지원",
  "Windows + macOS 지원",
  "NAS 관리용 데스크톱 클라이언트",
  "장기적으로 크로스플랫폼 목표",
];

const finalSteps = [
  {
    title: "1단계",
    text: "Console로 Semantic Kernel + Ollama 연결 검증",
    status: "implemented",
  },
  {
    title: "2단계",
    text: "ChatService, KernelFactory, Plugin 구조 분리",
    status: "implemented",
  },
  {
    title: "3단계",
    text: "ASP.NET API로 AI 기능 서버화",
    status: "implemented",
  },
  {
    title: "4단계",
    text: "WPF로 Windows MVP 제작",
    status: "implemented",
  },
  {
    title: "5단계",
    text: "기능 안정화 후 WinUI 또는 Avalonia 선택",
    status: "scaffolded",
  },
  {
    title: "6단계",
    text: "장기 배포판은 Avalonia 또는 Web UI로 확장",
    status: "scaffolded",
  },
];

const state = {
  stage: "final",
  apiBaseUrl: "http://localhost:5088",
  statusText: "아직 검증하지 않았습니다.",
  selectedRole: "채팅창",
  selectedSituation: "Windows 11 스타일 UI",
  selectedAvalonia: "Windows + Linux 지원",
  logs: [
    makeLog("INFO", "UI", "최종 구현 순서 화면이 준비되었습니다."),
    makeLog("INFO", "Discovery", `${discoveredAis.length}개의 .NET 항목을 읽었습니다.`),
  ],
};

function makeLog(level, area, message) {
  return {
    time: new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date()),
    level,
    area,
    message,
  };
}

function addLog(level, area, message) {
  state.logs.unshift(makeLog(level, area, message));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function checkApiHealth() {
  state.statusText = "ASP.NET API 상태를 확인하는 중입니다.";
  render();

  try {
    const response = await fetch(`${state.apiBaseUrl}/api/health`);
    const payload = await response.json();
    state.statusText = JSON.stringify(payload, null, 2);
    addLog(response.ok ? "INFO" : "ERROR", "API", `${response.status} ${response.statusText}`);
  } catch (error) {
    state.statusText = `요청 실패: ${error.message}`;
    addLog("ERROR", "API", error.message);
  }

  render();
}

function render() {
  app.innerHTML = `
    <main class="console-page">
      <nav class="stage-nav" aria-label="구현 단계">
        ${renderStageButton("console", "1. Console")}
        ${renderStageButton("api", "2. ASP.NET API")}
        ${renderStageButton("wpf", "3. WPF")}
        ${renderStageButton("winui", "4. WinUI")}
        ${renderStageButton("avalonia", "5. Avalonia")}
        ${renderStageButton("final", "최종 순서")}
      </nav>
      ${state.stage === "console" ? renderConsoleStage() : ""}
      ${state.stage === "api" ? renderApiStage() : ""}
      ${state.stage === "wpf" ? renderWpfStage() : ""}
      ${state.stage === "winui" ? renderWinUiStage() : ""}
      ${state.stage === "avalonia" ? renderAvaloniaStage() : ""}
      ${state.stage === "final" ? renderFinalStage() : ""}
    </main>
  `;

  bindEvents();
}

function renderStageButton(stage, label) {
  return `<button class="${state.stage === stage ? "active" : ""}" type="button" data-stage="${stage}">${label}</button>`;
}

function renderConsoleStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">1차 검증용</p>
        <h1>1. Console</h1>
        <p class="lead">가장 먼저 Console로 Semantic Kernel 연결, Ollama 연결, 모델 응답, 대화 기록, 플러그인 호출, 오류 로그를 확인합니다.</p>
      </div>
    </header>
    <section class="reference-grid">
      ${renderCodeCard("목적", "console-purpose", `Semantic Kernel 연결 확인
Ollama 연결 확인
모델 응답 확인
대화 기록 확인
플러그인 호출 확인
오류 로그 확인`)}
      ${renderCodeCard("구조", "console-structure", `Console
  ↓
ChatService
  ↓
Semantic Kernel
  ↓
Ollama`)}
      ${renderCodeCard("구현 위치", "console-path", "ui/console")}
    </section>
  `;
}

function renderApiStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">핵심 분리 계층</p>
        <h1>2. ASP.NET API</h1>
        <p class="lead">AI 기능을 UI에서 분리하고 Desktop, Unity, Web, Mobile이 같은 HTTP 계층을 사용하게 합니다.</p>
      </div>
    </header>
    <section class="reference-grid">
      ${renderCodeCard("이유", "api-reason", "AI 기능을 UI에서 분리해야 함")}
      ${renderCodeCard("추천 구조", "api-structure", `Desktop UI / Unity / Web / Mobile
  ↓ HTTP
ASP.NET API
  ↓
Semantic Kernel
  ↓
Ollama`)}
      ${renderCodeCard("엔드포인트", "api-endpoints", apiEndpoints.join("\n"))}
    </section>
    ${renderApiHealthPanel()}
  `;
}

function renderWpfStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">Windows 전용 데스크톱 MVP</p>
        <h1>3. WPF</h1>
        <p class="lead">빠른 Windows 데스크톱 UI를 만들되 Semantic Kernel은 직접 넣지 않고 ASP.NET API를 호출합니다.</p>
      </div>
    </header>
    <section class="reference-grid">
      ${renderCodeCard("목적", "wpf-purpose", "빠른 Windows 데스크톱 UI 제작")}
      ${renderCodeCard("추천 역할", "wpf-roles", wpfRoles.join("\n"))}
      ${renderCodeCard("좋은 구조", "wpf-structure", `WPF
  ↓
HttpClient
  ↓
ASP.NET API
  ↓
Semantic Kernel`)}
    </section>
    <section class="note-panel">WPF에서는 Semantic Kernel을 직접 넣지 않는 편이 좋습니다. 데스크톱 앱은 사용자 입력과 설정에 집중하고 AI 실행은 API 계층이 맡습니다.</section>
    ${renderDesktopRolePanel("WPF", "WPF 실행", `dotnet run --project "ui\\wpf\\WpfDesktopMvp.csproj"`)}
  `;
}

function renderWinUiStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">최신 Windows 앱이 필요할 때</p>
        <h1>4. WinUI</h1>
        <p class="lead">WinUI는 Windows 10/11 스타일의 현대적인 UI를 만들 때 적합합니다. 단, 순수 생산성 기준으로는 WPF보다 초기 개발 속도가 느릴 수 있습니다.</p>
      </div>
      <div class="scoreboard" aria-label="WinUI 추천 요약">
        <strong>WPF</strong>
        <span>빠른 완성</span>
        <strong>WinUI</strong>
        <span>현대적 앱</span>
      </div>
    </header>
    <section class="reference-grid">
      ${renderCodeCard("추천 상황", "winui-situations", winuiSituations.join("\n"))}
      ${renderCodeCard("추천 순서", "winui-order", `빠른 완성 -> WPF
현대적 Windows 앱 -> WinUI`)}
      ${renderCodeCard("좋은 구조", "winui-structure", `WinUI
  ↓
HttpClient
  ↓
ASP.NET API
  ↓
Semantic Kernel`)}
    </section>
    <section class="note-panel">현재 PC에는 <strong>dotnet new winui</strong> 템플릿이 설치되어 있지 않습니다. Windows App SDK 설치 후 스캐폴드를 실제 프로젝트로 옮기는 구조입니다.</section>
    ${renderSituationPanel("WinUI", winuiSituations, state.selectedSituation, "data-situation", "WinUI 스캐폴드 위치", `ui\\winui`)}
  `;
}

function renderAvaloniaStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">크로스플랫폼 최종 UI</p>
        <h1>5. Avalonia</h1>
        <p class="lead">Avalonia는 Windows, macOS, Linux까지 고려할 때 강합니다. NAS 관리 도구, 로컬 AI 데스크톱 클라이언트, 사내 배포용 앱처럼 OS 확장성이 중요하면 WPF/WinUI보다 유리합니다.</p>
      </div>
      <div class="scoreboard" aria-label="Avalonia 추천 요약">
        <strong>3</strong>
        <span>OS</span>
        <strong>1</strong>
        <span>코드베이스</span>
      </div>
    </header>
    <section class="reference-grid">
      ${renderCodeCard("추천 상황", "avalonia-situations", avaloniaSituations.join("\n"))}
      ${renderCodeCard("설명", "avalonia-note", `Avalonia는 여러 플랫폼을 공식 지원하는 .NET UI 프레임워크입니다.
Microsoft MAUI는 공식 크로스플랫폼 UI 프레임워크지만, 주로 모바일과 데스크톱을 단일 코드베이스로 다루는 방향입니다.`)}
      ${renderCodeCard("좋은 구조", "avalonia-structure", `Avalonia
  ↓
HttpClient
  ↓
ASP.NET API
  ↓
Semantic Kernel`)}
    </section>
    <section class="note-panel">Avalonia에도 Semantic Kernel을 직접 넣지 않습니다. UI는 Windows/macOS/Linux 차이를 흡수하고, AI 실행은 ASP.NET API가 맡는 구조를 유지합니다.</section>
    ${renderSituationPanel("Avalonia", avaloniaSituations, state.selectedAvalonia, "data-avalonia", "Avalonia 스캐폴드 위치", `ui\\avalonia`)}
  `;
}

function renderFinalStage() {
  return `
    <header class="hero">
      <div>
        <p class="eyebrow">엄격 검증 완료 기준</p>
        <h1>최종 구현 순서</h1>
        <p class="lead">실전 기준으로는 Console 검증에서 시작해 API로 기능을 분리하고, WPF MVP로 빠르게 안정화한 뒤 WinUI/Avalonia/Web 확장 여부를 결정합니다.</p>
      </div>
      <div class="scoreboard" aria-label="최종 단계 요약">
        <strong>4</strong>
        <span>구현</span>
        <strong>2</strong>
        <span>스캐폴드</span>
      </div>
    </header>

    <section class="final-sequence">
      ${finalSteps.map((step) => `
        <article class="final-step ${step.status}">
          <span>${escapeHtml(step.title)}</span>
          <strong>${escapeHtml(step.text)}</strong>
          <em>${step.status === "implemented" ? "검증 대상" : "템플릿 설치 후 전환"}</em>
        </article>
      `).join("")}
    </section>

    <section class="reference-grid">
      ${renderCodeCard("최종 구현 순서", "final-order", finalSteps.map((step) => `${step.title}\n${step.text}`).join("\n\n"))}
      ${renderCodeCard("엄격 검증 명령", "final-verify", `powershell -ExecutionPolicy Bypass -File scripts\\verify-all.ps1`)}
      ${renderCodeCard("보완된 실패 지점", "final-fixes", `ONNX: NuGet restore 없이 빌드 가능한 오프라인 probe로 보완
WinUI: 템플릿 미설치 상태를 스캐폴드로 명확히 분리
Avalonia: 템플릿 미설치 상태를 스캐폴드로 명확히 분리
API: Ollama 미실행 상태에서도 fallback 응답으로 UI/API 분리 검증`)}
    </section>

    ${renderApiHealthPanel()}
  `;
}

function renderDesktopRolePanel(name, title, command) {
  return `
    <section class="workbench api-workbench">
      <aside class="panel checks-panel">
        <div class="panel-head"><div><p class="eyebrow">${escapeHtml(name)} Roles</p><h2>추천 역할</h2></div></div>
        <div class="endpoint-list">
          ${wpfRoles.map((role) => `
            <button class="endpoint-item ${state.selectedRole === role ? "selected" : ""}" type="button" data-role="${escapeHtml(role)}">
              <span class="method get">UI</span>
              <strong>${escapeHtml(role)}</strong>
              <em>${role === "채팅창" ? "main" : "mvp"}</em>
            </button>
          `).join("")}
        </div>
      </aside>
      ${renderClientPreview(name, state.selectedRole, describeRole(state.selectedRole))}
    </section>
    <section class="bottom-grid">
      ${renderRunbook(title, command)}
      ${renderLogPanel(`${name} 검증 로그`)}
    </section>
  `;
}

function renderSituationPanel(name, items, selected, dataName, title, command) {
  return `
    <section class="workbench api-workbench">
      <aside class="panel checks-panel">
        <div class="panel-head"><div><p class="eyebrow">${escapeHtml(name)} Fit</p><h2>추천 상황</h2></div></div>
        <div class="endpoint-list">
          ${items.map((item) => `
            <button class="endpoint-item ${selected === item ? "selected" : ""}" type="button" ${dataName}="${escapeHtml(item)}">
              <span class="method post">UI</span>
              <strong>${escapeHtml(item)}</strong>
              <em>${item.includes("NAS") ? "nas" : "os"}</em>
            </button>
          `).join("")}
        </div>
      </aside>
      ${renderClientPreview(name, selected, name === "Avalonia" ? describeAvalonia(selected) : describeWinUi(selected))}
    </section>
    <section class="bottom-grid">
      ${renderRunbook(title, command)}
      ${renderLogPanel(`${name} 검증 로그`)}
    </section>
  `;
}

function renderClientPreview(name, title, description) {
  return `
    <section class="panel detail-panel">
      <div class="panel-head">
        <div><p class="eyebrow">Client Preview</p><h2>${escapeHtml(title)}</h2></div>
        <button class="secondary" type="button" data-check-api>API 상태 확인</button>
      </div>
      <div class="api-detail">
        ${renderApiBaseInput()}
        <div class="desktop-preview ${name.toLowerCase()}-preview">
          <div class="desktop-sidebar">
            <strong>${escapeHtml(name)}</strong>
            <span>HttpClient</span>
            <span>ASP.NET API</span>
            <span>Semantic Kernel</span>
          </div>
          <div class="desktop-main">
            <strong>${escapeHtml(title)}</strong>
            <p>${escapeHtml(description)}</p>
          </div>
        </div>
        ${renderResponseBox("API Health", state.statusText)}
      </div>
    </section>
  `;
}

function renderApiHealthPanel() {
  return `
    <section class="workbench api-workbench">
      <section class="panel detail-panel">
        <div class="panel-head">
          <div><p class="eyebrow">HTTP Test</p><h2>GET /api/health</h2></div>
          <button class="secondary" type="button" data-check-api>상태 확인</button>
        </div>
        <div class="api-detail">
          ${renderApiBaseInput()}
          ${renderResponseBox("Response", state.statusText)}
        </div>
      </section>
      ${renderRunbook("ASP.NET API 실행", `dotnet run --project "ui\\api\\AspNetAiApi.csproj"`)}
    </section>
  `;
}

function renderApiBaseInput() {
  return `
    <label>
      <span>API Base URL</span>
      <input type="text" data-api-base value="${escapeHtml(state.apiBaseUrl)}" autocomplete="off">
    </label>
  `;
}

function renderResponseBox(title, text) {
  return `
    <div class="response-box">
      <span>${escapeHtml(title)}</span>
      <pre>${escapeHtml(text)}</pre>
    </div>
  `;
}

function renderCodeCard(title, id, text) {
  return `
    <article class="code-card">
      <button class="copy-button" type="button" data-copy="${id}" aria-label="${escapeHtml(title)} 복사">⧉</button>
      <span class="code-title">${escapeHtml(title)}</span>
      <pre id="${id}">${escapeHtml(text)}</pre>
    </article>
  `;
}

function renderRunbook(title, command) {
  return `
    <article class="panel chat-panel">
      <div class="panel-head compact"><div><p class="eyebrow">Runtime</p><h2>${escapeHtml(title)}</h2></div></div>
      <div class="runbook">
        <code>${escapeHtml(command)}</code>
        <p>먼저 ASP.NET API를 실행한 뒤 데스크톱 클라이언트 또는 웹 화면에서 상태를 확인합니다.</p>
      </div>
    </article>
  `;
}

function renderLogPanel(title) {
  return `
    <article class="panel terminal-panel">
      <div class="panel-head compact"><div><p class="eyebrow">Logs</p><h2>${escapeHtml(title)}</h2></div></div>
      <div class="terminal" aria-live="polite">
        ${state.logs.map((log) => `
          <div class="terminal-row ${log.level.toLowerCase()}">
            <span>${escapeHtml(log.time)}</span>
            <strong>${escapeHtml(log.level)}</strong>
            <em>${escapeHtml(log.area)}</em>
            <p>${escapeHtml(log.message)}</p>
          </div>
        `).join("")}
      </div>
    </article>
  `;
}

function describeRole(role) {
  return {
    "채팅창": "사용자 메시지를 받고 /api/chat으로 전송합니다.",
    "설정창": "API 주소와 NAS 경로 같은 로컬 설정을 관리합니다.",
    "모델 선택": "/api/models 결과를 읽어 사용할 모델을 고릅니다.",
    "로그 뷰어": "요청 성공, 실패, 예외 메시지를 사용자가 볼 수 있게 남깁니다.",
    "파일 선택": "Windows 파일 선택창으로 분석 대상 파일을 고릅니다.",
    "NAS 경로 설정": "로컬 또는 NAS 작업 경로를 데스크톱 앱에서 설정합니다.",
  }[role] ?? "데스크톱 MVP 역할입니다.";
}

function describeWinUi(item) {
  return {
    "Windows 11 스타일 UI": "Fluent 디자인, NavigationView, 현대적인 Windows 레이아웃이 중요한 경우에 적합합니다.",
    "Microsoft Store 배포": "패키징과 Store 배포를 고려하는 Windows 앱이라면 WinUI 전환 가치가 있습니다.",
    "현대적인 XAML UI": "WPF보다 최신 XAML 컨트롤과 Windows App SDK 생태계가 필요할 때 선택합니다.",
    "터치 친화적 UI": "태블릿, 터치 입력, 큰 hit target 중심의 Windows 앱에 적합합니다.",
  }[item] ?? "최신 Windows UI가 필요한 상황입니다.";
}

function describeAvalonia(item) {
  return {
    "Windows + Linux 지원": "NAS 관리 도구나 사내 운영 도구가 Linux 데스크톱까지 고려해야 할 때 적합합니다.",
    "Windows + macOS 지원": "운영자 PC가 Windows와 macOS로 섞여 있을 때 한 코드베이스로 배포하기 좋습니다.",
    "NAS 관리용 데스크톱 클라이언트": "NAS 경로, 로컬 파일, 원격 API 상태를 OS별 클라이언트에서 같은 흐름으로 다룹니다.",
    "장기적으로 크로스플랫폼 목표": "초기에는 Windows만 쓰더라도 장기적으로 OS 확장성이 중요하면 Avalonia가 유리합니다.",
  }[item] ?? "크로스플랫폼 UI가 필요한 상황입니다.";
}

function bindEvents() {
  document.querySelectorAll("[data-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stage = button.dataset.stage;
      render();
    });
  });

  document.querySelectorAll("[data-role]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedRole = button.dataset.role;
      addLog("INFO", "WPF", `${state.selectedRole} 역할을 선택했습니다.`);
      render();
    });
  });

  document.querySelectorAll("[data-situation]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSituation = button.dataset.situation;
      addLog("INFO", "WinUI", `${state.selectedSituation} 상황을 선택했습니다.`);
      render();
    });
  });

  document.querySelectorAll("[data-avalonia]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedAvalonia = button.dataset.avalonia;
      addLog("INFO", "Avalonia", `${state.selectedAvalonia} 상황을 선택했습니다.`);
      render();
    });
  });

  document.querySelector("[data-api-base]")?.addEventListener("input", (event) => {
    state.apiBaseUrl = event.target.value.trim();
  });

  document.querySelector("[data-check-api]")?.addEventListener("click", () => {
    state.apiBaseUrl = document.querySelector("[data-api-base]")?.value.trim() || state.apiBaseUrl;
    checkApiHealth();
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.querySelector(`#${button.dataset.copy}`);
      if (!target) return;
      await navigator.clipboard?.writeText(target.textContent.trim());
      addLog("INFO", "Clipboard", `${button.dataset.copy} 내용을 복사했습니다.`);
      render();
    });
  });
}

render();
