"""
Main Flask application for Fabric Embedded Agent.
Combines PowerBI embedded reports with Fabric Data Agent chat interface.
"""

import logging
import requests
import re
from flask import Flask, render_template, request, jsonify, session
from identity.flask import Auth
import msal

from app_config import get_config, validate_config
from fabric_data_agent_client import FabricDataAgentClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
config = get_config()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = config["FLASK_SECRET_KEY"]
app.config["SESSION_TYPE"] = config["SESSION_TYPE"]

# Fabric API scope for token acquisition (client credentials / service principal)
FABRIC_SCOPE = ["https://api.fabric.microsoft.com/.default"]

# Fabric API scope for delegated (user) token acquisition
FABRIC_USER_SCOPE = ["https://api.fabric.microsoft.com/Item.Execute.All"]

# Initialize Entra ID Authentication with Fabric scope
auth = Auth(
    app,
    authority=config["AUTHORITY"],
    client_id=config["CLIENT_ID"],
    client_credential=config["CLIENT_SECRET"],
    redirect_uri=config["REDIRECT_URI"]
)

# Initialize Fabric Data Agent client (lazy initialization)
fabric_client = None


_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _is_guid(value: str) -> bool:
    if not value:
        return False
    return bool(_GUID_RE.match(value.strip()))


def _parse_roles(roles_raw):
    if roles_raw is None:
        return []
    if isinstance(roles_raw, list):
        roles_list = roles_raw
    else:
        roles_list = str(roles_raw).split(",")
    roles = [str(r).strip() for r in roles_list if str(r).strip()]
    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for r in roles:
        if r not in seen:
            deduped.append(r)
            seen.add(r)
    return deduped


def get_effective_embed_settings():
    """Merge env config defaults with per-session overrides.

    Note: we intentionally do NOT allow the frontend to set the RLS username.
    Identity always comes from the authenticated Entra ID session.
    """
    defaults = {
        "workspaceId": config.get("PBI_WORKSPACE_ID"),
        "reportId": config.get("PBI_REPORT_ID"),
        "datasetId": config.get("PBI_DATASET_ID"),
        "rlsEnabled": bool(config.get("RLS_ENABLED")),
        "rlsRoles": list(config.get("RLS_ROLES", [])),
    }

    overrides = session.get("embed_settings") or {}
    merged = {**defaults, **overrides}

    # Normalize
    merged["workspaceId"] = (merged.get("workspaceId") or "").strip() or None
    merged["reportId"] = (merged.get("reportId") or "").strip() or None
    merged["datasetId"] = (merged.get("datasetId") or "").strip() or None
    merged["rlsEnabled"] = bool(merged.get("rlsEnabled"))
    merged["rlsRoles"] = _parse_roles(merged.get("rlsRoles"))
    return merged


def _validate_embed_settings(settings: dict):
    errors = []

    workspace_id = (settings.get("workspaceId") or "").strip()
    report_id = (settings.get("reportId") or "").strip()
    dataset_id = (settings.get("datasetId") or "").strip()
    rls_enabled = bool(settings.get("rlsEnabled"))
    rls_roles = _parse_roles(settings.get("rlsRoles"))

    if not workspace_id:
        errors.append("workspaceId is required")
    elif not _is_guid(workspace_id):
        errors.append("workspaceId must be a GUID")

    if not report_id:
        errors.append("reportId is required")
    elif not _is_guid(report_id):
        errors.append("reportId must be a GUID")

    if dataset_id and not _is_guid(dataset_id):
        errors.append("datasetId must be a GUID when provided")

    # Guardrails: keep roles reasonable
    if len(rls_roles) > 20:
        errors.append("rlsRoles has too many entries (max 20)")
    if any(len(r) > 128 for r in rls_roles):
        errors.append("rlsRoles entries must be <= 128 characters")

    # If RLS enabled but no roles, we allow it (Power BI will treat as no role)
    # but dataset must exist (or be derivable from report)

    cleaned = {
        "workspaceId": workspace_id,
        "reportId": report_id,
        "datasetId": dataset_id or None,
        "rlsEnabled": rls_enabled,
        "rlsRoles": rls_roles,
    }
    return cleaned, errors


def get_fabric_client():
    """
    Get or initialize the Fabric Data Agent client.
    Uses lazy initialization to avoid blocking app startup.
    """
    global fabric_client
    if fabric_client is None and config.get("DATA_AGENT_URL") and config.get("TENANT_ID"):
        try:
            fabric_client = FabricDataAgentClient(
                tenant_id=config["TENANT_ID"],
                data_agent_url=config["DATA_AGENT_URL"]
            )
        except Exception as e:
            logger.error(f"Failed to initialize Fabric client: {e}")
    return fabric_client


def get_fabric_token():
    """
    Acquire Fabric API access token using Service Principal (client credentials).
    
    Returns:
        str: Access token for Fabric API, or None if acquisition fails
    """
    try:
        # Create MSAL confidential client application
        msal_client = msal.ConfidentialClientApplication(
            config["CLIENT_ID"],
            authority=config["AUTHORITY"],
            client_credential=config["CLIENT_SECRET"]
        )
        
        # Acquire token for Fabric API using client credentials
        token_response = msal_client.acquire_token_for_client(scopes=FABRIC_SCOPE)
        
        if "access_token" not in token_response:
            logger.error(f"Failed to acquire Fabric token: {token_response.get('error_description', 'Unknown error')}")
            return None
        
        return token_response["access_token"]
        
    except Exception as e:
        logger.error(f"Error acquiring Fabric token: {e}")
        return None


def get_powerbi_embed_token(user_context=None):
    """
    Acquire PowerBI embed token using Service Principal authentication.
    Supports dynamic Row-Level Security (RLS) when enabled.
    
    SECURITY: The user identity for RLS is ALWAYS derived from the authenticated
    user context (Entra ID session), never from frontend input. This prevents
    users from spoofing their identity to access other users' data.
    
    Args:
        user_context: The authenticated user context from Entra ID (contains 'preferred_username', 'oid', etc.)
                     This is obtained from the backend session, NOT from client input.
    
    Returns:
        dict: Contains embedUrl, accessToken, and reportId
    """
    try:
        # Create MSAL confidential client application
        msal_client = msal.ConfidentialClientApplication(
            config["CLIENT_ID"],
            authority=config["AUTHORITY"],
            client_credential=config["CLIENT_SECRET"]
        )
        
        # Acquire token for PowerBI API
        scope = ["https://analysis.windows.net/powerbi/api/.default"]
        token_response = msal_client.acquire_token_for_client(scopes=scope)
        
        if "access_token" not in token_response:
            logger.error(f"Failed to acquire PowerBI token: {token_response.get('error_description', 'Unknown error')}")
            return None
        
        access_token = token_response["access_token"]
        
        # Get report details from PowerBI API (allow per-session overrides)
        effective = get_effective_embed_settings()
        workspace_id = effective.get("workspaceId")
        report_id = effective.get("reportId")
        dataset_id = effective.get("datasetId")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Get report info
        report_url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}"
        report_response = requests.get(report_url, headers=headers)
        report_response.raise_for_status()
        report_info = report_response.json()
        
        # If dataset_id is not configured, get it from the report
        if not dataset_id:
            dataset_id = report_info.get("datasetId")
        
        # Build embed token request body
        embed_token_body = {
            "accessLevel": "View",
            "allowSaveAs": False
        }
        
        # Add RLS identity if enabled - SECURITY: Identity comes from backend session only
        if effective.get("rlsEnabled") and user_context:
            rls_roles = effective.get("rlsRoles", [])
            
            if not rls_roles:
                logger.warning("RLS is enabled but no roles are configured. Set RLS_ROLES in environment.")
            
            if not dataset_id:
                logger.error("RLS requires a dataset ID. Set PBI_DATASET_ID in environment or ensure report has a linked dataset.")
                return None
            
            # SECURITY: Extract user identity from the authenticated session
            # This is the key security measure - the username is NEVER accepted from the frontend
            # We use 'preferred_username' (UPN/email) which is the standard for RLS with userprincipalname()
            # Fallback to 'email' or construct from name if UPN is not available
            user_identity = (
                user_context.get("preferred_username")  # Standard UPN claim
                or user_context.get("email")             # Fallback to email claim
                or user_context.get("upn")               # Alternative UPN claim
            )
            
            if not user_identity:
                logger.error("Cannot apply RLS: User identity (UPN/email) not found in authentication context")
                return None
            
            logger.info(f"Applying RLS for user: {user_identity} with roles: {rls_roles}")
            
            # Build the effective identity for RLS
            # This identity is passed to Power BI to filter data according to RLS rules
            embed_token_body["identities"] = [{
                "username": user_identity,  # Used by DAX username() or userprincipalname() functions
                "roles": rls_roles,          # RLS roles defined in the Power BI dataset
                "datasets": [dataset_id]     # Dataset(s) to apply RLS to
            }]
        
        # Generate embed token
        embed_token_url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/GenerateToken"
        
        embed_response = requests.post(embed_token_url, headers=headers, json=embed_token_body)
        embed_response.raise_for_status()
        embed_token_info = embed_response.json()
        
        return {
            "embedUrl": report_info.get("embedUrl"),
            "accessToken": embed_token_info.get("token"),
            "reportId": report_id,
            "tokenExpiry": embed_token_info.get("expiration")
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"PowerBI API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting PowerBI embed token: {e}")
        return None


# Routes
@app.route("/")
@auth.login_required
def index(*, context):
    """
    Main page with embedded PowerBI report and chat interface.
    """
    return render_template('index.html', user=context['user'], embed_settings=get_effective_embed_settings())


@app.route("/login")
def login():
    """
    Login page for unauthenticated users.
    """
    return render_template('login.html')


@app.route("/api/getembedinfo")
@auth.login_required
def get_embed_info(*, context):
    """
    API endpoint to get PowerBI embed information.
    Returns embedUrl, accessToken, and reportId for the configured report.
    
    SECURITY: For RLS-enabled reports, the user identity is extracted from the
    authenticated session context (Entra ID), NOT from any client-provided input.
    This ensures users cannot spoof their identity to access other users' data.
    """
    try:
        # Pass the authenticated user context to the embed token generator
        # SECURITY: user context comes from Entra ID authentication, not from client
        user_context = context.get('user') if context else None
        embed_info = get_powerbi_embed_token(user_context=user_context)
        
        if embed_info:
            return jsonify(embed_info)
        else:
            return jsonify({"error": "Failed to generate embed token"}), 500
            
    except Exception as e:
        logger.error(f"Error in get_embed_info: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/embedsettings", methods=["GET", "POST"])
@auth.login_required
def embed_settings(*, context):
    """Get or set per-session Power BI embed + RLS settings.

    SECURITY: This endpoint never accepts an RLS username. User identity is always
    derived from the authenticated Entra ID session when generating the embed token.
    """
    if request.method == "GET":
        return jsonify(get_effective_embed_settings())

    try:
        payload = request.get_json(silent=True) or request.form.to_dict(flat=True) or {}
        candidate = {
            "workspaceId": payload.get("workspaceId"),
            "reportId": payload.get("reportId"),
            "datasetId": payload.get("datasetId"),
            "rlsEnabled": payload.get("rlsEnabled"),
            "rlsRoles": payload.get("rlsRoles"),
        }

        # Normalize checkbox / string booleans
        if isinstance(candidate.get("rlsEnabled"), str):
            candidate["rlsEnabled"] = candidate["rlsEnabled"].lower() in ("1", "true", "yes", "on")

        cleaned, errors = _validate_embed_settings(candidate)
        if errors:
            return jsonify({"error": "Invalid settings", "details": errors}), 400

        session["embed_settings"] = cleaned
        return jsonify({"message": "Settings saved", "settings": get_effective_embed_settings()})

    except Exception as e:
        logger.error(f"Error saving embed settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/embedsettings/reset", methods=["POST"])
@auth.login_required
def reset_embed_settings(*, context):
    """Clear per-session embed settings so env defaults apply."""
    try:
        session.pop("embed_settings", None)
        return jsonify({"message": "Settings reset", "settings": get_effective_embed_settings()})
    except Exception as e:
        logger.error(f"Error resetting embed settings: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
@auth.login_required(scopes=FABRIC_USER_SCOPE)
def chat(*, context):
    """
    API endpoint for chat with Fabric Data Agent.
    Maintains conversation thread per user session.
    Uses the authenticated user's delegated token (not the service principal).
    """
    try:
        data = request.json
        question = data.get("question")
        
        if not question:
            return jsonify({"error": "Question is required"}), 400
        
        # Get or create thread name based on user session
        thread_name = session.get("chat_thread")
        if not thread_name:
            thread_name = f"session_{context['user'].get('oid', 'anonymous')}"
            session["chat_thread"] = thread_name
        
        # Get Fabric client
        client = get_fabric_client()
        if not client:
            return jsonify({
                "error": "Fabric Data Agent is not configured. Please check DATA_AGENT_URL and TENANT_ID settings."
            }), 503
        
        # Use the authenticated user's delegated token from Entra ID
        access_token = context.get("access_token")
        if not access_token:
            return jsonify({
                "error": "Failed to acquire user token for Fabric API. The user may need to re-authenticate."
            }), 401
        
        # Send question to Fabric Data Agent
        response = client.ask(question, access_token=access_token, thread_name=thread_name)
        
        return jsonify({"response": response})
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/clear", methods=["POST"])
@auth.login_required
def clear_chat(*, context):
    """
    Clear the current chat thread for the user.
    """
    try:
        thread_name = session.get("chat_thread")
        if thread_name:
            client = get_fabric_client()
            if client:
                client.clear_thread(thread_name)
            session.pop("chat_thread", None)
        
        return jsonify({"message": "Chat cleared successfully"})
        
    except Exception as e:
        logger.error(f"Error clearing chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    """
    Health check endpoint.
    """
    return jsonify({"status": "healthy"})


# Error handlers
@app.errorhandler(401)
def unauthorized(error):
    """Handle unauthorized access."""
    return render_template('login.html', error="Please log in to access this page."), 401


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "An internal error occurred"}), 500


if __name__ == "__main__":
    # Validate configuration before starting
    try:
        validate_config(config)
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.warning(f"Configuration warning: {e}")
        logger.warning("Some features may not work without proper configuration")
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)
