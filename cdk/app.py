import os

import aws_cdk as cdk
from stack import LambdaS3SqliteStack

app = cdk.App()

LambdaS3SqliteStack(
    app,
    "LambdaS3SqliteStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION") or "ap-northeast-1",
    ),
)

app.synth()
