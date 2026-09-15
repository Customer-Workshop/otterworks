# 02_glossary — OtterWorks terms in plain words

| Term | Meaning |
|---|---|
| CUSTBILL | The month-end finance close chain: an SFTP poller, a fixed-width parser, and a report writer. Named after the fixed-width file it consumes. |
| Dunning | Chasing unpaid invoices. `pkg_dunning` escalates through attempt levels and writes `DUNNING_ATTEMPTS`. |
| Rating | Turning raw usage events into priced amounts. `pkg_rating` writes `RATING_RESULTS` per `RATING_PERIODS` window. |
| Overage | Usage above what the plan includes, priced at the plan's overage rate. |
| EAV overflow | `ENTITY_ATTR_VALUE` — key/value rows holding attributes that never got columns on `CUSTOMER_MASTER`. |
| `_HIST` twin | A shadow table written by a trigger to keep row history. The Delta target replaces it with SCD-2. |
| Tenant | A customer account. The unit of isolation for billing and for the new usage meter. |
| Close cycle | One month-end run of the finance close, start to finished report. |
| AR ageing | Accounts-receivable buckets by how overdue an invoice is. |
| ARR / MRR | Annual / monthly recurring revenue. |
| Anomaly set | The known-bad rows (orphan invoice lines, unparseable dates, malformed CSV lists) that the migration must reproduce exactly rather than clean up. |
| Live window | The single granted read against the real source that a unit gets for its merge-authority recon. |
| STOP E | The blocking human authorization before cutover. Never default-accepted. |
