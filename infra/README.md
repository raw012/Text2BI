# AWS deployment plan

These templates have not been deployed. Use a non-root CLI profile in `us-east-1`
after verifying its STS ARN. Provide two public subnets in different Availability
Zones in one VPC. The subnets need an internet gateway route for the ALB and
Fargate task. Provide an ACM certificate and a DNS name that resolves to the ALB.

1. Deploy `foundation.yml` with the VPC and subnet parameters. It creates a
   private, versioned S3 bucket, immutable backend/frontend ECR repositories,
   and private RDS PostgreSQL with an RDS-managed password.
2. Create a Secrets Manager secret containing the Qwen key as a plain secret
   string. Keep its ARN outside Git.
3. Build and push both images to the repository URIs in the foundation outputs.
   Build the frontend with `--build-arg VITE_API_URL=/api`. Use an immutable
   commit SHA as the image tag. The backend container needs no secrets at build
   time.
4. Deploy `application.yml` using the foundation outputs, image URIs, Qwen
   secret ARN, certificate ARN, and public HTTPS origin. Point the DNS name to
   the ALB DNS output. Check `/api/docs`, `/api/datasets`, and the full upload →
   dashboard → standalone HTML path.

The application template runs one backend replica because workflow progress is
currently held in process memory. The ECS execution role reads the database and
Qwen secrets at task startup. After rotating Qwen, force a new ECS deployment to
replace the task; no image rebuild is needed. The task role has access only to
objects in the upload bucket. Database and bucket retention settings preserve
data if the stack is removed. Review costs before deployment: RDS, ALB, Fargate,
CloudWatch, S3, and data transfer incur charges.

For live database questions, create a dedicated PostgreSQL login with SELECT
access to the curated tables and no write grants. Connect it from **Ask your
data → Live database**. The backend checks the role and stores its URL only in
Secrets Manager under `text2bi/connectors/`. It stores just the ARN and table
allowlist in PostgreSQL. The ECS task role has scoped create/read/delete secret
permissions for that prefix. A question re-inspects the live schema, accepts
only a single SELECT over allowlisted tables, and executes within a read-only
transaction with a five-second timeout and 100-row response cap. Limit
application access to trusted users until authentication and tenant isolation
are implemented.

For a limited deployment profile, allow CloudFormation stack create/update/read,
the resource actions needed by these templates (S3, ECR, RDS, EC2 networking,
ELBv2, ECS, IAM role/policy creation with `iam:PassRole`, CloudWatch Logs, and
Secrets Manager), ECR image push, and ECS service update. Scope permissions to
the Text2BI stacks, repositories, roles, and secrets where the service supports
resource scoping. Do not grant account-wide administrator access. The runtime
roles are defined separately in `application.yml`.

The templates are a deployment starting point. Before real user data, add app
authentication, a dedicated least-privilege database user, HTTPS domain
verification, backup/restore drills, database migrations, and durable workflow
progress. No AWS resources are created by this repository alone.
