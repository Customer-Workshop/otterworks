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
   * Account-global GitHub Actions OIDC provider (created once in the shared
   * services stack) that this environment's deploy role trusts.
   */
  readonly oidcProvider: iam.IOpenIdConnectProvider;

  /**
   * Allowed OIDC `sub` claim patterns (least privilege). Each entry is a full
   * subject such as `repo:org/repo:ref:refs/heads/main` or a glob like
   * `repo:org/repo:*`. Non-prod environments typically allow any ref; prod
   * should be restricted to a protected branch.
   */
  readonly allowedGithubSubjects: string[];

  /**
   * Optional public DNS zone for the platform's public endpoints
   * (CloudFront/ALB). Created only when a domain name is provided.
   */
  readonly domainName?: string;
}

/**
 * Per-environment IAM foundation the downstream managed-platform deploys use: a
 * deploy role assumable from the platform repo via the shared GitHub OIDC
 * provider (no long-lived credentials), with the OIDC subject scoped by
 * `allowedGithubSubjects`. Optionally creates a Route 53 public hosted zone.
 */
export class IamBaseline extends Construct {
  public readonly deployRole: iam.Role;
  public readonly hostedZone?: route53.PublicHostedZone;

  constructor(scope: Construct, id: string, props: IamBaselineProps) {
    super(scope, id);

    this.deployRole = new iam.Role(this, 'PlatformDeployRole', {
      roleName: `otterworks-${props.environment}-platform-deploy`,
      description:
        'Assumed by GitHub Actions (via OIDC) to deploy the managed platform stack',
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.WebIdentityPrincipal(
        props.oidcProvider.openIdConnectProviderArn,
        {
          StringEquals: {
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
          },
          StringLike: {
            'token.actions.githubusercontent.com:sub': props.allowedGithubSubjects,
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
        resources: [`arn:aws:iam::${cdk.Stack.of(this).account}:role/cdk-*`],
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
