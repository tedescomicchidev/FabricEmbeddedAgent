"""
Fabric Data Agent SDK Client.
Handles communication with Microsoft Fabric Data Agent API using OpenAI Assistants API.
"""

import logging
import time
import uuid
import requests
from typing import Optional, Dict, Any, List

from openai import OpenAI

logger = logging.getLogger(__name__)


class FabricDataAgentClient:
    """
    Client for interacting with Microsoft Fabric Data Agent.
    Uses the OpenAI Assistants API that Fabric Data Agent exposes.
    Access tokens are provided by the calling application for authentication.
    """
    
    FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
    
    def __init__(self, tenant_id: str, data_agent_url: str):
        """
        Initialize the Fabric Data Agent client.
        
        Args:
            tenant_id: Azure AD tenant ID
            data_agent_url: Full URL to the Fabric Data Agent API endpoint
                           (e.g., https://api.fabric.microsoft.com/v1/workspaces/{id}/dataAgents/{id}/aiassistant/openai)
        """
        self.tenant_id = tenant_id
        self.data_agent_url = data_agent_url
        self._threads: Dict[str, Dict[str, Any]] = {}  # Cache for conversation threads
        self._openai_client: Optional[OpenAI] = None
        self._current_token: Optional[str] = None
        logger.info("Fabric Data Agent client initialized successfully")
    
    def _get_openai_client(self, access_token: str) -> OpenAI:
        """
        Get or create an OpenAI client configured for Fabric Data Agent.
        Recreates the client if the token has changed.
        
        Args:
            access_token: Bearer token for Fabric API authentication
            
        Returns:
            OpenAI: Configured OpenAI client
        """
        if self._openai_client is None or self._current_token != access_token:
            self._openai_client = OpenAI(
                api_key="",  # Not used - we use Bearer token in headers
                base_url=self.data_agent_url,
                default_query={"api-version": "2024-05-01-preview"},
                default_headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "ActivityId": str(uuid.uuid4())
                }
            )
            self._current_token = access_token
            logger.debug("Created new OpenAI client for Fabric Data Agent")
        return self._openai_client
    
    def _get_or_create_thread(self, access_token: str, thread_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get existing thread or create a new conversation thread via Fabric API.
        
        This method transforms the data agent URL to the correct threads endpoint
        and makes a direct HTTP request to create/retrieve threads.
        
        Args:
            access_token: Bearer token for Fabric API authentication
            thread_name: Optional name for the thread. If None, a random name is generated.
            
        Returns:
            Dict containing thread id and name
        """
        # If thread_name provided and exists in cache, return it
        if thread_name and thread_name in self._threads:
            logger.debug(f"Using cached thread: {thread_name}")
            return self._threads[thread_name]
        
        # Generate thread name if not provided
        if thread_name is None:
            thread_name = f'external-client-thread-{uuid.uuid4()}'
        
        # Transform URL for thread creation endpoint
        # Handle both "aiskills" and "dataAgents" URL formats
        if "aiskills" in self.data_agent_url:
            base_url = self.data_agent_url.replace("aiskills", "dataagents").removesuffix("/openai").replace("/aiassistant", "/__private/aiassistant")
        else:
            base_url = self.data_agent_url.removesuffix("/openai").replace("/aiassistant", "/__private/aiassistant")
        
        get_thread_url = f'{base_url}/threads/fabric?tag="{thread_name}"'
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ActivityId": str(uuid.uuid4())
        }
        
        logger.debug(f"Creating/retrieving thread from: {get_thread_url}")
        
        response = requests.get(get_thread_url, headers=headers)
        response.raise_for_status()
        
        thread = response.json()
        thread["name"] = thread_name  # Add thread name to returned object
        thread["messages"] = []  # Local message history for display
        
        # Cache the thread
        self._threads[thread_name] = thread
        logger.info(f"Created/retrieved thread '{thread_name}' with ID: {thread.get('id')}")
        
        return thread
    
    def ask(self, question: str, access_token: str, timeout: int = 120, thread_name: Optional[str] = None) -> str:
        """
        Send a question to the Fabric Data Agent and get a response using Assistants API.
        
        Args:
            question: The question to ask the agent
            access_token: Bearer token for Fabric API authentication
            timeout: Maximum time to wait for response in seconds
            thread_name: Optional thread name for conversation continuity
            
        Returns:
            str: The agent's response
        """
        try:
            # Get OpenAI client configured for Fabric
            client = self._get_openai_client(access_token)
            
            # Create assistant (required by Fabric Data Agent)
            assistant = client.beta.assistants.create(model="not used")
            
            # Get or create thread for conversation continuity
            thread = self._get_or_create_thread(access_token, thread_name)
            thread_id = thread["id"]
            
            # Add the user's question to local history
            thread["messages"].append({
                "role": "user",
                "content": question
            })
            
            logger.info(f"Sending question to Fabric Data Agent: {question[:50]}...")
            
            # Add message to thread via Assistants API
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=question
            )
            
            # Create and poll run using the assistant
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant.id
            )
            
            # Poll for completion
            start_time = time.time()
            while run.status in ["queued", "in_progress"]:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Request timed out after {timeout} seconds")
                
                time.sleep(2)  # Wait before polling again
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                logger.debug(f"Run status: {run.status}")
            
            if run.status == "completed":
                # Get all messages and find assistant responses
                messages = client.beta.threads.messages.list(
                    thread_id=thread_id,
                    order="asc"
                )
                
                # Extract assistant responses
                responses = []
                for msg in messages.data:
                    if msg.role == "assistant":
                        try:
                            content = msg.content[0]
                            if hasattr(content, 'text'):
                                text_content = getattr(content, 'text', None)
                                if text_content is not None and hasattr(text_content, 'value'):
                                    responses.append(text_content.value)
                                elif text_content is not None:
                                    responses.append(str(text_content))
                                else:
                                    responses.append(str(content))
                            else:
                                responses.append(str(content))
                        except (IndexError, AttributeError):
                            responses.append(str(msg.content))
                
                if responses:
                    assistant_message = "\n".join(responses)
                    
                    # Add assistant's response to local history
                    thread["messages"].append({
                        "role": "assistant",
                        "content": assistant_message
                    })
                    
                    logger.info("Received response from Fabric Data Agent")
                    return assistant_message
                else:
                    logger.warning("No assistant messages returned from Fabric Data Agent")
                    return "No response received from the data agent."
            
            elif run.status == "failed":
                error_msg = run.last_error.message if run.last_error else "Unknown error"
                logger.error(f"Fabric Data Agent run failed: {error_msg}")
                return f"The agent encountered an error: {error_msg}"
            
            else:
                logger.warning(f"Unexpected run status: {run.status}")
                return f"Unexpected status: {run.status}. Please try again."
                
        except TimeoutError as e:
            logger.error(str(e))
            return "The request timed out. Please try again with a simpler question."
        except Exception as e:
            logger.error(f"Error communicating with Fabric Data Agent: {e}")
            return f"Error communicating with the agent: {str(e)}"
    
    def get_conversation_history(self, thread_name: str) -> List[Dict[str, str]]:
        """
        Get the conversation history for a thread.
        
        Args:
            thread_name: Name of the thread
            
        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        if thread_name in self._threads:
            return self._threads[thread_name].get("messages", []).copy()
        return []
    
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
