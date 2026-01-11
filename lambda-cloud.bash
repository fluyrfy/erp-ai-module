#!/bin/bash
set -e

echo "=== 1. 安裝 Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

echo "=== 2. 停止並禁用 systemd 服務（避免干擾）==="
sudo systemctl stop ollama || true
sudo systemctl disable ollama || true

echo "=== 3. 手動啟動 Ollama（綁定 0.0.0.0）==="
# 殺掉可能殘留的進程
pkill -f ollama || true

# 用 nohup 真正背景啟動
OLLAMA_HOST=0.0.0.0:11434 nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 10

echo "=== 3. 拉 GPT-OSS 20B ==="
ollama pull gpt-oss:20b

echo "⬇️ Pulling GPT-OSS 120B (Flagship/Reasoning)..."
ollama pull gpt-oss:120b

echo "=== 4. 驗證端口綁定 ==="
netstat -tuln | grep 11434


echo "=== 6. 最終驗證 ==="
curl http://localhost:11434/api/tags

echo "完成！外部可透過 http://$(curl -s ifconfig.me):11434 連線"