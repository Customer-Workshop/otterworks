# Databricks serverless egress and Oracle connectivity findings

Date of research: 2026-09-14

This is a read-only research artifact. No Oracle, Databricks, Lakebase, NCC,
PrivateLink, firewall, or cloud-resource writes were performed.

## Executive summary

- The workspace hostname is `dbc-8bc9474f-40ae.cloud.databricks.com`.
- DNS resolves the workspace through an AWS load balancer in `us-west-2`.
  Therefore, `us-west-2` is the workspace-region determination used below.
  This is DNS evidence and an inference from the AWS region in the canonical
  name, not a direct workspace-region field returned by the CLI.
- For serverless compute accessing non-S3/non-DynamoDB resources, Databricks'
  current documented method is to allowlist the region-specific CIDRs in its
  published `ip-ranges.json`. These are not permanent one-time static values:
  Databricks says the list changes over time and customers must automate
  updates.
- The current `us-west-2` AWS Databricks outbound CIDRs observed in the
  published JSON are:
  `18.246.106.0/24`, `3.42.138.0/25`, `44.234.192.32/28`, and
  `52.27.216.188/32`.
- The legacy NCC/UI/API stable-IP list is decommissioned. NCC remains an
  account-level, regional mechanism for private endpoint connectivity; it is
  not required for the public outbound-CIDR allowlist method.
- Oracle is supported by Lakehouse Federation, including Pro and serverless
  SQL warehouses, subject to the documented runtime and network requirements.
  Oracle is also supported by Lakeflow Connect's integrated CDC connector and
  its query-based connectors. The premise that Oracle is not a federation
  connector is contradicted by the current Databricks documentation.

## 1. Workspace region evidence

Host-only value inspected from `$DATABRICKS_DEMO_HOST`:

```text
dbc-8bc9474f-40ae.cloud.databricks.com
```

DNS lookup result:

```text
dbc-8bc9474f-40ae.cloud.databricks.com.
  oregon.cloud.databricks.com.
  public-ingress-a84df8d06aede39e.elb.us-west-2.amazonaws.com.
  44.234.192.46
  44.234.192.47
  44.234.192.45
```

The `us-west-2` region in the AWS ELB canonical name is the direct evidence
used to infer the workspace region. A header-only request to the host returned
HTTP 404 and did not expose an `X-Databricks-Region` header; no secret or token
was printed. The Lakebase host observed in the earlier probe is also in
`us-west-2`, which is corroborating context but not the primary evidence.

## 2. Authoritative serverless egress documentation

### Serverless firewall configuration

URL:
<https://docs.databricks.com/aws/en/security/network/serverless-network-security/serverless-firewall-config>

Relevant Databricks statements:

> “For resources other than Amazon S3 or Amazon DynamoDB in the same region as
> your workspace, serverless compute uses public IP addresses to reach your
> resources.”

> “To allow serverless to access resources with firewalls, you must add the CIDR
> blocks published by Databricks to your allowlist.”

The page instructs customers to download
<https://www.databricks.com/networking/v1/ip-ranges.json> and retain entries
where:

- `service` is `Databricks`;
- `type` is `outbound`;
- `region` matches the workspace region; and
- `platform` is `aws`.

It then says to allowlist the matching `ipv4Prefixes`. The page explicitly
requires automation:

> “You must automate updates to your allowlist. Databricks changes these IPs
> over time, so a static, one-time copy eventually breaks serverless
> connectivity.”

It further states that updates can publish as often as every 30 days and new
IPs can become active as soon as 60 days after publication. Thus these are
published per-region outbound CIDRs, but they should not be treated as
permanent static addresses.

The same page says that dedicated private connectivity is a separate option:

> “If you require dedicated, private connectivity to your resources, use an
> outbound Private Link connection to reach your resource instead of
> allowlisting IP addresses.”

### Published `ip-ranges.json` result for `us-west-2`

URL:
<https://www.databricks.com/networking/v1/ip-ranges.json>

Observed top-level `timestampSeconds`:

```text
1788759480 (2026-09-07T05:38:00Z)
```

The matching entry had `platform=aws`, `region=us-west-2`,
`service=Databricks`, `type=outbound`, and no IPv6 prefixes:

```json
{
  "ipv4Prefixes": [
    "18.246.106.0/24",
    "3.42.138.0/25",
    "44.234.192.32/28",
    "52.27.216.188/32"
  ],
  "ipv6Prefixes": [],
  "platform": "aws",
  "region": "us-west-2",
  "service": "Databricks",
  "type": "outbound"
}
```

These are the addresses to provide to the owner of a firewall or security
group protecting the custom Oracle endpoint, subject to the update automation
requirement above. This research did not modify that firewall or test Oracle
reachability from serverless.

### NCC and legacy stable IPs

URL:
<https://docs.databricks.com/aws/en/security/network/serverless-network-security/>

The current networking page states:

> “Serverless network connectivity is managed with network connectivity
> configurations (NCCs). NCCs are account-level regional constructs that manage
> private endpoint creation.”

It also states:

> “The legacy list of stable IPs from the Public Preview was decommissioned and
> is no longer available through the NCC UI or Network Connectivity API.”

Therefore, an old NCC/UI/API stable-IP list must not be used as the current
source of public serverless egress addresses. The supported public-firewall
source is the Databricks-published JSON above.

## 3. PrivateLink/NCC and account-admin requirements

URL:
<https://docs.databricks.com/aws/en/security/network/serverless-network-security/pl-to-internal-network>

For private connectivity from serverless compute to a customer VPC, the
documented requirements include:

> “The workspace is on the Enterprise plan.”

> “You are the account admin of your Databricks account.”

The page also documents that this path uses PrivateLink to an NLB/VPC endpoint
service. Consequently:

- PrivateLink/NCC is **not required** merely to allowlist the published public
  serverless egress CIDRs.
- PrivateLink/NCC **is required as the relevant path** when the customer
  chooses dedicated private connectivity to a VPC resource.
- The documented private-connectivity setup requires an account admin and the
  Enterprise plan. NCCs are account-level and regional, and an account admin
  attaches them to workspaces.

## 4. Lakehouse Federation and Oracle

### Oracle is a supported Lakehouse Federation connector

URL:
<https://docs.databricks.com/aws/en/query-federation/database-federation>

The supported-source list explicitly includes:

> “MySQL”
>
> “PostgreSQL”
>
> “Teradata”
>
> “Oracle”
>
> “Amazon Redshift”
>
> “Salesforce Data 360”
>
> “Snowflake”
>
> “Microsoft SQL Server”
>
> “Azure Synapse (SQL Data Warehouse)”
>
> “Google BigQuery”
>
> “Databricks”

The same page says query federation uses JDBC and provides read-only querying
through a Unity Catalog foreign catalog. Its compute requirements include Pro
or serverless SQL warehouses (2023.40 or above) and network connectivity to
the target database.

Oracle-specific documentation:
<https://docs.databricks.com/aws/en/query-federation/oracle>

The Oracle page says:

> “This page describes how to set up Lakehouse Federation to run federated
> queries on Oracle data that is not managed by Databricks.”

It requires network connectivity from compute to the target database and says
SQL warehouses must be Pro or serverless (2024.50 or above). It also documents
Oracle-specific encryption requirements: TLS for Oracle Cloud and Native
Network Encryption (NNE) for other Oracle databases.

### Public-internet Oracle connectivity

URL:
<https://docs.databricks.com/aws/en/query-federation/networking>

Databricks' networking recommendations state:

> “Databricks compute (that is, clusters and SQL warehouses) always deploys in
> the cloud, but the external database system can be on-premises or hosted on
> any cloud provider, as long as there's a viable network path between your
> Databricks compute and the external database.”

They also state:

> “The connection should work without any configuration.”

That statement is under the case where both the database system and Databricks
compute are accessible from the internet. For a firewall-restricted Oracle
host, the same page points serverless compute users to the published outbound
IPs. Therefore, a custom Oracle host over the public internet is a documented
supported topology when the Oracle listener is reachable, the required Oracle
encryption mode is configured, and the Oracle-side firewall allowlists the
current `us-west-2` serverless CIDRs. This probe did not attempt a serverless
query and does not establish reachability of `52.201.36.9`.

## 5. Lakeflow Connect and query-based connectors

### Oracle integrated CDC connector

URL:
<https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/oracle-concepts>

The page describes an Oracle integrated CDC connector using JDBC:

> “Databricks connects to Oracle using a JDBC connection.”

It supports Oracle on cloud infrastructure, including Amazon RDS for Oracle
and Oracle on Amazon EC2, as well as on-premises Oracle over Direct Connect,
ExpressRoute, or VPN when sufficient bandwidth is available. It also states:

> “In addition to the Oracle integrated CDC connector in Lakeflow Connect,
> Databricks offers a zero-copy connector in Lakehouse Federation.”

The integrated CDC connector is a different path from read-only query
federation: it reads Oracle redo/archive logs using LogMiner and ingests
changes into Databricks.

### Query-based connectors

URL:
<https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/query-based-overview>

The page says query-based connectors query the source directly on a schedule
using a cursor column, and:

> “Query-based connectors use Unity Catalog connections and Lakehouse
> Federation to connect to source databases, and they write results to
> streaming tables.”

The supported foreign-connection sources are explicitly:

- Oracle
- Teradata
- SQL Server
- MySQL
- MariaDB
- PostgreSQL

The same page says query-based pipelines run on serverless compute by default.
Thus Oracle is supported both as a direct query-based Lakeflow Connect source
and as a foreign catalog source through Lakehouse Federation.

## 6. Read-only NCC API availability probe

Only help and list/read operations were attempted. No create, update, delete,
NCC attachment, or private endpoint operation was invoked.

Command:

```bash
env -u DATABRICKS_CLIENT_ID -u DATABRICKS_CLIENT_SECRET \
  DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" \
  DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" \
  databricks account network-connectivity --help
```

The installed CLI advertised these relevant read commands:

```text
get-network-connectivity-configuration
list-network-connectivity-configurations
list-private-endpoint-rules
```

Command attempted:

```bash
env -u DATABRICKS_CLIENT_ID -u DATABRICKS_CLIENT_SECRET \
  DATABRICKS_HOST="$DATABRICKS_DEMO_HOST" \
  DATABRICKS_TOKEN="$DATABRICKS_DEMO_TOKEN" \
  databricks account network-connectivity \
  list-network-connectivity-configurations -o json
```

Result:

```text
Error: Not Found
Exit code: 1
```

This means the account-level list command was not available at the configured
workspace endpoint in this session. It was not interpreted as evidence that
NCCs do or do not exist in the account. The result is consistent with the
current documentation's statement that the legacy stable-IP list is no longer
available through the Network Connectivity API.

## 7. Safety and scope

- No secret values, PATs, Oracle passwords, or generated Lakebase credentials
  were printed in this research.
- No writes were performed against Oracle, Databricks, Lakebase, NCC,
  PrivateLink, firewalls, security groups, or other cloud resources.
- No serverless workload was started and no connectivity test was run against
  the Oracle endpoint.
