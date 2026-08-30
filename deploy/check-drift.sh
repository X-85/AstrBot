#!/bin/bash
# 校验 deploy/astrbot/ 载荷与生产线分支自身的文件是否一致（防漂移）。
# 用法：bash check-drift.sh   （在仓库根目录执行；无输出 = 无漂移）

set -e
cd "$(dirname "$0")/.."

payload_files="$(cd deploy/astrbot && find . -type f | sed 's|^\./||')"

drift=0
for rel in $payload_files; do
    if ! diff -q "deploy/astrbot/$rel" "astrbot/$rel" >/dev/null 2>&1; then
        echo "[drift] deploy/astrbot/$rel 与分支文件不一致"
        drift=1
    fi
done

if [ "$drift" = "0" ]; then
    echo "[ok] deploy 载荷与 company 分支文件一致，无漂移"
else
    echo "[!!] 发现漂移：请以分支文件为准重新拷贝到 deploy/astrbot/ 后提交"
    exit 1
fi
