const STATUS_PILL = document.getElementById("status-pill");
const SECRETS_LIST = document.getElementById("secrets-list");
const TARGETS_LIST = document.getElementById("targets-list");
const LOGS_TABLE = document.getElementById("logs-table");
const LOGS_EMPTY = document.getElementById("logs-empty");
const SECRETS_COUNT = document.getElementById("secrets-count");
const TARGETS_COUNT = document.getElementById("targets-count");
const LOGS_COUNT = document.getElementById("logs-count");

const EMPTY_ROW_CLASS = "empty";

const setStatus = (text, isError = false) => {
  STATUS_PILL.textContent = text;
  STATUS_PILL.style.borderColor = isError ? "rgba(255, 103, 242, 0.9)" : "rgba(103, 250, 255, 0.6)";
};

const clearList = (list) => {
  list.innerHTML = "";
};

const createListItem = (title, meta) => {
  const item = document.createElement("li");
  const titleEl = document.createElement("strong");
  titleEl.textContent = title;
  item.appendChild(titleEl);
  if (meta) {
    const metaEl = document.createElement("span");
    metaEl.className = "meta";
    metaEl.textContent = meta;
    item.appendChild(metaEl);
  }
  return item;
};

const renderSecrets = (secrets) => {
  clearList(SECRETS_LIST);
  if (!secrets.length) {
    const empty = document.createElement("li");
    empty.className = EMPTY_ROW_CLASS;
    empty.textContent = "No secrets configured yet.";
    SECRETS_LIST.appendChild(empty);
  } else {
    secrets.forEach((secret) => {
      SECRETS_LIST.appendChild(createListItem(secret.name, `ID: ${secret.id}`));
    });
  }
  SECRETS_COUNT.textContent = secrets.length;
};

const renderTargets = (targets) => {
  clearList(TARGETS_LIST);
  if (!targets.length) {
    const empty = document.createElement("li");
    empty.className = EMPTY_ROW_CLASS;
    empty.textContent = "No targets configured yet.";
    TARGETS_LIST.appendChild(empty);
  } else {
    targets.forEach((target) => {
      const status = target.is_enabled ? "Enabled" : "Disabled";
      TARGETS_LIST.appendChild(
        createListItem(
          `${target.host}.${target.domain}`,
          `Secret ID: ${target.secret_id} · ${status}`
        )
      );
    });
  }
  TARGETS_COUNT.textContent = targets.length;
};

const renderLogs = (logs) => {
  LOGS_TABLE.querySelectorAll(".table-row.log-row").forEach((row) => row.remove());
  if (!logs.length) {
    LOGS_EMPTY.style.display = "block";
  } else {
    LOGS_EMPTY.style.display = "none";
    logs.forEach((log) => {
      const row = document.createElement("div");
      row.className = "table-row log-row";
      row.innerHTML = `
        <span>#${log.target_id}</span>
        <span>${log.status}</span>
        <span>${log.ip_address ?? "-"}</span>
        <span>${log.response_code ?? "-"}</span>
        <span>${log.message ?? "-"}</span>
        <span>${new Date(log.created_at).toLocaleString()}</span>
      `;
      LOGS_TABLE.appendChild(row);
    });
  }
  LOGS_COUNT.textContent = logs.length;
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
    renderSecrets(secrets);
    renderTargets(targets);
    renderLogs(logsPayload.logs ?? []);
    setStatus("Live sync complete");
  } catch (error) {
    setStatus("Data sync failed — check server", true);
  }
};

loadData();
setInterval(loadData, 20000);
