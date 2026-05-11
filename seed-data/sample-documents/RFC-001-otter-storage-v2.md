# RFC-001: Migrate File Service to Otter Storage v2

| Field | Value |
|-------|-------|
| **Author** | Marina Enhydra |
| **Status** | Published |
| **Created** | 2025-03-10 |
| **Last Updated** | 2026-04-28 |
| **Reviewers** | Ollie Lutris, River Canadensis, Dam Sanfilippo |

## Summary

Migrate the file storage backend from a single-bucket S3 architecture to a multi-tier "Otter Storage v2" system with intelligent lifecycle management.

## Motivation

Our current setup stores all files in a single S3 Standard bucket (`otterworks-files`). With 245 files totaling 86+ GB and growing 15% month-over-month, storage costs are becoming significant. Analysis shows:

- 68% of files haven't been accessed in 30+ days
- 23% haven't been accessed in 90+ days
- Only 9% of files are accessed daily

Otters cache their favorite rocks -- we should cache our favorite files similarly.

## Proposed Design

### Storage Tiers

| Tier | Storage Class | Access Pattern | Transition Rule |
|------|--------------|----------------|-----------------|
| Hot | S3 Standard | Accessed in last 30 days | Default for new uploads |
| Warm | S3 Standard-IA | 30-90 days since last access | Automatic lifecycle rule |
| Cold | S3 Glacier Instant | 90+ days since last access | Automatic lifecycle rule |
| Archive | S3 Glacier Deep Archive | 365+ days, compliance hold | Manual or policy-based |

### Access Tracking

Add a DynamoDB `last_accessed_at` field to `otterworks-file-metadata`. Updated on every download or preview request via an async SQS consumer to avoid adding latency to the read path.

### Retrieval from Cold Storage

Files in Glacier Instant Retrieval are accessible within milliseconds. For Deep Archive, the file-service returns a 202 Accepted with a retrieval job ID. The notification-service sends an alert when the file is ready.

## Cost Analysis

| Scenario | Monthly Cost (Current) | Monthly Cost (v2) | Savings |
|----------|----------------------|-------------------|---------|
| 100 GB | $2.30 | $1.38 | 40% |
| 500 GB | $11.50 | $6.21 | 46% |
| 1 TB | $23.00 | $11.85 | 48% |

## Migration Plan

1. Deploy lifecycle rules to existing bucket (no data movement needed)
2. Add `last_accessed_at` tracking to file-service
3. Backfill `last_accessed_at` from CloudTrail S3 data events
4. Enable retrieval-from-cold flow in file-service
5. Monitor for 2 weeks, then enable Glacier Deep Archive tier

## Risks

- **Cold file latency**: Mitigated by using Glacier Instant Retrieval for warm-to-cold transition
- **Restore costs**: Deep Archive restores billed per GB; monitor via CloudWatch billing alerts
- **Compliance**: Files under legal hold must remain in Standard; add metadata tag `compliance_hold=true`

## Decision

Approved by architecture review on 2025-04-15. Implementation tracked in Project Riverbank.
