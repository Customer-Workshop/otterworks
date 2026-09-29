#!/usr/bin/env bash
# Pod-IP capacity of the cluster's node subnets, per availability zone.
#
# The VPC CNI runs with prefix delegation (ENABLE_PREFIX_DELEGATION=true): every pod IP comes from a /28 that
# must be free *as a contiguous block* in the ENI's subnet. A /24 node subnet with dozens of free addresses can
# still hold zero free /28 blocks once node primary IPs and load-balancer ENIs are scattered through it; a node
# launched into such a subnet registers Ready but cannot give any pod an address (FailedCreatePodSandBox
# "aws-cni ... failed to assign an IP address", pods stuck ContainerCreating). Subnet discovery
# (ENABLE_SUBNET_DISCOVERY=true) lets ipamd put secondary ENIs into any same-AZ subnet tagged
# kubernetes.io/role/cni=1, so the private subnets of the VPC (no nodes, no load balancers) carry the pod IPs.
#
#   usage: pod-ip-capacity.sh              print free /28 blocks per AZ (node subnets + CNI subnets)
#          pod-ip-capacity.sh --check      same, exit 1 if any node AZ has no free /28 block at all
#          pod-ip-capacity.sh --ensure     tag the VPC's private subnets kubernetes.io/role/cni=1, then --check
# Node subnets are the ones Karpenter discovers (karpenter.sh/discovery=<cluster>) plus those of the current nodes.
source "$(dirname "$0")/lib.sh"
MODE="${1:-}"
[[ -z "${MODE}" || "${MODE}" = --check || "${MODE}" = --ensure ]] || die "usage: pod-ip-capacity.sh [--check|--ensure]" 2
command -v python3 >/dev/null || { log "pod-ip-capacity: python3 missing, skipping"; exit 0; }
ensure_kubeconfig

VPC_ID="$(kubectl -n kube-system get ds aws-node -o jsonpath='{.spec.template.spec.containers[?(@.name=="aws-node")].env[?(@.name=="VPC_ID")].value}' 2>/dev/null || true)"
[ -n "${VPC_ID}" ] || VPC_ID="$(aws ec2 describe-vpcs --region "${AWS_REGION}" --filters "Name=tag:kubernetes.io/cluster/${CLUSTER_NAME},Values=shared,owned" --query 'Vpcs[0].VpcId' --output text)"
[ -n "${VPC_ID}" ] && [ "${VPC_ID}" != None ] || die "cannot find the VPC of ${CLUSTER_NAME}"

if [ "${MODE}" = --ensure ]; then
  PRIVATE="$(aws ec2 describe-subnets --region "${AWS_REGION}" --filters "Name=vpc-id,Values=${VPC_ID}" "Name=tag:kubernetes.io/role/internal-elb,Values=1" \
              --query 'Subnets[?MapPublicIpOnLaunch==`false`].SubnetId' --output text)"
  [ -n "${PRIVATE}" ] || die "no private subnets in ${VPC_ID} to tag for the CNI"
  # shellcheck disable=SC2086
  aws ec2 create-tags --region "${AWS_REGION}" --resources ${PRIVATE} --tags Key=kubernetes.io/role/cni,Value=1
  log "pod-ip-capacity: tagged kubernetes.io/role/cni=1 on ${PRIVATE//$'\t'/ }"
fi

SUBNETS_JSON="$(aws ec2 describe-subnets --region "${AWS_REGION}" --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'Subnets[].{id:SubnetId,cidr:CidrBlock,az:AvailabilityZone,free:AvailableIpAddressCount,tags:Tags}' --output json)"
NODE_SUBNETS="$(kubectl get nodes -o jsonpath='{range .items[*]}{.spec.providerID}{"\n"}{end}' | awk -F/ 'NF{print $NF}' | paste -sd, -)"
NODE_ENIS_JSON="[]"
[ -n "${NODE_SUBNETS}" ] && NODE_ENIS_JSON="$(aws ec2 describe-instances --region "${AWS_REGION}" --instance-ids ${NODE_SUBNETS//,/ } \
  --query 'Reservations[].Instances[].NetworkInterfaces[?Attachment.DeviceIndex==`0`].SubnetId' --output json 2>/dev/null || echo '[]')"
ENIS_JSON="$(aws ec2 describe-network-interfaces --region "${AWS_REGION}" --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'NetworkInterfaces[].{subnet:SubnetId,ips:PrivateIpAddresses[].PrivateIpAddress,prefixes:Ipv4Prefixes[].Ipv4Prefix}' --output json)"

python3 - "${CLUSTER_NAME}" "${MODE}" "${SUBNETS_JSON}" "${NODE_ENIS_JSON}" "${ENIS_JSON}" <<'PY'
import ipaddress, json, sys
cluster, mode, subnets, node_enis, enis = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]), json.loads(sys.argv[5])
used = {}
for e in enis:
    used.setdefault(e["subnet"], set()).update(ipaddress.ip_address(i) for i in e["ips"])
    for p in e.get("prefixes") or []:
        used[e["subnet"]].update(ipaddress.ip_network(p))
node_subnet_ids = {s for group in node_enis for s in group}
zones, bad = {}, []
for s in subnets:
    tags = {t["Key"]: t["Value"] for t in (s["tags"] or [])}
    role = ("node" if tags.get("karpenter.sh/discovery") == cluster or s["id"] in node_subnet_ids else
            "cni" if tags.get("kubernetes.io/role/cni") == "1" else None)
    if not role:
        continue
    net = ipaddress.ip_network(s["cidr"])
    reserved = {net[0], net[1], net[2], net[3], net[-1]}
    taken = used.get(s["id"], set()) | reserved
    blocks = sum(1 for b in net.subnets(new_prefix=28) if not any(a in taken for a in b))
    zones.setdefault(s["az"], []).append((role, s["cidr"], s["free"], blocks))
for az in sorted(zones):
    rows = sorted(zones[az])
    total = sum(b for _, _, _, b in rows)
    print(f"{az}: {total} free /28 pod-IP block(s)  " + ", ".join(f"{r} {c} free_ips={f} free_/28={b}" for r, c, f, b in rows))
    if total == 0 and any(r == "node" for r, _, _, _ in rows):
        bad.append(az)
    if not any(r == "cni" for r, _, _, _ in rows) and any(r == "node" for r, _, _, _ in rows):
        print(f"   WARNING {az}: no subnet tagged kubernetes.io/role/cni=1 — run pod-ip-capacity.sh --ensure")
if bad:
    print(f"ERROR: no free /28 block for pods in {', '.join(bad)}: new nodes there cannot start pods "
          f"(FailedCreatePodSandBox aws-cni 'failed to assign an IP address'); run pod-ip-capacity.sh --ensure", file=sys.stderr)
    sys.exit(1 if mode else 0)
PY
