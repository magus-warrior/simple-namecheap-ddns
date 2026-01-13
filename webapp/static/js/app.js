const STATUS_PILL = document.getElementById("status-pill");
const SECRETS_TABLE = document.getElementById("secrets-table");
const SECRETS_LIST = document.getElementById("secrets-list");
const SECRET_ADD_HEADER = document.getElementById("secret-add-header");
const SECRET_DRAWER = document.getElementById("secret-drawer");
const TARGETS_TABLE = document.getElementById("targets-table");
const TARGETS_LIST = document.getElementById("targets-list");
const TARGET_ADD_HEADER = document.getElementById("target-add-header");
const TARGETS_FORCE_ALL = document.getElementById("targets-force-all");

const throwResponseError = async (response, fallbackMessage) => {
  let message = fallbackMessage;
  try {
    const payload = await response.json();
    if (payload) {
      const parts = [];
      if (payload.error) {
        parts.push(payload.error);
      }
      if (payload.detail) {
        parts.push(payload.detail);
      }
      if (payload.config_path) {
        parts.push(`Config: ${payload.config_path}`);
      }
      if (payload.hint) {
        parts.push(payload.hint);
      }
      if (parts.length) {
        message = parts.join(" • ");
      }
    }
  } catch (error) {
    // Ignore JSON parsing errors and use fallback message.
  }
  throw new Error(message);
};

const readPublishError = async (response) => {
  try {
    const payload = await response.json();
    return payload?.publish_error ?? null;
  } catch (error) {
    return null;
  }
};

const formatPublishError = (publishError) => {
  if (!publishError) {
    return null;
  }
  const parts = [];
  if (publishError.error) {
    parts.push(publishError.error);
  }
  if (publishError.detail) {
    parts.push(publishError.detail);
  }
  if (publishError.config_path) {
    parts.push(`Config: ${publishError.config_path}`);
  }
  if (publishError.hint) {
    parts.push(publishError.hint);
  }
  return parts.length ? parts.join(" • ") : "Config publish failed";
};
const TARGET_DRAWER = document.getElementById("target-drawer");
const LOGS_TABLE = document.getElementById("logs-table");
const LOGS_EMPTY = document.getElementById("logs-empty");
const SECRETS_COUNT = document.getElementById("secrets-count");
const TARGETS_COUNT = document.getElementById("targets-count");
const LOGS_COUNT = document.getElementById("logs-count");
const SECRET_FORM = document.getElementById("secret-form");
const SECRET_NAME = document.getElementById("secret-name");
const SECRET_VALUE = document.getElementById("secret-value");
const SECRET_SUBMIT = document.getElementById("secret-submit");
const SECRET_CANCEL = document.getElementById("secret-cancel");
const TARGET_FORM = document.getElementById("target-form");
const TARGET_HOST = document.getElementById("target-host");
const TARGET_DOMAIN = document.getElementById("target-domain");
const TARGET_SECRET = document.getElementById("target-secret");
const TARGET_ENABLED = document.getElementById("target-enabled");
const TARGET_INTERVAL = document.getElementById("target-interval");
const TARGET_SUBMIT = document.getElementById("target-submit");
const TARGET_CANCEL = document.getElementById("target-cancel");
const TARGET_SECRET_HINT = document.getElementById("target-secret-hint");
const TARGET_SECRET_ADD = document.getElementById("target-secret-add");
const TARGET_SECRET_MODAL = document.getElementById("target-secret-modal");
const TARGET_SECRET_BACKDROP = document.getElementById("target-secret-backdrop");
const TARGET_SECRET_CLOSE = document.getElementById("target-secret-close");
const TARGET_SECRET_FORM = document.getElementById("target-secret-form");
const TARGET_SECRET_NAME = document.getElementById("target-secret-name");
const TARGET_SECRET_VALUE = document.getElementById("target-secret-value");
const TARGET_SECRET_SUBMIT = document.getElementById("target-secret-submit");
const TARGET_SECRET_CANCEL = document.getElementById("target-secret-cancel");
const TAB_SECRETS = document.getElementById("tab-secrets");
const TAB_TARGETS = document.getElementById("tab-targets");
const TAB_LOGS = document.getElementById("tab-logs");
const PANEL_SECRETS = document.getElementById("panel-secrets");
const PANEL_TARGETS = document.getElementById("panel-targets");
const PANEL_LOGS = document.getElementById("panel-logs");
const SETTINGS_FORM = document.getElementById("settings-form");
const SETTINGS_STATUS = document.getElementById("settings-status");
const SETTINGS_SUBMIT = document.getElementById("settings-submit");
const MANUAL_IP_ENABLED = document.getElementById("manual-ip-enabled");
const MANUAL_IP_ADDRESS = document.getElementById("manual-ip-address");

const secretsCache = [];
let editingSecretId = null;
let editingTargetId = null;
let targetsCache = [];

const setStatus = (text, isError = false) => {
  STATUS_PILL.textContent = text;
  STATUS_PILL.style.borderColor = isError ? "rgba(255, 103, 242, 0.9)" : "rgba(103, 250, 255, 0.6)";
};

const setActiveTab = (tab) => {
  const isSecrets = tab === "secrets";
  const isTargets = tab === "targets";
  const isLogs = tab === "logs";
  TAB_SECRETS.classList.toggle("is-active", isSecrets);
  TAB_TARGETS.classList.toggle("is-active", isTargets);
  TAB_LOGS.classList.toggle("is-active", isLogs);
  TAB_SECRETS.setAttribute("aria-selected", String(isSecrets));
  TAB_TARGETS.setAttribute("aria-selected", String(isTargets));
  TAB_LOGS.setAttribute("aria-selected", String(isLogs));
  PANEL_SECRETS.hidden = !isSecrets;
  PANEL_TARGETS.hidden = !isTargets;
  PANEL_LOGS.hidden = !isLogs;
  PANEL_SECRETS.classList.toggle("is-active", isSecrets);
  PANEL_TARGETS.classList.toggle("is-active", isTargets);
  PANEL_LOGS.classList.toggle("is-active", isLogs);
};

const clearTableRows = (table) => {
  table.querySelectorAll(".table-row.data-row").forEach((row) => row.remove());
};

const toggleDrawer = (drawer, toggleButtons, forceOpen) => {
  const buttons = Array.isArray(toggleButtons) ? toggleButtons : [toggleButtons];
  const shouldOpen = forceOpen ?? drawer.hidden;
  drawer.hidden = !shouldOpen;
  buttons.forEach((button) => button?.setAttribute("aria-expanded", String(shouldOpen)));
};

const ensureDrawerOpen = (drawer, toggleButtons) => {
  if (drawer.hidden) {
    toggleDrawer(drawer, toggleButtons, true);
  }
};

const toggleModal = (modal, forceOpen) => {
  const shouldOpen = forceOpen ?? modal.hidden;
  modal.hidden = !shouldOpen;
};

const normalizeHosts = (hostValue) =>
  hostValue
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);

const formatTargetLabel = (target) => {
  const hosts = normalizeHosts(target.host);
  const formattedHosts = (hosts.length ? hosts : [target.host]).map((host) =>
    host === "@" ? "root" : host
  );
  return `${formattedHosts.join(", ")}.${target.domain}`;
};

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const renderSecrets = (secrets, targets) => {
  secretsCache.length = 0;
  secretsCache.push(...secrets);
  clearTableRows(SECRETS_TABLE);
  SECRETS_LIST.innerHTML = "";
  if (!secrets.length) {
    SECRETS_TABLE.hidden = true;
    const emptyCard = document.createElement("div");
    emptyCard.className = "list-card list-card-empty";
    emptyCard.textContent = "No secrets configured yet.";
    SECRETS_LIST.appendChild(emptyCard);
  } else {
    SECRETS_TABLE.hidden = false;
    const usageCounts = targets.reduce((acc, target) => {
      acc[target.secret_id] = (acc[target.secret_id] ?? 0) + 1;
      return acc;
    }, {});
    secrets.forEach((secret) => {
      const usageCount = usageCounts[secret.id] ?? 0;
      const card = document.createElement("div");
      card.className = "list-card";
      card.innerHTML = `
        <strong>${secret.name}</strong>
        <span class="list-card-meta">${usageCount} target${usageCount === 1 ? "" : "s"}</span>
      `;
      SECRETS_LIST.appendChild(card);

      const row = document.createElement("div");
      row.className = "table-row data-row";
      row.innerHTML = `
        <span><strong>${secret.name}</strong></span>
        <span>—</span>
        <span>${usageCount} target${usageCount === 1 ? "" : "s"}</span>
        <span class="table-actions"></span>
      `;
      const actionsCell = row.querySelector(".table-actions");
      const mask = document.createElement("span");
      mask.className = "mask";
      mask.textContent = "••••••";
      actionsCell.appendChild(mask);
      actionsCell.appendChild(
        buildActionButton("Edit name", "ghost", () => startSecretEdit(secret))
      );
      actionsCell.appendChild(
        buildActionButton("Rotate", "primary", () => startSecretRotate(secret))
      );
      actionsCell.appendChild(
        buildActionButton("Delete", "danger", () => deleteSecret(secret.id))
      );
      SECRETS_TABLE.appendChild(row);
    });
  }
  SECRETS_COUNT.textContent = secrets.length;
  refreshSecretOptions(secrets);
};

const renderTargets = (targets, secrets) => {
  targetsCache = [...targets];
  clearTableRows(TARGETS_TABLE);
  TARGETS_LIST.innerHTML = "";
  if (!targets.length) {
    TARGETS_TABLE.hidden = true;
    const emptyCard = document.createElement("div");
    emptyCard.className = "list-card list-card-empty";
    emptyCard.textContent = "No targets configured yet.";
    TARGETS_LIST.appendChild(emptyCard);
  } else {
    TARGETS_TABLE.hidden = false;
    const secretNames = secrets.reduce((acc, secret) => {
      acc[secret.id] = secret.name;
      return acc;
    }, {});
    targets.forEach((target) => {
      const card = document.createElement("div");
      card.className = "list-card";
      card.innerHTML = `
        <strong>${formatTargetLabel(target)}</strong>
        <span class="list-card-meta">${target.is_enabled ? "Enabled" : "Disabled"}</span>
      `;
      TARGETS_LIST.appendChild(card);

      const row = document.createElement("div");
      row.className = "table-row data-row";
      row.innerHTML = `
        <span><strong>${formatTargetLabel(target)}</strong></span>
        <span>${target.is_enabled ? "Yes" : "No"}</span>
        <span>${secretNames[target.secret_id] ?? `Secret #${target.secret_id}`}</span>
        <span>${target.interval_minutes} min</span>
        <span class="table-actions"></span>
      `;
      const actionsCell = row.querySelector(".table-actions");
      const forceButton = buildActionButton("Force update", "ghost", async () => {
        forceButton.disabled = true;
        setStatus(`Forcing update for ${formatTargetLabel(target)}…`);
        try {
          const payload = await forceTargetUpdate(target.id);
          await loadData();
          const summary = (payload.results ?? [])
            .map((result) => `${result.hostname}: ${result.status === "success" ? "OK" : "FAIL"}`)
            .join(", ");
          setStatus(`Force update complete${summary ? ` • ${summary}` : ""}`);
        } catch (error) {
          setStatus(error.message || "Force update failed", true);
        } finally {
          forceButton.disabled = false;
        }
      });
      actionsCell.appendChild(forceButton);
      actionsCell.appendChild(
        buildActionButton("Edit", "ghost", () => startTargetEdit(target))
      );
      actionsCell.appendChild(
        buildActionButton(target.is_enabled ? "Disable" : "Enable", "primary", () =>
          setTargetEnabled(target, !target.is_enabled)
        )
      );
      actionsCell.appendChild(
        buildActionButton("Delete", "danger", () => deleteTarget(target.id))
      );
      TARGETS_TABLE.appendChild(row);
    });
  }
  TARGETS_COUNT.textContent = targets.length;
};

const renderSettings = (settings) => {
  const manualEnabled = Boolean(settings?.manual_ip_enabled);
  const manualAddress = settings?.manual_ip_address ?? "";
  MANUAL_IP_ENABLED.checked = manualEnabled;
  MANUAL_IP_ADDRESS.value = manualAddress;
  MANUAL_IP_ADDRESS.disabled = !manualEnabled;
  SETTINGS_STATUS.textContent = manualEnabled
    ? `On • ${manualAddress || "Missing IP"}`
    : "Off";
};

const parseAgentMessage = (message) => {
  if (!message) {
    return { errCount: "-", errorSummary: "-" };
  }
  const errCountMatch = message.match(/<ErrCount>(\d+)<\/ErrCount>/i);
  const errCount = errCountMatch ? errCountMatch[1] : "-";
  const errors = [];
  const errorRegex = /<Err\d+>(.*?)<\/Err\d+>/gi;
  let match = errorRegex.exec(message);
  while (match) {
    errors.push(match[1]);
    match = errorRegex.exec(message);
  }
  let errorSummary = errors.length ? errors.join("; ") : message;
  if (errCount === "0" && !errors.length) {
    errorSummary = "—";
  }
  return { errCount, errorSummary };
};

const renderLogs = (logs, targets) => {
  LOGS_TABLE.querySelectorAll(".table-row.log-row").forEach((row) => row.remove());
  if (!logs.length) {
    LOGS_EMPTY.style.display = "block";
  } else {
    LOGS_EMPTY.style.display = "none";
    const targetLabels = targets.reduce((acc, target) => {
      acc[target.id] = formatTargetLabel(target);
      return acc;
    }, {});
    const statusLabels = {
      success: "OK",
      error: "FAIL",
      skipped: "SKIP",
    };
    logs.forEach((log) => {
      const parsed = parseAgentMessage(log.message);
      const statusLabel =
        statusLabels[log.status] ?? String(log.status ?? "").toUpperCase();
      const targetLabel =
        targetLabels[log.target_id] ??
        (log.target_id === "cycle" ? "Cycle" : `Target #${log.target_id}`);
      const row = document.createElement("div");
      row.className = "table-row log-row";
      row.innerHTML = `
        <span>${targetLabel}</span>
        <span>${statusLabel}</span>
        <span>${log.ip_address ?? "-"}</span>
        <span>${parsed.errCount}</span>
        <span>${parsed.errorSummary}</span>
        <span>${new Date(log.created_at).toLocaleString()}</span>
      `;
      LOGS_TABLE.appendChild(row);
    });
  }
  LOGS_COUNT.textContent = logs.length;
};

const buildActionButton = (label, variant, onClick) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `button ${variant ?? ""}`.trim();
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
};

const refreshSecretOptions = (secrets) => {
  const currentValue = TARGET_SECRET.value;
  TARGET_SECRET.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = secrets.length ? "Select a secret" : "Add a secret first";
  placeholder.disabled = true;
  placeholder.selected = true;
  TARGET_SECRET.appendChild(placeholder);
  secrets.forEach((secret) => {
    const option = document.createElement("option");
    option.value = String(secret.id);
    option.textContent = `${secret.name} (ID ${secret.id})`;
    TARGET_SECRET.appendChild(option);
  });
  if (currentValue && secrets.some((secret) => String(secret.id) === currentValue)) {
    TARGET_SECRET.value = currentValue;
  }
  TARGET_SECRET.disabled = secrets.length === 0;
  TARGET_SUBMIT.disabled = secrets.length === 0;
  TARGET_SECRET_HINT.hidden = secrets.length !== 0;
};

const resetSecretForm = () => {
  editingSecretId = null;
  SECRET_FORM.reset();
  SECRET_SUBMIT.textContent = "Add secret";
  SECRET_CANCEL.hidden = true;
  toggleDrawer(SECRET_DRAWER, SECRET_ADD_HEADER, false);
};

const resetTargetForm = () => {
  editingTargetId = null;
  TARGET_FORM.reset();
  TARGET_ENABLED.checked = true;
  TARGET_INTERVAL.value = "5";
  TARGET_SUBMIT.textContent = "Add target";
  TARGET_CANCEL.hidden = true;
  toggleDrawer(TARGET_DRAWER, TARGET_ADD_HEADER, false);
};

const resetTargetSecretForm = () => {
  TARGET_SECRET_FORM.reset();
  TARGET_SECRET_SUBMIT.disabled = false;
};

const closeTargetSecretModal = () => {
  toggleModal(TARGET_SECRET_MODAL, false);
  resetTargetSecretForm();
};

const openTargetSecretModal = () => {
  toggleModal(TARGET_SECRET_MODAL, true);
  TARGET_SECRET_NAME.focus();
};

const startSecretEdit = (secret) => {
  editingSecretId = secret.id;
  SECRET_NAME.value = secret.name;
  SECRET_VALUE.value = "";
  SECRET_SUBMIT.textContent = "Update secret";
  SECRET_CANCEL.hidden = false;
  setActiveTab("secrets");
  ensureDrawerOpen(SECRET_DRAWER, SECRET_ADD_HEADER);
  SECRET_NAME.focus();
};

const startSecretRotate = (secret) => {
  editingSecretId = secret.id;
  SECRET_NAME.value = secret.name;
  SECRET_VALUE.value = "";
  SECRET_SUBMIT.textContent = "Rotate secret";
  SECRET_CANCEL.hidden = false;
  setActiveTab("secrets");
  ensureDrawerOpen(SECRET_DRAWER, SECRET_ADD_HEADER);
  SECRET_VALUE.focus();
};

const startTargetEdit = (target) => {
  editingTargetId = target.id;
  TARGET_HOST.value = target.host;
  TARGET_DOMAIN.value = target.domain;
  TARGET_SECRET.value = String(target.secret_id);
  TARGET_ENABLED.checked = Boolean(target.is_enabled);
  TARGET_INTERVAL.value = String(target.interval_minutes ?? 5);
  TARGET_SUBMIT.textContent = "Update target";
  TARGET_CANCEL.hidden = false;
  setActiveTab("targets");
  ensureDrawerOpen(TARGET_DRAWER, TARGET_ADD_HEADER);
  TARGET_HOST.focus();
};

const openSecretAddDrawer = () => {
  if (editingSecretId) {
    resetSecretForm();
  }
  setActiveTab("secrets");
  ensureDrawerOpen(SECRET_DRAWER, SECRET_ADD_HEADER);
  SECRET_NAME.focus();
};

const openTargetAddDrawer = () => {
  if (editingTargetId) {
    resetTargetForm();
  }
  setActiveTab("targets");
  ensureDrawerOpen(TARGET_DRAWER, TARGET_ADD_HEADER);
  TARGET_HOST.focus();
};

const createSecret = async () => {
  const payload = {
    name: SECRET_NAME.value.trim(),
    value: SECRET_VALUE.value.trim(),
  };
  const response = await fetch("/secrets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to create secret");
  }
  return readPublishError(response);
};

const createSecretFromTarget = async () => {
  const payload = {
    name: TARGET_SECRET_NAME.value.trim(),
    value: TARGET_SECRET_VALUE.value.trim(),
  };
  const response = await fetch("/secrets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to create secret");
  }
  const secretPayload = await response.json();
  return {
    secret: secretPayload,
    publishError: secretPayload?.publish_error ?? null,
  };
};

const updateSecret = async (secretId) => {
  const payload = {
    name: SECRET_NAME.value.trim(),
  };
  if (SECRET_VALUE.value.trim()) {
    payload.value = SECRET_VALUE.value.trim();
  }
  const response = await fetch(`/secrets/${secretId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to update secret");
  }
  return readPublishError(response);
};

const deleteSecret = async (secretId) => {
  if (!confirm("Delete this secret? Targets using it will fail to update.")) {
    return;
  }
  const response = await fetch(`/secrets/${secretId}`, { method: "DELETE" });
  if (!response.ok) {
    setStatus("Failed to delete secret", true);
    return;
  }
  const publishError = await readPublishError(response);
  if (editingSecretId === secretId) {
    resetSecretForm();
  }
  await loadData();
  if (publishError) {
    setStatus(`Secret saved • ${formatPublishError(publishError)}`, true);
  }
};

const createTarget = async () => {
  const payload = {
    host: TARGET_HOST.value.trim(),
    domain: TARGET_DOMAIN.value.trim(),
    secret_id: Number(TARGET_SECRET.value),
    is_enabled: TARGET_ENABLED.checked,
    interval_minutes: Number(TARGET_INTERVAL.value),
  };
  const response = await fetch("/targets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to create target");
  }
  return readPublishError(response);
};

const updateTarget = async (targetId) => {
  const payload = {
    host: TARGET_HOST.value.trim(),
    domain: TARGET_DOMAIN.value.trim(),
    secret_id: Number(TARGET_SECRET.value),
    is_enabled: TARGET_ENABLED.checked,
    interval_minutes: Number(TARGET_INTERVAL.value),
  };
  const response = await fetch(`/targets/${targetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to update target");
  }
  return readPublishError(response);
};

const setTargetEnabled = async (target, isEnabled) => {
  const response = await fetch(`/targets/${target.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_enabled: isEnabled }),
  });
  if (!response.ok) {
    setStatus("Failed to update target", true);
    return;
  }
  await loadData();
};

const forceTargetUpdate = async (targetId) => {
  const response = await fetch(`/targets/${targetId}/force`, { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Force update failed");
  }
  return payload;
};

const forceAllTargets = async () => {
  const response = await fetch("/targets/force", { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Bulk update failed");
  }
  return payload;
};

const refreshLogs = async () => {
  const response = await fetch("/dashboard");
  if (!response.ok) {
    throw new Error("Failed to refresh logs");
  }
  const logsPayload = await response.json();
  renderLogs(logsPayload.logs ?? [], targetsCache);
};

const updateSettings = async () => {
  const payload = {
    manual_ip_enabled: MANUAL_IP_ENABLED.checked,
    manual_ip_address: MANUAL_IP_ADDRESS.value.trim() || null,
  };
  const response = await fetch("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwResponseError(response, "Unable to update settings");
  }
  const responsePayload = await response.json();
  return {
    settings: responsePayload,
    publishError: responsePayload?.publish_error ?? null,
  };
};

const deleteTarget = async (targetId) => {
  if (!confirm("Delete this target?")) {
    return;
  }
  const response = await fetch(`/targets/${targetId}`, { method: "DELETE" });
  if (!response.ok) {
    setStatus("Failed to delete target", true);
    return;
  }
  const publishError = await readPublishError(response);
  if (editingTargetId === targetId) {
    resetTargetForm();
  }
  await loadData();
  if (publishError) {
    setStatus(`Target saved • ${formatPublishError(publishError)}`, true);
  }
};

const loadData = async () => {
  try {
    setStatus("Syncing neon data streams…");
    const [secretsResponse, targetsResponse, logsResponse, settingsResponse] = await Promise.all([
      fetch("/secrets"),
      fetch("/targets"),
      fetch("/dashboard"),
      fetch("/settings"),
    ]);
    if (
      !secretsResponse.ok ||
      !targetsResponse.ok ||
      !logsResponse.ok ||
      !settingsResponse.ok
    ) {
      throw new Error("Failed to fetch data");
    }
    const [secrets, targets, logsPayload, settingsPayload] = await Promise.all([
      secretsResponse.json(),
      targetsResponse.json(),
      logsResponse.json(),
      settingsResponse.json(),
    ]);
    renderSecrets(secrets, targets);
    renderTargets(targets, secrets);
    renderLogs(logsPayload.logs ?? [], targets);
    renderSettings(settingsPayload);
    const refreshTime = formatTime(Date.now());
    setStatus(`Status loaded from agent log store • Last refresh ${refreshTime} • Config publish: —`);
  } catch (error) {
    setStatus("Agent log store unreachable • Last refresh —", true);
  }
};

TARGETS_FORCE_ALL?.addEventListener("click", async () => {
  TARGETS_FORCE_ALL.disabled = true;
  setStatus("Forcing updates for all enabled targets…");
  try {
    const payload = await forceAllTargets();
    const targetResults = payload.results ?? [];
    const hostResults = targetResults.flatMap((target) => target.results ?? []);
    const successCount = hostResults.filter((result) => result.status === "success").length;
    const errorCount = hostResults.filter((result) => result.status === "error").length;
    const summaryParts = [];
    if (successCount) {
      summaryParts.push(`${successCount} OK`);
    }
    if (errorCount) {
      summaryParts.push(`${errorCount} failed`);
    }
    if (!summaryParts.length) {
      summaryParts.push("No updates sent");
    }
    setStatus(`Bulk update complete • ${summaryParts.join(" • ")}`);
    await refreshLogs();
  } catch (error) {
    setStatus(error.message || "Bulk update failed", true);
  } finally {
    TARGETS_FORCE_ALL.disabled = false;
  }
});

SECRET_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setStatus(editingSecretId ? "Updating secret…" : "Creating secret…");
    let publishError = null;
    if (editingSecretId) {
      publishError = await updateSecret(editingSecretId);
    } else {
      publishError = await createSecret();
    }
    resetSecretForm();
    await loadData();
    if (publishError) {
      setStatus(`Secret saved • ${formatPublishError(publishError)}`, true);
    }
  } catch (error) {
    setStatus(`Secret save failed — ${error.message || "check inputs"}`, true);
  }
});

SECRET_CANCEL.addEventListener("click", () => {
  resetSecretForm();
});

SECRET_ADD_HEADER.addEventListener("click", () => {
  if (editingSecretId) {
    resetSecretForm();
  }
  toggleDrawer(SECRET_DRAWER, SECRET_ADD_HEADER);
  if (!SECRET_DRAWER.hidden) {
    SECRET_NAME.focus();
  }
});

TAB_SECRETS.addEventListener("click", () => {
  setActiveTab("secrets");
});

TAB_TARGETS.addEventListener("click", () => {
  setActiveTab("targets");
});

TAB_LOGS.addEventListener("click", () => {
  setActiveTab("logs");
});

TARGET_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setStatus(editingTargetId ? "Updating target…" : "Creating target…");
    let publishError = null;
    if (editingTargetId) {
      publishError = await updateTarget(editingTargetId);
    } else {
      publishError = await createTarget();
    }
    resetTargetForm();
    await loadData();
    if (publishError) {
      setStatus(`Target saved • ${formatPublishError(publishError)}`, true);
    }
  } catch (error) {
    setStatus(`Target save failed — ${error.message || "check inputs"}`, true);
  }
});

TARGET_CANCEL.addEventListener("click", () => {
  resetTargetForm();
});

TARGET_ADD_HEADER.addEventListener("click", () => {
  if (editingTargetId) {
    resetTargetForm();
  }
  toggleDrawer(TARGET_DRAWER, TARGET_ADD_HEADER);
  if (!TARGET_DRAWER.hidden) {
    TARGET_HOST.focus();
  }
});

TARGET_SECRET_ADD.addEventListener("click", () => {
  openTargetSecretModal();
});

TARGET_SECRET_CLOSE.addEventListener("click", () => {
  closeTargetSecretModal();
});

TARGET_SECRET_CANCEL.addEventListener("click", () => {
  closeTargetSecretModal();
});

TARGET_SECRET_BACKDROP.addEventListener("click", () => {
  closeTargetSecretModal();
});

TARGET_SECRET_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    TARGET_SECRET_SUBMIT.disabled = true;
    setStatus("Creating secret…");
    const { secret, publishError } = await createSecretFromTarget();
    await loadData();
    if (secret?.id) {
      TARGET_SECRET.value = String(secret.id);
    }
    if (publishError) {
      setStatus(`Secret saved • ${formatPublishError(publishError)}`, true);
    } else {
      setStatus("Secret added to targets.");
    }
    closeTargetSecretModal();
  } catch (error) {
    TARGET_SECRET_SUBMIT.disabled = false;
    setStatus(`Secret save failed — ${error.message || "check inputs"}`, true);
  }
});

MANUAL_IP_ENABLED.addEventListener("change", () => {
  MANUAL_IP_ADDRESS.disabled = !MANUAL_IP_ENABLED.checked;
});

SETTINGS_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    SETTINGS_SUBMIT.disabled = true;
    setStatus("Saving settings…");
    const { settings, publishError } = await updateSettings();
    renderSettings(settings);
    if (publishError) {
      setStatus(`Settings saved • ${formatPublishError(publishError)}`, true);
    } else {
      setStatus("Settings saved.");
    }
  } catch (error) {
    setStatus(`Settings save failed — ${error.message || "check inputs"}`, true);
  } finally {
    SETTINGS_SUBMIT.disabled = false;
  }
});

loadData();
setInterval(loadData, 20000);
