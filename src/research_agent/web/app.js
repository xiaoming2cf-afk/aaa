const storageKeys = {
  token: "erp.session.token",
  workspaceId: "erp.workspace.id",
};

const state = {
  token: localStorage.getItem(storageKeys.token) || "",
  user: null,
  workspaces: [],
  selectedWorkspaceId: localStorage.getItem(storageKeys.workspaceId) || "",
  openAlexResults: [],
};

const dom = {
  toast: document.getElementById("toast"),
  healthStatus: document.getElementById("health-status"),
  sessionIndicator: document.getElementById("session-indicator"),
  userSummary: document.getElementById("user-summary"),
  workspaceSelect: document.getElementById("workspace-select"),
  integrationList: document.getElementById("integration-list"),
  briefingList: document.getElementById("briefing-list"),
  openalexResults: document.getElementById("openalex-results"),
  literatureList: document.getElementById("literature-list"),
  assetList: document.getElementById("asset-list"),
  knowledgeList: document.getElementById("knowledge-list"),
  scheduleList: document.getElementById("schedule-list"),
  analysisOutput: document.getElementById("analysis-output"),
};

function escapeHtml(value) {
  return (value ?? "")
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message, isError = false) {
  dom.toast.textContent = message;
  dom.toast.classList.remove("hidden");
  dom.toast.style.background = isError ? "rgba(111, 29, 29, 0.95)" : "rgba(31, 30, 26, 0.92)";
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => dom.toast.classList.add("hidden"), 3200);
}

async function api(path, options = {}, auth = true) {
  const headers = new Headers(options.headers || {});
  if (auth && state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    if (response.status === 401) {
      clearSession();
    }
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

function clearSession() {
  state.token = "";
  state.user = null;
  state.workspaces = [];
  state.selectedWorkspaceId = "";
  localStorage.removeItem(storageKeys.token);
  localStorage.removeItem(storageKeys.workspaceId);
  renderSession();
  renderWorkspaceOptions();
  clearLists();
}

function ensureWorkspace() {
  if (!state.selectedWorkspaceId) {
    throw new Error("请先登录并选择工作区。");
  }
}

function setSession(payload) {
  state.token = payload.session_token;
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  state.selectedWorkspaceId =
    state.selectedWorkspaceId ||
    state.workspaces[0]?.id ||
    "";
  localStorage.setItem(storageKeys.token, state.token);
  if (state.selectedWorkspaceId) {
    localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
  }
  renderSession();
  renderWorkspaceOptions();
}

function renderSession() {
  if (!state.user) {
    dom.sessionIndicator.textContent = "未登录";
    dom.userSummary.textContent = "请先注册或登录";
    return;
  }
  dom.sessionIndicator.textContent = "已登录";
  dom.userSummary.textContent = `${state.user.full_name} · ${state.user.email}`;
}

function renderWorkspaceOptions() {
  dom.workspaceSelect.innerHTML = "";
  if (!state.workspaces.length) {
    dom.workspaceSelect.innerHTML = `<option value="">暂无工作区</option>`;
    return;
  }
  for (const workspace of state.workspaces) {
    const option = document.createElement("option");
    option.value = workspace.id;
    option.textContent = workspace.name;
    option.selected = workspace.id === state.selectedWorkspaceId;
    dom.workspaceSelect.appendChild(option);
  }
}

function emptyCard(message) {
  return `<div class="card"><p>${escapeHtml(message)}</p></div>`;
}

function clearLists() {
  dom.integrationList.innerHTML = emptyCard("登录后可查看连接。");
  dom.briefingList.innerHTML = emptyCard("登录后可生成简报。");
  dom.openalexResults.innerHTML = emptyCard("等待检索。");
  dom.literatureList.innerHTML = emptyCard("暂无文献。");
  dom.assetList.innerHTML = emptyCard("暂无资产。");
  dom.knowledgeList.innerHTML = emptyCard("暂无知识条目。");
  dom.scheduleList.innerHTML = emptyCard("暂无定时任务。");
  dom.analysisOutput.textContent = "等待分析结果";
}

function renderIntegrations(items) {
  if (!items.length) {
    dom.integrationList.innerHTML = emptyCard("暂无连接。");
    return;
  }
  dom.integrationList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.label)}</h4>
          <p>${escapeHtml(item.category)} · ${escapeHtml(item.kind)} · ${escapeHtml(item.model || "default model")}</p>
          <p>${item.is_default ? "默认连接" : "非默认连接"}</p>
          <div class="actions">
            <button type="button" class="secondary" data-test-integration="${item.id}">测试</button>
            <button type="button" class="secondary" data-delete-integration="${item.id}">删除</button>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderBriefings(items) {
  if (!items.length) {
    dom.briefingList.innerHTML = emptyCard("暂无简报。");
    return;
  }
  dom.briefingList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.created_at)}</p>
          <pre>${escapeHtml(item.summary_markdown)}</pre>
        </div>
      `,
    )
    .join("");
}

function renderOpenAlexResults(items) {
  if (!items.length) {
    dom.openalexResults.innerHTML = emptyCard("暂无检索结果。");
    return;
  }
  dom.openalexResults.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.authors || []).slice(0, 4).join(", "))}</p>
          <p>${escapeHtml(`${item.publication_year || "n/a"} · cited ${item.cited_by_count || 0}`)}</p>
        </div>
      `,
    )
    .join("");
}

function renderLiterature(items) {
  if (!items.length) {
    dom.literatureList.innerHTML = emptyCard("文献库为空。");
    return;
  }
  dom.literatureList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.authors || []).slice(0, 4).join(", "))}</p>
          <p>${escapeHtml(item.venue || "unknown venue")} · ${escapeHtml(item.publication_year || "n/a")}</p>
        </div>
      `,
    )
    .join("");
}

function renderAssets(items) {
  if (!items.length) {
    dom.assetList.innerHTML = emptyCard("暂无数据资产。");
    return;
  }
  dom.assetList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>ID: ${escapeHtml(item.id)}</p>
          <p>${escapeHtml(item.kind)} · ${escapeHtml(item.content_type || "unknown")}</p>
          <div class="actions">
            <button type="button" class="secondary" data-download-asset="${item.id}">下载</button>
            ${item.kind.startsWith("dataset") ? `<button type="button" class="secondary" data-clean-asset="${item.id}">清洗</button>` : ""}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderKnowledge(items) {
  if (!items.length) {
    dom.knowledgeList.innerHTML = emptyCard("暂无知识条目。");
    return;
  }
  dom.knowledgeList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.tags || []).join(", ")) || "无标签"}</p>
          <p>${escapeHtml(item.content)}</p>
        </div>
      `,
    )
    .join("");
}

function renderSchedules(items) {
  if (!items.length) {
    dom.scheduleList.innerHTML = emptyCard("暂无定时任务。");
    return;
  }
  dom.scheduleList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.name)}</h4>
          <p>${escapeHtml(item.job_type)} · ${escapeHtml(item.timezone_name)} · ${escapeHtml(item.local_time)}</p>
          <p>下次运行: ${escapeHtml(item.next_run_at || "未计算")}</p>
        </div>
      `,
    )
    .join("");
}

async function fetchHealth() {
  const [health, bootstrap] = await Promise.all([
    api("/api/health", {}, false),
    api("/api/bootstrap", {}, false),
  ]);
  dom.healthStatus.textContent = `${health.status} · ${bootstrap.supported_llm_kinds.length} providers`;
}

async function loadSession() {
  if (!state.token) {
    renderSession();
    renderWorkspaceOptions();
    clearLists();
    return;
  }
  const payload = await api("/api/auth/me");
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  if (!state.workspaces.some((item) => item.id === state.selectedWorkspaceId)) {
    state.selectedWorkspaceId = state.workspaces[0]?.id || "";
    if (state.selectedWorkspaceId) {
      localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
    }
  }
  renderSession();
  renderWorkspaceOptions();
  await refreshWorkspaceData();
}

async function refreshWorkspaceData() {
  ensureWorkspace();
  const workspaceId = state.selectedWorkspaceId;
  const [integrations, briefings, literature, assets, knowledge, schedules] = await Promise.all([
    api("/api/integrations"),
    api(`/api/workspaces/${workspaceId}/briefings`),
    api(`/api/workspaces/${workspaceId}/literature`),
    api(`/api/workspaces/${workspaceId}/assets`),
    api(`/api/workspaces/${workspaceId}/knowledge`),
    api(`/api/workspaces/${workspaceId}/schedules`),
  ]);
  renderIntegrations(integrations.items || []);
  renderBriefings(briefings.items || []);
  renderLiterature(literature.items || []);
  renderAssets(assets.items || []);
  renderKnowledge(knowledge.items || []);
  renderSchedules(schedules.items || []);
}

async function handleRegister(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  const response = await api(
    "/api/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setSession(response);
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("账户已创建。");
}

async function handleLogin(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  const response = await api(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setSession(response);
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("登录成功。");
}

async function handleCreateWorkspace(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  const response = await api("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.workspaces.push(response.workspace);
  state.selectedWorkspaceId = response.workspace.id;
  localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
  renderWorkspaceOptions();
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("工作区已创建。");
}

async function handleIntegration(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.is_default = formData.get("is_default") === "on";
  const response = await api("/api/integrations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast(`连接已保存：${response.integration.label}`);
}

async function handleBriefing(event) {
  event.preventDefault();
  ensureWorkspace();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  await api(`/api/workspaces/${state.selectedWorkspaceId}/briefings/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  showToast("简报已生成。");
}

async function handleOpenAlexSearch(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const params = new URLSearchParams({
    q: formData.get("query").toString(),
    max_results: "8",
    open_access_only: formData.get("open_access_only") === "on" ? "true" : "false",
  });
  const response = await api(`/api/openalex/search?${params.toString()}`, {}, false);
  state.openAlexResults = response.items || [];
  renderOpenAlexResults(state.openAlexResults);
  showToast(`检索到 ${state.openAlexResults.length} 条文献。`);
}

async function handleOpenAlexImport() {
  ensureWorkspace();
  if (!state.openAlexResults.length) {
    throw new Error("请先执行文献检索。");
  }
  await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ works: state.openAlexResults }),
  });
  await refreshWorkspaceData();
  showToast("文献已导入私有文献库。");
}

async function handleUpload(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/upload`, {
    method: "POST",
    body: formData,
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("文件已上传。");
}

async function handleKnowledge(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.tags = payload.tags ? payload.tags.split(",").map((item) => item.trim()).filter(Boolean) : [];
  payload.metadata = {};
  await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("知识条目已写入。");
}

async function handleSchedule(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = {
    name: formData.get("name"),
    local_time: formData.get("local_time"),
    timezone_name: "Asia/Shanghai",
    job_type: "economic_briefing",
    config: {
      query_text: formData.get("query_text"),
      title: formData.get("name"),
    },
  };
  await api(`/api/workspaces/${state.selectedWorkspaceId}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("每日任务已创建。");
}

async function handleOls(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = {
    asset_id: formData.get("asset_id"),
    dependent: formData.get("dependent"),
    independents: formData
      .get("independents")
      .toString()
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/ols`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  dom.analysisOutput.textContent = JSON.stringify(response, null, 2);
  await refreshWorkspaceData();
  showToast("OLS 已完成。");
}

async function handleIntegrationActions(event) {
  const testId = event.target.getAttribute("data-test-integration");
  const deleteId = event.target.getAttribute("data-delete-integration");
  if (testId) {
    const response = await api(`/api/integrations/${testId}/test`, { method: "POST" });
    showToast(response.preview || "连接测试成功。");
    return;
  }
  if (deleteId) {
    await api(`/api/integrations/${deleteId}`, { method: "DELETE" });
    await refreshWorkspaceData();
    showToast("连接已删除。");
  }
}

async function downloadAsset(assetId) {
  const response = await fetch(`/api/assets/${assetId}/download`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    throw new Error("下载失败。");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `${assetId}.bin`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function handleAssetActions(event) {
  const cleanId = event.target.getAttribute("data-clean-asset");
  const downloadId = event.target.getAttribute("data-download-asset");
  if (cleanId) {
    await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/${cleanId}/clean`, { method: "POST" });
    await refreshWorkspaceData();
    showToast("数据已清洗，并生成新的资产。");
    return;
  }
  if (downloadId) {
    await downloadAsset(downloadId);
    showToast("下载已开始。");
  }
}

function bind() {
  document.getElementById("register-form").addEventListener("submit", wrap(handleRegister));
  document.getElementById("login-form").addEventListener("submit", wrap(handleLogin));
  document.getElementById("workspace-form").addEventListener("submit", wrap(handleCreateWorkspace));
  document.getElementById("integration-form").addEventListener("submit", wrap(handleIntegration));
  document.getElementById("briefing-form").addEventListener("submit", wrap(handleBriefing));
  document.getElementById("openalex-form").addEventListener("submit", wrap(handleOpenAlexSearch));
  document.getElementById("import-openalex").addEventListener("click", wrap(handleOpenAlexImport));
  document.getElementById("upload-form").addEventListener("submit", wrap(handleUpload));
  document.getElementById("knowledge-form").addEventListener("submit", wrap(handleKnowledge));
  document.getElementById("schedule-form").addEventListener("submit", wrap(handleSchedule));
  document.getElementById("ols-form").addEventListener("submit", wrap(handleOls));
  dom.workspaceSelect.addEventListener("change", wrap(async (event) => {
    state.selectedWorkspaceId = event.target.value;
    localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
    await refreshWorkspaceData();
  }));
  dom.integrationList.addEventListener("click", wrap(handleIntegrationActions));
  dom.assetList.addEventListener("click", wrap(handleAssetActions));
}

function wrap(handler) {
  return async (event) => {
    try {
      await handler(event);
    } catch (error) {
      showToast(error.message || "发生错误。", true);
    }
  };
}

async function init() {
  bind();
  clearLists();
  try {
    await fetchHealth();
    await loadSession();
  } catch (error) {
    showToast(error.message || "初始化失败。", true);
  }
}

init();
