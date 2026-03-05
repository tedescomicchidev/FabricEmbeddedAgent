# Change these values to the ones used to create the App Service.
RESOURCE_GROUP_NAME='mitedescdevfabricagent'
APP_SERVICE_NAME='mitedescDevFabricAgent'

az webapp config appsettings set --resource-group $RESOURCE_GROUP_NAME --name $APP_SERVICE_NAME --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true

# Change these values to the ones used to create the App Service.
# RESOURCE_GROUP_NAME='msdocs-python-webapp-quickstart'
# APP_SERVICE_NAME='msdocs-python-webapp-quickstart-123'

az webapp deploy --name $APP_SERVICE_NAME --resource-group $RESOURCE_GROUP_NAME --src-path app.zip --clean