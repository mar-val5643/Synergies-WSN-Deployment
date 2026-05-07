#!/bin/bash

# Script to automate the installation and setup of the openHAB platform and utilities

# Main script starts here
source ./config.env

cd utils || { echo "Error - No utils folder"; exit 1; }
chmod +x install_dependencies.sh
chmod +x deploy_openhab.sh
chmod +x perform_operational_checks.sh
chmod +x console_command.sh

# Execute the separate scripts for each task
./install_dependencies.sh

./deploy_openhab.sh 
#./perform_operational_checks.sh  # skipped

# Source the config.env file to load the variables
URL="http://$WSN_HOSTNAME:$OPENHAB_HTTP_PORT"


# Display completion message
echo ""
echo "Deployment completed successfully!"
echo ""
echo "You can now access the openHAB user interface (UI) by visiting the following URL:"
echo "$URL"
