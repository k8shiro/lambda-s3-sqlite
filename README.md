# lambda-s3-sqlite

AWS Lambda の S3 Files マウント機能を使って SQLite データベースを読み書きする検証コードです。

## 構成

```
lambda-s3-sqlite/
├── cdk/            # CDK スタック（VPC, S3, S3 Files, Lambda）
├── lambda/         # Lambda 関数コード
├── scripts/        # テスト・検証スクリプト
├── Dockerfile      # 実行環境（AWS CLI + CDK）
├── docker-compose.yml
└── .env.example    # 環境変数テンプレート
```

## 前提条件

- Docker / Docker Compose
- AWSアカウントと操作権限（IAM, Lambda, S3, VPC, CloudFormation）

## セットアップ

### 1. 環境変数を設定する

```bash
cp .env.example .env
```

`.env` を編集してAWS認証情報とアカウントIDを設定します。

```
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_DEFAULT_REGION=us-east-1
CDK_DEFAULT_ACCOUNT=123456789012
CDK_DEFAULT_REGION=us-east-1
```

### 2. Dockerコンテナを起動する

```bash
docker compose run --rm app bash
```

以降の操作はコンテナ内で実行します。

## デプロイ

```bash
cd cdk
pip install -r requirements.txt
cdk bootstrap  # 初回のみ
cdk deploy
```

デプロイ完了後、バケット名と Lambda 関数名が出力されます。

```bash
# 以降のコマンドで使う変数をセット
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name LambdaS3SqliteStack \
  --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" \
  --output text)

FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name LambdaS3SqliteStack \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text)
```

## テストデータの準備

```bash
cd /workspace
python3 scripts/create_db.py
aws s3 cp /tmp/database.db s3://$BUCKET_NAME/database.db
```

S3 Files が S3 のオブジェクトをマウントパスに同期するまで数秒かかります。

## テスト実行

### 基本的な読み取り

```bash
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload '{"action": "query_users"}' \
  /tmp/response.json && cat /tmp/response.json
```

### 書き込み

```bash
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload '{"action": "insert_user", "name": "Alice", "email": "alice@example.com"}' \
  /tmp/response.json && cat /tmp/response.json
```

### 書き込み直後の読み取り

```bash
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --payload '{"action": "write_then_read", "name": "TestUser", "email": "test@example.com"}' \
  /tmp/response.json && cat /tmp/response.json
```

### 同時書き込み・読み込み（5並列）

```bash
bash scripts/03_concurrent_test.sh
```

### S3バージョニングの挙動確認

```bash
bash scripts/04_versioning_test.sh
```

## 削除

```bash
cd cdk
cdk destroy
```

> `cdk destroy` はS3バケット内のオブジェクトを含めて削除します（`auto_delete_objects=True` が設定されています）。
