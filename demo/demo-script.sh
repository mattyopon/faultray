#!/bin/bash
# Scripted demo for FaultRay
# Simulates typing for a natural feel

type_cmd() {
    local cmd="$1"
    echo ""
    echo -ne "\033[1;32m❯\033[0m "
    for (( i=0; i<${#cmd}; i++ )); do
        echo -n "${cmd:$i:1}"
        sleep 0.04
    done
    echo ""
    sleep 0.3
    eval "$cmd"
    sleep 1.5
}

clear

# Title
echo ""
echo -e "\033[1;36m  ╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;36m  ║  FaultRay — Zero-Risk Chaos Engineering     ║\033[0m"
echo -e "\033[1;36m  ║  Simulate failures before they hit prod     ║\033[0m"
echo -e "\033[1;36m  ╚══════════════════════════════════════════════╝\033[0m"
echo ""
sleep 2

# Step 1: Install
echo -e "\033[1;33m# Step 1: Install FaultRay\033[0m"
type_cmd "pip install faultray -q"

# Step 2: Version check
echo ""
echo -e "\033[1;33m# Step 2: Check version\033[0m"
type_cmd "faultray --version"

# Step 3: Run demo simulation
echo ""
echo -e "\033[1;33m# Step 3: Simulate chaos on a demo infrastructure\033[0m"
type_cmd "faultray demo"

sleep 2

# Closing
echo ""
echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo -e "\033[1;32m  Get started: pip install faultray\033[0m"
echo -e "\033[1;32m  GitHub: github.com/mattyopon/faultray\033[0m"
echo -e "\033[1;32m  Docs: faultray.com\033[0m"
echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo ""
sleep 3
