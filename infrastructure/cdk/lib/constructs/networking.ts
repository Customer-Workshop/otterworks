import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface NetworkingProps {
  /**
   * Name prefix for the VPC and related resources.
   */
  readonly vpcName: string;

  /**
   * CIDR block for the VPC.
   * @default '10.0.0.0/16'
   */
  readonly vpcCidr?: string;

  /**
   * Maximum number of Availability Zones to use.
   * @default 2
   */
  readonly maxAzs?: number;

  /**
   * Number of NAT Gateways (1 for cost saving in non-prod).
   * @default 1
   */
  readonly natGateways?: number;

  /**
   * KMS key used to encrypt the VPC flow-log group.
   */
  readonly logDestinationKey: kms.IKey;

  /**
   * Flow-log retention.
   * @default logs.RetentionDays.ONE_MONTH
   */
  readonly logRetention?: logs.RetentionDays;
}

/**
 * Shared VPC that the downstream managed platform stack runs in. Provides
 * public + private-with-egress subnets across AZs, VPC flow logs, gateway and
 * interface endpoints (so Fargate/managed-service traffic to S3, DynamoDB, ECR,
 * CloudWatch Logs, Secrets Manager and SSM stays on the AWS backbone), and a
 * shared application security group for the platform's compute/data tiers.
 *
 * All resources use DESTROY removal policy for clean teardown.
 */
export class Networking extends Construct {
  public readonly vpc: ec2.Vpc;
  public readonly appSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkingProps) {
    super(scope, id);

    // Encrypted destination for VPC flow logs.
    const flowLogGroup = new logs.LogGroup(this, 'FlowLogGroup', {
      logGroupName: `/otterworks/${props.vpcName}/flow-logs`,
      retention: props.logRetention ?? logs.RetentionDays.ONE_MONTH,
      encryptionKey: props.logDestinationKey,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    // CloudWatch Logs in this region must be able to use the CMK.
    props.logDestinationKey.grantEncryptDecrypt(
      new cdk.aws_iam.ServicePrincipal(
        `logs.${cdk.Stack.of(this).region}.amazonaws.com`,
      ),
    );

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: props.vpcName,
      ipAddresses: ec2.IpAddresses.cidr(props.vpcCidr ?? '10.0.0.0/16'),
      maxAzs: props.maxAzs ?? 2,
      natGateways: props.natGateways ?? 1,
      enableDnsHostnames: true,
      enableDnsSupport: true,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      ],
      flowLogs: {
        cloudwatch: {
          destination: ec2.FlowLogDestination.toCloudWatchLogs(flowLogGroup),
          trafficType: ec2.FlowLogTrafficType.ALL,
        },
      },
    });

    // Tag subnets for ELB/ALB auto-discovery (used by the managed platform's
    // load balancers and any future in-VPC ingress).
    for (const subnet of this.vpc.publicSubnets) {
      cdk.Tags.of(subnet).add('kubernetes.io/role/elb', '1');
    }
    for (const subnet of this.vpc.privateSubnets) {
      cdk.Tags.of(subnet).add('kubernetes.io/role/internal-elb', '1');
    }

    // --- Gateway endpoints (free): keep S3/DynamoDB traffic private ---
    this.vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });
    this.vpc.addGatewayEndpoint('DynamoDbEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
    });

    // --- Interface endpoints: pull images / read secrets / ship logs privately ---
    const interfaceEndpoints: Record<string, ec2.InterfaceVpcEndpointAwsService> = {
      EcrApiEndpoint: ec2.InterfaceVpcEndpointAwsService.ECR,
      EcrDockerEndpoint: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
      CloudWatchLogsEndpoint: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
      SecretsManagerEndpoint: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
      SsmEndpoint: ec2.InterfaceVpcEndpointAwsService.SSM,
    };
    for (const [endpointId, service] of Object.entries(interfaceEndpoints)) {
      this.vpc.addInterfaceEndpoint(endpointId, {
        service,
        privateDnsEnabled: true,
      });
    }

    // Shared SG for the platform's compute/data tiers; allows intra-SG traffic.
    this.appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      vpc: this.vpc,
      description: 'Shared OtterWorks application security group',
      allowAllOutbound: true,
    });
    this.appSecurityGroup.addIngressRule(
      this.appSecurityGroup,
      ec2.Port.allTraffic(),
      'Intra-security-group traffic between platform tiers',
    );

    this.vpc.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);
  }
}
