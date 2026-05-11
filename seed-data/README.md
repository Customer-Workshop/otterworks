# OtterWorks Seed Data

Development seed data for populating the OtterWorks platform with realistic, otter-themed engineering organization content.

## Directory Structure

```
seed-data/
  postgres/          SQL scripts for Postgres-backed services (auth, document)
  dynamodb/          JSON items for DynamoDB tables (files, audit, notifications)
  analytics/         CSV datasets for analytics, metrics, and reporting
  opensearch/        Bulk-index payloads for the search service
  events/            Sample SNS/SQS event bus messages
  sample-documents/  Markdown docs an engineering org would actually have
```

## Quick Load

```bash
# From the repo root (services must be running)
./scripts/seed-data.sh
```

The loader script is idempotent — it uses `ON CONFLICT DO NOTHING` for SQL and `ConditionExpression` for DynamoDB puts.

## Otter-Themed Naming Convention

| Concept | Convention | Examples |
|---------|-----------|----------|
| Teams | River features | River Runners, Dam Builders, Kelp Weavers |
| Departments | Otter habitats | The Lodge (Eng), The Raft (Product), The Den (Design) |
| Projects | Aquatic codenames | Project Riverbank, Operation Kelp Forest |
| Users | Otter species + tech names | Ollie Lutris, Marina Enhydra, Finn Aonyx |

## Data Volume

| Resource | Count | Notes |
|----------|-------|-------|
| Users | 25 | Across 6 departments, 4 roles |
| Documents | 30 | RFCs, ADRs, runbooks, meeting notes |
| Files | 40 | Uploads across all folders |
| Folders | 12 | Team-organized hierarchy |
| Audit events | 60 | 2 weeks of activity |
| Notifications | 35 | Mix of read/unread |
| Analytics rows | 500+ | 6 months of daily activity |
| Search entries | 40 | Pre-indexed documents and files |
| Event bus msgs | 20 | SNS/SQS samples |
