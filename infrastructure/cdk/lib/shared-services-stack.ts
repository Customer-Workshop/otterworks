import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';
import { Registry } from './constructs';

export interface SharedServicesStackProps extends cdk.StackProps {
  /**
   * ECR repository names to create in the shared registry.
   */
  readonly ecrRepositoryNames: string[];
}

/**
 * Account/region-global core shared services, deployed ONCE (not per env):
 *
 *  - The shared ECR registry (repository names are unique per account/region,
 *    so they cannot be created by every environment stack). Images are built
 *    once and promoted across environments.
 *  - The GitHub Actions OIDC provider (only one may exist per account for a
 *    given issuer URL). Per-environment deploy roles in LandingZoneStack trust
 *    this provider.
 *
 * Handles are published to SSM under `/otterworks/shared/...` and as CfnOutput
 * exports so both the per-env landing zones and the downstream managed platform
 * can consume them.
 */
export class SharedServicesStack extends cdk.Stack {
  public readonly registry: Registry;
  public readonly oidcProvider: iam.OpenIdConnectProvider;
  public readonly registryKey: kms.Key;

  constructor(scope: Construct, id: string, props: SharedServicesStackProps) {
    super(scope, id, props);

    this.registryKey = new kms.Key(this, 'RegistryKey', {
      alias: 'alias/otterworks-shared-registry',
      description: 'OtterWorks shared ECR registry CMK',
      enableKeyRotation: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.registry = new Registry(this, 'Registry', {
      repositoryNames: props.ecrRepositoryNames,
      encryptionKey: this.registryKey,
    });

    this.oidcProvider = new iam.OpenIdConnectProvider(this, 'GithubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    // --- Exports (SSM + CfnOutput) ---
    new ssm.StringParameter(this, 'ParamOidcArn', {
      parameterName: '/otterworks/shared/github-oidc-provider-arn',
      stringValue: this.oidcProvider.openIdConnectProviderArn,
      description: 'GitHub Actions OIDC provider ARN',
    });
    new cdk.CfnOutput(this, 'OutputOidcArn', {
      value: this.oidcProvider.openIdConnectProviderArn,
      description: 'GitHub Actions OIDC provider ARN',
      exportName: 'otterworks-shared-github-oidc-provider-arn',
    });

    for (const [name, repo] of this.registry.repositories) {
      const slug = name.replace(/\//g, '-');
      new ssm.StringParameter(this, `ParamEcr${slug}`, {
        parameterName: `/otterworks/shared/ecr/${slug}-uri`,
        stringValue: repo.repositoryUri,
        description: `ECR repository URI for ${name}`,
      });
      new cdk.CfnOutput(this, `OutputEcr${slug}`, {
        value: repo.repositoryUri,
        description: `ECR repository URI for ${name}`,
        exportName: `otterworks-shared-ecr-${slug}-uri`,
      });
    }

    cdk.Tags.of(this).add('Project', 'otterworks');
    cdk.Tags.of(this).add('ManagedBy', 'cdk');
    cdk.Tags.of(this).add('Layer', 'shared-services');
  }
}
