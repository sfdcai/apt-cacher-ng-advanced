#!/bin/bash
# Apt-Cacher NG & Advanced Dashboard Installer
# Single-line installation: curl -sSL https://raw.githubusercontent.com/sfdcai/apt-cacher-ng-advanced/main/install.sh | bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   Apt-Cacher NG & Advanced Dashboard Installer     ${NC}"
echo -e "${BLUE}====================================================${NC}"

# 1. Ensure running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run this script as root or using sudo.${NC}"
    exit 1
fi

# 2. Update package lists and install system packages
echo -e "${BLUE}[1/5] Installing package dependencies...${NC}"
apt-get update
apt-get install -y apt-cacher-ng python3 python3-pip python3-venv curl

# Ensure apt-cacher-ng is running and enabled
echo -e "${BLUE}[2/5] Enabling and starting Apt-Cacher NG...${NC}"
systemctl enable apt-cacher-ng
systemctl start apt-cacher-ng

# 3. Create dashboard folders
echo -e "${BLUE}[3/5] Setting up dashboard directory structure...${NC}"
INSTALL_DIR="/opt/apt-cacher-dashboard"
mkdir -p "${INSTALL_DIR}/templates"

# 4. Download app files from GitHub
echo -e "${BLUE}[4/5] Downloading Dashboard files from GitHub...${NC}"
REPO_RAW_URL="https://raw.githubusercontent.com/sfdcai/apt-cacher-ng-advanced/main"
curl -sSL -o "${INSTALL_DIR}/app.py" "${REPO_RAW_URL}/app.py"
curl -sSL -o "${INSTALL_DIR}/templates/index.html" "${REPO_RAW_URL}/templates/index.html"

# 5. Set up virtual environment and install python packages
echo -e "${BLUE}[5/5] Building Python virtual environment and installing library dependencies...${NC}"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install flask requests beautifulsoup4

# 6. Configure Systemd Service
echo -e "${BLUE}[6/6] Creating and starting the Systemd service daemon...${NC}"
cat <<EOF > /etc/systemd/system/apt-cacher-dashboard.service
[Unit]
Description=Apt-Cacher NG Custom Web Dashboard
After=network.target apt-cacher-ng.service
Wants=apt-cacher-ng.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Restart/Reload services
systemctl daemon-reload
systemctl enable apt-cacher-dashboard
systemctl restart apt-cacher-dashboard

# Retrieve IP address
IP_ADDR=$(hostname -I | awk '{print $1}')
if [ -z "$IP_ADDR" ]; then
    IP_ADDR="localhost"
fi

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN}🎉 Installation and Setup Completed Successfully!    ${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "You can now access your services at:"
echo -e "  - ${BLUE}Custom Dashboard:${NC}    http://${IP_ADDR}:8080/"
echo -e "  - ${BLUE}Apt-Cacher NG Admin:${NC} http://${IP_ADDR}:3142/acng-report.html"
echo -e ""
echo -e "To configure your client systems to route through this cache:"
echo -e "  - ${BLUE}Debian/Ubuntu:${NC} Run the following as root on the client:"
echo -e "    echo 'Acquire::http::Proxy \"http://${IP_ADDR}:3142\";' > /etc/apt/apt.conf.d/00aptproxy"
echo -e "====================================================\n"
