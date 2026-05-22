const app = document.querySelector("#app");

const panels = [
  {
    id: "chat",
    label: "체팅",
    shortLabel: "채",
    description: "질문과 응답",
  },
  {
    id: "connection",
    label: "AI 모델 선택",
    shortLabel: "AI",
    description: "API와 모델",
  },
  {
    id: "settings",
    label: "Ai 마켓",
    shortLabel: "마",
    description: "NAS와 세션",
  },
  {
    id: "logs",
    label: "설정",
    shortLabel: "설",
    description: "실행 기록",
  },
];

panels.splice(
  0,
  panels.length,
  {
    id: "chat",
    label: "채팅",
    shortLabel: "채",
    description: "질문과 응답",
  },
  {
    id: "connection",
    label: "AI 모델 선택",
    shortLabel: "AI",
    description: "모델과 조합",
  },
  {
    id: "market",
    label: "AI 마켓",
    shortLabel: "마",
    description: "모델 확장",
  },
  {
    id: "settings",
    label: "설정",
    shortLabel: "설",
    description: "API와 NAS",
  },
  {
    id: "logs",
    label: "로그",
    shortLabel: "로",
    description: "실행 기록",
  },
);

const promptGuidelines = [
  "이 프로젝트에서 가장 먼저 확인해야 할 파일과 이유를 알려줘.",
  "현재 오류를 재현하고 고칠 순서를 짧게 정리해줘.",
  "선택한 프로젝트 폴더 기준으로 코드 구조를 요약해줘.",
];

const inferenceStepTemplates = [
  ["입력 분석", "요청 의도와 현재 프로젝트 맥락을 정리합니다."],
  ["컨텍스트 구성", "세션, 모델, 선택한 프로젝트 정보를 프롬프트에 반영합니다."],
  ["모델 호출", "로컬 모델에 요청을 보내고 응답을 기다립니다."],
  ["응답 정리", "수신한 결과를 채팅 메시지로 정리합니다."],
];

const localProjectStorageKey = "local-ai.web.projects.v1";
const modelCombinationStorageKey = "local-ai.web.model-combinations.v1";

const runtimeModelCatalog = {
  semanticKernel: {
    id: "semantic-kernel",
    name: "Semantic Kernel",
    route: "runtime/semantic-kernel",
    model: "Orchestration layer",
    purpose: ".NET 런타임과 Ollama 모델을 연결하는 상위 AI 오케스트레이션 계층",
  },
  dotnet: [
    {
      id: "onnx-runtime-dotnet",
      name: "ONNX Runtime .NET",
      route: "runtime/dotnet/onnx-probe",
      model: "ONNX Runtime",
      memory: "Offline probe",
      specialty: "ONNX runtime configuration check",
      description: "ONNX 모델을 .NET 런타임에서 실행하거나 구성을 점검할 때 쓰는 로컬 추론 런타임입니다.",
    },
  ],
  ollama: [
    {
      id: "llama3.2",
      name: "llama3.2",
      route: "runtime/ollama/server/models",
      model: "Ollama language model",
      specialty: "General chat",
      description: "일반 대화와 기본 질의응답에 쓰기 좋은 범용 로컬 언어 모델입니다.",
    },
    {
      id: "nomic-embed-text",
      name: "nomic-embed-text",
      route: "runtime/ollama/server/models",
      model: "Ollama embedding model",
      specialty: "Embedding / RAG",
      description: "문서와 질문을 벡터로 바꿔 검색/RAG 흐름에서 관련 내용을 찾는 임베딩 모델입니다.",
    },
    {
      id: "qwen2.5",
      name: "qwen2.5",
      route: "runtime/ollama/server/models",
      model: "Ollama language model",
      specialty: "Chat / coding",
      description: "코딩, 분석, 한국어/영어 혼합 질의에 대응하기 좋은 채팅용 로컬 언어 모델입니다.",
    },
    {
      id: "llama3.1",
      name: "llama3.1",
      route: "runtime/ollama/server/models",
      model: "Ollama language model",
      specialty: "Chat",
      description: "안정적인 일반 대화와 요약 작업에 사용할 수 있는 범용 채팅 모델입니다.",
    },
    {
      id: "local-assistant",
      name: "local-assistant",
      route: "runtime/ollama/server/models",
      model: "Custom Ollama model",
      specialty: "Local assistant",
      description: "local-ai 환경에 맞춰 조정된 사용자 정의 보조 모델 프로필입니다.",
    },
  ],
};

const state = {
  activePanel: "chat",
  sidebarOpen: true,
  apiBaseUrl: "http://localhost:5088",
  model: "llama3.2",
  models: runtimeModelCatalog.ollama.map((model) => model.name),
  selectedDotnetAiId: "",
  selectedCombinationId: "",
  modelCombinations: [],
  cloudAiInterface: null,
  cloudAiModels: [],
  cloudAiCompositions: [],
  cloudAiLoadError: "",
  marketModels: [],
  marketLoaded: false,
  marketError: "",
  draftCombinationName: "",
  draftCombinationParts: [],
  nasPath: "\\\\NAS\\local-ai",
  selectedFile: "선택된 파일 없음",
  projectPanelOpen: true,
  inferencePanelOpen: true,
  projectsLoaded: false,
  projects: [],
  isCreatingProject: false,
  draftProjectName: "",
  editingProjectName: "",
  editingProjectValue: "",
  selectedProjectName: "",
  selectedChatId: "",
  projectLoadError: "",
  sessionId: "",
  busy: false,
  inferenceSteps: inferenceStepTemplates.map(([title, detail]) => ({
    title,
    detail,
    status: "waiting",
  })),
  inferenceSummary: "아직 실행된 요청이 없습니다.",
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

state.modelCombinations = readStoredModelCombinations();

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
  return state.model || "llama3.2";
}

function getStableOllamaModelNames() {
  const orderedNames = [];
  for (const model of state.cloudAiModels.filter((item) => item.type === "ollama")) {
    if (model.name && !orderedNames.includes(model.name)) {
      orderedNames.push(model.name);
    }
  }

  for (const name of runtimeModelCatalog.ollama.map((model) => model.name)) {
    if (name && !orderedNames.includes(name)) {
      orderedNames.push(name);
    }
  }

  for (const name of state.models) {
    if (name && !orderedNames.includes(name)) {
      orderedNames.push(name);
    }
  }

  if (state.model && !orderedNames.includes(state.model)) {
    orderedNames.push(state.model);
  }

  return orderedNames;
}

function getAiModelIdentity(model) {
  const type = String(model.type ?? model.provider ?? model.typeLabel ?? "model").toLowerCase();
  const rawName = model.modelId ?? model.name ?? model.id ?? model.key ?? "";
  const name = String(rawName)
    .trim()
    .toLowerCase()
    .replace(/:latest$/i, "");
  return `${type}:${name}`;
}

function splitModelSpecialty(value) {
  return String(value ?? "")
    .split("/")
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueValues(values) {
  return Array.from(new Set(values.filter(Boolean)));
}

function isCatalogRoute(route) {
  const value = String(route ?? "");
  return value.length > 0 && !/^[a-z]:[\\/]/i.test(value) && !value.startsWith("\\\\");
}

function shouldPreferModelCandidate(current, candidate) {
  const currentIsCatalog = isCatalogRoute(current.route);
  const candidateIsCatalog = isCatalogRoute(candidate.route);
  if (candidateIsCatalog !== currentIsCatalog) {
    return candidateIsCatalog;
  }

  const currentCapabilityCount = current.capabilities?.length ?? splitModelSpecialty(current.specialty).length;
  const candidateCapabilityCount = candidate.capabilities?.length ?? splitModelSpecialty(candidate.specialty).length;
  return candidateCapabilityCount > currentCapabilityCount;
}

function mergeDuplicateAiModel(current, candidate) {
  const primary = shouldPreferModelCandidate(current, candidate) ? candidate : current;
  const secondary = primary === current ? candidate : current;
  const capabilities = uniqueValues([
    ...(primary.capabilities ?? []),
    ...(secondary.capabilities ?? []),
    ...splitModelSpecialty(primary.specialty),
    ...splitModelSpecialty(secondary.specialty),
  ]);
  const expertIds = uniqueValues([
    ...(primary.expertIds ?? []),
    primary.expertId,
    ...(secondary.expertIds ?? []),
    secondary.expertId,
  ]);

  return {
    ...primary,
    capabilities,
    specialty: capabilities.length > 0
      ? capabilities.slice(0, 4).join(" / ")
      : primary.specialty,
    expertIds,
    duplicateCount: Math.max(primary.duplicateCount ?? 1, 1) + Math.max(secondary.duplicateCount ?? 1, 1),
  };
}

function dedupeAiModels(models) {
  const byIdentity = new Map();
  for (const model of models) {
    const identity = getAiModelIdentity(model);
    const existing = byIdentity.get(identity);
    byIdentity.set(identity, existing ? mergeDuplicateAiModel(existing, model) : model);
  }

  return Array.from(byIdentity.values());
}

function getAvailableAiModels() {
  if (state.cloudAiModels.length > 0) {
    return dedupeAiModels(state.cloudAiModels);
  }

  const ollamaNames = getStableOllamaModelNames();
  const ollamaModels = ollamaNames.map((name) => {
    const catalogItem = runtimeModelCatalog.ollama.find((model) => model.name === name);
    return {
      key: `ollama:${name}`,
      id: name,
      type: "ollama",
      typeLabel: "Ollama",
      name,
      route: catalogItem?.route ?? "runtime/ollama/server/models",
      model: catalogItem?.model ?? "Ollama model",
      specialty: catalogItem?.specialty ?? "Installed model",
      description: catalogItem?.description ?? "Ollama에 설치된 로컬 모델입니다. 채팅 또는 조합 모델의 실행 모델로 사용할 수 있습니다.",
      runnable: true,
    };
  });

  const dotnetModels = runtimeModelCatalog.dotnet.map((item) => ({
    key: `dotnet:${item.id}`,
    id: item.id,
    type: "dotnet",
    typeLabel: ".NET",
    name: item.name ?? item.id,
    route: item.route,
    model: item.model,
    specialty: item.specialty,
    description: item.description,
    runnable: false,
  }));

  return dedupeAiModels([...ollamaModels, ...dotnetModels]);
}

function normalizeCloudAIModel(model) {
  const expertId = model.expertId ?? model.ExpertId ?? model.id ?? model.Id ?? "";
  const provider = (model.provider ?? model.Provider ?? "expert").toLowerCase();
  const modelType = model.modelType ?? model.ModelType ?? "";
  const name = model.name ?? model.Name ?? model.modelId ?? model.ModelId ?? expertId;
  return {
    key: model.key ?? model.Key ?? `expert:${expertId}`,
    id: expertId,
    expertId,
    type: provider === "custom-dotnet" ? "dotnet" : provider,
    typeLabel: model.typeLabel ?? model.TypeLabel ?? provider,
    name,
    route: model.route ?? model.Route ?? "Cloud AI interface",
    model: model.modelId ?? model.ModelId ?? modelType,
    modelId: model.modelId ?? model.ModelId ?? name,
    specialty: model.specialty ?? model.Specialty ?? modelType,
    description: model.description ?? model.Description ?? `${expertId} Cloud AI expert`,
    runnable: model.runnable ?? model.Runnable ?? modelType !== "embedding",
    capabilities: model.capabilities ?? model.Capabilities ?? [],
    supportsStreaming: model.supportsStreaming ?? model.SupportsStreaming ?? false,
    supportsJsonOutput: model.supportsJsonOutput ?? model.SupportsJsonOutput ?? false,
    requiredMemoryMb: model.requiredMemoryMb ?? model.RequiredMemoryMb ?? 0,
  };
}

function normalizeCloudAIComposition(composition) {
  const expertIds = composition.expertIds ?? composition.ExpertIds ?? [];
  const parts = composition.parts ?? composition.Parts ?? expertIds.map((id) => `expert:${id}`);
  return normalizeModelCombination({
    id: composition.id ?? composition.Id ?? composition.compositionId ?? composition.CompositionId,
    compositionId: composition.id ?? composition.Id ?? composition.compositionId ?? composition.CompositionId,
    name: composition.name ?? composition.Name ?? composition.id ?? composition.Id,
    parts,
    expertIds,
    strategy: composition.strategy ?? composition.Strategy,
    fallback: composition.fallback ?? composition.Fallback ?? [],
    serverBacked: true,
  });
}

function applyCloudAIInterface(payload) {
  const models = payload.models ?? payload.Models ?? [];
  const compositions = payload.compositions ?? payload.Compositions ?? [];
  state.cloudAiInterface = payload;
  state.cloudAiModels = models.map(normalizeCloudAIModel).filter((model) => model.expertId);
  state.cloudAiCompositions = compositions.map(normalizeCloudAIComposition);
  state.modelCombinations = mergeModelCombinations(state.cloudAiCompositions, readStoredModelCombinations());
  state.models = state.cloudAiModels
    .filter((model) => model.type === "ollama")
    .map((model) => model.name);
  if (!state.selectedCombinationId && state.models.length > 0 && !state.models.includes(state.model)) {
    state.model = state.models[0];
  }
  state.cloudAiLoadError = "";
}

function mergeModelCombinations(primary, fallback) {
  const byId = new Map();
  for (const combination of [...primary, ...fallback]) {
    byId.set(combination.id, combination);
  }

  return Array.from(byId.values());
}

async function loadCloudAIInterface() {
  const payload = await getJson("/api/cloud-ai/interface");
  applyCloudAIInterface(payload);
  addLog(`Cloud AI interface models=${state.cloudAiModels.length}, compositions=${state.modelCombinations.length}`);
  render();
}

function normalizeMarketModel(model) {
  return {
    id: model.id ?? model.Id ?? "",
    name: model.name ?? model.Name ?? "",
    provider: model.provider ?? model.Provider ?? "",
    kind: model.kind ?? model.Kind ?? "",
    category: model.category ?? model.Category ?? "",
    modelId: model.modelId ?? model.ModelId ?? "",
    description: model.description ?? model.Description ?? "",
    license: model.license ?? model.License ?? "",
    sourceUrl: model.sourceUrl ?? model.SourceUrl ?? "",
    targetPath: model.targetPath ?? model.TargetPath ?? "",
    installed: model.installed ?? model.Installed ?? false,
  };
}

async function loadAiMarket() {
  const payload = await getJson("/api/market/models");
  const models = payload.models ?? payload.Models ?? [];
  state.marketModels = models.map(normalizeMarketModel).filter((model) => model.id);
  state.marketLoaded = true;
  state.marketError = "";
  addLog(`AI market models=${state.marketModels.length}`);
  render();
}

function resolveModelPart(partKey) {
  const availableModels = getAvailableAiModels();
  const directMatch = availableModels.find((model) => model.key === partKey);
  if (directMatch) {
    return directMatch;
  }

  const sourceMatch = state.cloudAiModels.find((model) => model.key === partKey);
  if (sourceMatch) {
    return sourceMatch;
  }

  if (partKey.startsWith("ollama:")) {
    const modelName = partKey.slice("ollama:".length);
    return availableModels.find((model) =>
      model.type === "ollama" &&
      (model.name === modelName || model.modelId === modelName || model.modelId === `${modelName}:latest`)
    ) ?? null;
  }

  return null;
}

function getExpertIdForModelPart(part) {
  if (!part) {
    return "";
  }

  if (Array.isArray(part.expertIds) && part.expertIds.length > 0) {
    return part.expertIds[0];
  }

  if (part.expertId) {
    return part.expertId;
  }

  if (part.type === "ollama") {
    const normalized = part.id.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
    return `ollama-${normalized}${normalized.endsWith("-latest") ? "" : "-latest"}`;
  }

  return part.id ?? "";
}

function inferCombinationApiModel(parts) {
  const ollamaPart = parts
    .map(resolveModelPart)
    .find((part) => part?.type === "ollama");
  return ollamaPart?.name ?? state.model ?? "llama3.2";
}

function getCombinationName(parts) {
  return parts
    .map(resolveModelPart)
    .filter(Boolean)
    .map((part) => part.name)
    .join(" + ");
}

function readStoredModelCombinations() {
  try {
    const raw = localStorage.getItem(modelCombinationStorageKey);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed.combinations)
      ? parsed.combinations.map(normalizeModelCombination).filter((combination) => combination.parts.length > 0)
      : [];
  } catch {
    return [];
  }
}

function writeStoredModelCombinations(combinations) {
  localStorage.setItem(
    modelCombinationStorageKey,
    JSON.stringify({ combinations: combinations.map(normalizeModelCombination) }),
  );
}

function normalizeModelCombination(combination) {
  const parts = Array.isArray(combination.parts)
    ? combination.parts.filter(Boolean)
    : Array.isArray(combination.Parts)
      ? combination.Parts.filter(Boolean)
      : [];
  const now = new Date().toISOString();
  return {
    id: combination.id ?? combination.Id ?? makeId("model-combo"),
    compositionId: combination.compositionId ?? combination.CompositionId ?? combination.id ?? combination.Id ?? "",
    name: combination.name ?? combination.Name ?? (getCombinationName(parts) || "AI 모델 조합"),
    parts,
    expertIds: Array.isArray(combination.expertIds)
      ? combination.expertIds.filter(Boolean)
      : Array.isArray(combination.ExpertIds)
        ? combination.ExpertIds.filter(Boolean)
        : parts.map(resolveModelPart).filter(Boolean).map(getExpertIdForModelPart).filter(Boolean),
    strategy: combination.strategy ?? combination.Strategy ?? "",
    fallback: combination.fallback ?? combination.Fallback ?? [],
    serverBacked: combination.serverBacked ?? combination.ServerBacked ?? false,
    apiModel: combination.apiModel ?? combination.ApiModel ?? inferCombinationApiModel(parts),
    createdAt: combination.createdAt ?? combination.CreatedAt ?? now,
  };
}

function getSelectedCombination() {
  return state.modelCombinations.find((combination) => combination.id === state.selectedCombinationId) ?? null;
}

function getActiveModelProfile() {
  const combination = getSelectedCombination();
  if (combination) {
    const parts = combination.parts.map(resolveModelPart).filter(Boolean);
    return {
      kind: "combination",
      label: combination.name,
      compositionId: combination.compositionId || combination.id,
      expertIds: combination.expertIds?.length > 0
        ? combination.expertIds
        : parts.map(getExpertIdForModelPart).filter(Boolean),
      apiModel: combination.apiModel || inferCombinationApiModel(combination.parts),
      parts,
      detail: parts.map((part) => `${part.name}: ${part.specialty}`).join(" / "),
    };
  }

  const selectedPart = resolveModelPart(`ollama:${state.model}`) ?? {
    type: "ollama",
    typeLabel: "Ollama",
    name: state.model,
    expertId: `ollama-${state.model.toLowerCase().replaceAll(".", "-")}-latest`,
    route: "runtime/ollama/server/models",
    model: "Ollama model",
    specialty: "Current chat model",
    runnable: true,
  };
  return {
    kind: "single",
    label: selectedPart.name,
    compositionId: "",
    expertIds: [getExpertIdForModelPart(selectedPart)].filter(Boolean),
    apiModel: selectedPart.name,
    parts: [selectedPart],
    detail: selectedPart.specialty,
  };
}

function buildChatRequestMessage(prompt, modelProfile) {
  const modelPrefix = modelProfile.kind === "combination"
    ? [
        `[AI 모델 조합: ${modelProfile.label}]`,
        `[실행 모델: ${modelProfile.apiModel}]`,
        `[조합 기능: ${modelProfile.detail}]`,
      ].join("\n")
    : "";
  const projectPrefix = state.selectedProjectName ? `[프로젝트: ${state.selectedProjectName}]` : "";
  return [modelPrefix, projectPrefix, prompt].filter(Boolean).join("\n");
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
    const error = await readError(response);
    throw new Error(error || `${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function deleteJson(path) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    const error = await readError(response);
    throw new Error(error || `${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function readError(response) {
  try {
    const payload = await response.json();
    return payload.error ?? payload.Error ?? "";
  } catch {
    return "";
  }
}

function makeId(prefix) {
  const randomId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${randomId}`;
}

function readStoredProjects() {
  const raw = localStorage.getItem(localProjectStorageKey);
  if (!raw) {
    return [];
  }

  const parsed = JSON.parse(raw);
  return Array.isArray(parsed.projects) ? parsed.projects.map(normalizeProject) : [];
}

function writeStoredProjects(projects) {
  localStorage.setItem(localProjectStorageKey, JSON.stringify({ projects: projects.map(normalizeProject) }));
}

function normalizeProject(project) {
  const name = getProjectName(project);
  const now = new Date().toISOString();
  return {
    id: project.id ?? project.Id ?? makeId("project"),
    name,
    relativePath: project.relativePath ?? project.RelativePath ?? `local://${name}`,
    createdAt: project.createdAt ?? project.CreatedAt ?? now,
    modifiedAt: project.modifiedAt ?? project.ModifiedAt ?? now,
    chats: getProjectChats(project).map(normalizeChat),
  };
}

function normalizeChat(chat) {
  const now = new Date().toISOString();
  return {
    id: getChatId(chat) || makeId("chat"),
    title: getChatTitle(chat),
    sessionId: getChatSessionId(chat) || makeId("session"),
    apiBaseUrl: chat.apiBaseUrl ?? chat.ApiBaseUrl ?? state.apiBaseUrl,
    titleFromFirstPrompt: chat.titleFromFirstPrompt ?? chat.TitleFromFirstPrompt ?? false,
    createdAt: chat.createdAt ?? chat.CreatedAt ?? now,
    modifiedAt: chat.modifiedAt ?? chat.ModifiedAt ?? now,
  };
}

function createLocalProject(name) {
  const cleanName = normalizeProjectName(name);
  if (state.projects.some((project) => getProjectName(project).toLowerCase() === cleanName.toLowerCase())) {
    throw new Error("이미 같은 이름의 프로젝트가 있습니다.");
  }

  const now = new Date().toISOString();
  const project = {
    id: makeId("project"),
    name: cleanName,
    relativePath: `local://${cleanName}`,
    createdAt: now,
    modifiedAt: now,
    chats: [],
  };

  state.projects = [project, ...state.projects];
  writeStoredProjects(state.projects);
  return project;
}

function renameLocalProject(currentName, nextName) {
  const cleanName = normalizeProjectName(nextName);
  if (
    currentName.toLowerCase() !== cleanName.toLowerCase() &&
    state.projects.some((project) => getProjectName(project).toLowerCase() === cleanName.toLowerCase())
  ) {
    throw new Error("이미 같은 이름의 프로젝트가 있습니다.");
  }

  let renamedProject = null;
  state.projects = state.projects.map((project) => {
    if (getProjectName(project) !== currentName) {
      return project;
    }

    renamedProject = {
      ...project,
      name: cleanName,
      relativePath: `local://${cleanName}`,
      modifiedAt: new Date().toISOString(),
    };
    return renamedProject;
  });

  if (!renamedProject) {
    throw new Error("프로젝트를 찾을 수 없습니다.");
  }

  writeStoredProjects(state.projects);
  return renamedProject;
}

function deleteLocalProject(projectName) {
  const nextProjects = state.projects.filter((project) => getProjectName(project) !== projectName);
  if (nextProjects.length === state.projects.length) {
    throw new Error("프로젝트를 찾을 수 없습니다.");
  }

  state.projects = nextProjects;
  writeStoredProjects(state.projects);
}

function createLocalChat(projectName) {
  let createdChat = null;
  state.projects = state.projects.map((project) => {
    if (getProjectName(project) !== projectName) {
      return project;
    }

    const chats = getProjectChats(project);
    const now = new Date().toISOString();
    createdChat = {
      id: makeId("chat"),
      title: `새 채팅 ${chats.length + 1}`,
      sessionId: makeId("session"),
      apiBaseUrl: state.apiBaseUrl,
      titleFromFirstPrompt: false,
      createdAt: now,
      modifiedAt: now,
    };

    return {
      ...project,
      chats: [createdChat, ...chats],
      modifiedAt: now,
    };
  });

  if (!createdChat) {
    throw new Error("프로젝트를 찾을 수 없습니다.");
  }

  writeStoredProjects(state.projects);
  return createdChat;
}

function updateSelectedChatTitleFromPrompt(prompt) {
  if (!state.selectedProjectName || !state.selectedChatId) {
    return;
  }

  let updatedTitle = "";
  const now = new Date().toISOString();
  state.projects = state.projects.map((project) => {
    if (getProjectName(project) !== state.selectedProjectName) {
      return project;
    }

    const chats = getProjectChats(project).map((chat) => {
      if (getChatId(chat) !== state.selectedChatId || chat.titleFromFirstPrompt) {
        return chat;
      }

      const currentTitle = getChatTitle(chat);
      if (!/^새 채팅 \d+$/.test(currentTitle)) {
        return { ...chat, titleFromFirstPrompt: true };
      }

      updatedTitle = summarizePromptTitle(prompt);
      return {
        ...chat,
        title: updatedTitle,
        titleFromFirstPrompt: true,
        modifiedAt: now,
      };
    });

    return {
      ...project,
      chats,
      modifiedAt: updatedTitle ? now : project.modifiedAt,
    };
  });

  if (updatedTitle) {
    writeStoredProjects(state.projects);
    addLog(`채팅 제목 변경: ${updatedTitle}`);
  }
}

function updateSelectedChatSession(sessionId) {
  if (!state.selectedProjectName || !state.selectedChatId || !sessionId) {
    return;
  }

  const now = new Date().toISOString();
  state.projects = state.projects.map((project) => {
    if (getProjectName(project) !== state.selectedProjectName) {
      return project;
    }

    return {
      ...project,
      modifiedAt: now,
      chats: getProjectChats(project).map((chat) =>
        getChatId(chat) === state.selectedChatId
          ? { ...chat, sessionId, apiBaseUrl: state.apiBaseUrl, modifiedAt: now }
          : chat),
    };
  });
  writeStoredProjects(state.projects);
}

function summarizePromptTitle(prompt) {
  const normalizedPrompt = prompt
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

  const rawTokens = normalizedPrompt.split(" ").filter(Boolean);
  const stopWords = new Set([
    "오늘",
    "내일",
    "이번",
    "제가",
    "나는",
    "나",
    "우리",
    "좀",
    "제발",
    "근데",
    "건데",
    "인데",
    "그리고",
    "그럼",
    "이거",
    "저거",
    "그거",
    "해줘",
    "해주세요",
    "알려줘",
    "알려주세요",
    "만들어줘",
    "만들어주세요",
    "갈",
    "가는",
    "가려고",
    "할",
    "하는",
    "하려고",
  ]);

  const keywords = [];
  for (const rawToken of rawTokens) {
    const keyword = normalizeTitleKeyword(rawToken);
    if (!keyword || stopWords.has(keyword) || keyword.length < 2 || keywords.includes(keyword)) {
      continue;
    }

    keywords.push(keyword);
    if (keywords.length >= 4) {
      break;
    }
  }

  const finalKeywords = keywords.includes("여행지")
    ? keywords.filter((keyword) => keyword !== "여행")
    : keywords;

  return finalKeywords.length > 0 ? finalKeywords.join(" ") : normalizedPrompt.slice(0, 18) || "새 채팅";
}

function normalizeTitleKeyword(token) {
  const cleanToken = token.trim().toLowerCase();
  if (!cleanToken) {
    return "";
  }

  if (cleanToken.includes("여행지")) {
    return "여행지";
  }

  if (cleanToken.includes("추천")) {
    return "추천";
  }

  if (cleanToken.includes("오류") || cleanToken.includes("에러") || cleanToken.includes("버그")) {
    return "오류";
  }

  if (cleanToken.includes("수정") || cleanToken.includes("고쳐") || cleanToken.includes("해결")) {
    return "수정";
  }

  if (cleanToken.includes("설명") || cleanToken.includes("알려")) {
    return "설명";
  }

  if (cleanToken.includes("구현") || cleanToken.includes("만들")) {
    return "구현";
  }

  return token
    .replace(/(해줘|해주세요|해줄래|해볼래|할래)$/u, "")
    .replace(/(합니다|하세요|해요|했어|했어요|하는|하려고|하고|해서|하면)$/u, "")
    .replace(/(으로|로|에서|에게|한테|부터|까지|보다|처럼|같이)$/u, "")
    .trim();
}

function normalizeProjectName(name) {
  const cleanName = (name ?? "").trim();
  if (!cleanName) {
    throw new Error("프로젝트 이름을 입력해주세요.");
  }

  if (cleanName === "." || cleanName === ".." || /[\\/:*?"<>|]/.test(cleanName)) {
    throw new Error("프로젝트 이름에 사용할 수 없는 문자가 있습니다.");
  }

  return cleanName;
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
    if (name === "채팅") {
      markInferenceError(error.message);
    }
    addLog(`${name} 실패: ${error.message}`);
  } finally {
    state.busy = false;
    render();
  }
}

function resetInferenceSteps() {
  state.inferenceSteps = inferenceStepTemplates.map(([title, detail]) => ({
    title,
    detail,
    status: "waiting",
  }));
}

function setInferenceStep(index, status, detail) {
  state.inferenceSteps = state.inferenceSteps.map((step, stepIndex) => {
    if (stepIndex < index && status === "running") {
      return { ...step, status: "done" };
    }

    if (stepIndex !== index) {
      return step;
    }

    return {
      ...step,
      status,
      detail: detail || step.detail,
    };
  });
}

function markInferenceError(message) {
  state.inferenceSteps = state.inferenceSteps.map((step) =>
    step.status === "running"
      ? { ...step, status: "error", detail: message }
      : step);
  state.inferenceSummary = `실패: ${message}`;
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
    <main class="panel-app ${state.sidebarOpen ? "" : "sidebar-collapsed"}" aria-label="Local AI web desktop panel">
      <aside class="sidebar ${state.sidebarOpen ? "" : "collapsed"}" aria-label="패널 메뉴">
        <header class="brand-row">
          <div class="brand-mark" aria-label="Local AI">N</div>
          <div class="brand-title">
            <strong>Local AI</strong>
            <span>Desktop Panel</span>
          </div>
          <button
            id="sidebarToggle"
            class="sidebar-toggle"
            type="button"
            aria-label="${state.sidebarOpen ? "패널 접기" : "패널 열기"}"
            aria-expanded="${state.sidebarOpen}">
            ${state.sidebarOpen ? "접기" : "열기"}
          </button>
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

    if (state.activePanel === "chat" && !state.projectsLoaded) {
      state.projectsLoaded = true;
      loadProjects({ silent: true });
    }

    if (state.activePanel === "market" && !state.marketLoaded && !state.busy) {
      state.marketLoaded = true;
      loadAiMarket().catch((error) => {
        state.marketError = error.message;
        addLog(`AI market load failed: ${error.message}`);
        render();
      });
    }

    document.querySelector("[data-autofocus]")?.focus();
  });
}

function renderNavButton(panel) {
  return `
    <button
      class="nav-card ${state.activePanel === panel.id ? "active" : ""}"
      type="button"
      title="${escapeHtml(panel.label)}"
      data-short-label="${escapeHtml(panel.shortLabel ?? panel.label.slice(0, 1))}"
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
    case "market":
      return renderMarketPanel();
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
    <section class="chat-panel ${state.projectPanelOpen ? "" : "project-collapsed"} ${state.inferencePanelOpen ? "" : "inference-collapsed"}">
      ${renderProjectPanel()}
      <section class="chat-main" aria-label="채팅 입력과 응답">
        <div class="chat-list" id="chatList" aria-live="polite">
          ${state.messages.map(renderMessage).join("")}
        </div>
        <section class="prompt-guides" aria-label="예시 입력 가이드라인">
          ${promptGuidelines.map((guide) => `
            <button class="guide-chip" type="button" data-guide="${escapeHtml(guide)}">${escapeHtml(guide)}</button>
          `).join("")}
        </section>
        <form class="prompt-panel" id="promptForm">
          <textarea id="promptInput" rows="3">WPF에서 ASP.NET API를 통해 응답해주세요.</textarea>
          <button id="sendButton" type="submit" ${state.busy ? "disabled" : ""}>전송</button>
        </form>
      </section>
      ${renderInferencePanel()}
    </section>
  `;
}

function renderProjectPanel() {
  if (!state.projectPanelOpen) {
    return `
      <aside class="project-panel collapsed" aria-label="프로젝트 패널 닫힘">
        <button id="toggleProjectPanel" class="panel-toggle" type="button" aria-label="프로젝트 패널 열기">열기</button>
        <span>프로젝트</span>
      </aside>
    `;
  }

  return `
    <aside class="project-panel" aria-label="프로젝트 폴더 관리">
      <header class="project-panel-header">
        <div>
          <strong>프로젝트</strong>
        </div>
        <button id="toggleProjectPanel" class="icon-button" type="button" aria-label="프로젝트 패널 닫기">접기</button>
      </header>

      <button id="addProjectButton" class="project-add-button" type="button" ${state.busy ? "disabled" : ""}>프로젝트 폴더 추가</button>

      <div class="project-list" aria-live="polite">
        ${renderProjectList()}
      </div>
    </aside>
  `;
}

function renderProjectList() {
  if (state.projectLoadError) {
    return `<p class="empty-text">${escapeHtml(state.projectLoadError)}</p>`;
  }

  if (!state.projectsLoaded) {
    return `<p class="empty-text">프로젝트 폴더를 불러오는 중입니다.</p>`;
  }

  if (state.projects.length === 0 && !state.isCreatingProject) {
    return `<p class="empty-text">생성된 프로젝트 폴더가 없습니다.</p>`;
  }

  const rows = [];
  if (state.isCreatingProject) {
    rows.push(renderProjectDraft());
  }

  rows.push(...state.projects.map(renderProjectItem));

  return rows.join("");
}

function renderProjectDraft() {
  return `
    <article class="project-item editing">
      <input
        id="projectDraftInput"
        class="project-name-input"
        type="text"
        value="${escapeHtml(state.draftProjectName)}"
        placeholder="프로젝트 이름 입력"
        data-autofocus>
    </article>
  `;
}

function renderProjectItem(project) {
  const name = getProjectName(project);
  const chats = getProjectChats(project);
  const selected = state.selectedProjectName === name;
  const editing = state.editingProjectName === name;

  return `
    <article class="project-item ${selected ? "selected" : ""}">
      <div class="project-row">
        ${editing
          ? `<input
              class="project-name-input"
              type="text"
              value="${escapeHtml(state.editingProjectValue)}"
              data-edit-project="${escapeHtml(name)}"
              data-autofocus>`
          : `<button class="project-select" type="button" data-project-name="${escapeHtml(name)}">
              <strong>${escapeHtml(name)}</strong>
            </button>`}
        <div class="project-actions">
          <button class="project-edit" type="button" data-edit-project-start="${escapeHtml(name)}" ${state.busy || editing ? "disabled" : ""}>수정</button>
          <button class="project-delete" type="button" data-delete-project="${escapeHtml(name)}" ${state.busy ? "disabled" : ""}>삭제</button>
        </div>
      </div>
      ${selected && !editing ? renderProjectChats(name, chats) : ""}
    </article>
  `;
}

function renderProjectChats(projectName, chats) {
  return `
    <div class="project-chat-box">
      <button class="chat-add" type="button" data-create-chat="${escapeHtml(projectName)}" ${state.busy ? "disabled" : ""}>+ 채팅 추가</button>
      <div class="project-chat-list">
        ${chats.length === 0
          ? `<p class="empty-text">아직 추가된 채팅이 없습니다.</p>`
          : chats.map((chat) => {
              const chatId = getChatId(chat);
              const selected = state.selectedChatId === chatId;
              return `
                <button
                  class="project-chat ${selected ? "selected" : ""}"
                  type="button"
                  data-project-name="${escapeHtml(projectName)}"
                  data-chat-id="${escapeHtml(chatId)}">
                  ${escapeHtml(getChatTitle(chat))}
                </button>
              `;
            }).join("")}
      </div>
    </div>
  `;
}

function renderInferencePanel() {
  if (!state.inferencePanelOpen) {
    return `
      <aside class="inference-panel collapsed" aria-label="추론 과정 패널 닫힘">
        <button id="toggleInferencePanel" class="panel-toggle" type="button" aria-label="추론 과정 패널 열기">열기</button>
        <span>추론 과정</span>
      </aside>
    `;
  }

  return `
    <aside class="inference-panel" aria-label="모델 추론 과정">
      <header>
        <div>
          <strong>추론 과정</strong>
          <span>${escapeHtml(state.inferenceSummary)}</span>
        </div>
        <button id="toggleInferencePanel" class="icon-button" type="button" aria-label="추론 과정 패널 닫기">접기</button>
      </header>
      <ol class="inference-steps">
        ${state.inferenceSteps.map((step) => `
          <li class="${escapeHtml(step.status)}">
            <strong>${escapeHtml(step.title)}</strong>
            <p>${escapeHtml(step.detail)}</p>
          </li>
        `).join("")}
      </ol>
    </aside>
  `;
}

function renderConnectionPanel() {
  return `
    <section class="model-layout">
      <section class="model-section orchestrator" aria-label="Semantic Kernel 상위 레이어">
        <header class="model-section-header">
          <div>
            <strong>Semantic Kernel</strong>
            <span>.NET 런타임과 Ollama 모델을 묶는 상위 오케스트레이션 계층</span>
          </div>
        </header>
        ${renderSemanticKernelLayer()}
      </section>

      ${renderModelCombinationSection()}
      ${renderModelDescriptionSection()}
    </section>
  `;
}

function renderSemanticKernelLayer() {
  const layer = state.cloudAiModels.find((model) => model.capabilities?.includes("local-runtime"))
    ?? runtimeModelCatalog.semanticKernel;
  return `
    <div class="model-item semantic-layer">
      <strong>${escapeHtml(layer.name)}</strong>
      <span>${escapeHtml(layer.purpose ?? layer.description ?? "Cloud AI interface orchestration layer")}</span>
      <small>${escapeHtml(layer.route)}</small>
    </div>
  `;
}

function renderDotnetModelList() {
  const dotnetModels = getAvailableAiModels().filter((item) =>
    item.type === "dotnet" || item.type === "mlnet" || item.type === "onnx-local" || item.type === "mlnet-local"
  );
  if (dotnetModels.length === 0) {
    return `<p class="empty-text">runtime/dotnet 아래에서 발견된 .NET 모델 런타임이 없습니다.</p>`;
  }

  return dotnetModels.map((item) => {
    const selected = state.selectedDotnetAiId === item.key;
    return `
      <button
        class="model-item ${selected ? "selected" : ""}"
        type="button"
        data-dotnet-ai-id="${escapeHtml(item.key)}">
        <strong>${escapeHtml(item.name ?? item.id)}</strong>
        <span>${escapeHtml(`${item.model} / ${item.specialty}`)}</span>
        <p class="model-item-description">${escapeHtml(item.description ?? "runtime/dotnet 아래에서 동작하는 .NET 기반 AI 런타임입니다.")}</p>
        <small>${escapeHtml(item.route)}</small>
      </button>
    `;
  }).join("");
}

function renderOllamaModelList() {
  const cloudOllamaModels = getAvailableAiModels().filter((model) => model.type === "ollama");
  if (cloudOllamaModels.length > 0) {
    return cloudOllamaModels.map((item) => {
      const selected = state.model === item.name || state.model === item.modelId;
      return `
        <button
          class="model-item ${selected ? "selected" : ""}"
          type="button"
          data-ollama-model="${escapeHtml(item.name)}">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(`${item.typeLabel} / ${item.specialty}`)}</span>
          <p class="model-item-description">${escapeHtml(item.description)}</p>
          <small>${escapeHtml(item.route)}</small>
        </button>
      `;
    }).join("");
  }

  const catalogByName = new Map(runtimeModelCatalog.ollama.map((model) => [model.name, model]));
  const modelNames = getStableOllamaModelNames();
  if (modelNames.length === 0) {
    return `<p class="empty-text">runtime/ollama 아래에서 발견된 Ollama 모델이 없습니다.</p>`;
  }

  return modelNames.map((modelName) => {
    const item = catalogByName.get(modelName) ?? {
      name: modelName,
      route: "Ollama API",
      model: "Ollama model",
      specialty: "Installed model",
      description: "Ollama에 설치된 로컬 모델입니다. 채팅 또는 조합 모델의 실행 모델로 사용할 수 있습니다.",
    };
    const selected = state.model === item.name;
    return `
      <button
        class="model-item ${selected ? "selected" : ""}"
        type="button"
        data-ollama-model="${escapeHtml(item.name)}">
        <strong>${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(selected ? `현재 채팅 모델 / ${item.specialty}` : `${item.model} / ${item.specialty}`)}</span>
        <p class="model-item-description">${escapeHtml(item.description)}</p>
        <small>${escapeHtml(item.route)}</small>
      </button>
    `;
  }).join("");
}

function renderModelCombinationSection() {
  const availableModels = getAvailableAiModels();
  const canCreateCombination = state.draftCombinationParts.length >= 2;
  return `
    <section class="model-section" aria-label="AI 모델 조합">
      <header class="model-section-header">
        <div>
          <strong>AI 모델 조합</strong>
          <span>local-ai 런타임 모델을 선택해 채팅에서 사용할 새 조합 모델을 만듭니다.</span>
        </div>
        <button id="createCombinationButton" class="compact-button" type="button" ${canCreateCombination ? "" : "disabled"}>조합 생성</button>
      </header>

      <div class="combination-builder">
        <label class="field">
          <span>조합 모델 이름</span>
          <input id="combinationName" type="text" value="${escapeHtml(state.draftCombinationName)}" placeholder="예: qwen2.5 + ONNX 분석">
        </label>
        <div class="combination-options" aria-label="조합할 AI 모델 선택">
          ${availableModels.map((item) => `
            <label class="combination-option">
              <input
                type="checkbox"
                value="${escapeHtml(item.key)}"
                data-combination-part="${escapeHtml(item.key)}"
                ${state.draftCombinationParts.includes(item.key) ? "checked" : ""}>
              <span>
                <strong>${escapeHtml(item.name)}</strong>
                <small>${escapeHtml(`${item.typeLabel} / ${item.specialty}`)}</small>
              </span>
            </label>
          `).join("")}
        </div>
      </div>

      <div class="combination-list">
        ${state.modelCombinations.length > 0
          ? state.modelCombinations.map(renderModelCombinationItem).join("")
          : `<p class="empty-text">아직 생성된 AI 모델 조합이 없습니다.</p>`}
      </div>
    </section>
  `;
}

function renderModelCombinationItem(combination) {
  const selected = state.selectedCombinationId === combination.id;
  const parts = combination.parts.map(resolveModelPart).filter(Boolean);
  return `
    <article class="combination-card ${selected ? "selected" : ""}">
      <button class="combination-select" type="button" data-select-combination="${escapeHtml(combination.id)}">
        <strong>${escapeHtml(combination.name)}</strong>
        <span>${escapeHtml(parts.map((part) => part.name).join(" + "))}</span>
        <small>${escapeHtml(`채팅 실행 모델: ${combination.apiModel}`)}</small>
      </button>
      <button class="compact-button danger" type="button" data-delete-combination="${escapeHtml(combination.id)}">삭제</button>
    </article>
  `;
}

function renderModelDescriptionSection() {
  return `
    <section class="model-section" aria-label="AI 모델 설명">
      <header class="model-section-header">
        <div>
          <strong>AI 모델 설명</strong>
          <span>local-ai에서 사용할 수 있는 모델의 역할과 용도를 확인합니다.</span>
        </div>
      </header>

      <div class="model-description-lists">
        <section class="model-list-group" aria-label=".NET 기반 AI 모델 리스트">
          <header class="model-list-group-header">
            <div>
              <strong>.NET 기반 AI 모델 리스트</strong>
              <span>runtime/dotnet 아래의 .NET 모델 런타임입니다.</span>
            </div>
          </header>
          <div class="model-list">
            ${renderDotnetModelList()}
          </div>
        </section>

        <section class="model-list-group" aria-label="Ollama 기반 AI 모델 리스트">
          <header class="model-list-group-header">
            <div>
              <strong>Ollama 기반 AI 모델 리스트</strong>
              <span>runtime/ollama 아래의 로컬 Ollama 모델입니다.</span>
            </div>
            <button id="modelsButton" class="compact-button" type="button" ${state.busy ? "disabled" : ""}>새로고침</button>
          </header>
          <div class="model-list">
            ${renderOllamaModelList()}
          </div>
        </section>
      </div>
    </section>
  `;
}

function renderConnectionPanel() {
  return renderModelWorkspace();
}

function renderModelWorkspace() {
  const activeProfile = getActiveModelProfile();
  const availableModels = getAvailableAiModels();
  const ollamaModels = availableModels.filter((model) => model.type === "ollama");
  const runtimeModels = availableModels.filter((model) => model.type !== "ollama");
  const loadedFromCloud = state.cloudAiModels.length > 0;
  return `
    <section class="model-workspace" aria-label="AI 모델 선택">
      <header class="model-hero">
        <div class="model-hero-copy">
          <span class="eyebrow">Cloud AI Interface</span>
          <h2>AI 모델 선택</h2>
          <p>모델을 고르고, 필요한 경우 여러 expert를 조합해서 채팅 실행 경로를 구성합니다.</p>
        </div>
        <div class="model-hero-actions">
          <button id="modelsButton" class="primary-action" type="button" ${state.busy ? "disabled" : ""}>모델 새로고침</button>
          <span class="sync-state ${loadedFromCloud ? "ready" : "warning"}">
            ${loadedFromCloud ? "Cloud AI 연결됨" : "로컬 기본 목록"}
          </span>
        </div>
      </header>

      ${state.cloudAiLoadError ? `<p class="model-alert">Cloud AI interface 로드 실패: ${escapeHtml(state.cloudAiLoadError)}</p>` : ""}

      <section class="model-status-grid" aria-label="현재 모델 상태">
        ${renderModelStatusCard("현재 실행", activeProfile.label, activeProfile.kind === "combination" ? "조합 프로필" : "단일 모델")}
        ${renderModelStatusCard("등록 expert", `${availableModels.length}개`, loadedFromCloud ? "Cloud AI catalog" : "fallback catalog")}
        ${renderModelStatusCard("조합 프로필", `${state.modelCombinations.length}개`, state.selectedCombinationId ? "선택됨" : "선택 없음")}
      </section>

      <section class="model-builder-shell">
        <div class="model-panel model-builder-panel">
          <div class="panel-heading">
            <div>
              <span class="section-kicker">Step 1</span>
              <strong>조합 만들기</strong>
              <p>2개 이상의 expert를 선택하면 Cloud AI composition profile로 저장됩니다.</p>
            </div>
            <button id="createCombinationButton" class="primary-action" type="button" ${state.draftCombinationParts.length >= 2 ? "" : "disabled"}>조합 생성</button>
          </div>
          <label class="field model-name-field">
            <span>조합 이름</span>
            <input id="combinationName" type="text" value="${escapeHtml(state.draftCombinationName)}" placeholder="예: qwen2.5 + 코드 검증">
          </label>
          <div class="model-pick-grid" aria-label="조합할 모델 선택">
            ${availableModels.map(renderModelPickOption).join("")}
          </div>
        </div>

        <aside class="model-panel model-summary-panel" aria-label="선택한 모델 요약">
          <div class="panel-heading compact">
            <div>
              <span class="section-kicker">Step 2</span>
              <strong>실행 경로</strong>
              <p>${escapeHtml(activeProfile.detail || "채팅에 사용할 모델을 선택하세요.")}</p>
            </div>
          </div>
          ${renderSemanticKernelSummary()}
          <div class="composition-stack">
            ${state.modelCombinations.length > 0
              ? state.modelCombinations.map(renderCompositionPill).join("")
              : `<p class="empty-text">아직 생성된 조합이 없습니다.</p>`}
          </div>
        </aside>
      </section>

      <section class="model-panel model-catalog-panel" aria-label="모델 카탈로그">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">Step 3</span>
            <strong>모델 카탈로그</strong>
            <p>Cloud AI interface에 등록된 expert를 역할별로 확인하고 단일 실행 모델을 선택합니다.</p>
          </div>
        </div>
        <div class="catalog-columns">
          <section>
            <h3>Ollama 모델</h3>
            <div class="catalog-grid">
              ${ollamaModels.length > 0 ? ollamaModels.map(renderCatalogModelCard).join("") : `<p class="empty-text">Ollama 모델이 없습니다.</p>`}
            </div>
          </section>
          <section>
            <h3>.NET / 로컬 런타임</h3>
            <div class="catalog-grid">
              ${runtimeModels.length > 0 ? runtimeModels.map(renderCatalogModelCard).join("") : `<p class="empty-text">.NET 또는 로컬 모델이 없습니다.</p>`}
            </div>
          </section>
        </div>
      </section>
    </section>
  `;
}

function renderModelStatusCard(label, value, detail) {
  return `
    <article class="model-status-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </article>
  `;
}

function renderModelPickOption(item) {
  const checked = state.draftCombinationParts.includes(item.key);
  return `
    <label class="model-pick-card ${checked ? "selected" : ""}">
      <input
        type="checkbox"
        value="${escapeHtml(item.key)}"
        data-combination-part="${escapeHtml(item.key)}"
        ${checked ? "checked" : ""}>
      <span>
        <strong>${escapeHtml(item.name)}</strong>
        <small>${escapeHtml(`${item.typeLabel} / ${item.specialty}`)}</small>
      </span>
    </label>
  `;
}

function renderSemanticKernelSummary() {
  const layer = state.cloudAiModels.find((model) => model.capabilities?.includes("local-runtime"))
    ?? runtimeModelCatalog.semanticKernel;
  return `
    <div class="runtime-summary">
      <span>Orchestrator</span>
      <strong>${escapeHtml(layer.name)}</strong>
      <p>${escapeHtml(layer.purpose ?? layer.description ?? "Cloud AI interface orchestration layer")}</p>
      <small>${escapeHtml(layer.route)}</small>
    </div>
  `;
}

function renderCompositionPill(combination) {
  const selected = state.selectedCombinationId === combination.id;
  const parts = combination.parts.map(resolveModelPart).filter(Boolean);
  return `
    <article class="composition-pill ${selected ? "selected" : ""}">
      <button type="button" data-select-combination="${escapeHtml(combination.id)}">
        <strong>${escapeHtml(combination.name)}</strong>
        <span>${escapeHtml(parts.map((part) => part.name).join(" + ") || combination.expertIds.join(" + "))}</span>
      </button>
      <button class="icon-danger" type="button" data-delete-combination="${escapeHtml(combination.id)}" aria-label="조합 삭제">삭제</button>
    </article>
  `;
}

function renderCatalogModelCard(item) {
  const selected = item.type === "ollama"
    ? state.model === item.name || state.model === item.modelId
    : state.selectedDotnetAiId === item.key;
  const dataAttribute = item.type === "ollama"
    ? `data-ollama-model="${escapeHtml(item.name)}"`
    : `data-dotnet-ai-id="${escapeHtml(item.key)}"`;
  return `
    <button class="catalog-card ${selected ? "selected" : ""}" type="button" ${dataAttribute}>
      <span class="model-chip">${escapeHtml(item.typeLabel)}</span>
      <strong>${escapeHtml(item.name)}</strong>
      <small>${escapeHtml(item.specialty)}</small>
      <p>${escapeHtml(item.description)}</p>
      <em>${escapeHtml(item.route)}</em>
    </button>
  `;
}

function renderMarketPanel() {
  const availableModels = getAvailableAiModels();
  const localModels = availableModels.filter((model) => model.type === "ollama");
  const runtimeModels = availableModels.filter((model) => model.type !== "ollama");
  return `
    <section class="market-workspace" aria-label="AI 마켓">
      <header class="market-hero">
        <div>
          <span class="eyebrow">AI Market</span>
          <h2>AI 마켓</h2>
          <p>Cloud AI interface에 붙일 모델, expert, 조합 템플릿을 관리하는 확장 공간입니다.</p>
        </div>
      </header>

      <section class="market-grid">
        <article class="market-card">
          <strong>로컬 모델</strong>
          <span>${localModels.length}개 사용 가능</span>
          <p>Ollama 모델은 AI 모델 선택 페이지에서 바로 조합하거나 단일 실행 모델로 사용할 수 있습니다.</p>
        </article>
        <article class="market-card">
          <strong>.NET / ML 런타임</strong>
          <span>${runtimeModels.length}개 연결됨</span>
          <p>ONNX, ML.NET, custom .NET expert는 Cloud AI interface의 공통 Expert 규격 뒤에 숨겨집니다.</p>
        </article>
        <article class="market-card">
          <strong>조합 템플릿</strong>
          <span>${state.modelCombinations.length}개 등록됨</span>
          <p>생성된 composition profile은 채팅 요청에서 compositionId로 전달됩니다.</p>
        </article>
      </section>

      <section class="market-panel">
        <div class="panel-heading compact">
          <span class="section-kicker">Next</span>
          <strong>마켓 기능 준비 영역</strong>
          <p>설치, 업데이트, 권한 검토, expert 템플릿 추가 같은 배포용 기능은 이 페이지에 배치합니다.</p>
        </div>
      </section>
    </section>
  `;
}

function renderMarketPanel() {
  const models = state.marketModels;
  const installedCount = models.filter((model) => model.installed).length;
  const ollamaModels = models.filter((model) => model.kind === "ollama");
  const dotnetModels = models.filter((model) => model.kind !== "ollama");
  return `
    <section class="market-workspace" aria-label="AI 마켓">
      <header class="market-hero">
        <div>
          <span class="eyebrow">AI Market</span>
          <h2>AI 마켓</h2>
          <p>무료로 사용할 수 있는 로컬 AI 모델을 runtime 아래에 분류해서 다운로드하거나 삭제합니다.</p>
        </div>
        <button id="marketRefreshButton" class="primary-action" type="button" ${state.busy ? "disabled" : ""}>목록 새로고침</button>
      </header>

      ${state.marketError ? `<p class="model-alert">AI 마켓 로드 실패: ${escapeHtml(state.marketError)}</p>` : ""}

      <section class="market-grid">
        <article class="market-card">
          <strong>마켓 모델</strong>
          <span>${models.length}개</span>
          <p>Ollama, ONNX, ML.NET 계열을 runtime 폴더 기준으로 분류합니다.</p>
        </article>
        <article class="market-card">
          <strong>설치됨</strong>
          <span>${installedCount}개</span>
          <p>설치된 모델은 AI 모델 선택 화면과 Cloud AI interface catalog에서 사용할 수 있습니다.</p>
        </article>
        <article class="market-card">
          <strong>저장 위치</strong>
          <span>runtime</span>
          <p>Ollama는 runtime/ollama/server/models, ONNX는 runtime/dotnet/models/onnx에 저장됩니다.</p>
        </article>
      </section>

      <section class="market-panel">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">Ollama</span>
            <strong>언어 모델 / 임베딩 모델</strong>
            <p>다운로드는 ollama pull을 사용하며 OLLAMA_MODELS를 runtime/ollama/server/models로 고정합니다.</p>
          </div>
        </div>
        <div class="market-model-grid">
          ${ollamaModels.length > 0 ? ollamaModels.map(renderMarketModelCard).join("") : `<p class="empty-text">마켓 모델 목록을 불러오는 중입니다.</p>`}
        </div>
      </section>

      <section class="market-panel">
        <div class="panel-heading">
          <div>
            <span class="section-kicker">.NET</span>
            <strong>ONNX / ML.NET 모델</strong>
            <p>직접 다운로드 가능한 모델은 runtime/dotnet/models 아래에 성질별로 저장합니다.</p>
          </div>
        </div>
        <div class="market-model-grid">
          ${dotnetModels.length > 0 ? dotnetModels.map(renderMarketModelCard).join("") : `<p class="empty-text">.NET 계열 마켓 모델이 없습니다.</p>`}
        </div>
      </section>
    </section>
  `;
}

function renderMarketModelCard(model) {
  return `
    <article class="market-model-card ${model.installed ? "installed" : ""}">
      <div class="market-model-card-header">
        <span class="model-chip">${escapeHtml(model.kind.toUpperCase())}</span>
        <span class="install-state">${model.installed ? "설치됨" : "미설치"}</span>
      </div>
      <strong>${escapeHtml(model.name)}</strong>
      <small>${escapeHtml(`${model.provider} / ${model.category}`)}</small>
      <p>${escapeHtml(model.description)}</p>
      <dl>
        <div><dt>모델 ID</dt><dd>${escapeHtml(model.modelId)}</dd></div>
        <div><dt>라이선스</dt><dd>${escapeHtml(model.license)}</dd></div>
        <div><dt>저장 위치</dt><dd>${escapeHtml(model.targetPath)}</dd></div>
      </dl>
      <div class="market-actions">
        <button class="primary-action" type="button" data-market-download="${escapeHtml(model.id)}" ${state.busy || model.installed ? "disabled" : ""}>다운로드</button>
        <button class="compact-button danger" type="button" data-market-delete="${escapeHtml(model.id)}" ${state.busy || !model.installed ? "disabled" : ""}>삭제</button>
      </div>
    </article>
  `;
}

function renderSettingsPanel() {
  return `
    <section class="content-grid">
      <div class="content-card wide">
        <label class="field">
          <span>API 연결</span>
          <input id="apiBaseUrl" type="text" value="${escapeHtml(state.apiBaseUrl)}">
        </label>
        <button id="healthButton" type="button" ${state.busy ? "disabled" : ""}>상태 확인</button>
      </div>

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

function getProjectName(project) {
  return project.name ?? project.Name ?? "";
}

function getProjectChats(project) {
  return project.chats ?? project.Chats ?? [];
}

function getChatId(chat) {
  return chat.id ?? chat.Id ?? "";
}

function getChatTitle(chat) {
  return chat.title ?? chat.Title ?? "새 채팅";
}

function getChatSessionId(chat) {
  return chat.sessionId ?? chat.SessionId ?? "";
}

function getChatApiBaseUrl(chat) {
  return chat.apiBaseUrl ?? chat.ApiBaseUrl ?? "";
}

function findProject(projectName) {
  return state.projects.find((project) => getProjectName(project) === projectName);
}

function findProjectChat(projectName, chatId) {
  return getProjectChats(findProject(projectName) ?? {}).find((chat) => getChatId(chat) === chatId);
}

async function loadProjects({ silent = false } = {}) {
  try {
    state.projects = readStoredProjects();
    state.projectLoadError = "";
  } catch (error) {
    state.projectLoadError = "브라우저 저장소에서 프로젝트를 불러올 수 없습니다.";
    if (!silent) {
      addLog(`프로젝트 목록 실패: ${error.message}`);
    }
  } finally {
    state.projectsLoaded = true;
    render();
  }
}

function renderMessage(message) {
  if (message.role === "system") {
    return "";
  }

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

  document.querySelector("#sidebarToggle")?.addEventListener("click", () => {
    state.sidebarOpen = !state.sidebarOpen;
    render();
  });

  document.querySelector("#toggleProjectPanel")?.addEventListener("click", () => {
    state.projectPanelOpen = !state.projectPanelOpen;
    render();
  });

  document.querySelector("#toggleInferencePanel")?.addEventListener("click", () => {
    state.inferencePanelOpen = !state.inferencePanelOpen;
    render();
  });

  document.querySelector("#addProjectButton")?.addEventListener("click", () => {
    state.isCreatingProject = true;
    state.draftProjectName = "";
    state.editingProjectName = "";
    state.editingProjectValue = "";
    render();
  });

  document.querySelector("#projectDraftInput")?.addEventListener("input", (event) => {
    state.draftProjectName = event.target.value;
  });

  document.querySelector("#projectDraftInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      createProjectFromDraft();
    }

    if (event.key === "Escape") {
      state.isCreatingProject = false;
      state.draftProjectName = "";
      render();
    }
  });

  document.querySelectorAll("[data-edit-project-start]").forEach((button) => {
    button.addEventListener("click", () => {
      state.editingProjectName = button.dataset.editProjectStart;
      state.editingProjectValue = button.dataset.editProjectStart;
      state.isCreatingProject = false;
      render();
    });
  });

  document.querySelectorAll("[data-edit-project]").forEach((input) => {
    input.addEventListener("input", (event) => {
      state.editingProjectValue = event.target.value;
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        renameProjectFromEdit(input.dataset.editProject);
      }

      if (event.key === "Escape") {
        state.editingProjectName = "";
        state.editingProjectValue = "";
        render();
      }
    });
  });

  function createProjectFromDraft() {
    const name = state.draftProjectName.trim();
    if (!name) {
      addLog("프로젝트 이름을 입력해주세요.");
      render();
      return;
    }

    runAction("프로젝트 폴더 생성", async () => {
      const project = createLocalProject(name);
      state.isCreatingProject = false;
      state.draftProjectName = "";
      state.selectedProjectName = getProjectName(project);
      state.selectedChatId = "";
      addLog(`프로젝트 생성: ${state.selectedProjectName}`);
    });
  }

  function renameProjectFromEdit(currentName) {
    const nextName = state.editingProjectValue.trim();
    if (!nextName) {
      addLog("프로젝트 이름을 입력해주세요.");
      render();
      return;
    }

    runAction("프로젝트 이름 수정", async () => {
      const project = renameLocalProject(currentName, nextName);
      const renamedName = getProjectName(project);
      if (state.selectedProjectName === currentName) {
        state.selectedProjectName = renamedName;
      }
      state.editingProjectName = "";
      state.editingProjectValue = "";
      addLog(`프로젝트 이름 수정: ${currentName} -> ${renamedName}`);
    });
  }

  document.querySelectorAll(".project-select[data-project-name]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedProjectName = button.dataset.projectName;
      state.selectedChatId = "";
      addLog(`프로젝트 선택: ${state.selectedProjectName}`);
      render();
    });
  });

  document.querySelectorAll("[data-create-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      const projectName = button.dataset.createChat;
      runAction("프로젝트 채팅 추가", async () => {
        const chat = createLocalChat(projectName);
        state.selectedProjectName = projectName;
        state.selectedChatId = getChatId(chat);
        state.sessionId = getChatSessionId(chat);
        state.messages = [
          {
            role: "system",
            content: `${projectName} 폴더에 ${getChatTitle(chat)}이 추가되었습니다.`,
          },
        ];
        addLog(`채팅 추가: ${projectName} / ${getChatTitle(chat)}`);
      });
    });
  });

  document.querySelectorAll("[data-chat-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const projectName = button.dataset.projectName;
      const chatId = button.dataset.chatId;
      const chat = findProjectChat(projectName, chatId);
      state.selectedProjectName = projectName;
      state.selectedChatId = chatId;
      state.sessionId = chat ? getChatSessionId(chat) : state.sessionId;
      state.apiBaseUrl = chat ? getChatApiBaseUrl(chat) || state.apiBaseUrl : state.apiBaseUrl;
      state.messages = [
        {
          role: "system",
          content: `${projectName} / ${chat ? getChatTitle(chat) : "선택한 채팅"}으로 전환되었습니다.`,
        },
      ];
      addLog(`채팅 선택: ${projectName} / ${chat ? getChatTitle(chat) : chatId}`);
      render();
    });
  });

  document.querySelectorAll("[data-delete-project]").forEach((button) => {
    button.addEventListener("click", () => {
      const projectName = button.dataset.deleteProject;
      runAction("프로젝트 폴더 삭제", async () => {
        deleteLocalProject(projectName);
        if (state.selectedProjectName === projectName) {
          state.selectedProjectName = "";
          state.selectedChatId = "";
          state.sessionId = "";
        }
        addLog(`프로젝트 삭제: ${projectName}`);
      });
    });
  });

  document.querySelectorAll("[data-guide]").forEach((button) => {
    button.addEventListener("click", () => {
      const promptInput = document.querySelector("#promptInput");
      if (promptInput) {
        promptInput.value = button.dataset.guide;
        promptInput.focus();
      }
    });
  });

  document.querySelector("#apiBaseUrl")?.addEventListener("input", (event) => {
    state.apiBaseUrl = event.target.value;
  });

  document.querySelectorAll("[data-dotnet-ai-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedDotnetAiId = button.dataset.dotnetAiId;
      state.selectedCombinationId = "";
      addLog(`.NET AI 선택: ${state.selectedDotnetAiId}`);
      render();
    });
  });

  document.querySelectorAll("[data-ollama-model]").forEach((button) => {
    button.addEventListener("click", () => {
      state.model = button.dataset.ollamaModel;
      state.selectedCombinationId = "";
      addLog(`Ollama 모델 선택: ${state.model}`);
      render();
    });
  });

  document.querySelector("#combinationName")?.addEventListener("input", (event) => {
    state.draftCombinationName = event.target.value;
  });

  document.querySelectorAll("[data-combination-part]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const partKey = checkbox.dataset.combinationPart;
      state.draftCombinationParts = checkbox.checked
        ? Array.from(new Set([...state.draftCombinationParts, partKey]))
        : state.draftCombinationParts.filter((key) => key !== partKey);
      render();
    });
  });

  document.querySelector("#createCombinationButton")?.addEventListener("click", () => {
    const parts = state.draftCombinationParts.filter(Boolean);
    if (parts.length < 2) {
      addLog("AI 모델 조합은 2개 이상의 모델을 선택해야 합니다.");
      render();
      return;
    }

    const name = state.draftCombinationName.trim() || getCombinationName(parts);
    const selectedExperts = parts
      .map(resolveModelPart)
      .filter(Boolean)
      .map(getExpertIdForModelPart)
      .filter(Boolean);

    runAction("Cloud AI composition", async () => {
      const created = await postJson("/api/cloud-ai/compositions", {
        name,
        expertIds: selectedExperts,
        strategy: selectedExperts.length > 2 ? "parallel-judge" : "pipeline",
      });
      const combination = normalizeCloudAIComposition(created);
      state.modelCombinations = mergeModelCombinations([combination], state.modelCombinations);
      state.selectedCombinationId = combination.id;
      state.model = combination.apiModel;
      state.draftCombinationName = "";
      state.draftCombinationParts = [];
      writeStoredModelCombinations(state.modelCombinations.filter((item) => !item.serverBacked));
      addLog(`Cloud AI composition created: ${combination.name}`);
    });
    return;

    const combination = normalizeModelCombination({
      id: makeId("model-combo"),
      name,
      parts,
      apiModel: inferCombinationApiModel(parts),
      createdAt: new Date().toISOString(),
    });
    state.modelCombinations = [...state.modelCombinations, combination];
    state.selectedCombinationId = combination.id;
    state.model = combination.apiModel;
    state.draftCombinationName = "";
    state.draftCombinationParts = [];
    writeStoredModelCombinations(state.modelCombinations);
    addLog(`AI 모델 조합 생성: ${combination.name}`);
    render();
  });

  document.querySelectorAll("[data-select-combination]").forEach((button) => {
    button.addEventListener("click", () => {
      const combination = state.modelCombinations.find((item) => item.id === button.dataset.selectCombination);
      if (!combination) {
        return;
      }

      state.selectedCombinationId = combination.id;
      state.model = combination.apiModel || inferCombinationApiModel(combination.parts);
      addLog(`AI 모델 조합 선택: ${combination.name}`);
      render();
    });
  });

  document.querySelectorAll("[data-delete-combination]").forEach((button) => {
    button.addEventListener("click", () => {
      const combinationId = button.dataset.deleteCombination;
      const combination = state.modelCombinations.find((item) => item.id === combinationId);
      state.modelCombinations = state.modelCombinations.filter((item) => item.id !== combinationId);
      if (state.selectedCombinationId === combinationId) {
        state.selectedCombinationId = "";
      }
      writeStoredModelCombinations(state.modelCombinations.filter((item) => !item.serverBacked));
      addLog(`AI 모델 조합 삭제: ${combination?.name ?? combinationId}`);
      render();
    });
  });

  document.querySelector("#nasPath")?.addEventListener("input", (event) => {
    state.nasPath = event.target.value;
  });

  document.querySelector("#healthButton")?.addEventListener("click", () => {
    state.activePanel = "settings";
    runAction("상태 확인", async () => {
      const health = await getJson("/api/health");
      addLog(`API=${health.api ?? health.Api}, Status=${health.status ?? health.Status}, Ollama=${health.ollama ?? "unknown"}`);
    });
  });

  document.querySelector("#modelsButton")?.addEventListener("click", () => {
    state.activePanel = "connection";
    runAction("Cloud AI interface catalog", loadCloudAIInterface);
    return;
    runAction("모델 목록", async () => {
      const payload = await getJson("/api/models");
      const models = payload.models ?? payload.Models ?? [];
      state.models = models.length > 0 ? models : [payload.configuredModel ?? payload.ConfiguredModel ?? state.model];
      if (!state.selectedCombinationId) {
        state.model = state.models[0] || state.model;
      }
      addLog(`모델 ${state.models.length}개를 읽었습니다.`);
    });
  });

  document.querySelector("#marketRefreshButton")?.addEventListener("click", () => {
    state.activePanel = "market";
    runAction("AI market refresh", loadAiMarket);
  });

  document.querySelectorAll("[data-market-download]").forEach((button) => {
    button.addEventListener("click", () => {
      const modelId = button.dataset.marketDownload;
      runAction("AI model download", async () => {
        const result = await postJson(`/api/market/models/${encodeURIComponent(modelId)}/download`, {});
        const model = normalizeMarketModel(result.model ?? result.Model ?? {});
        state.marketModels = state.marketModels.map((item) => item.id === model.id ? model : item);
        state.marketLoaded = false;
        await loadAiMarket();
        await loadCloudAIInterface();
        addLog(`AI model downloaded: ${model.name || modelId}`);
      });
    });
  });

  document.querySelectorAll("[data-market-delete]").forEach((button) => {
    button.addEventListener("click", () => {
      const modelId = button.dataset.marketDelete;
      runAction("AI model delete", async () => {
        const result = await deleteJson(`/api/market/models/${encodeURIComponent(modelId)}`);
        const model = normalizeMarketModel(result.model ?? result.Model ?? {});
        state.marketModels = state.marketModels.map((item) => item.id === model.id ? model : item);
        state.marketLoaded = false;
        await loadAiMarket();
        await loadCloudAIInterface();
        addLog(`AI model deleted: ${model.name || modelId}`);
      });
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
    resetInferenceSteps();
    state.inferenceSummary = state.selectedProjectName
      ? `${state.selectedProjectName} 기준으로 요청을 준비합니다.`
      : "선택된 프로젝트 없이 요청을 준비합니다.";
    runAction("채팅", async () => {
      const modelProfile = getActiveModelProfile();
      state.model = modelProfile.apiModel;
      addMessage("user", prompt);
      updateSelectedChatTitleFromPrompt(prompt);
      setInferenceStep(0, "done", `입력 길이 ${prompt.length}자를 분석했습니다.`);
      setInferenceStep(1, "running", state.selectedProjectName
        ? `${state.selectedProjectName} 프로젝트 맥락을 포함합니다.`
        : "일반 채팅 세션 맥락으로 구성합니다.");
      render();

      setInferenceStep(1, "done");
      setInferenceStep(2, "running", `${modelProfile.label} 모델 응답을 기다립니다.`);
      render();

      const response = await postJson("/api/chat", {
        sessionId: state.sessionId || null,
        model: modelProfile.apiModel,
        compositionId: modelProfile.compositionId || null,
        preferredExperts: modelProfile.expertIds ?? [],
        message: buildChatRequestMessage(prompt, modelProfile),
      });
      state.sessionId = response.sessionId ?? response.SessionId ?? state.sessionId;
      updateSelectedChatSession(state.sessionId);
      setInferenceStep(2, "done", response.source ?? response.Source ?? "모델 응답을 수신했습니다.");
      setInferenceStep(3, "done", "채팅 화면에 표시할 응답을 정리했습니다.");
      state.inferenceSummary = `모델: ${modelProfile.label}`;
      addMessage("assistant", response.response ?? response.Response ?? response.message ?? response.Message ?? "응답 본문이 비어 있습니다.");
      addLog(`채팅 응답 수신: ${new Date().toLocaleTimeString("ko-KR", { hour12: false })}`);
    });
  });
}

render();
loadCloudAIInterface().catch((error) => {
  state.cloudAiLoadError = error.message;
  addLog(`Cloud AI interface load failed: ${error.message}`);
  render();
});
