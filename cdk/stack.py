import os

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    CfnResource,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
)
from constructs import Construct

LAMBDA_DIR = os.path.join(os.path.dirname(__file__), "..", "lambda")


class LambdaS3SqliteStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # -------------------------------------------------------
        # VPC / ネットワーク
        # -------------------------------------------------------

        vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=1,
            nat_gateways=0,  # Lambda は NFS のみ使用するため不要
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            ],
        )

        # Lambda 用 SG と マウントターゲット用 SG を作成してから相互ルールを追加する
        lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSG",
            vpc=vpc,
            description="SG for Lambda - NFS egress only",
            allow_all_outbound=False,
        )

        mt_sg = ec2.SecurityGroup(
            self,
            "MountTargetSG",
            vpc=vpc,
            description="SG for S3 Files mount target",
            allow_all_outbound=False,
        )

        # SG 作成後に相互参照ルールを追加（循環参照を避けるための2ステップ）
        lambda_sg.add_egress_rule(
            peer=mt_sg,
            connection=ec2.Port.tcp(2049),
            description="NFS to S3 Files mount target",
        )
        mt_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(2049),
            description="NFS from Lambda",
        )

        private_subnet = vpc.isolated_subnets[0]

        # -------------------------------------------------------
        # S3 バケット（バージョニング必須）
        # -------------------------------------------------------

        bucket = s3.Bucket(
            self,
            "Bucket",
            versioned=True,  # S3 Files の必須要件
            removal_policy=cdk.RemovalPolicy.DESTROY, # cdk destroy 時にバケットも削除
            auto_delete_objects=True,
        )

        # -------------------------------------------------------
        # IAM: S3 Files サービスロール
        # S3 Files（elasticfilesystem.amazonaws.com）が S3 バケットと同期するためのロール
        # 信頼ポリシーには SourceAccount/SourceArn 条件を付けて権限昇格を防ぐ
        # -------------------------------------------------------

        s3files_service_role = iam.Role(
            self,
            "S3FilesServiceRole",
            assumed_by=iam.ServicePrincipal(
                "elasticfilesystem.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:s3files:{self.region}:{self.account}:file-system/*"
                    },
                },
            ),
        )
        # S3 バケットへの読み書き権限（List*/GetBucket*/PutObject*/DeleteObject*/Abort* を含む）
        bucket.grant_read_write(s3files_service_role)

        # S3 Files が内部で使用する EventBridge ルールの管理権限
        s3files_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "events:DeleteRule",
                    "events:DisableRule",
                    "events:EnableRule",
                    "events:PutRule",
                    "events:PutTargets",
                    "events:RemoveTargets",
                ],
                resources=["arn:aws:events:*:*:rule/DO-NOT-DELETE-S3-Files*"],
                conditions={
                    "StringEquals": {
                        "events:ManagedBy": "elasticfilesystem.amazonaws.com"
                    }
                },
            )
        )
        s3files_service_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "events:DescribeRule",
                    "events:ListRuleNamesByTarget",
                    "events:ListRules",
                    "events:ListTargetsByRule",
                ],
                resources=["arn:aws:events:*:*:rule/*"],
            )
        )

        # -------------------------------------------------------
        # S3 Files リソース（CloudFormation L1 コンストラクト）
        #
        # CDK の aws_cdk.aws_s3files モジュールとして
        # 対応クラスが追加されるまでは CfnResource で直接定義する
        # -------------------------------------------------------

        file_system = CfnResource(
            self,
            "S3FilesFileSystem",
            type="AWS::S3Files::FileSystem",
            properties={
                "Bucket": bucket.bucket_arn,
                "RoleArn": s3files_service_role.role_arn,
            },
        )

        mount_target = CfnResource(
            self,
            "S3FilesMountTarget",
            type="AWS::S3Files::MountTarget",
            properties={
                "FileSystemId": file_system.get_att("FileSystemId").to_string(),
                "SubnetId": private_subnet.subnet_id,
                "SecurityGroups": [mt_sg.security_group_id],
            },
        )

        access_point = CfnResource(
            self,
            "S3FilesAccessPoint",
            type="AWS::S3Files::AccessPoint",
            properties={
                "FileSystemId": file_system.get_att("FileSystemId").to_string(),
                "PosixUser": {"Uid": 0, "Gid": 0},
                "RootDirectory": {
                    "Path": "/",
                },
            },
        )
        # マウントターゲットが available になってからアクセスポイントを作成する
        access_point.add_dependency(mount_target)

        # -------------------------------------------------------
        # IAM: Lambda 実行ロール
        # -------------------------------------------------------

        lambda_role = iam.Role(
            self,
            "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # S3 Files マウント・書き込み権限
        # ClientMount: マウントに必要（読み書き共通）
        # ClientWrite: 書き込みに追加で必要
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3files:ClientMount", "s3files:ClientWrite"],
                resources=["*"],
            )
        )

        # S3 バケットへの読み取り権限
        bucket.grant_read(lambda_role)

        # -------------------------------------------------------
        # Lambda 関数
        # -------------------------------------------------------

        fn = lambda_.Function(
            self,
            "SqliteFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(LAMBDA_DIR),
            role=lambda_role,
            timeout=cdk.Duration.seconds(30),
            # 512 MB 未満では S3 からの direct-read 最適化が無効になる
            memory_size=512,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[lambda_sg],
            environment={
                "DB_PATH": "/mnt/s3data/database.db",
            },
        )

        # S3 Files アクセスポイントをマウント設定として追加する
        # CDK の FileSystem.from_efs_access_point は EFS 専用のため、
        # CfnFunction の FileSystemConfigs プロパティを直接上書きする
        cfn_fn = fn.node.default_child
        cfn_fn.add_property_override(
            "FileSystemConfigs",
            [
                {
                    "Arn": access_point.get_att("AccessPointArn").to_string(),
                    "LocalMountPath": "/mnt/s3data",
                }
            ],
        )
        fn.node.add_dependency(access_point)

        # -------------------------------------------------------
        # Outputs
        # -------------------------------------------------------

        CfnOutput(self, "LambdaFunctionName", value=fn.function_name)
        CfnOutput(self, "S3BucketName", value=bucket.bucket_name)
        CfnOutput(
            self,
            "S3FilesFileSystemId",
            value=file_system.get_att("FileSystemId").to_string(),
        )
