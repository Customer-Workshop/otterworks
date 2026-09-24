import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription } from 'rxjs';
import { MigrationApiService } from '../../core/services/migration-api.service';
import {
  MIG_ISSUES, ReconciliationFailureRow, ReconciliationReport, RunSummary,
} from '../../core/models/migration.model';
import { ArchiveCompareComponent } from './archive-compare.component';

export const LATEST_RUN = 'latest';

@Component({
  selector: 'app-migration',
  standalone: true,
  imports: [
    CommonModule, FormsModule, RouterModule, MatCardModule, MatIconModule, MatButtonModule,
    MatInputModule, MatFormFieldModule, MatSelectModule, MatProgressSpinnerModule, MatTooltipModule,
    ArchiveCompareComponent,
  ],
  template: `
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">Migration</h1>
          <p class="page-subtitle">Db2 → Azure SQL selective migration: row-level reconciliation and before/after archive comparison</p>
        </div>
        <div class="header-actions" *ngIf="report">
          <a mat-stroked-button [href]="api.htmlUrl(report.run_id)" target="_blank" rel="noopener">
            <mat-icon>open_in_new</mat-icon> HTML report
          </a>
          <a mat-raised-button color="primary" [href]="api.csvUrl(report.run_id)" download>
            <mat-icon>download</mat-icon> Download CSV
          </a>
        </div>
      </div>

      <mat-card class="run-card">
        <mat-card-content>
          <form class="run-form" (ngSubmit)="loadRun()">
            <mat-form-field appearance="outline" class="run-field">
              <mat-label>Run ID</mat-label>
              <input matInput name="runId" [(ngModel)]="runIdInput" placeholder="latest" />
              <mat-hint>Empty or "latest" resolves to the most recent run in this namespace</mat-hint>
            </mat-form-field>
            <mat-form-field appearance="outline" class="runs-field" *ngIf="runs.length">
              <mat-label>Known runs</mat-label>
              <mat-select name="knownRun" [(ngModel)]="runIdInput">
                <mat-option *ngFor="let r of runs" [value]="r.run_id">
                  {{ r.run_id }} · {{ r.status }}{{ r.closes ? '' : ' · open' }}
                </mat-option>
              </mat-select>
            </mat-form-field>
            <button mat-raised-button color="primary" type="submit" [disabled]="loading">
              <mat-icon>refresh</mat-icon> Load
            </button>
          </form>
        </mat-card-content>
      </mat-card>

      <div class="loading" *ngIf="loading"><mat-spinner diameter="36"></mat-spinner></div>

      <mat-card class="notice" *ngIf="error && !loading">
        <mat-icon>{{ errorStatus === 404 ? 'info' : 'error' }}</mat-icon>
        <div>
          <strong>{{ error }}</strong>
          <div class="hint" *ngIf="errorHint">{{ errorHint }}</div>
        </div>
      </mat-card>

      <ng-container *ngIf="report && !loading">
        <div class="status-row">
          <span class="badge" [class.ok]="report.closes" [class.fail]="!report.closes">
            {{ report.closes ? 'RECONCILED' : 'OPEN' }}
          </span>
          <span class="meta">run <code>{{ report.run_id }}</code></span>
          <span class="meta">namespace <code>{{ report.namespace }}</code></span>
          <span class="meta">status {{ report.status }}</span>
          <span class="meta" *ngIf="report.started_at">started {{ report.started_at }}</span>
          <span class="meta" *ngIf="report.finished_at">finished {{ report.finished_at }}</span>
          <span class="meta">generated {{ report.generated_at }}</span>
        </div>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Per-table summary</mat-card-title>
            <mat-card-subtitle>A table closes only when extracted = loaded + rejected and purged = validated</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <table class="grid">
              <thead>
                <tr>
                  <th>table</th><th class="num">extracted</th><th class="num">loaded</th><th class="num">rejected</th>
                  <th class="num">validated</th><th class="num">validate failed</th><th class="num">purged</th>
                  <th class="num">failed</th><th>purge</th><th>closes</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let t of report.tables" [class.open]="!t.closes">
                  <td><strong>{{ t.table }}</strong></td>
                  <td class="num">{{ t.extracted | number }}</td>
                  <td class="num">{{ t.loaded | number }}</td>
                  <td class="num">{{ t.rejected | number }}</td>
                  <td class="num">{{ t.validated | number }}</td>
                  <td class="num">{{ t.validate_failed | number }}</td>
                  <td class="num">{{ t.purged | number }}</td>
                  <td class="num">{{ t.failed | number }}</td>
                  <td>{{ t.purge_dry_run === null ? '—' : (t.purge_dry_run ? 'dry run' : 'live') }}</td>
                  <td>{{ t.closes ? 'yes' : 'NO' }}</td>
                </tr>
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>

        <mat-card *ngIf="report.class_totals?.length">
          <mat-card-header>
            <mat-card-title>Storage-charge totals by retention class</mat-card-title>
            <mat-card-subtitle>MIG-07: table-level totals can agree while a class total does not; class totals are the gate</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <table class="grid">
              <thead>
                <tr><th>table</th><th>class</th><th class="num">source rows</th><th class="num">target rows</th>
                  <th class="num">source sum</th><th class="num">target sum</th><th>matches</th></tr>
              </thead>
              <tbody>
                <tr *ngFor="let c of report.class_totals" [class.mig07]="!c.matches">
                  <td>{{ c.table }}</td><td><code>{{ c.class }}</code></td>
                  <td class="num">{{ c.source_count | number }}</td><td class="num">{{ c.target_count | number }}</td>
                  <td class="num"><code>{{ c.source_sum }}</code></td><td class="num"><code>{{ c.target_sum }}</code></td>
                  <td>{{ c.matches ? 'yes' : 'MISMATCH' }}</td>
                </tr>
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Failed rows ({{ filteredFailures.length }} of {{ report.failures.length }})</mat-card-title>
            <mat-card-subtitle>Failed rows stay in the source store; each carries its rejection rule and SQLSTATE or conversion error</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <div class="filters">
              <mat-form-field appearance="outline">
                <mat-label>Rule</mat-label>
                <mat-select [(ngModel)]="ruleFilter" (ngModelChange)="applyFilter()">
                  <mat-option value="">All rules</mat-option>
                  <mat-option *ngFor="let r of rules" [value]="r">{{ r }}</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Issue</mat-label>
                <mat-select [(ngModel)]="issueFilter" (ngModelChange)="applyFilter()">
                  <mat-option value="">All issues</mat-option>
                  <mat-option *ngFor="let i of issues" [value]="i">{{ i }}</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Table</mat-label>
                <mat-select [(ngModel)]="tableFilter" (ngModelChange)="applyFilter()">
                  <mat-option value="">All tables</mat-option>
                  <mat-option *ngFor="let t of report.tables" [value]="t.table">{{ t.table }}</mat-option>
                </mat-select>
              </mat-form-field>
              <div class="issue-pills">
                <span class="pill" *ngFor="let i of issueCounts | keyvalue" [class.mig07]="i.key === 'MIG-07'"
                      (click)="issueFilter = i.key; applyFilter()" role="button" tabindex="0">
                  {{ i.key }} × {{ i.value }}
                </span>
              </div>
            </div>
            <table class="grid failures" *ngIf="filteredFailures.length; else noFailures">
              <thead>
                <tr><th>table</th><th>source key</th><th>rule</th><th>stage</th><th>field</th>
                  <th>SQLSTATE</th><th>native</th><th>error</th><th>issue</th></tr>
              </thead>
              <tbody>
                <tr *ngFor="let f of filteredFailures" [class.mig07]="f.issue === 'MIG-07'">
                  <td>{{ f.table }}</td>
                  <td><code>{{ f.source_key }}</code></td>
                  <td>{{ f.rule }}</td>
                  <td>{{ f.stage }}</td>
                  <td>{{ f.field || '' }}</td>
                  <td><code>{{ f.sqlstate || '' }}</code></td>
                  <td>{{ f.native_error ?? '' }}</td>
                  <td class="err">{{ f.error }}</td>
                  <td><strong>{{ f.issue || '' }}</strong></td>
                </tr>
              </tbody>
            </table>
            <ng-template #noFailures><p class="empty">No failed rows match the filter.</p></ng-template>
          </mat-card-content>
        </mat-card>

        <mat-card>
          <mat-card-header>
            <mat-card-title>Devin sessions that produced this code</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <ul class="sessions" *ngIf="report.sessions?.length; else noSessions">
              <li *ngFor="let s of report.sessions">
                <mat-icon inline>link</mat-icon>
                <a [href]="s.url" target="_blank" rel="noopener">{{ s.label }}</a>
                <span class="url">{{ s.url }}</span>
              </li>
            </ul>
            <ng-template #noSessions><p class="empty">No session links recorded for this run.</p></ng-template>
          </mat-card-content>
        </mat-card>
      </ng-container>

      <app-archive-compare [docId]="docId" [autoLoad]="!!docId"></app-archive-compare>
    </div>
  `,
  styles: [`
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
    .header-actions { display: flex; gap: 8px; }
    .run-card { margin-bottom: 16px; }
    .run-form { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
    .run-field { min-width: 280px; }
    .runs-field { min-width: 320px; }
    .run-form button { margin-top: 6px; }
    .loading { display: flex; justify-content: center; padding: 32px; }
    .notice { display: flex; gap: 12px; align-items: center; padding: 16px; margin-bottom: 16px; }
    .notice .hint { color: #52606d; font-size: 0.85rem; margin-top: 4px; }
    .status-row { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin: 8px 0 16px; }
    .badge { padding: 6px 12px; border-radius: 4px; font-weight: 700; letter-spacing: 0.04em; }
    .badge.ok { background: #e3f9e5; color: #0f5132; }
    .badge.fail { background: #fde2e1; color: #7a1d1d; }
    .meta { color: #52606d; font-size: 0.85rem; }
    mat-card { margin-bottom: 16px; }
    table.grid { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
    table.grid th, table.grid td { border: 1px solid #d9e2ec; padding: 6px 8px; text-align: left; vertical-align: top; }
    table.grid th { background: #f0f4f8; }
    .num { text-align: right !important; font-variant-numeric: tabular-nums; }
    tr.open td { background: #fff4e5; }
    tr.mig07 td { background: #fde2e1; font-weight: 600; }
    .filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
    .issue-pills { display: flex; gap: 6px; flex-wrap: wrap; }
    .pill { background: #e4e7eb; border-radius: 12px; padding: 2px 10px; font-size: 0.8rem; cursor: pointer; }
    .pill.mig07 { background: #fde2e1; color: #7a1d1d; font-weight: 600; }
    .err { max-width: 420px; word-break: break-word; }
    .sessions { list-style: none; padding: 0; margin: 0; }
    .sessions li { display: flex; gap: 8px; align-items: center; padding: 4px 0; }
    .sessions .url { color: #52606d; font-size: 0.8rem; }
    .empty { color: #52606d; font-style: italic; }
  `],
})
export class MigrationComponent implements OnInit, OnDestroy {
  runIdInput = '';
  runs: RunSummary[] = [];
  report: ReconciliationReport | null = null;
  loading = false;
  error: string | null = null;
  errorHint: string | null = null;
  errorStatus = 0;

  ruleFilter = '';
  issueFilter = '';
  tableFilter = '';
  rules: string[] = [];
  issues: string[] = [];
  issueCounts: Record<string, number> = {};
  filteredFailures: ReconciliationFailureRow[] = [];

  docId = '';

  private sub = new Subscription();

  constructor(
    public api: MigrationApiService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.sub.add(this.route.paramMap.subscribe(params => {
      const runId = params.get('runId');
      const docId = params.get('docId');
      if (docId) {
        this.docId = docId;
      }
      this.runIdInput = runId && runId !== LATEST_RUN ? runId : '';
      this.fetch(runId || LATEST_RUN);
    }));
    this.sub.add(this.api.listRuns().subscribe({
      next: runs => (this.runs = runs),
      error: () => (this.runs = []),
    }));
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
  }

  loadRun(): void {
    const target = this.runIdInput.trim() || LATEST_RUN;
    this.router.navigate(['/migration/reconciliation', target]);
  }

  applyFilter(): void {
    if (!this.report) {
      this.filteredFailures = [];
      return;
    }
    this.filteredFailures = this.report.failures.filter(f =>
      (!this.ruleFilter || f.rule === this.ruleFilter)
      && (!this.issueFilter || f.issue === this.issueFilter)
      && (!this.tableFilter || f.table === this.tableFilter));
  }

  private fetch(runId: string): void {
    this.loading = true;
    this.error = null;
    this.errorHint = null;
    this.report = null;
    this.api.getReport(runId).subscribe({
      next: report => {
        this.report = report;
        this.loading = false;
        this.runIdInput = report.run_id;
        this.indexFailures(report);
        this.applyFilter();
      },
      error: (err: HttpErrorResponse) => {
        this.loading = false;
        this.errorStatus = err.status;
        const body = err.error;
        if (body && typeof body === 'object' && 'error' in body) {
          this.error = String(body.error);
          this.errorHint = 'hint' in body && body.hint ? String(body.hint) : null;
        } else if (err.status === 0) {
          this.error = 'Report service unreachable';
        } else {
          this.error = `Report request failed (${err.status})`;
        }
      },
    });
  }

  private indexFailures(report: ReconciliationReport): void {
    const ruleSet = new Set<string>();
    const issueSet = new Set<string>(MIG_ISSUES);
    const counts: Record<string, number> = {};
    for (const f of report.failures) {
      if (f.rule) {
        ruleSet.add(f.rule);
      }
      if (f.issue) {
        issueSet.add(f.issue);
        counts[f.issue] = (counts[f.issue] || 0) + 1;
      }
    }
    this.rules = [...ruleSet].sort();
    this.issues = [...issueSet].sort();
    this.issueCounts = counts;
  }
}
