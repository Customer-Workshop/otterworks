import { Component, Input, OnChanges, OnInit, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { MigrationApiService } from '../../core/services/migration-api.service';
import {
  ArchiveDocument, ArchiveEvent, ArchiveHash, ArchivePolicy as RetentionPolicy, ArchiveVersion,
} from '../../core/models/migration.model';

export interface ArchiveSide {
  label: string;
  baseUrl: string;
  loading: boolean;
  error: string | null;
  document: ArchiveDocument | null;
  hash: ArchiveHash | null;
}

export type CellKey = keyof ArchiveVersion | keyof ArchiveEvent;

/**
 * "Before / After" panel: the same archived document fetched from this deployment and from the
 * peer deployment (PEER_APP_URL), rendered side by side with per-field mismatch highlighting.
 */
@Component({
  selector: 'app-archive-compare',
  standalone: true,
  imports: [
    CommonModule, FormsModule, MatCardModule, MatIconModule, MatButtonModule, MatInputModule,
    MatFormFieldModule, MatProgressSpinnerModule, MatTooltipModule,
  ],
  template: `
    <mat-card class="compare-card">
      <mat-card-header>
        <mat-card-title><mat-icon>compare</mat-icon> Before / After: archived document</mat-card-title>
        <mat-card-subtitle>
          Retention history and audit trail must be byte-identical across the two deployments
        </mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <form class="compare-form" (ngSubmit)="load()">
          <mat-form-field appearance="outline" class="doc-field">
            <mat-label>Document ID</mat-label>
            <input matInput name="docId" [(ngModel)]="docId" placeholder="DOC-000000000042" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="peer-field">
            <mat-label>Peer deployment (PEER_APP_URL)</mat-label>
            <input matInput name="peerUrl" [value]="peerUrl" readonly placeholder="not configured" />
            <mat-hint *ngIf="!peerUrl">No peer configured: only this deployment is shown</mat-hint>
            <mat-hint *ngIf="peerUrl">Set by the operator at deploy time; the session token is only sent to this host</mat-hint>
          </mat-form-field>
          <button mat-raised-button color="primary" type="submit" [disabled]="!docId || loading">
            <mat-icon>search</mat-icon> Compare
          </button>
        </form>

        <div class="verdict" *ngIf="verdict" [class.match]="verdict === 'match'" [class.mismatch]="verdict === 'mismatch'"
             [class.unknown]="verdict === 'unknown'">
          <mat-icon>{{ verdict === 'match' ? 'verified' : verdict === 'mismatch' ? 'error' : 'help' }}</mat-icon>
          <span *ngIf="verdict === 'match'">Identical: {{ hashSummary }}</span>
          <span *ngIf="verdict === 'mismatch'">Differences found: {{ mismatchCount }} field(s) differ; {{ hashSummary }}</span>
          <span *ngIf="verdict === 'unknown'">Not proven identical: {{ hashSummary }}</span>
        </div>

        <div class="sides">
          <section class="side" *ngFor="let side of sides; let i = index">
            <h3>
              {{ side.label }}
              <span class="store" *ngIf="side.document">{{ side.document.store }}</span>
              <span class="base" *ngIf="side.baseUrl">{{ side.baseUrl }}</span>
              <span class="base" *ngIf="!side.baseUrl">this deployment</span>
            </h3>
            <mat-spinner diameter="28" *ngIf="side.loading"></mat-spinner>
            <p class="error" *ngIf="side.error">{{ side.error }}</p>
            <ng-container *ngIf="side.document as doc">
              <p class="hash" *ngIf="side.hash">
                <mat-icon inline>fingerprint</mat-icon>
                <code>{{ side.hash.document_hash }}</code>
              </p>
              <div class="version" *ngFor="let v of doc.versions; let vi = index" [class.missing]="versionMissing(vi)">
                <h4>
                  Version {{ v.version_no }} <code>{{ v.arch_key }}</code>
                  <span class="missing-tag" *ngIf="versionMissing(vi)">missing on other side</span>
                </h4>
                <table class="kv">
                  <tr *ngFor="let f of versionFields" [class.diff]="differs(vi, f)">
                    <th>{{ f }}</th>
                    <td><code>{{ v[f] }}</code></td>
                  </tr>
                  <tr *ngIf="v.policy" [class.diff]="policyDiffers(vi)">
                    <th>policy</th>
                    <td>{{ v.policy.policy_code }} · {{ v.policy.policy_desc }} · {{ v.policy.retention_years }}y · {{ v.policy.disposition_action }}</td>
                  </tr>
                </table>
                <table class="events" *ngIf="v.events?.length">
                  <thead>
                    <tr><th>event_ts</th><th>type</th><th>actor</th><th>disp</th><th>client_ip</th><th>detail</th></tr>
                  </thead>
                  <tbody>
                    <tr *ngFor="let e of v.events; let ei = index" [class.diff]="eventDiffers(vi, ei)">
                      <td><code>{{ e.event_ts }}</code></td>
                      <td>{{ e.event_type }}</td>
                      <td><code>{{ e.actor_id }}</code></td>
                      <td>{{ e.disposition_code }}</td>
                      <td>{{ e.client_ip }}</td>
                      <td>{{ e.detail_text }}</td>
                    </tr>
                  </tbody>
                </table>
                <p class="empty" *ngIf="!v.events?.length">No audit events</p>
              </div>
            </ng-container>
          </section>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .compare-card { margin-top: 24px; }
    .compare-form { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; margin-top: 8px; }
    .doc-field { min-width: 260px; }
    .peer-field { flex: 1; min-width: 320px; }
    .compare-form button { margin-top: 6px; }
    .verdict { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 4px; margin: 8px 0 16px; font-weight: 600; }
    .verdict.match { background: #e3f9e5; color: #0f5132; }
    .verdict.mismatch { background: #fde2e1; color: #7a1d1d; }
    .verdict.unknown { background: #fff4d6; color: #6b4b00; }
    .sides { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
    .side { border: 1px solid #d9e2ec; border-radius: 4px; padding: 12px; }
    .side h3 { margin: 0 0 8px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
    .store { font-size: 0.75rem; background: #1f3a5f; color: #fff; padding: 2px 8px; border-radius: 10px; text-transform: uppercase; }
    .base { font-size: 0.75rem; color: #52606d; }
    .hash code { word-break: break-all; font-size: 0.8rem; }
    .version { margin-top: 12px; }
    .version.missing { border-left: 4px solid #c0392b; padding-left: 8px; }
    .missing-tag { font-size: 0.75rem; background: #fde2e1; color: #7a1d1d; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }
    .version h4 { margin: 0 0 6px; }
    table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
    th, td { border: 1px solid #e4e7eb; padding: 4px 8px; text-align: left; vertical-align: top; }
    .kv th { width: 160px; color: #52606d; font-weight: 500; }
    .events { margin-top: 8px; }
    tr.diff td, tr.diff th { background: #fde2e1; }
    .error { color: #7a1d1d; }
    .empty { color: #52606d; font-style: italic; }
  `],
})
export class ArchiveCompareComponent implements OnInit, OnChanges {
  @Input() docId = '';
  @Input() autoLoad = false;

  peerUrl = '';
  loading = false;
  sides: ArchiveSide[] = [];
  verdict: 'match' | 'mismatch' | 'unknown' | null = null;
  mismatchCount = 0;
  hashSummary = '';

  readonly versionFields: (keyof ArchiveVersion)[] = [
    'arch_key', 'version_no', 'retention_class', 'last_access_ts', 'storage_charge', 'unit_rate', 'owner_name',
    'disposition_dt', 'legal_hold', 'checksum_alg', 'content_sha256', 'byte_size', 'source_sys',
  ];
  private readonly policyFields: (keyof RetentionPolicy)[] = [
    'policy_code', 'policy_desc', 'retention_years', 'successor_code', 'active_flag', 'disposition_action', 'effective_ts',
  ];
  private readonly eventFields: (keyof ArchiveEvent)[] = [
    'audit_key', 'event_type', 'event_ts', 'actor_id', 'retention_class', 'disposition_code', 'client_ip', 'detail_text',
  ];

  constructor(private api: MigrationApiService) {}

  ngOnInit(): void {
    this.api.peerAppUrl().subscribe(url => {
      if (!this.peerUrl) {
        this.peerUrl = url;
      }
      if (this.autoLoad && this.docId) {
        this.load();
      }
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['docId'] && !changes['docId'].firstChange && this.autoLoad && this.docId) {
      this.load();
    }
  }

  load(): void {
    const id = this.docId.trim();
    if (!id) {
      return;
    }
    this.loading = true;
    this.verdict = null;
    this.mismatchCount = 0;
    this.hashSummary = '';
    const peer = this.peerUrl.trim().replace(/\/+$/, '');
    this.sides = [
      { label: 'This deployment', baseUrl: '', loading: true, error: null, document: null, hash: null },
    ];
    if (peer) {
      this.sides.push({ label: 'Peer deployment', baseUrl: peer, loading: true, error: null, document: null, hash: null });
    }

    forkJoin(this.sides.map(side => this.fetchSide(id, side))).subscribe(() => {
      this.loading = false;
      this.computeVerdict();
    });
  }

  /** True when the other deployment (when loaded) has no version at this position. */
  versionMissing(versionIndex: number): boolean {
    if (this.sides.length < 2 || this.sides.some(s => !s.document)) {
      return false;
    }
    const [a, b] = this.pairVersions(versionIndex);
    return !a !== !b;
  }

  differs(versionIndex: number, field: keyof ArchiveVersion): boolean {
    const [a, b] = this.pairVersions(versionIndex);
    return !!a && !!b && String(a[field] ?? '') !== String(b[field] ?? '');
  }

  policyDiffers(versionIndex: number): boolean {
    const [a, b] = this.pairVersions(versionIndex);
    if (!a || !b) {
      return false;
    }
    if (!a.policy || !b.policy) {
      return !!a.policy !== !!b.policy;
    }
    const pa = a.policy;
    const pb = b.policy;
    return this.policyFields.some(f => String(pa[f] ?? '') !== String(pb[f] ?? ''));
  }

  eventDiffers(versionIndex: number, eventIndex: number): boolean {
    const [a, b] = this.pairVersions(versionIndex);
    if (!a || !b) {
      return false;
    }
    const ea = a.events?.[eventIndex];
    const eb = b.events?.[eventIndex];
    if (!ea || !eb) {
      return true;
    }
    return this.eventFields.some(f => String(ea[f] ?? '') !== String(eb[f] ?? ''));
  }

  private fetchSide(id: string, side: ArchiveSide) {
    return forkJoin({
      document: this.api.getDocument(id, side.baseUrl || undefined),
      hash: this.api.getDocumentHash(id, side.baseUrl || undefined).pipe(catchError(() => of(null))),
    }).pipe(
      map(({ document, hash }) => {
        side.document = document;
        side.hash = hash;
        side.loading = false;
        return side;
      }),
      catchError((err: HttpErrorResponse) => {
        side.loading = false;
        side.error = this.describeError(err);
        return of(side);
      }),
    );
  }

  private describeError(err: HttpErrorResponse): string {
    const body = err.error;
    if (body && typeof body === 'object' && 'error' in body) {
      const hint = 'hint' in body && body.hint ? ` (${body.hint})` : '';
      return `${err.status}: ${body.error}${hint}`;
    }
    if (err.status === 0) {
      return 'Network error: peer unreachable or blocked by CORS';
    }
    return `${err.status}: ${err.message}`;
  }

  private pairVersions(versionIndex: number): [ArchiveVersion | undefined, ArchiveVersion | undefined] {
    const a = this.sides[0]?.document?.versions?.[versionIndex];
    const b = this.sides[1]?.document?.versions?.[versionIndex];
    return [a, b];
  }

  private computeVerdict(): void {
    if (this.sides.length < 2 || this.sides.some(s => !s.document)) {
      return;
    }
    const [a, b] = this.sides;
    let diffs = 0;
    const count = Math.max(a.document!.versions.length, b.document!.versions.length);
    for (let vi = 0; vi < count; vi++) {
      const [va, vb] = this.pairVersions(vi);
      if (!va || !vb) {
        diffs++;
        continue;
      }
      diffs += this.versionFields.filter(f => this.differs(vi, f)).length;
      if (this.policyDiffers(vi)) {
        diffs++;
      }
      const events = Math.max(va.events?.length ?? 0, vb.events?.length ?? 0);
      for (let ei = 0; ei < events; ei++) {
        if (this.eventDiffers(vi, ei)) {
          diffs++;
        }
      }
    }
    this.mismatchCount = diffs;
    // A match is only claimed when both business hashes were retrieved and agree; a missing
    // hash leaves the comparison unproven rather than "identical".
    if (!a.hash || !b.hash) {
      this.hashSummary = 'hash endpoint unavailable on one side';
      this.verdict = diffs === 0 ? 'unknown' : 'mismatch';
      return;
    }
    const hashMatches = a.hash.document_hash === b.hash.document_hash;
    this.hashSummary = hashMatches ? 'business hash matches' : 'business hash differs';
    this.verdict = diffs === 0 && hashMatches ? 'match' : 'mismatch';
  }
}
