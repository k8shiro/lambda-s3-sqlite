FROM python:3.12-slim

# Node.js をインストール（CDK CLI の実行に必要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    nodejs \
    npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# AWS CDK CLI をインストール
RUN npm install -g aws-cdk

# AWS CLI v2 をインストール
RUN pip install --no-cache-dir awscli

# CDK アプリの Python 依存パッケージをインストール
COPY cdk/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /workspace
