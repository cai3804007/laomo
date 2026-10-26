#!/bin/zsh
# 微信里复制文章链接后，在项目目录直接跑 ./go
cd "$(dirname "$0")" && exec ./.venv/bin/python mp/run.py "$@"
