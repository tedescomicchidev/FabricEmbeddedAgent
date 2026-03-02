# Fabric Embedded Agent

A Flask web application that combines an embedded **Power BI report** with a **Microsoft Fabric Data Agent** chat interface, all secured by **Microsoft Entra ID** authentication.

## Features

- 🔐 **Entra ID (Azure AD) authentication** – users sign in with their Microsoft identity before accessing the app
- 📊 **Embedded Power BI report** – AppOwnsData pattern using a Service Principal to generate embed tokens
- 🔒 **Row-Level Security (RLS)** – optionally apply dynamic RLS using the authenticated user's UPN
- 🤖 **Fabric Data Agent chat** – ask natural-language questions about your data via the Microsoft Fabric Data Agent Python SDK
- ☁️ **Azure App Service ready** – includes deployment scripts and `gunicorn` for production use

## Architecture

```
Browser
  │
  ├── Entra ID (MSAL / ms-identity-python)   ← authentication
  │
  ├── Flask (app.py)
  │     ├── /                → index.html (PowerBI + chat UI)
  │     ├── /api/getembedinfo → generates PowerBI embed token (Service Principal)
  │     ├── /api/embedsettings → per-session workspace / report / RLS overrides
  │     ├── /api/chat         → forwards question to Fabric Data Agent
  │     └── /api/chat/clear   → resets the conversation thread
  │
  ├── Power BI REST API       ← embed token generation
  └── Fabric Data Agent API   ← OpenAI Assistants-compatible endpoint
```

## Prerequisites

| Requirement | Details |
|---|---|
| Python 3.9+ | Tested with the `mcr.microsoft.com/devcontainers/python:2-3.14-trixie` image |
| Azure AD App Registration | Needs `PowerBI Service` and `Microsoft Fabric` API permissions |
| Power BI Workspace | Service Principal must be a member |
| Fabric Data Agent | Created in a Microsoft Fabric workspace |

### Azure AD App Registration permissions

| API | Permission | Type |
|---|---|---|
| Power BI Service | `Report.ReadAll`, `Dataset.ReadAll` | Application |
| Microsoft Fabric | `FabricDataAgent.ReadAll` (or equivalent) | Application |

> **Note:** After granting permissions, an admin must consent on behalf of the organisation.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/tedescomicchidev/FabricEmbeddedAgent.git
cd FabricEmbeddedAgent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `CLIENT_ID` | ✅ | Azure AD App Registration (Application) ID |
| `CLIENT_SECRET` | ✅ | Client secret for the App Registration |
| `TENANT_ID` | ✅ | Azure AD Tenant ID |
| `AUTHORITY` | | Login authority URL (defaults to `https://login.microsoftonline.com/<TENANT_ID>`) |
| `REDIRECT_URI` | | OAuth redirect URI (defaults to `http://localhost:5000/getAToken`) |
| `PBI_WORKSPACE_ID` | | Power BI Workspace GUID |
| `PBI_REPORT_ID` | | Power BI Report GUID |
| `PBI_DATASET_ID` | | Power BI Dataset GUID (required when RLS is enabled) |
| `RLS_ENABLED` | | Set to `true` to enable Row-Level Security (default: `false`) |
| `RLS_ROLES` | | Comma-separated list of RLS role names defined in the dataset |
| `DATA_AGENT_URL` | | Full URL to the Fabric Data Agent API endpoint |
| `FLASK_SECRET_KEY` | | Secret key for Flask session signing |
| `SESSION_TYPE` | | Flask-Session backend (default: `filesystem`) |

### 4. Run locally

```bash
python app.py
```

The application starts on `http://localhost:5000`. Navigate there and sign in with your Microsoft account.

## Row-Level Security (RLS)

When `RLS_ENABLED=true`, the Power BI embed token is generated with the **authenticated user's UPN** (from the Entra ID session) as the RLS identity. The user's identity is **never** accepted from the browser — this prevents identity spoofing.

You can also override workspace, report, dataset, and RLS settings per browser session using the ⚙️ settings panel in the UI. Those overrides are stored server-side in the Flask session.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Main page (requires login) |
| `GET` | `/login` | Login page |
| `GET` | `/health` | Health check |
| `GET` | `/api/getembedinfo` | Returns Power BI embed token and URL |
| `GET/POST` | `/api/embedsettings` | Get or update per-session embed settings |
| `POST` | `/api/embedsettings/reset` | Reset embed settings to `.env` defaults |
| `POST` | `/api/chat` | Send a question to the Fabric Data Agent |
| `POST` | `/api/chat/clear` | Clear the current chat thread |

## Deploying to Azure App Service

1. Create an App Service (Python runtime) and note the resource group and app name.

2. Set the application settings:

   ```bash
   az webapp config appsettings set \
     --resource-group <resource-group> \
     --name <app-service-name> \
     --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
   ```

3. Zip and deploy the application:

   ```bash
   zip -r app.zip . -x "*.git*" -x "__pycache__/*" -x "temp/*"
   az webapp deploy \
     --name <app-service-name> \
     --resource-group <resource-group> \
     --src-path app.zip
   ```

4. Configure all environment variables from the table above as App Service **Application settings**.

5. Update `REDIRECT_URI` to match your App Service URL (e.g., `https://<app-service-name>.azurewebsites.net/getAToken`) and add it as a valid Redirect URI in your Azure AD App Registration.

## Development Container

A ready-to-use dev container configuration is provided in `.devcontainer/devcontainer.json` (Python 3.14). Open the repository in VS Code and select **Reopen in Container** to get a pre-configured development environment.

## Project Structure

```
FabricEmbeddedAgent/
├── app.py                      # Main Flask application
├── app_config.py               # Configuration loader (reads .env)
├── fabric_data_agent_client.py # Fabric Data Agent SDK client
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── templates/
│   ├── index.html              # Main UI (Power BI + chat)
│   └── login.html              # Login page
├── static/
│   └── css/styles.css          # Application styles
└── .devcontainer/
    └── devcontainer.json       # VS Code dev container config
```

## License

This project is provided as-is for demonstration purposes.
