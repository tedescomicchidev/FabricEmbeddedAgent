You are a senior Python/Flask developer. Build a complete Flask web application with the following requirements:

## Project Structure
Create these files:
- app.py (main Flask application)
- app_config.py (configuration loader)
- fabric_data_agent_client.py (Fabric Data Agent SDK client)
- requirements.txt
- .env.example (template for environment variables)
- templates/index.html (main page with embedded report + chat)
- templates/login.html
- static/css/styles.css

## 1. Entra ID Authentication
Use the `ms_identity_python[flask]` library for authentication:
- Import `from identity.flask import Auth`
- Configure with AUTHORITY, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI from environment
- Protect routes with `@auth.login_required` decorator
- Pass user context to templates

Example pattern:
```python
auth = Auth(app, authority=config["AUTHORITY"], client_id=config["CLIENT_ID"], 
            client_credential=config["CLIENT_SECRET"], redirect_uri=config["REDIRECT_URI"])

@app.route("/")
@auth.login_required
def index(*, context):
    return render_template('index.html', user=context['user'])
```

## 2. PowerBI Embedded Report (AppOwnsData Pattern)
Implement Service Principal authentication for PowerBI embedding:
- Create `/api/getembedinfo` endpoint that:
  1. Acquires token using MSAL ConfidentialClientApplication with scope `https://analysis.windows.net/powerbi/api/.default`
  2. Calls PowerBI REST API to get embed token: `POST https://api.powerbi.com/v1.0/myorg/groups/{workspaceId}/reports/{reportId}/GenerateToken`
  3. Returns embedUrl, accessToken, and reportId as JSON

Configuration parameters (use placeholder GUIDs):
- PBI_WORKSPACE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
- PBI_REPORT_ID = "11111111-2222-3333-4444-555555555555"

In the template, include PowerBI JavaScript SDK:
```html
<script src="https://cdn.jsdelivr.net/npm/powerbi-client@2.22.0/dist/powerbi.min.js"></script>
<div id="reportContainer" style="height: 600px;"></div>
```

## 3. Fabric Data Agent Chat UI
Create `fabric_data_agent_client.py` with class `FabricDataAgentClient`:
- Use `azure.identity.InteractiveBrowserCredential` for auth with scope `https://fabric.microsoft.com/.default`
- Use `openai.AzureOpenAI` client pattern for API calls
- Implement methods:
  - `__init__(self, tenant_id, data_agent_url)` - initialize with browser auth
  - `ask(self, question, timeout=120, thread_name=None)` - send question, return response string
  - `_get_or_create_new_thread(self, data_agent_url, thread_name)` - manage conversation threads

Configuration:
- DATA_AGENT_URL = "https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/dataAgents/{agent_id}"
- TENANT_ID from environment

Create `/api/chat` endpoint:
```python
@app.route("/api/chat", methods=["POST"])
@auth.login_required
def chat(*, context):
    data = request.json
    question = data.get("question")
    thread_name = session.get("chat_thread", f"session_{context['user']['oid']}")
    session["chat_thread"] = thread_name
    response = fabric_client.ask(question, thread_name=thread_name)
    return jsonify({"response": response})
```

## 4. Combined UI Template (index.html)
Create a single-page layout with:
- Header showing logged-in user name
- PowerBI report container (top section, 60% height)
- Chat interface (bottom section, 40% height) with:
  - Message history display area
  - Input field + Send button
  - JavaScript to call /api/chat and display responses

## 5. Requirements.txt
```
flask
python-dotenv
requests
ms_identity_python[flask] @ git+https://github.com/azure-samples/ms-identity-python@0.9
azure-identity
openai
msal
```

## 6. Environment Variables (.env.example)
```
# Entra ID Authentication
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret
TENANT_ID=your-tenant-id
AUTHORITY=https://login.microsoftonline.com/your-tenant-id
REDIRECT_URI=http://localhost:5000/getAToken

# PowerBI Embedding
PBI_WORKSPACE_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
PBI_REPORT_ID=11111111-2222-3333-4444-555555555555

# Fabric Data Agent
DATA_AGENT_URL=https://api.fabric.microsoft.com/v1/workspaces/workspace-id/dataAgents/agent-id

# Flask
FLASK_SECRET_KEY=your-secret-key-here
SESSION_TYPE=filesystem
```

## Additional Requirements
- Use Flask sessions for chat thread persistence
- Add proper error handling with try/except blocks
- Include logging for debugging
- Add CORS headers if needed for PowerBI embedding
- Make the UI responsive with CSS flexbox/grid
