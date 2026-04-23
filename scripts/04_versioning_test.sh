#!/usr/bin/env bash
# S3 バージョニングの挙動確認スクリプト
# 1. 書き込み前のバージョン一覧を確認する
# 2. Lambda で INSERT して S3 への同期（約 60 秒）を待つ
# 3. バージョンが増えているか確認する
# 4. 古いバージョンをダウンロードしてロールバックできるか確認する
set -euo pipefail

STACK_NAME="LambdaS3SqliteStack"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" \
  --output text)

FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" \
  --output text)

echo "=== バケット: $BUCKET_NAME ==="
echo ""

# -----------------------------------------------------------
# 1. 書き込み前のバージョン一覧
# -----------------------------------------------------------
echo "=== [1] 書き込み前のバージョン一覧 ==="
aws s3api list-object-versions \
  --bucket "$BUCKET_NAME" \
  --prefix "database.db" \
  --region "$REGION" \
  --query "Versions[].{VersionId:VersionId, LastModified:LastModified, IsLatest:IsLatest}" \
  --output table

BEFORE_COUNT=$(aws s3api list-object-versions \
  --bucket "$BUCKET_NAME" \
  --prefix "database.db" \
  --region "$REGION" \
  --query "length(Versions)" \
  --output text)
echo "書き込み前のバージョン数: $BEFORE_COUNT"
echo ""

# -----------------------------------------------------------
# 2. Lambda で INSERT して同期を待つ
# -----------------------------------------------------------
echo "=== [2] Lambda で INSERT（3件）==="
for i in 1 2 3; do
  aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --payload "{\"action\": \"insert_user\", \"name\": \"VersionTest${i}\", \"email\": \"vtest${i}@example.com\"}" \
    --region "$REGION" \
    /tmp/version_insert_${i}.json > /dev/null
  echo "INSERT ${i} 完了: $(cat /tmp/version_insert_${i}.json)"
done
echo ""

echo "=== [3] S3 への同期を待つ（70秒）==="
for i in $(seq 70 -10 10); do
  echo "  残り ${i} 秒..."
  sleep 10
done
echo ""

# -----------------------------------------------------------
# 3. バージョンが増えているか確認
# -----------------------------------------------------------
echo "=== [4] 書き込み後のバージョン一覧 ==="
aws s3api list-object-versions \
  --bucket "$BUCKET_NAME" \
  --prefix "database.db" \
  --region "$REGION" \
  --query "Versions[].{VersionId:VersionId, LastModified:LastModified, IsLatest:IsLatest}" \
  --output table

AFTER_COUNT=$(aws s3api list-object-versions \
  --bucket "$BUCKET_NAME" \
  --prefix "database.db" \
  --region "$REGION" \
  --query "length(Versions)" \
  --output text)
echo "書き込み後のバージョン数: $AFTER_COUNT（増加: $((AFTER_COUNT - BEFORE_COUNT))）"
echo ""

# -----------------------------------------------------------
# 4. 古いバージョン（最新より1つ前）をダウンロードしてロールバック確認
# -----------------------------------------------------------
echo "=== [5] 1つ前のバージョンをダウンロードしてレコード数を確認 ==="
OLD_VERSION=$(aws s3api list-object-versions \
  --bucket "$BUCKET_NAME" \
  --prefix "database.db" \
  --region "$REGION" \
  --query "Versions[?IsLatest==\`false\`] | sort_by(@, &LastModified) | [-1].VersionId" \
  --output text)

if [ "$OLD_VERSION" = "None" ] || [ -z "$OLD_VERSION" ]; then
  echo "古いバージョンが見つかりません（バージョン数が 1 のみ）"
else
  echo "ダウンロードするバージョン ID: $OLD_VERSION"
  aws s3api get-object \
    --bucket "$BUCKET_NAME" \
    --key "database.db" \
    --version-id "$OLD_VERSION" \
    --region "$REGION" \
    /tmp/database_old.db > /dev/null
  echo "古いバージョンのレコード数:"
  python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/database_old.db')
count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
rows = conn.execute('SELECT id, name FROM users ORDER BY id').fetchall()
print(f'  count = {count}')
for r in rows:
    print(f'  id={r[0]}, name={r[1]}')
conn.close()
"
  echo ""
  echo "最新バージョンのレコード数:"
  aws s3 cp "s3://$BUCKET_NAME/database.db" /tmp/database_latest.db --region "$REGION" > /dev/null
  python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/database_latest.db')
count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
rows = conn.execute('SELECT id, name FROM users ORDER BY id').fetchall()
print(f'  count = {count}')
for r in rows:
    print(f'  id={r[0]}, name={r[1]}')
conn.close()
"
fi

echo ""
echo "=== 完了 ==="
