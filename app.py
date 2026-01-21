"""
Main Flask application for Fabric Embedded Agent.
Combines PowerBI embedded reports with Fabric Data Agent chat interface.
"""

import logging
import requests
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

# Fabric API scope for token acquisition
FABRIC_SCOPE = ["https://api.fabric.microsoft.com/.default"]

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


def get_powerbi_embed_token():
    """
    Acquire PowerBI embed token using Service Principal authentication.
    
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
        
        # Get report details from PowerBI API
        workspace_id = config["PBI_WORKSPACE_ID"]
        report_id = config["PBI_REPORT_ID"]
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Get report info
        report_url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}"
        report_response = requests.get(report_url, headers=headers)
        report_response.raise_for_status()
        report_info = report_response.json()
        
        # Generate embed token
        embed_token_url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/reports/{report_id}/GenerateToken"
        embed_token_body = {
            "accessLevel": "View",
            "allowSaveAs": False
        }
        
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
    return render_template('index.html', user=context['user'])


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
    """
    try:
        embed_info = get_powerbi_embed_token()
        
        if embed_info:
            return jsonify(embed_info)
        else:
            return jsonify({"error": "Failed to generate embed token"}), 500
            
    except Exception as e:
        logger.error(f"Error in get_embed_info: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
@auth.login_required
def chat(*, context):
    """
    API endpoint for chat with Fabric Data Agent.
    Maintains conversation thread per user session.
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
        
        # Get Fabric API access token
        access_token = get_fabric_token()
        if not access_token:
            return jsonify({
                "error": "Failed to acquire Fabric API token. Please check your Azure AD app registration has the required Fabric API permissions."
            }), 503
        
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
