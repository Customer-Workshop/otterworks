import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface EncryptionProps {
  /**
   * Environment name (dev, staging, prod). Used in the KMS alias.
   */
  readonly environment: string;
}

/**
 * Shared customer-managed KMS key for encrypting data at rest across the whole
 * platform (log archive, ECR repositories, and — for the downstream managed
 * platform stack — RDS, S3, DynamoDB, SQS/SNS, and Secrets Manager).
 *
 * Created first so every other landing-zone construct can encrypt with a single
 * CMK. Key rotation is enabled; DESTROY removal policy keeps teardown clean.
 */
export class Encryption extends Construct {
  public readonly key: kms.Key;

  constructor(scope: Construct, id: string, props: EncryptionProps) {
    super(scope, id);

    this.key = new kms.Key(this, 'SharedKey', {
      alias: `alias/otterworks-${props.environment}-shared`,
      description: `OtterWorks ${props.environment} shared data-at-rest CMK`,
      enableKeyRotation: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
  }
}
