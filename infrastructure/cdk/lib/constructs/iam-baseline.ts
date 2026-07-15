import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as route53 from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';

export interface IamBaselineProps {
  /**
   * Environment name (dev, staging, prod).
   */
  readonly environment: string;

  /**
   * GitHub org that owns the deploying repositories (for the OIDC trust).
   * @default 'Cognition-Partner-Workshops'
   */
  readonly githubOrg?: string;

  /**
   * GitHub repo allowed to assume the deploy role via OIDC. Supports the
   * `owner/repo:ref:*` subject glob.
   * @default 'otterworks'
   */
  readonly githubRepo?: string;

  /**
   * Optional public DNS zone for the platform's public endpoints
   * (CloudFront/ALB). Created only when a domain name is provided.
   */
  readonly domainName?: string;
}

/**
 * IAM foundation the downstream managed-platform deploys use: a GitHub Actions
 * OIDC provider and a deploy role assumable from the platform repo (no
 * long-lived credentials), plus an optional Route 53 public hosted zone.
 */
export class IamBaseline extends Construct {
  public readonly deployRole: iam.Role;
  public readonly hostedZone?: route53.PublicHostedZone;

  constructor(scope: Construct, id: string, props: IamBaselineProps) {
    super(scope, id);

    const githubOrg = props.githubOrg ?? 'Cognition-Partner-Workshops';
    const githubRepo = props.githubRepo ?? 'otterworks';

    const oidcProvider = new iam.OpenIdConnectProvider(this, 'GithubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    this.deployRole = new iam.Role(this, 'PlatformDeployRole', {
      roleName: `otterworks-${props.environment}-platform-deploy`,
      description:
        'Assumed by GitHub Actions (via OIDC) to deploy the managed platform stack',
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.WebIdentityPrincipal(
        oidcProvider.openIdConnectProviderArn,
        {
          StringEquals: {
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
          },
          StringLike: {
            'token.actions.githubusercontent.com:sub': `repo:${githubOrg}/${githubRepo}:*`,
          },
        },
      ),
    });
    // CloudFormation-driven CDK deploys assume the CDK bootstrap roles; grant
    // the deploy role permission to assume them.
    this.deployRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'AssumeCdkBootstrapRoles',
        actions: ['sts:AssumeRole'],
        resources: [
          `arn:aws:iam::${cdk.Stack.of(this).account}:role/cdk-*`,
        ],
      }),
    );

    if (props.domainName) {
      this.hostedZone = new route53.PublicHostedZone(this, 'HostedZone', {
        zoneName: props.domainName,
        comment: `OtterWorks ${props.environment} public zone`,
      });
      this.hostedZone.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);
    }
  }
}
