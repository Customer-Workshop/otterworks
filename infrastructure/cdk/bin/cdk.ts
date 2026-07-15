#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { LandingZoneStack } from '../lib/landing-zone-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
};

// One shared ECR repository per OtterWorks service + frontend image.
const ecrRepositoryNames = [
  'otterworks/api-gateway',
  'otterworks/auth-service',
  'otterworks/file-service',
  'otterworks/document-service',
  'otterworks/collab-service',
  'otterworks/notification-service',
  'otterworks/search-service',
  'otterworks/analytics-service',
  'otterworks/admin-service',
  'otterworks/audit-service',
  'otterworks/report-service',
  'otterworks/web-app',
  'otterworks/admin-dashboard',
];

// ────────────────────────────────────────────────────────────────────────────
// Dev
// ────────────────────────────────────────────────────────────────────────────
new LandingZoneStack(app, 'OtterworksLandingZoneDev', {
  env,
  environment: 'dev',
  vpcCidr: '10.0.0.0/16',
  maxAzs: 2,
  natGateways: 1,
  logRetentionDays: 30,
  ecrRepositoryNames,
});

// ────────────────────────────────────────────────────────────────────────────
// Staging
// ────────────────────────────────────────────────────────────────────────────
new LandingZoneStack(app, 'OtterworksLandingZoneStaging', {
  env,
  environment: 'staging',
  vpcCidr: '10.1.0.0/16',
  maxAzs: 2,
  natGateways: 1,
  logRetentionDays: 30,
  ecrRepositoryNames,
});

// ────────────────────────────────────────────────────────────────────────────
// Production
// ────────────────────────────────────────────────────────────────────────────
new LandingZoneStack(app, 'OtterworksLandingZoneProd', {
  env,
  environment: 'prod',
  vpcCidr: '10.2.0.0/16',
  maxAzs: 3,
  natGateways: 2,
  logRetentionDays: 90,
  ecrRepositoryNames,
});

app.synth();
