#!/bin/bash
echo "Installing dependencies..."
DEB_FOLDER="../debs"

# Update repositories
sudo apt-get update
# sudo apt-get -y upgrade

##### expect #####
# this is for executing commands into the openhab console
sudo apt-get install expect -y

##### Docker #####
# Create a Python virtual environment
sudo python -m venv pythonvenv

# Change ownership to openhab
sudo chown -R openhab pythonvenv

# Activate the virtual environment
source pythonvenv/bin/activate

# Upgrade setuptools and wheel
pip install --upgrade setuptools wheel

# Upgrade pip
pip install --upgrade pip

# Deactivate the virtual environment
deactivate

# Re-activate the virtual environment
source pythonvenv/bin/activate

# Install docker-compose
pip3 install --no-build-isolation docker-compose==1.29.2

# Check if Docker Compose is installed
if ! command -v docker-compose &>/dev/null; then
    echo "Docker Compose installation failed. Please check the installation steps and try again."
    sleep 2
    exit 1
else
    echo "Docker Compose installation successful. Version: $(docker-compose --version)"
fi

# Uninstall existing requests library
pip uninstall requests -y

# Install specific version of requests library
pip install requests==2.31.0

# Install docker
pip install docker==6.1.3

sudo apt-get install docker.io -y

# Check if Docker is installed
if ! command -v docker &>/dev/null; then
    echo "Docker installation failed. Please check the installation steps and try again."
    sleep 2
    exit 1
else
    echo "Docker installation successful. Version: $(docker --version)"
fi
