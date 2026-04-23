#!/usr/bin/env bash
# SQLite データベースを作成して S3 にアップロードする
#
# 実行タイミング:
#   cdk deploy 完了後に実行する
#
# 前提:
#   - Python3 がインストールされていること
#   - AWS CLI v2 がインストールされていること

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDK_DIR="${SCRIPT_DIR}/../cdk"
TMP_DB="/tmp/database.db"

# CDK の出力からバケット名を取得
echo "==> S3 バケット名を取得中..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name LambdaS3SqliteStack \
  --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" \
  --output text)
echo "  バケット名: ${BUCKET_NAME}"

# SQLite データベースを作成
echo ""
echo "==> SQLite データベースを作成中..."
python3 "${SCRIPT_DIR}/create_db.py"

# S3 にアップロード
echo ""
echo "==> S3 にアップロード中..."
aws s3 cp "${TMP_DB}" "s3://${BUCKET_NAME}/database.db"
echo "  アップロード完了: s3://${BUCKET_NAME}/database.db"

echo ""
echo "==> 完了！次のコマンドでテストを実行してください:"
echo "    bash ${SCRIPT_DIR}/02_test_invoke.sh"
