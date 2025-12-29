const STATUS_PILL = document.getElementById("status-pill");
const SECRETS_TABLE = document.getElementById("secrets-table");
const SECRETS_EMPTY = document.getElementById("secrets-empty");
const SECRET_EMPTY_ADD = document.getElementById("secret-empty-add");
const TARGETS_TABLE = document.getElementById("targets-table");
const TARGETS_EMPTY = document.getElementById("targets-empty");
const TARGET_EMPTY_ADD = document.getElementById("target-empty-add");
const TARGETS_EMPTY_HELPER = document.getElementById("targets-empty-helper");
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
const TARGET_SUBMIT = document.getElementById("target-submit");
const TARGET_CANCEL = document.getElementById("target-cancel");
const TARGET_SECRET_HINT = document.getElementById("target-secret-hint");

const secretsCache = [];
let editingSecretId = null;
let editingTargetId = null;

const setStatus = (text, isError = false) => {
  STATUS_PILL.textContent = text;
  STATUS_PILL.style.borderColor = isError ? "rgba(255, 103, 242, 0.9)" : "rgba(103, 250, 255, 0.6)";
};

const clearTableRows = (table) => {
  table.querySelectorAll(".table-row.data-row").forEach((row) => row.remove());
};

const formatTargetLabel = (target) => {
  const host = target.host === "@" ? "root" : target.host;
  return `${host}.${target.domain}`;
};

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

const renderSecrets = (secrets, targets) => {
  secretsCache.length = 0;
  secretsCache.push(...secrets);
  clearTableRows(SECRETS_TABLE);
  if (!secrets.length) {
    SECRETS_EMPTY.hidden = false;
    SECRETS_TABLE.hidden = true;
  } else {
    SECRETS_EMPTY.hidden = true;
    SECRETS_TABLE.hidden = false;
    const usageCounts = targets.reduce((acc, target) => {
      acc[target.secret_id] = (acc[target.secret_id] ?? 0) + 1;
      return acc;
    }, {});
    secrets.forEach((secret) => {
      const row = document.createElement("div");
      row.className = "table-row data-row";
      const usageCount = usageCounts[secret.id] ?? 0;
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
  clearTableRows(TARGETS_TABLE);
  if (!targets.length) {
    TARGETS_EMPTY.hidden = false;
    TARGETS_TABLE.hidden = true;
  } else {
    TARGETS_EMPTY.hidden = true;
    TARGETS_TABLE.hidden = false;
    const secretNames = secrets.reduce((acc, secret) => {
      acc[secret.id] = secret.name;
      return acc;
    }, {});
    targets.forEach((target) => {
      const row = document.createElement("div");
      row.className = "table-row data-row";
      row.innerHTML = `
        <span><strong>${formatTargetLabel(target)}</strong></span>
        <span>${target.is_enabled ? "Yes" : "No"}</span>
        <span>—</span>
        <span>${secretNames[target.secret_id] ?? `Secret #${target.secret_id}`}</span>
        <span>—</span>
        <span>—</span>
        <span>—</span>
        <span>—</span>
        <span class="table-actions"></span>
      `;
      const actionsCell = row.querySelector(".table-actions");
      const forceButton = buildActionButton("Force update", "ghost", () => {
        setStatus("Force update requires the agent API.", true);
      });
      forceButton.disabled = true;
      forceButton.title = "Requires agent API";
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
    logs.forEach((log) => {
      const parsed = parseAgentMessage(log.message);
      const row = document.createElement("div");
      row.className = "table-row log-row";
      row.innerHTML = `
        <span>${targetLabels[log.target_id] ?? `Target #${log.target_id}`}</span>
        <span>${log.status === "success" ? "OK" : "FAIL"}</span>
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
  TARGET_SECRET.disabled = secrets.length === 0;
  TARGET_SUBMIT.disabled = secrets.length === 0;
  TARGET_EMPTY_ADD.disabled = secrets.length === 0;
  TARGETS_EMPTY_HELPER.hidden = secrets.length !== 0;
  TARGET_SECRET_HINT.hidden = secrets.length !== 0;
};

const resetSecretForm = () => {
  editingSecretId = null;
  SECRET_FORM.reset();
  SECRET_SUBMIT.textContent = "Add secret";
  SECRET_CANCEL.hidden = true;
};

const resetTargetForm = () => {
  editingTargetId = null;
  TARGET_FORM.reset();
  TARGET_ENABLED.checked = true;
  TARGET_SUBMIT.textContent = "Add target";
  TARGET_CANCEL.hidden = true;
};

const startSecretEdit = (secret) => {
  editingSecretId = secret.id;
  SECRET_NAME.value = secret.name;
  SECRET_VALUE.value = "";
  SECRET_SUBMIT.textContent = "Update secret";
  SECRET_CANCEL.hidden = false;
  SECRET_NAME.focus();
};

const startSecretRotate = (secret) => {
  editingSecretId = secret.id;
  SECRET_NAME.value = secret.name;
  SECRET_VALUE.value = "";
  SECRET_SUBMIT.textContent = "Rotate secret";
  SECRET_CANCEL.hidden = false;
  SECRET_VALUE.focus();
};

const startTargetEdit = (target) => {
  editingTargetId = target.id;
  TARGET_HOST.value = target.host;
  TARGET_DOMAIN.value = target.domain;
  TARGET_SECRET.value = String(target.secret_id);
  TARGET_ENABLED.checked = Boolean(target.is_enabled);
  TARGET_SUBMIT.textContent = "Update target";
  TARGET_CANCEL.hidden = false;
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
    throw new Error("Unable to create secret");
  }
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
    throw new Error("Unable to update secret");
  }
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
  if (editingSecretId === secretId) {
    resetSecretForm();
  }
  loadData();
};

const createTarget = async () => {
  const payload = {
    host: TARGET_HOST.value.trim(),
    domain: TARGET_DOMAIN.value.trim(),
    secret_id: Number(TARGET_SECRET.value),
    is_enabled: TARGET_ENABLED.checked,
  };
  const response = await fetch("/targets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Unable to create target");
  }
};

const updateTarget = async (targetId) => {
  const payload = {
    host: TARGET_HOST.value.trim(),
    domain: TARGET_DOMAIN.value.trim(),
    secret_id: Number(TARGET_SECRET.value),
    is_enabled: TARGET_ENABLED.checked,
  };
  const response = await fetch(`/targets/${targetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Unable to update target");
  }
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

const deleteTarget = async (targetId) => {
  if (!confirm("Delete this target?")) {
    return;
  }
  const response = await fetch(`/targets/${targetId}`, { method: "DELETE" });
  if (!response.ok) {
    setStatus("Failed to delete target", true);
    return;
  }
  if (editingTargetId === targetId) {
    resetTargetForm();
  }
  loadData();
};

const loadData = async () => {
  try {
    setStatus("Syncing neon data streams…");
    const [secretsResponse, targetsResponse, logsResponse] = await Promise.all([
      fetch("/secrets"),
      fetch("/targets"),
      fetch("/dashboard"),
    ]);
    if (!secretsResponse.ok || !targetsResponse.ok || !logsResponse.ok) {
      throw new Error("Failed to fetch data");
    }
    const [secrets, targets, logsPayload] = await Promise.all([
      secretsResponse.json(),
      targetsResponse.json(),
      logsResponse.json(),
    ]);
    renderSecrets(secrets, targets);
    renderTargets(targets, secrets);
    renderLogs(logsPayload.logs ?? [], targets);
    const refreshTime = formatTime(Date.now());
    setStatus(`Status loaded from agent log store • Last refresh ${refreshTime} • Config publish: —`);
  } catch (error) {
    setStatus("Agent log store unreachable • Last refresh —", true);
  }
};

SECRET_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setStatus(editingSecretId ? "Updating secret…" : "Creating secret…");
    if (editingSecretId) {
      await updateSecret(editingSecretId);
    } else {
      await createSecret();
    }
    resetSecretForm();
    await loadData();
  } catch (error) {
    setStatus("Secret save failed — check inputs", true);
  }
});

SECRET_CANCEL.addEventListener("click", () => {
  resetSecretForm();
});

TARGET_FORM.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    setStatus(editingTargetId ? "Updating target…" : "Creating target…");
    if (editingTargetId) {
      await updateTarget(editingTargetId);
    } else {
      await createTarget();
    }
    resetTargetForm();
    await loadData();
  } catch (error) {
    setStatus("Target save failed — check inputs", true);
  }
});

TARGET_CANCEL.addEventListener("click", () => {
  resetTargetForm();
});

SECRET_EMPTY_ADD.addEventListener("click", () => {
  SECRET_NAME.focus();
});

TARGET_EMPTY_ADD.addEventListener("click", () => {
  TARGET_HOST.focus();
});

loadData();
setInterval(loadData, 20000);
