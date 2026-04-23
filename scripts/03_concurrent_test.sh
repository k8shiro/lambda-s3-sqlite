#!/usr/bin/env bash
# 同時書き込み・同時読み込みテスト
#
# 複数の Lambda 呼び出しを並列で実行して、S3 Files 越しの
# SQLite 同時アクセスの挙動を確認する

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESPONSE_DIR="/tmp/lambda_concurrent_responses"
mkdir -p "${RESPONSE_DIR}"

# CloudFormation の出力から Lambda 関数名を取得
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name LambdaS3SqliteStack \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text)
echo "関数名: ${FUNCTION_NAME}"

# -------------------------------------------------------
# テスト 1: 同時書き込み（5並列）
# -------------------------------------------------------
echo ""
echo "=== テスト1: 同時書き込み（5並列）==="

PIDS=()
for i in $(seq 1 5); do
  aws lambda invoke \
    --function-name "${FUNCTION_NAME}" \
    --payload "{\"action\": \"concurrent_write\", \"label\": \"worker${i}\"}" \
    --cli-binary-format raw-in-base64-out \
    "${RESPONSE_DIR}/write_${i}.json" \
    > /dev/null &
  PIDS+=($!)
  echo "  worker${i} を起動しました（PID: ${PIDS[-1]}）"
done

echo "  全 worker の完了を待機中..."
for pid in "${PIDS[@]}"; do
  wait "${pid}"
done

echo "  結果:"
for i in $(seq 1 5); do
  echo -n "  worker${i}: "
  python3 -c "
import json, sys
data = json.load(open('${RESPONSE_DIR}/write_${i}.json'))
body = data.get('body', data)
if isinstance(body, str):
    body = json.loads(body)
print(f\"commit={body.get('commit_ms')}ms, total={body.get('total_count')}件\")
"
done

# -------------------------------------------------------
# テスト 2: 同時読み込み（5並列）
# -------------------------------------------------------
echo ""
echo "=== テスト2: 同時読み込み（5並列）==="

PIDS=()
for i in $(seq 1 5); do
  aws lambda invoke \
    --function-name "${FUNCTION_NAME}" \
    --payload '{"action": "query_users"}' \
    --cli-binary-format raw-in-base64-out \
    "${RESPONSE_DIR}/read_${i}.json" \
    > /dev/null &
  PIDS+=($!)
done

echo "  全 reader の完了を待機中..."
for pid in "${PIDS[@]}"; do
  wait "${pid}"
done

echo "  結果:"
for i in $(seq 1 5); do
  echo -n "  reader${i}: "
  python3 -c "
import json
data = json.load(open('${RESPONSE_DIR}/read_${i}.json'))
body = data.get('body', data)
if isinstance(body, str):
    body = json.loads(body)
print(f\"count={body.get('count')}件\")
"
done

# -------------------------------------------------------
# 最終状態の確認
# -------------------------------------------------------
echo ""
echo "=== 最終状態確認 ==="
aws lambda invoke \
  --function-name "${FUNCTION_NAME}" \
  --payload '{"action": "db_info"}' \
  --cli-binary-format raw-in-base64-out \
  "${RESPONSE_DIR}/final.json" \
  > /dev/null

python3 -m json.tool "${RESPONSE_DIR}/final.json"

echo ""
echo "==> 完了"
