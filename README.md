# simple-namecheap-ddns

A lightweight, self-hosted Dynamic DNS (DDNS) manager for Namecheap. It consists of:

- **Agent (background service)** that polls for your public IP and calls Namecheap’s DDNS
  update endpoint.
- **Web UI (Flask app)** that stores secrets/targets, publishes encrypted agent
  configuration, and shows recent update logs.

The project is intentionally small: a Python agent, a Flask web UI, SQLite for state, and
simple systemd service definitions.

---

## How it works (high level, end to end)

1. **You add secrets in the web UI** (Namecheap DDNS password tokens).
   - Secrets are encrypted in the web UI database using `FLASK_MASTER_KEY`.
2. **You add DDNS targets** (host + domain + secret + interval).
   - The UI normalizes hostnames (comma-separated list) and stores target metadata in the
     web UI database.
3. **The web UI publishes an agent config file** whenever secrets/targets change.
   - The config is written to `${DDNS_WORKDIR}/.ddns/config.enc.json` by default.
   - Tokens are decrypted with `FLASK_MASTER_KEY`, then re-encrypted using
     `AGENT_MASTER_KEY` so only the agent can use them.
4. **The agent loads the encrypted config file** and runs an update loop:
   - Fetches your public IP (default `https://api.ipify.org`).
   - Skips updates if the IP hasn’t changed for a given target.
   - Calls Namecheap’s update URL for each enabled target.
   - Logs each update result to `${DDNS_WORKDIR}/.ddns/agent.db`.
5. **The web UI reads the agent log DB** to show recent update activity in the dashboard.

This gives you a single UI to manage secrets/targets while keeping the agent focused on
DDNS updates.

---

## Repository layout

- `agent/`
  - `main.py`: process lifecycle and reload loop.
  - `core.py`: DDNS update loop (fetch IP, call update URL, log results).
  - `database.py`: SQLite logging/cache used by the agent.
- `webapp/`
  - `routes.py`: REST API + dashboard endpoints.
  - `publisher.py`: compiles and writes the agent config.
  - `models.py`: SQLAlchemy models for secrets/targets.
  - `templates/` + `static/`: single-page UI.
- `shared_lib/`
  - `schema.py`: agent config schema.
  - `security.py`: Fernet encryption helpers.
- `start-agent.sh`: run the agent module.
- `start.sh`: run the Flask web UI.
- `install.sh`: helper for installing dependencies, permissions, and systemd services.
- `ddns-agent.service` / `ddns-gui.service`: systemd unit files.

---

## Data storage

### Web UI database
- **Default path:** `webapp.db` in the repo root (configurable via `WEBAPP_DB_PATH`).
- **Contents:**
  - `secrets` table: `name`, `encrypted_value` (encrypted with `FLASK_MASTER_KEY`).
  - `targets` table: hostnames, domain, secret reference, enabled flag, interval.

### Agent log database
- **Default path:** `${DDNS_WORKDIR}/.ddns/agent.db`.
- **Contents:**
  - `update_history` table: status, response, IP, timestamps per target update.
  - `cache` table: last IP cache for skipping redundant updates.

---

## Agent configuration file

The agent reads a JSON config with this shape (written by the web UI):

```json
{
  "check_ip_url": "https://api.ipify.org",
  "targets": [
    {
      "id": "<target id>",
      "hostname": "www",
      "update_url": "https://dynamicdns.park-your-domain.com/update?host=www&domain=example.com&password={token}&ip={ip}",
      "encrypted_token": "<fernet-encrypted token>",
      "interval": 300
    }
  ]
}
```

The agent **decrypts** `encrypted_token` with `AGENT_MASTER_KEY` at runtime, substitutes
`{token}` and `{ip}` into `update_url`, and performs the HTTP request.

---

## Update loop behavior (agent)

- Loads config at startup.
- Reloads config on:
  - SIGHUP (systemd `reload`), or
  - detected file mtime change.
- Every cycle:
  1. Fetch public IP from `check_ip_url`.
  2. Compare to cached IP:
     - If unchanged, skip targets already updated with that IP.
  3. For each enabled target:
     - Decrypt token.
     - Build update URL and call it.
     - Log success/error to `agent.db`.
- Sleeps for the **minimum interval** across targets, bounded to **30s minimum**.

---

## Web UI behavior

- **Secrets**
  - Create/update/delete secrets.
  - Encrypts values using `FLASK_MASTER_KEY`.
- **Targets**
  - Create/update/delete targets.
  - Supports comma-separated hostnames (e.g. `@, www`).
  - Interval in minutes is stored per target.
- **Publishing**
  - Any change to secrets/targets triggers a config publish.
  - Publish errors are returned to the UI so you can see permission/config issues.
- **Dashboard**
  - Reads `agent.db` to show recent updates.
  - Refreshes every 20 seconds.

---

## Environment variables

### Core runtime
- `DDNS_WORKDIR`: base working directory for `.ddns/` (defaults to repo root in scripts).
- `AGENT_DB_PATH`: path to agent log DB (default `${DDNS_WORKDIR}/.ddns/agent.db`).
- `AGENT_CONFIG_PATH`: path to agent config file
  (default `${DDNS_WORKDIR}/.ddns/config.enc.json`).

### Security keys
- `AGENT_MASTER_KEY`: **required** for the agent to decrypt tokens.
- `FLASK_MASTER_KEY`: **required** for the web UI to encrypt/decrypt secrets.
  - `start.sh` will generate and persist a key in `.flask_master_key` if missing.

#### Trust model / key storage
- `start.sh` persists `FLASK_MASTER_KEY` to `.flask_master_key` with permissions `0600`
  (read/write only by the owning user).
- `install.sh` stores `AGENT_MASTER_KEY` in `.ddns/agent.env`. When running without
  `DDNS_SYSTEM_WIDE=1`, it is created with `0600` (only the owning user can read it).
  In system-wide mode, it is created with `0400` (root-only) or `0440` (root + group)
  depending on installer settings; either way it is not world-readable.
- Anyone with read access to these files can decrypt stored secrets and use the tokens.
- If the host is compromised, an attacker can decrypt secrets, modify the configuration,
  or exfiltrate Namecheap tokens. Mitigate this by using full-disk encryption, limiting
  shell access to trusted admins, and rotating keys/tokens after any suspected breach.

### Web UI / Flask
- `FLASK_APP`: defaults to `app`.
- `FLASK_RUN_HOST`: defaults to `0.0.0.0`.
- `FLASK_RUN_PORT`: defaults to `8001`.
- `WEBAPP_DB_PATH`: path to the web UI SQLite DB (default `webapp.db`).

### Agent behavior
- `AGENT_CHECK_IP_URL`: override public IP endpoint (default `https://api.ipify.org`).
- `AGENT_UPDATE_URL_TEMPLATE`: override Namecheap update URL template.
  - Default: `https://dynamicdns.park-your-domain.com/update?host={hostname}&domain={domain}&password={token}&ip={ip}`
- `AGENT_SERVICE_NAME`: name to reload after publishing (default `ddns-agent`).

### Installer / service configuration
- `DDNS_PYTHON_BIN`: python executable used by systemd agent service.
- `DDNS_CONFIG_DIR`: where config/env files live (default `${DDNS_WORKDIR}/.ddns`).
- `DDNS_DATA_DIR`: where data files live (default `${DDNS_WORKDIR}/.ddns`).
- `DDNS_SERVICE_USER`: user for systemd services (default: sudo user or `ddns-agent`).
- `DDNS_SYSTEM_WIDE=1`: enable system user creation + sudoers entry.

---

## Running locally (no systemd)

### Web UI

```bash
export FLASK_MASTER_KEY="<your generated key>"
export AGENT_MASTER_KEY="<your agent key>"
export DDNS_WORKDIR="$(pwd)"
python -m flask --app app run --host 0.0.0.0 --port 8001
```

### Agent

```bash
export AGENT_MASTER_KEY="<same agent key>"
export DDNS_WORKDIR="$(pwd)"
python -m agent.main
```

---

## Running with systemd

- `ddns-agent.service` runs the agent.
- `ddns-gui.service` runs the Flask UI.

Both use environment files at `${DDNS_WORKDIR}/.ddns/agent.env` to load keys and paths.

### Quick install flow

```bash
./install.sh
```

Follow the menu:
- **Guided install** handles dependencies, permissions, and service installation.
- **Verify paths** helps confirm Python path, unit paths, and env file contents.

### What the installer does

- Detects Python (supports venv/conda).
- Creates `.ddns/` config/data directories.
- Creates `agent.env` and generates `AGENT_MASTER_KEY` if missing.
- Installs Python dependencies from `requirements.txt`.
- Installs/updates systemd units and optionally enables/starts them.
- (Optional) Creates system users (`ddns-admin`, `ddns-agent`) and sudoers entry if
  `DDNS_SYSTEM_WIDE=1`.

---

## API endpoints (web UI)

- `GET /` → UI dashboard page.
- `GET /secrets` → list secrets.
- `POST /secrets` → create secret (name + value).
- `PUT /secrets/<id>` → rename or rotate secret.
- `DELETE /secrets/<id>` → delete secret.
- `GET /targets` → list targets.
- `POST /targets` → create target.
- `PUT /targets/<id>` → update target.
- `DELETE /targets/<id>` → delete target.
- `POST /targets/<id>/force` → run immediate update for a target.
- `GET /dashboard` → recent agent log entries.

---

## Common operational notes

- **Config publish failures** typically mean file permission/path issues writing
  `${DDNS_WORKDIR}/.ddns/config.enc.json`.
- **Agent not picking up new config**: ensure SIGHUP reload works (systemd `reload`)
  or that the agent can read the config file.
- **No logs in the UI**: verify `AGENT_DB_PATH` points to the same `agent.db` used by
  the agent process.

---

## Environment detail

Both the agent and the webapp read the agent log database path from `AGENT_DB_PATH`. If it
is not set, they fall back to `${DDNS_WORKDIR}/.ddns/agent.db`.
