#!/bin/bash
# AstrBot 核心文件一键替换脚本（docker cp 方式，含替换前备份）
# 用法：把本脚本和 astrbot/ 目录放到服务器同一目录，然后：
#       bash replace.sh
# 流程：备份容器内原文件到 astrbot-bak/ -> 替换补丁文件 -> 重启容器使生效。

set -e

CONTAINER=astrbot
DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$DEPLOY_DIR/astrbot"
BACKUP_DIR="$DEPLOY_DIR/astrbot-bak"

echo "[*] 检查容器 $CONTAINER ..."
docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER" || { echo "[!] 容器 $CONTAINER 不存在，请先创建容器再执行本脚本"; exit 1; }

# 容器未运行时先启动（备份/替换需要容器在线）
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "[*] 容器未运行，先启动 ..."
    docker start "$CONTAINER"
fi

mkdir -p "$BACKUP_DIR"

count=0
while IFS= read -r f; do
    # rel 保留 astrbot/ 前缀（相对 deploy/），容器内对应 /AstrBot/astrbot/...
    rel="${f#$DEPLOY_DIR/}"
    target="/AstrBot/$rel"
    bak="$BACKUP_DIR/$rel"

    # 1) 备份容器内原文件
    if docker exec "$CONTAINER" test -f "$target"; then
        mkdir -p "$(dirname "$bak")"
        docker cp "$CONTAINER:$target" "$bak"
        echo "[bak] $target -> astrbot-bak/$rel"
    else
        echo "[!!] 容器内不存在 $target（新增文件），跳过备份"
        # 新增文件：先创建父目录，否则 docker cp 目标目录不存在会失败
        docker exec "$CONTAINER" mkdir -p "$(dirname "$target")"
    fi

    # 2) 替换
    docker cp "$f" "$CONTAINER:$target"
    echo "[ok] -> $target"
    count=$((count + 1))
done < <(find "$SRC_DIR" -type f)

echo "[*] 已替换 $count 个文件，重启容器使生效 ..."
docker restart "$CONTAINER"
echo "[done] 完成。备份在 $BACKUP_DIR"
echo "[rollback] 如需回滚: bash rollback.sh"
