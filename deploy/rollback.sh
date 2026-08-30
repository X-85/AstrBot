#!/bin/bash
# AstrBot 回滚脚本：用 astrbot-bak/ 里的备份恢复容器内文件并重启
# 用法：bash rollback.sh
# 说明：只恢复 astrbot-bak/ 里存在的文件；备份里没有的文件（新增文件）不会删除。

set -e

CONTAINER=astrbot
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$DEPLOY_DIR/astrbot-bak"

echo "[*] 检查容器 $CONTAINER ..."
docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" || { echo "[!] 容器 $CONTAINER 不存在"; exit 1; }

if [ ! -d "$BACKUP_DIR" ] || [ -z "$(find "$BACKUP_DIR" -type f)" ]; then
    echo "[!] astrbot-bak/ 为空或不存在，没有可回滚的备份"
    exit 1
fi

count=0
while IFS= read -r f; do
    rel="${f#$BACKUP_DIR/}"
    docker cp "$f" "$CONTAINER:/AstrBot/$rel"
    echo "[ok] 恢复 -> /AstrBot/$rel"
    count=$((count + 1))
done < <(find "$BACKUP_DIR" -type f)

echo "[*] 已恢复 $count 个文件，重启容器 ..."
docker restart "$CONTAINER"
echo "[done] 回滚完成。"
