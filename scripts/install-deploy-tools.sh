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
    sudo apt-get update -y && APT_UPDATED=true
  fi
  sudo apt-get install -y "$@"
}

# ---------- Individual installers ----------
# Each installer is only invoked when the tool is missing. Installers return
# non-zero on any failed step (they run inside an `if`, which disables -e).

# AWS CLI Team public key, from
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
AWS_CLI_PGP_KEY='-----BEGIN PGP PUBLIC KEY BLOCK-----

mQINBF2Cr7UBEADJZHcgusOJl7ENSyumXh85z0TRV0xJorM2B/JL0kHOyigQluUG
ZMLhENaG0bYatdrKP+3H91lvK050pXwnO/R7fB/FSTouki4ciIx5OuLlnJZIxSzx
PqGl0mkxImLNbGWoi6Lto0LYxqHN2iQtzlwTVmq9733zd3XfcXrZ3+LblHAgEt5G
TfNxEKJ8soPLyWmwDH6HWCnjZ/aIQRBTIQ05uVeEoYxSh6wOai7ss/KveoSNBbYz
gbdzoqI2Y8cgH2nbfgp3DSasaLZEdCSsIsK1u05CinE7k2qZ7KgKAUIcT/cR/grk
C6VwsnDU0OUCideXcQ8WeHutqvgZH1JgKDbznoIzeQHJD238GEu+eKhRHcz8/jeG
94zkcgJOz3KbZGYMiTh277Fvj9zzvZsbMBCedV1BTg3TqgvdX4bdkhf5cH+7NtWO
lrFj6UwAsGukBTAOxC0l/dnSmZhJ7Z1KmEWilro/gOrjtOxqRQutlIqG22TaqoPG
fYVN+en3Zwbt97kcgZDwqbuykNt64oZWc4XKCa3mprEGC3IbJTBFqglXmZ7l9ywG
EEUJYOlb2XrSuPWml39beWdKM8kzr1OjnlOm6+lpTRCBfo0wa9F8YZRhHPAkwKkX
XDeOGpWRj4ohOx0d2GWkyV5xyN14p2tQOCdOODmz80yUTgRpPVQUtOEhXQARAQAB
tCFBV1MgQ0xJIFRlYW0gPGF3cy1jbGlAYW1hem9uLmNvbT6JAlQEEwEIAD4CGwMF
CwkIBwIGFQoJCAsCBBYCAwECHgECF4AWIQT7Xbd/1cEYuAURraimMQrMRnJHXAUC
akV0ygUJDqP4lQAKCRCmMQrMRnJHXFHjD/9eyZLYcKuQOlLvtqSDtUBiEZf6ZZjM
i3ygYH8rJNtuToUH+HvSpe819urJCquXhDrlK6N+aqW0hCLtNABJG/vsafIgvIYJ
hSGgpgtNnQyMV1jViRWqPjbouw8OkYKBThUfT1i2Y+wn58ifs6ODBCmTexWtXspA
Si+Gt49xDOW0APmbOPnI+a4HJW6tVEo6MWS0WjzpiBayR3d1A4pt4YrPfSdDgpLo
h2SLQqlRqvvVZJaWBjhkErNFpfsBA06sDcPEOb0G8LBUbR4WOcdvhe5LubJbZuxC
AG9kNPCVeQP1ixwjgjXKysaxeQ6rv0VzIQgRp6tLVLWhy6AKDNvLjFSsmXZ1Wl08
Y/RlOHXlzLuQMRE6sR1wOdRxc9TsrNWTGiBK65cvSWOy03JeBkQQ8pesqltiyxI9
U21kkgiXtTSKNGfKK8pO27D81YANhRqPK7iTp6kuFiY2WtOg90KTMNlIT+Ff85Y2
b1rHj6Z0SrCkJujhWk3IBPic/wJgz01LEc/OAdUPlby90RJZcIBhSlWhT7mXnXIO
c0HWlNQrns2s3CTyYwZSiSlYe9ApeLwhjDo8NhbFuCAy61l6O5UsR4AfZxx/rGKv
2wFb1/RN/P4gNe6vmxZAPjR0AQcwD3tc2McimOLr/22kmPz8IH3I0X7WoSFr0Biz
E91G7bb0hOb/cA==
=knv7
-----END PGP PUBLIC KEY BLOCK-----'

install_aws() {
  case "${PKG_MANAGER}" in
    brew) brew install awscli ;;
    apt)
      local tmp; tmp="$(mktemp -d)"
      local arch; arch="$(uname -m)"
      local url="https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip"
      local rc=0
      {
        apt_install curl gnupg unzip &&
        curl -fsSL "${url}" -o "${tmp}/awscliv2.zip" &&
        curl -fsSL "${url}.sig" -o "${tmp}/awscliv2.sig" &&
        mkdir -m 700 "${tmp}/gnupg" &&
        printf '%s\n' "${AWS_CLI_PGP_KEY}" | gpg --homedir "${tmp}/gnupg" --quiet --import &&
        gpg --homedir "${tmp}/gnupg" --quiet --verify "${tmp}/awscliv2.sig" "${tmp}/awscliv2.zip" &&
        (cd "${tmp}" && unzip -q awscliv2.zip && sudo ./aws/install --update)
      } || rc=1
      rm -rf "${tmp}"
      return "${rc}"
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
      apt_install gnupg software-properties-common curl &&
      curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg &&
      echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null &&
      APT_UPDATED=false &&
      apt_install terraform
      ;;
  esac
}

install_kubectl() {
  case "${PKG_MANAGER}" in
    brew) brew install kubectl ;;
    apt)
      local arch; arch="$(uname -m)"; [ "${arch}" = "x86_64" ] && arch="amd64"; [ "${arch}" = "aarch64" ] && arch="arm64"
      local ver; ver="$(curl -fsSL https://dl.k8s.io/release/stable.txt)" || return 1
      local tmp; tmp="$(mktemp -d)"
      local rc=0
      {
        curl -fsSL "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl" -o "${tmp}/kubectl" &&
        curl -fsSL "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl.sha256" -o "${tmp}/kubectl.sha256" &&
        (cd "${tmp}" && echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check --quiet) &&
        sudo install -o root -g root -m 0755 "${tmp}/kubectl" /usr/local/bin/kubectl
      } || rc=1
      rm -rf "${tmp}"
      return "${rc}"
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
      local rc=0
      {
        curl -fsSL "https://get.helm.sh/helm-${ver}-linux-${arch}.tar.gz" -o "${tmp}/helm.tar.gz" &&
        curl -fsSL "https://get.helm.sh/helm-${ver}-linux-${arch}.tar.gz.sha256sum" -o "${tmp}/helm.tar.gz.sha256sum" &&
        (cd "${tmp}" && sed "s|helm-${ver}-linux-${arch}.tar.gz|helm.tar.gz|" helm.tar.gz.sha256sum | sha256sum --check --quiet) &&
        tar -xzf "${tmp}/helm.tar.gz" -C "${tmp}" &&
        sudo install -o root -g root -m 0755 "${tmp}/linux-${arch}/helm" /usr/local/bin/helm
      } || rc=1
      rm -rf "${tmp}"
      return "${rc}"
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
