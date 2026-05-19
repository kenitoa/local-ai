const app = document.querySelector("#app");

const panels = [
  {
    id: "chat",
    label: "AI 모드",
    description: "질문과 응답",
  },
  {
    id: "connection",
    label: "연결 상태",
    description: "API와 모델",
  },
  {
    id: "settings",
    label: "설정",
    description: "NAS와 세션",
  },
  {
    id: "logs",
    label: "로그",
    description: "실행 기록",
  },
];

const state = {
  activePanel: "chat",
  apiBaseUrl: "http://localhost:5088",
  model: "llama3.2",
  models: ["llama3.2"],
  nasPath: "\\\\NAS\\local-ai",
  selectedFile: "선택된 파일 없음",
  sessionId: "",
  busy: false,
  messages: [
    {
      role: "system",
      content: "Web -> Fetch -> ASP.NET API -> Semantic Kernel 흐름으로 실행됩니다.",
    },
  ],
  logs: [
    makeLog("Web UI가 시작되었습니다."),
    makeLog("좌측 패널과 우측 작업 패널 구성을 적용했습니다."),
  ],
};

function makeLog(message) {
  return `[${new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date())}] ${message}`;
}

function addLog(message) {
  state.logs.unshift(makeLog(message));
}

function addMessage(role, content) {
  state.messages.push({ role, content });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getApiBaseUrl() {
  return document.querySelector("#apiBaseUrl")?.value.trim() || state.apiBaseUrl;
}

function getModel() {
  return document.querySelector("#modelInput")?.value.trim() || state.model || "llama3.2";
}

async function getJson(path) {
  const response = await fetch(`${getApiBaseUrl()}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function runAction(name, action) {
  if (state.busy) {
    return;
  }

  state.busy = true;
  addLog(`${name} 요청 시작`);
  render();

  try {
    await action();
  } catch (error) {
    addLog(`${name} 실패: ${error.message}`);
  } finally {
    state.busy = false;
    render();
  }
}

function setActivePanel(panelId) {
  state.activePanel = panelId;
  render();
}

function getActivePanel() {
  return panels.find((panel) => panel.id === state.activePanel) ?? panels[0];
}

function render() {
  const activePanel = getActivePanel();

  app.innerHTML = `
    <main class="panel-app" aria-label="Local AI web desktop panel">
      <aside class="sidebar" aria-label="패널 메뉴">
        <header class="brand-row">
          <div class="brand-mark" aria-label="Local AI">N</div>
          <div class="brand-title">
            <strong>Local AI</strong>
            <span>Desktop Panel</span>
          </div>
        </header>

        <nav class="side-nav">
          ${panels.map(renderNavButton).join("")}
        </nav>
      </aside>

      <section class="workspace-shell">
        <section class="workspace-panel" aria-label="${escapeHtml(activePanel.label)} 패널">
          <header class="workspace-header">
            <div>
              <span>${escapeHtml(activePanel.description)}</span>
              <h1>${escapeHtml(activePanel.label)}</h1>
            </div>
            <div class="status-pill ${state.busy ? "working" : ""}">
              ${state.busy ? "실행 중" : "대기"}
            </div>
          </header>
          <div class="workspace-body">
            ${renderActivePanel()}
          </div>
        </section>
      </section>
    </main>
  `;

  bindEvents();
  requestAnimationFrame(() => {
    const chatList = document.querySelector("#chatList");
    chatList?.scrollTo({ top: chatList.scrollHeight });
  });
}

function renderNavButton(panel) {
  return `
    <button
      class="nav-card ${state.activePanel === panel.id ? "active" : ""}"
      type="button"
      data-panel-target="${panel.id}">
      <span>${escapeHtml(panel.label)}</span>
      <small>${escapeHtml(panel.description)}</small>
    </button>
  `;
}

function renderActivePanel() {
  switch (state.activePanel) {
    case "connection":
      return renderConnectionPanel();
    case "settings":
      return renderSettingsPanel();
    case "logs":
      return renderLogsPanel();
    case "chat":
    default:
      return renderChatPanel();
  }
}

function renderChatPanel() {
  return `
    <section class="chat-panel">
      <div class="chat-list" id="chatList" aria-live="polite">
        ${state.messages.map(renderMessage).join("")}
      </div>
      <form class="prompt-panel" id="promptForm">
        <textarea id="promptInput" rows="3">WPF에서 ASP.NET API를 통해 응답해주세요.</textarea>
        <button id="sendButton" type="submit" ${state.busy ? "disabled" : ""}>전송</button>
      </form>
    </section>
  `;
}

function renderConnectionPanel() {
  return `
    <section class="content-grid">
      <div class="content-card wide">
        <label class="field">
          <span>API 연결</span>
          <input id="apiBaseUrl" type="text" value="${escapeHtml(state.apiBaseUrl)}">
        </label>
        <button id="healthButton" type="button" ${state.busy ? "disabled" : ""}>상태 확인</button>
      </div>

      <div class="content-card">
        <label class="field">
          <span>모델 선택</span>
          <input id="modelInput" type="text" list="modelList" value="${escapeHtml(state.model)}">
          <datalist id="modelList">
            ${state.models.map((model) => `<option value="${escapeHtml(model)}"></option>`).join("")}
          </datalist>
        </label>
        <button id="modelsButton" type="button" ${state.busy ? "disabled" : ""}>모델 목록 새로고침</button>
      </div>

      <div class="content-card">
        <label class="field">
          <span>파일 선택</span>
          <input id="fileInput" type="file">
        </label>
        <p class="file-name">${escapeHtml(state.selectedFile)}</p>
      </div>
    </section>
  `;
}

function renderSettingsPanel() {
  return `
    <section class="content-grid">
      <div class="content-card wide">
        <label class="field">
          <span>NAS 경로 설정</span>
          <input id="nasPath" type="text" value="${escapeHtml(state.nasPath)}">
        </label>
        <button id="saveSettingsButton" type="button">설정 저장</button>
      </div>

      <div class="content-card">
        <strong>세션</strong>
        <button id="newSessionButton" type="button" ${state.busy ? "disabled" : ""}>새 세션</button>
      </div>

      <div class="content-card">
        <strong>도구</strong>
        <button id="toolButton" type="button" ${state.busy ? "disabled" : ""}>time 실행</button>
      </div>
    </section>
  `;
}

function renderLogsPanel() {
  return `
    <section class="log-panel" aria-live="polite">
      ${state.logs.map((log) => `<div class="log-row">${escapeHtml(log)}</div>`).join("")}
    </section>
  `;
}

function renderMessage(message) {
  return `
    <article class="message ${escapeHtml(message.role)}">
      <strong>${escapeHtml(message.role)}</strong>
      <p>${escapeHtml(message.content)}</p>
    </article>
  `;
}

function bindEvents() {
  document.querySelectorAll("[data-panel-target]").forEach((button) => {
    button.addEventListener("click", () => setActivePanel(button.dataset.panelTarget));
  });

  document.querySelector("#apiBaseUrl")?.addEventListener("input", (event) => {
    state.apiBaseUrl = event.target.value;
  });

  document.querySelector("#modelInput")?.addEventListener("input", (event) => {
    state.model = event.target.value;
  });

  document.querySelector("#nasPath")?.addEventListener("input", (event) => {
    state.nasPath = event.target.value;
  });

  document.querySelector("#healthButton")?.addEventListener("click", () => {
    state.activePanel = "connection";
    runAction("상태 확인", async () => {
      const health = await getJson("/api/health");
      addLog(`API=${health.api ?? health.Api}, Status=${health.status ?? health.Status}, Ollama=${health.ollama ?? "unknown"}`);
    });
  });

  document.querySelector("#modelsButton")?.addEventListener("click", () => {
    state.activePanel = "connection";
    runAction("모델 목록", async () => {
      const payload = await getJson("/api/models");
      const models = payload.models ?? payload.Models ?? [];
      state.models = models.length > 0 ? models : [payload.configuredModel ?? payload.ConfiguredModel ?? state.model];
      state.model = state.models[0] || state.model;
      addLog(`모델 ${state.models.length}개를 읽었습니다.`);
    });
  });

  document.querySelector("#newSessionButton")?.addEventListener("click", () => {
    state.activePanel = "chat";
    runAction("새 세션", async () => {
      const session = await postJson("/api/session/new", { title: "Web desktop session" });
      state.sessionId = session.sessionId ?? session.SessionId ?? "";
      state.messages = [
        {
          role: "system",
          content: `새 세션이 생성되었습니다. ${state.sessionId}`,
        },
      ];
      addLog(`새 세션: ${state.sessionId}`);
    });
  });

  document.querySelector("#toolButton")?.addEventListener("click", () => {
    state.activePanel = "logs";
    runAction("도구 실행", async () => {
      const result = await postJson("/api/tools/execute", { name: "time", input: "" });
      addLog(result.success ?? result.Success ? `time=${result.result ?? result.Result}` : `도구 실패: ${result.error ?? result.Error}`);
    });
  });

  document.querySelector("#saveSettingsButton")?.addEventListener("click", () => {
    state.activePanel = "settings";
    addLog(`설정 저장: API=${state.apiBaseUrl}, NAS=${state.nasPath}`);
    render();
  });

  document.querySelector("#fileInput")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    state.selectedFile = file ? file.name : "선택된 파일 없음";
    addLog(`파일 선택: ${state.selectedFile}`);
    render();
  });

  document.querySelector("#promptForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const prompt = document.querySelector("#promptInput")?.value.trim() || "";
    if (!prompt) {
      addLog("전송할 메시지가 없습니다.");
      render();
      return;
    }

    state.activePanel = "chat";
    runAction("채팅", async () => {
      state.model = getModel();
      addMessage("user", prompt);
      const response = await postJson("/api/chat", {
        sessionId: state.sessionId || null,
        model: state.model,
        message: prompt,
      });
      state.sessionId = response.sessionId ?? response.SessionId ?? state.sessionId;
      addMessage("assistant", response.message ?? response.Message ?? "응답 본문이 비어 있습니다.");
      addLog(`채팅 응답 수신: ${new Date().toLocaleTimeString("ko-KR", { hour12: false })}`);
    });
  });
}

render();
