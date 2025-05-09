# calendar-sync

![CI](https://github.com/dimonb/calendar-sync/actions/workflows/build.yml/badge.svg)

Service for automatic synchronization of "Busy" events between calendars in different systems (Google Calendar, Outlook, CalDAV, etc).

If a meeting appears in one of your calendars, the service creates a corresponding `Busy` event in all other connected calendars.

---

## Features

- Supports Google Calendar, Microsoft 365 (Outlook), and CalDAV.
- Watches for events only in the next N days (configurable via `sync_window_days`).
- Correctly handles recurring events.
- Smart synchronization: automatically creates and deletes `Busy` events as needed.
- Reliable, production-ready deployment in Kubernetes via Helm.
- Uses SQLite database to track synced events and prevent duplication.
- Full automation of CI/CD via GitHub Actions.

---

## Architecture

```mermaid
flowchart TD
    subgraph Calendars
        A[Google Calendar]
        B[Outlook Calendar]
        C[CalDAV Calendar]
    end

    D[calendar-sync service]
    E[(SQLite DB)]

    A -- Fetch events --> D
    B -- Fetch events --> D
    C -- Fetch events --> D
    D -- Create Busy --> A
    D -- Create Busy --> B
    D -- Create Busy --> C
    D -- Track mappings --> E
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/dimonb/calendar-sync.git
cd calendar-sync
```

---

### 2. Build the Docker image

```bash
docker build -t calendar-sync .
```

---

### 3. Prepare Kubernetes secrets and configmap

Set up the required secrets and configuration map:

```bash
kubectl create namespace calendar-sync

# Secrets with credential files
kubectl create secret generic calendar-sync-secrets -n calendar-sync \
  --from-file=google_credentials.json \
  --from-file=microsoft_credentials.json

# ConfigMap with calendar configuration
touch config.yaml # (edit accordingly if needed)
kubectl create configmap calendar-sync-config -n calendar-sync \
  --from-file=config.yaml
```

---

### 4. Deploy with Helm

```bash
helm upgrade --install calendar-sync ./charts/calendar-sync \
  --namespace calendar-sync \
  --create-namespace
```

---

## Configuration

**Sample `config.yaml`**

```yaml
calendars:
  - type: google
    id: your-google-calendar-id
    credentials_path: /data/google_client_secret.json
    token_path: /data/token.json
    onlysource: true
  - type: outlook
    id: your-outlook-calendar-id
  - type: caldav
    url: https://caldav.example.com/user/calendars/personal/

sync_window_days: 14
```

> `onlysource: true` is an optional flag. When set, this calendar is only used as a source of events and no Busy events will be created in it.

Notes:
- For Google Calendar integration, you must provide valid `credentials_path` and `token_path` (see Google documentation for preparing OAuth credentials).
- For CalDAV support, you must provide the `url`, `username`, and `password` in the calendar block.

---

**Sample `values.yaml` for Helm**

```yaml
image:
  repository: ghcr.io/dimonb/calendar-sync
  tag: latest

schedule: "*/5 * * * *"

secrets:
  googleCredentialsSecret:
    name: calendar-sync-secrets
    data:
      google_client_secret: <base64 encoded secret>
  microsoftCredentialsSecret:
    name: calendar-sync-secrets
    data:
      microsoft_client_secret: <base64 encoded secret>

config:
  configMapName: calendar-sync-config
```

---

## CI/CD

- On push to `main`:
  - Docker image is built
  - Published to GitHub Container Registry `ghcr.io/dimonb/calendar-sync`
  - Automatically deployed to Kubernetes using Helm

---

## Requirements

- Python 3.11+
- Kubernetes 1.21+
- Helm 3+
- Working kubeconfig or access token for your cluster
- Access to GitHub Container Registry (GHCR) for downloading images

---

## License

MIT License. 
Feel free to use and modify.

---

## Authors

- [Dmitrii Balabanov](https://github.com/dimonb)

---

## FAQ / Troubleshooting

- **Google Calendar setup:**
  - The service requires OAuth2 credentials. See Google's official documentation to create client credentials and download as `client_secret.json`.
  - The first time you run calendar-sync it will prompt your browser for consent. The resulting token is cached in the `token.json` or whatever path you set as `token_path`.

- **CalDAV setup:**
  - Some CalDAV providers require app-specific passwords or two-factor authentication adjustments. Make sure your credentials work in your CalDAV client before using them in calendar-sync.

- **How do I only sync FROM one calendar?**
  - Use `onlysource: true` in the config.

---

For issues, discussions, and updates: see the [GitHub repository](https://github.com/dimonb/calendar-sync).
