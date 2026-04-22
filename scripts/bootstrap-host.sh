#!/usr/bin/env bash
# Bootstrap an Ubuntu host for Anvil: install Docker, fio, nvme-cli, smartmontools, etc.
set -euo pipefail

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null; then
  echo "This script needs sudo or root." >&2
  exit 1
fi

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

export DEBIAN_FRONTEND=noninteractive

$SUDO apt-get update -qq
$SUDO apt-get install -y -qq \
  fio nvme-cli smartmontools hdparm pciutils util-linux sg3-utils \
  cpufrequtils numactl ipmitool jq curl ca-certificates gnupg git

if ! command -v docker >/dev/null; then
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    $SUDO tee /etc/apt/keyrings/docker.asc >/dev/null
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" | \
    $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  $SUDO systemctl enable --now docker
fi

$SUDO usermod -aG docker "${SUDO_USER:-$USER}" || true

echo "Anvil bootstrap complete. You may need to re-login for the docker group to take effect."
