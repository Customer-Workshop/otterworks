import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudtrail from 'aws-cdk-lib/aws-cloudtrail';
import { Construct } from 'constructs';

export interface LoggingProps {
  /**
   * Environment name (dev, staging, prod).
   */
  readonly environment: string;

  /**
   * Shared KMS key used to encrypt the log-archive bucket and CloudTrail.
   */
  readonly encryptionKey: kms.IKey;

  /**
   * CloudWatch retention for the CloudTrail log group.
   * @default logs.RetentionDays.ONE_MONTH
   */
  readonly logRetention?: logs.RetentionDays;
}

/**
 * Centralised logging foundation for the landing zone: a KMS-encrypted,
 * versioned, access-logged S3 "log archive" bucket with a Glacier lifecycle,
 * plus an account CloudTrail trail (management events) delivering to both the
 * bucket and CloudWatch Logs for querying/alerting.
 *
 * Buckets use autoDeleteObjects + DESTROY so the environment tears down cleanly.
 */
export class Logging extends Construct {
  public readonly logArchiveBucket: s3.Bucket;
  public readonly trail: cloudtrail.Trail;

  constructor(scope: Construct, id: string, props: LoggingProps) {
    super(scope, id);

    // Bucket that stores S3 server access logs for the archive bucket itself.
    const accessLogsBucket = new s3.Bucket(this, 'AccessLogsBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: false,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [{ expiration: cdk.Duration.days(90) }],
    });

    this.logArchiveBucket = new s3.Bucket(this, 'LogArchiveBucket', {
      bucketName: `otterworks-log-archive-${props.environment}-${cdk.Stack.of(this).account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: props.encryptionKey,
      bucketKeyEnabled: true,
      enforceSSL: true,
      versioned: true,
      serverAccessLogsBucket: accessLogsBucket,
      serverAccessLogsPrefix: 'log-archive/',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [
        {
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    const trailLogGroup = new logs.LogGroup(this, 'TrailLogGroup', {
      logGroupName: `/otterworks/cloudtrail/${props.environment}`,
      retention: props.logRetention ?? logs.RetentionDays.ONE_MONTH,
      encryptionKey: props.encryptionKey,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    props.encryptionKey.grantEncryptDecrypt(
      new cdk.aws_iam.ServicePrincipal(
        `logs.${cdk.Stack.of(this).region}.amazonaws.com`,
      ),
    );

    this.trail = new cloudtrail.Trail(this, 'Trail', {
      trailName: `otterworks-${props.environment}`,
      bucket: this.logArchiveBucket,
      encryptionKey: props.encryptionKey,
      cloudWatchLogGroup: trailLogGroup,
      sendToCloudWatchLogs: true,
      includeGlobalServiceEvents: true,
      isMultiRegionTrail: true,
      enableFileValidation: true,
    });
  }
}
