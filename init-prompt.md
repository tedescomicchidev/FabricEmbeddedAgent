You're a senior software engineer.
You need to help me write a prompt for GitHub Copilot to be able to develop the following:
# Build web site with login
- Build a Flask app which allows users to sign in via Entra by following these documentation files: #file:Tutorial_ Sign-in users to a Python Flask web app by using Microsoft identity platform - Microsoft identity platform _ Microsoft Learn.pdf  and #file:Quickstart - Add app authentication to a web app - Azure App Service _ Microsoft Learn.pdf 
# Add PowerBI embedded report
- Open the git repository attached #file:PowerBI-Developer-Samples-master.zip  and navigate to "Python/Embed for your customers".
- Follow the "Python/Embed for your customers/AppOwnsData" sample and add an embedded report as the first component of the website with login
- Assume random values for the parameters needed (e.g. reportID,SPGuid,etc.)
# Add chat experience
- Leverage the #file:Intelligent app with Azure OpenAI (Flask) - Azure App Service _ Microsoft Learn.pdf  documentation to build a "chat" UI, which is based below the embedded report section. 
- Open the git repository in #file:fabric_data_agent_client-main.zip  and carefully read the example_usage.py and fabric_data_agent_client.py files
- Ensure the logic and the functions in fabric_data_agent_client are kept as is. Only chance to authentication to msal to leverage the same web site with login
- the chat UI needs to implement Fabric data agent with the Python client SDK to chat with a Fabric data agent
- Read the documentation #file:Consume Fabric data agent from external applications with Python client SDK - Microsoft Fabric _ Microsoft Learn.pdf  and  #file:Fabric data agent creation (preview) - Learn how to create a Fabric data agent _ Microsoft Learn.pdf  and #file:Best practices for configuring your data agent - Microsoft Fabric _ Microsoft Learn.pdf  to be able to leverage the SDK
