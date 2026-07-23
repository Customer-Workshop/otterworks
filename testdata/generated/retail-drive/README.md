# RetailCo Enterprise Drive — synthetic app-data seed

Populates a **large-retail enterprise file system** into a live OtterWorks
deployment so the web UI shows a deep, realistic, browsable drive: ~15
departments as top-level folders, a nested subfolder tree (3–4 levels), a
multi-format file corpus (xlsx/docx/pptx/pdf/csv/txt/md/json/png/jpg), and
rich-text documents.

Unlike the schema-based harness in `testdata/generated/seed` / `.../golden`
(which writes relational rows into an `otterworks_<ns>` **schema**), this seed
creates **real application data through the public API gateway**:

| Resource | Service | Backing store |
|----------|---------|---------------|
| Folders  | file-service `/api/v1/folders` | DynamoDB (folders table) |
| Files    | file-service `/api/v1/files/upload` | DynamoDB (metadata) + S3 (bytes) |
| Documents| document-service `/api/v1/documents` | Postgres `public` |

All resources are owned by one shared account (`drive@retailco.example`) so the
result is a single enterprise drive. The data is **synthetic** — no real people,
customers, or PII.

## Files

- `taxonomy.py` — the department/subfolder/file-template definition (data-driven;
  templates expand over years, quarters, regions, stores, vendors, campaigns,
  categories). Edit this to reshape the drive.
- `filegen.py` — produces real, openable bytes for each file type.
- `generate_drive.py` — logs in, walks the taxonomy for the requested
  departments, creates folders/files/documents. **Idempotent** (skips folders,
  files, and documents that already exist) and **shardable** by department.

## Run

```bash
pip install -r requirements.txt

# preview volume (nothing written)
python generate_drive.py --gateway http://<gw> --email x --password x \
    --departments all --scale 1.0 --dry-run

# populate one department (shard) ...
python generate_drive.py --gateway http://<gw-host>:8080 \
    --email drive@retailco.example --password "$DRIVE_PASSWORD" \
    --departments Finance --scale 1.0 --workers 6

# ... or the whole drive
python generate_drive.py --gateway http://<gw-host>:8080 \
    --email drive@retailco.example --password "$DRIVE_PASSWORD" \
    --departments all --scale 1.0
```

`--scale` multiplies per-axis breadth (default `1.0` ≈ 2,400 files across 15
departments). Because every department is an independent top-level subtree and
the generator is idempotent, the work fans out safely across many parallel
workers/sessions all writing under the same owner.

## Seed-loader integration

`seed-loader.job.yaml` is a Kubernetes Job that runs this generator against the
in-cluster gateway (`api-gateway.<ns>.svc.cluster.local:8080`) on demand /
after a spin-up, mirroring the golden reference-data loader. It reads the drive
credentials from the `retail-drive-seed` Secret and passes `--register` so it
bootstraps the account on a fresh environment. See the job manifest for details.
