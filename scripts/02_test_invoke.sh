#!/usr/bin/env bash
# Lambda を直接 invoke してテストする
#
# 実行タイミング:
#   01_create_db.sh 完了後に実行する

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESPONSE_FILE="/tmp/lambda_response.json"

# CloudFormation の出力から Lambda 関数名を取得
echo "==> Lambda 関数名を取得中..."
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name LambdaS3SqliteStack \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text)
echo "  関数名: ${FUNCTION_NAME}"

run_invoke() {
  local action="$1"
  echo ""
  echo "==> Lambda を実行中（action=${action}）..."

  aws lambda invoke \
    --function-name "${FUNCTION_NAME}" \
    --payload "{\"action\": \"${action}\"}" \
    --cli-binary-format raw-in-base64-out \
    "${RESPONSE_FILE}"

  echo "  レスポンス:"
  python3 -m json.tool "${RESPONSE_FILE}"
}

# テスト 1: DB の情報を確認
run_invoke "db_info"

# テスト 2: ユーザー一覧を取得
run_invoke "query_users"

# CloudWatch Logs で実行ログを確認
echo ""
echo "==> CloudWatch Logs（直近5分）:"
aws logs tail "/aws/lambda/${FUNCTION_NAME}" \
  --since 5m \
  --format short \
  || echo "  （ログの取得に失敗しました。少し待ってから再実行してください）"

echo ""
echo "==> テスト完了"
