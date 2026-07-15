import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface RegistryProps {
  /**
   * List of ECR repository names to create (one per service/frontend image).
   */
  readonly repositoryNames: string[];

  /**
   * Shared KMS key used to encrypt image layers at rest.
   */
  readonly encryptionKey: kms.IKey;
}

/**
 * Shared ECR registry — a core shared service consumed regardless of which
 * managed compute the platform uses (ECS Fargate / App Runner). Each repository
 * has scan-on-push, KMS encryption, and lifecycle rules (keep last 10 tagged,
 * expire untagged after 7 days). emptyOnDelete + DESTROY for clean teardown.
 */
export class Registry extends Construct {
  public readonly repositories: Map<string, ecr.Repository> = new Map();

  constructor(scope: Construct, id: string, props: RegistryProps) {
    super(scope, id);

    for (const repoName of props.repositoryNames) {
      // Convert slashes to hyphens for the construct ID.
      const constructId = repoName.replace(/\//g, '-');

      const repository = new ecr.Repository(this, constructId, {
        repositoryName: repoName,
        imageScanOnPush: true,
        imageTagMutability: ecr.TagMutability.MUTABLE,
        encryption: ecr.RepositoryEncryption.KMS,
        encryptionKey: props.encryptionKey,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        emptyOnDelete: true,
        lifecycleRules: [
          {
            description: 'Keep last 10 tagged images',
            rulePriority: 1,
            tagStatus: ecr.TagStatus.TAGGED,
            tagPrefixList: ['v', 'release'],
            maxImageCount: 10,
          },
          {
            description: 'Remove untagged images after 7 days',
            rulePriority: 2,
            tagStatus: ecr.TagStatus.UNTAGGED,
            maxImageAge: cdk.Duration.days(7),
          },
        ],
      });

      this.repositories.set(repoName, repository);
    }
  }
}
