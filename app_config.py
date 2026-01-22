"""
Configuration loader for the Flask application.
Loads environment variables from .env file and provides configuration dictionary.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_config():
    """
    Load and return application configuration from environment variables.
    
    Returns:
        dict: Configuration dictionary with all required settings
    """
    config = {
        # Entra ID Authentication
        "CLIENT_ID": os.getenv("CLIENT_ID"),
        "CLIENT_SECRET": os.getenv("CLIENT_SECRET"),
        "TENANT_ID": os.getenv("TENANT_ID"),
        "AUTHORITY": os.getenv("AUTHORITY", f"https://login.microsoftonline.com/{os.getenv('TENANT_ID')}"),
        "REDIRECT_URI": os.getenv("REDIRECT_URI", "http://localhost:5000/getAToken"),
        
        # PowerBI Embedding
        "PBI_WORKSPACE_ID": os.getenv("PBI_WORKSPACE_ID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        "PBI_REPORT_ID": os.getenv("PBI_REPORT_ID", "11111111-2222-3333-4444-555555555555"),
        "PBI_DATASET_ID": os.getenv("PBI_DATASET_ID"),  # Required for RLS
        
        # Row-Level Security (RLS) Configuration
        # Set RLS_ENABLED to "true" to enable dynamic RLS
        # RLS_ROLES: Comma-separated list of RLS role names defined in the Power BI dataset
        # The user's UPN (email) from Entra ID authentication will be used as the username
        "RLS_ENABLED": os.getenv("RLS_ENABLED", "false").lower() == "true",
        "RLS_ROLES": [role.strip() for role in os.getenv("RLS_ROLES", "").split(",") if role.strip()],
        
        # Fabric Data Agent
        "DATA_AGENT_URL": os.getenv("DATA_AGENT_URL"),
        
        # Flask
        "FLASK_SECRET_KEY": os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-production"),
        "SESSION_TYPE": os.getenv("SESSION_TYPE", "filesystem"),
    }
    
    return config


# Validate required configuration
def validate_config(config):
    """
    Validate that all required configuration values are present.
    
    Args:
        config: Configuration dictionary
        
    Raises:
        ValueError: If required configuration is missing
    """
    required_fields = ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"]
    missing = [field for field in required_fields if not config.get(field)]
    
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    
    return True
