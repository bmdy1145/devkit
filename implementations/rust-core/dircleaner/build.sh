#!/usr/bin/env bash
# 构建 DirCleaner 内核版（Rust）
set -euo pipefail
cd "$(dirname "$0")"
source ../../../toolchains.env
cargo build --release
echo "产物：$(pwd)/target/release/dircleaner.exe"
