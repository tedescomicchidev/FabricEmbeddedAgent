"""
Fabric Data Agent SDK Client.
Handles authentication and communication with Microsoft Fabric Data Agent API.
"""

import logging
import time
from typing import Optional
from azure.identity import InteractiveBrowserCredential
from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class FabricDataAgentClient:
    """
    Client for interacting with Microsoft Fabric Data Agent.
    Uses Azure Identity for authentication and OpenAI client pattern for API calls.
    """
    
    FABRIC_SCOPE = "https://fabric.microsoft.com/.default"
    
    def __init__(self, tenant_id: str, data_agent_url: str):
        """
        Initialize the Fabric Data Agent client.
        
        Args:
            tenant_id: Azure AD tenant ID
            data_agent_url: Full URL to the Fabric Data Agent API endpoint
        """
        self.tenant_id = tenant_id
        self.data_agent_url = data_agent_url
        self._threads = {}  # Cache for conversation threads
        
        # Initialize browser-based authentication
        self.credential = InteractiveBrowserCredential(
            tenant_id=tenant_id
        )
        
        # Get initial token to verify authentication
        try:
            self._get_token()
            logger.info("Fabric Data Agent client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Fabric Data Agent client: {e}")
            raise
    
    def _get_token(self) -> str:
        """
        Get access token for Fabric API.
        
        Returns:
            str: Access token
        """
        token = self.credential.get_token(self.FABRIC_SCOPE)
        return token.token
    
    def _get_or_create_new_thread(self, data_agent_url: str, thread_name: Optional[str] = None) -> str:
        """
        Get existing thread or create a new conversation thread.
        
        Args:
            data_agent_url: URL of the data agent
            thread_name: Optional name for the thread
            
        Returns:
            str: Thread ID
        """
        # If thread_name provided and exists in cache, return it
        if thread_name and thread_name in self._threads:
            logger.debug(f"Using existing thread: {thread_name}")
            return self._threads[thread_name]
        
        # Create a new thread ID
        import uuid
        thread_id = str(uuid.uuid4())
        
        # Cache the thread if a name was provided
        if thread_name:
            self._threads[thread_name] = thread_id
            logger.info(f"Created new thread '{thread_name}' with ID: {thread_id}")
        else:
            logger.info(f"Created anonymous thread with ID: {thread_id}")
        
        return thread_id
    
    def ask(self, question: str, timeout: int = 120, thread_name: Optional[str] = None) -> str:
        """
        Send a question to the Fabric Data Agent and get a response.
        
        Args:
            question: The question to ask the agent
            timeout: Maximum time to wait for response in seconds
            thread_name: Optional thread name for conversation continuity
            
        Returns:
            str: The agent's response
        """
        import requests
        
        try:
            # Get or create thread for conversation
            thread_id = self._get_or_create_new_thread(self.data_agent_url, thread_name)
            
            # Get fresh token
            token = self._get_token()
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # Prepare the request payload
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": question
                    }
                ],
                "thread_id": thread_id
            }
            
            logger.info(f"Sending question to Fabric Data Agent: {question[:50]}...")
            
            # Make the API call
            response = requests.post(
                f"{self.data_agent_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout
            )
            
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            
            # Extract the assistant's message
            if "choices" in result and len(result["choices"]) > 0:
                assistant_message = result["choices"][0].get("message", {}).get("content", "")
                logger.info("Received response from Fabric Data Agent")
                return assistant_message
            else:
                logger.warning("Unexpected response format from Fabric Data Agent")
                return "I couldn't process that request. Please try again."
                
        except requests.exceptions.Timeout:
            logger.error(f"Request to Fabric Data Agent timed out after {timeout} seconds")
            return "The request timed out. Please try again with a simpler question."
        except requests.exceptions.RequestException as e:
            logger.error(f"Error communicating with Fabric Data Agent: {e}")
            return f"Error communicating with the agent: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error in Fabric Data Agent client: {e}")
            return f"An unexpected error occurred: {str(e)}"
    
    def clear_thread(self, thread_name: str) -> bool:
        """
        Clear a conversation thread from cache.
        
        Args:
            thread_name: Name of the thread to clear
            
        Returns:
            bool: True if thread was cleared, False if not found
        """
        if thread_name in self._threads:
            del self._threads[thread_name]
            logger.info(f"Cleared thread: {thread_name}")
            return True
        return False
