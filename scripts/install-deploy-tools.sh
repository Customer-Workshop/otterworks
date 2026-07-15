#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Install Deploy Tools
#
# Installs the command-line tools required to deploy OtterWorks to AWS (see
# docs/AWS_EKS_SETUP.md, section 1). These are system binaries, not pip
# packages, so a requirements.txt cannot install them.
#
# Installs / verifies:
#   - AWS CLI v2      - Docker            - Terraform 1.7+
#   - kubectl         - Helm 3            - jq
#   - OpenSSL         - GNU Make
#
# Supported package managers:
#   - Homebrew (macOS / Linuxbrew)
#   - apt-get  (Debian / Ubuntu)
#
# Usage:
#   ./scripts/install-deploy-tools.sh          # install anything missing
#   ./scripts/install-deploy-tools.sh --check  # verify only, install nothing
# ------------------------------------------------------------------------------
set -euo pipefail

CHECK_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 1 ;;
  esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[install]${NC} $*"; }
warn() { echo -e "${YELLOW}[install]${NC} $*"; }
err()  { echo -e "${RED}[install]${NC} $*" >&2; }

# ---------- Detect package manager ----------

PKG_MANAGER=""
if command -v brew >/dev/null 2>&1; then
  PKG_MANAGER="brew"
elif command -v apt-get >/dev/null 2>&1; then
  PKG_MANAGER="apt"
else
  err "No supported package manager found (need Homebrew or apt-get)."
  err "Install Homebrew from https://brew.sh and re-run, or install the tools"
  err "manually per docs/AWS_EKS_SETUP.md section 1."
  exit 1
fi
log "Using package manager: ${PKG_MANAGER}"

APT_UPDATED=false
apt_install() {
  if [ "${APT_UPDATED}" = false ]; then
    sudo apt-get update -y
    APT_UPDATED=true
  fi
  sudo apt-get install -y "$@"
}

# ---------- Individual installers ----------
# Each installer is only invoked when the tool is missing.

install_aws() {
  case "${PKG_MANAGER}" in
    brew) brew install awscli ;;
    apt)
      local tmp; tmp="$(mktemp -d)"
      local arch; arch="$(uname -m)"
      curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip" -o "${tmp}/awscliv2.zip"
      (cd "${tmp}" && unzip -q awscliv2.zip && sudo ./aws/install --update)
      rm -rf "${tmp}"
      ;;
  esac
}

install_docker() {
  case "${PKG_MANAGER}" in
    brew)
      warn "Installing Docker Desktop. You must launch it once and finish setup before deploying."
      brew install --cask docker
      ;;
    apt)
      apt_install docker.io
      warn "You may need to add your user to the 'docker' group: sudo usermod -aG docker \$USER"
      ;;
  esac
}

install_terraform() {
  case "${PKG_MANAGER}" in
    brew)
      brew tap hashicorp/tap 2>/dev/null || true
      brew install hashicorp/tap/terraform
      ;;
    apt)
      apt_install gnupg software-properties-common curl
      curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
      echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
      APT_UPDATED=false
      apt_install terraform
      ;;
  esac
}

install_kubectl() {
  case "${PKG_MANAGER}" in
    brew) brew install kubectl ;;
    apt)
      local arch; arch="$(uname -m)"; [ "${arch}" = "x86_64" ] && arch="amd64"; [ "${arch}" = "aarch64" ] && arch="arm64"
      local ver; ver="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
      local tmp; tmp="$(mktemp -d)"
      curl -fsSL "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl" -o "${tmp}/kubectl"
      curl -fsSL "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl.sha256" -o "${tmp}/kubectl.sha256"
      (cd "${tmp}" && echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check --quiet)
      sudo install -o root -g root -m 0755 "${tmp}/kubectl" /usr/local/bin/kubectl
      rm -rf "${tmp}"
      ;;
  esac
}

install_helm() {
  case "${PKG_MANAGER}" in
    brew) brew install helm ;;
    apt)
      local ver="v3.14.4"
      local arch; arch="$(uname -m)"; [ "${arch}" = "x86_64" ] && arch="amd64"; [ "${arch}" = "aarch64" ] && arch="arm64"
      local tmp; tmp="$(mktemp -d)"
      curl -fsSL "https://get.helm.sh/helm-${ver}-linux-${arch}.tar.gz" -o "${tmp}/helm.tar.gz"
      curl -fsSL "https://get.helm.sh/helm-${ver}-linux-${arch}.tar.gz.sha256sum" -o "${tmp}/helm.tar.gz.sha256sum"
      (cd "${tmp}" && sed "s|helm-${ver}-linux-${arch}.tar.gz|helm.tar.gz|" helm.tar.gz.sha256sum | sha256sum --check --quiet)
      tar -xzf "${tmp}/helm.tar.gz" -C "${tmp}"
      sudo install -o root -g root -m 0755 "${tmp}/linux-${arch}/helm" /usr/local/bin/helm
      rm -rf "${tmp}"
      ;;
  esac
}

install_jq()      { case "${PKG_MANAGER}" in brew) brew install jq ;;      apt) apt_install jq ;;      esac; }
install_openssl() { case "${PKG_MANAGER}" in brew) brew install openssl ;; apt) apt_install openssl ;; esac; }
install_make()    { case "${PKG_MANAGER}" in brew) brew install make ;;    apt) apt_install make ;;    esac; }

# ---------- Tool table: "command:pretty name:installer" ----------

TOOLS=(
  "aws:AWS CLI v2:install_aws"
  "docker:Docker:install_docker"
  "terraform:Terraform 1.7+:install_terraform"
  "kubectl:kubectl:install_kubectl"
  "helm:Helm 3:install_helm"
  "jq:jq:install_jq"
  "openssl:OpenSSL:install_openssl"
  "make:GNU Make:install_make"
)

MISSING=()

for entry in "${TOOLS[@]}"; do
  cmd="${entry%%:*}"
  rest="${entry#*:}"
  name="${rest%%:*}"
  installer="${rest##*:}"

  if command -v "${cmd}" >/dev/null 2>&1; then
    log "found ${name} ($(command -v "${cmd}"))"
    continue
  fi

  if [ "${CHECK_ONLY}" = true ]; then
    warn "MISSING: ${name}"
    MISSING+=("${name}")
    continue
  fi

  warn "installing ${name}..."
  if "${installer}"; then
    log "installed ${name}"
  else
    err "failed to install ${name}; install it manually per docs/AWS_EKS_SETUP.md"
    MISSING+=("${name}")
  fi
done

echo
if [ -n "${MISSING[*]-}" ]; then
  err "The following tools are still missing: ${MISSING[*]-}"
  exit 1
fi

if [ "${CHECK_ONLY}" = true ]; then
  log "All required deploy tools are installed."
else
  log "All required deploy tools are installed. Next steps:"
  log "  1. Ensure Docker is running (launch Docker Desktop on macOS)."
  log "  2. Configure AWS SSO and .env per docs/AWS_EKS_SETUP.md."
  log "  3. source .env && make deploy-dev"
fi
