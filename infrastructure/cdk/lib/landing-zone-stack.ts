import * as cdk from 'aws-cdk-lib';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import {
  Encryption,
  Networking,
  Logging,
  Registry,
  IamBaseline,
  ParameterExports,
} from './constructs';

export interface LandingZoneStackProps extends cdk.StackProps {
  /**
   * Environment name (dev, staging, prod).
   */
  readonly environment: 'dev' | 'staging' | 'prod';

  /**
   * CIDR block for the shared VPC.
   * @default '10.0.0.0/16'
   */
  readonly vpcCidr?: string;

  /**
   * Maximum AZs to span.
   * @default 2
   */
  readonly maxAzs?: number;

  /**
   * Number of NAT gateways (1 for non-prod cost saving).
   * @default 1
   */
  readonly natGateways?: number;

  /**
   * Optional public domain name; creates a Route 53 hosted zone when set.
   * @default undefined (no DNS zone)
   */
  readonly domainName?: string;

  /**
   * ECR repository names to create in the shared registry.
   */
  readonly ecrRepositoryNames: string[];

  /**
   * CloudWatch log retention for flow logs and CloudTrail, in days.
   * @default 30
   */
  readonly logRetentionDays?: number;
}

/**
 * OtterWorks landing zone — the core shared AWS services every environment
 * builds on. Provisions a shared KMS key, a managed-service-ready VPC (with
 * endpoints + flow logs), a central log archive + CloudTrail, a shared ECR
 * registry, and an IAM/OIDC deploy baseline. All shared handles are published
 * to SSM + CfnOutputs so the downstream fully-managed platform stack (ECS
 * Fargate, RDS, ElastiCache, OpenSearch, DynamoDB, S3, SQS/SNS, Cognito, ALB,
 * CloudFront) can consume them.
 *
 * Wiring order follows data flow: Encryption → Networking → Logging →
 * Registry → IamBaseline → ParameterExports. All resources use
 * RemovalPolicy.DESTROY for clean `cdk destroy`.
 */
export class LandingZoneStack extends cdk.Stack {
  public readonly encryption: Encryption;
  public readonly networking: Networking;
  public readonly logging: Logging;
  public readonly registry: Registry;
  public readonly iamBaseline: IamBaseline;
  public readonly exports: ParameterExports;

  constructor(scope: Construct, id: string, props: LandingZoneStackProps) {
    super(scope, id, props);

    const logRetention = props.logRetentionDays
      ? toRetentionDays(props.logRetentionDays)
      : logs.RetentionDays.ONE_MONTH;

    // ── Shared CMK (created first; everything encrypts with it) ──────────────
    this.encryption = new Encryption(this, 'Encryption', {
      environment: props.environment,
    });

    // ── Shared VPC (managed-service ready) ──────────────────────────────────
    this.networking = new Networking(this, 'Networking', {
      vpcName: `otterworks-${props.environment}`,
      vpcCidr: props.vpcCidr,
      maxAzs: props.maxAzs ?? 2,
      natGateways: props.natGateways ?? 1,
      logDestinationKey: this.encryption.key,
      logRetention,
    });

    // ── Central logging (log archive + CloudTrail) ──────────────────────────
    this.logging = new Logging(this, 'Logging', {
      environment: props.environment,
      encryptionKey: this.encryption.key,
      logRetention,
    });

    // ── Shared container registry ───────────────────────────────────────────
    this.registry = new Registry(this, 'Registry', {
      repositoryNames: props.ecrRepositoryNames,
      encryptionKey: this.encryption.key,
    });

    // ── IAM / OIDC deploy baseline (+ optional DNS zone) ────────────────────
    this.iamBaseline = new IamBaseline(this, 'IamBaseline', {
      environment: props.environment,
      domainName: props.domainName,
    });

    // ── Publish shared handles for the downstream platform stack ────────────
    this.exports = new ParameterExports(this, 'Exports', {
      environment: props.environment,
      vpc: this.networking.vpc,
      appSecurityGroup: this.networking.appSecurityGroup,
      encryptionKey: this.encryption.key,
      logArchiveBucket: this.logging.logArchiveBucket,
      repositories: this.registry.repositories,
      deployRole: this.iamBaseline.deployRole,
      hostedZone: this.iamBaseline.hostedZone,
    });

    cdk.Tags.of(this).add('Project', 'otterworks');
    cdk.Tags.of(this).add('Environment', props.environment);
    cdk.Tags.of(this).add('ManagedBy', 'cdk');
    cdk.Tags.of(this).add('Layer', 'landing-zone');
  }
}

/** Map a raw day count to the nearest supported CloudWatch RetentionDays. */
function toRetentionDays(days: number): logs.RetentionDays {
  const match = Object.values(logs.RetentionDays).find((v) => v === days);
  return (match as logs.RetentionDays) ?? logs.RetentionDays.ONE_MONTH;
}
