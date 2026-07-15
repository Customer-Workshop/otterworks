import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface ParameterExportsProps {
  /**
   * Environment name (dev, staging, prod). Used in the SSM parameter path.
   */
  readonly environment: string;

  readonly vpc: ec2.IVpc;
  readonly appSecurityGroup: ec2.ISecurityGroup;
  readonly encryptionKey: kms.IKey;
  readonly logArchiveBucket: s3.IBucket;
  readonly deployRole: cdk.aws_iam.IRole;
  readonly hostedZone?: route53.IPublicHostedZone;
}

/**
 * Publishes every shared handle from the landing zone to SSM Parameter Store
 * under `/otterworks/landing-zone/<env>/...` and as CfnOutputs (with exportName).
 *
 * This is the contract the downstream managed-platform stack consumes: it reads
 * these parameters (e.g. `ssm.StringParameter.valueForStringParameter` or
 * `ec2.Vpc.fromLookup`) to place ECS/Fargate, RDS, ElastiCache, OpenSearch,
 * DynamoDB, S3, SQS/SNS, Cognito, ALB and CloudFront onto the shared foundation.
 */
export class ParameterExports extends Construct {
  private readonly base: string;
  private readonly environment: string;

  constructor(scope: Construct, id: string, props: ParameterExportsProps) {
    super(scope, id);

    this.environment = props.environment;
    this.base = `/otterworks/landing-zone/${props.environment}`;

    this.put('vpc-id', props.vpc.vpcId, 'Shared VPC ID');
    this.put(
      'vpc-cidr',
      props.vpc.vpcCidrBlock,
      'Shared VPC CIDR block',
    );
    this.put(
      'private-subnet-ids',
      cdk.Fn.join(',', props.vpc.privateSubnets.map((s) => s.subnetId)),
      'Comma-separated private subnet IDs',
    );
    this.put(
      'public-subnet-ids',
      cdk.Fn.join(',', props.vpc.publicSubnets.map((s) => s.subnetId)),
      'Comma-separated public subnet IDs',
    );
    this.put(
      'app-security-group-id',
      props.appSecurityGroup.securityGroupId,
      'Shared application security group ID',
    );
    this.put(
      'kms-key-arn',
      props.encryptionKey.keyArn,
      'Shared data-at-rest KMS key ARN',
    );
    this.put(
      'log-archive-bucket-arn',
      props.logArchiveBucket.bucketArn,
      'Central log-archive bucket ARN',
    );
    this.put(
      'platform-deploy-role-arn',
      props.deployRole.roleArn,
      'Platform deploy role ARN (GitHub OIDC)',
    );

    if (props.hostedZone) {
      this.put(
        'hosted-zone-id',
        props.hostedZone.hostedZoneId,
        'Route 53 public hosted zone ID',
      );
    }
  }

  /** Write one SSM string parameter plus a matching CfnOutput export. */
  private put(name: string, value: string, description: string): void {
    const id = name.replace(/[^A-Za-z0-9]/g, '');

    new ssm.StringParameter(this, `Param${id}`, {
      parameterName: `${this.base}/${name}`,
      stringValue: value,
      description,
    });

    new cdk.CfnOutput(this, `Output${id}`, {
      value,
      description,
      exportName: `otterworks-lz-${this.environment}-${name.replace(/\//g, '-')}`,
    });
  }
}
