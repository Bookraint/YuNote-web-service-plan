#!/usr/bin/env python3
"""
将本地 .env 同步到 Hugging Face Space 的 Variables / Secrets（均表现为容器内环境变量）。

依赖：
    pip install huggingface_hub python-dotenv

认证（任选其一）：
    - 环境变量 HF_TOKEN（需具备该 Space 的写权限）
    - 命令行 --token

用法示例：
    export  HF_TOKEN=hf_xxx
    export  HF_SPACE_REPO=yourname/YuNote
    python scripts/sync_hf_space_env.py -f .env

    python scripts/sync_hf_space_env.py -f .env --dry-run 

    # 仅把部分键作为「公开变量」，其余作为「私密 Secret」
    python scripts/sync_hf_space_env.py -f .env --public-keys CORS_ORIGINS,MAX_UPLOAD_MB

说明：
    - 默认所有键使用 add_space_secret（控制台不可见值，更安全）。
    - --public-keys 中的键使用 add_space_variable（值在设置页可见，适合非敏感配置）。
    - 每次变更会触发 Space 重启（Hub 行为）。
文档：https://huggingface.co/docs/huggingface_hub/guides/manage-spaces
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values


def _parse_public_keys(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def _load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"找不到 .env 文件: {path.resolve()}")
    raw = dotenv_values(path)
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        key = (k or "").strip()
        if not key or key.startswith("#"):
            continue
        out[key] = v
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="将 .env 同步到 Hugging Face Space（Secrets / Variables）",
    )
    parser.add_argument(
        "space",
        nargs="?",
        default=os.environ.get("HF_SPACE_REPO"),
        help="Space 仓库 id，如 username/YuNote；也可设环境变量 HF_SPACE_REPO",
    )
    parser.add_argument(
        "-f",
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="要读取的 .env 路径（默认：当前目录下的 .env）",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face User Access Token（或设环境变量 HF_TOKEN）",
    )
    parser.add_argument(
        "--public-keys",
        default="",
        help="逗号分隔：这些键同步为「公开变量」add_space_variable，其余为 Secret",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要设置的键名与类型，不调用 API",
    )
    args = parser.parse_args()

    if not args.space:
        print(
            "错误：请提供 Space id（例如 yourname/YuNote），或设置环境变量 HF_SPACE_REPO。",
            file=sys.stderr,
        )
        return 2

    token = args.token
    if not token and not args.dry_run:
        print(
            "错误：未提供 HF Token。请设置环境变量 HF_TOKEN 或使用 --token。",
            file=sys.stderr,
        )
        return 2

    try:
        env_map = _load_env(args.env_file)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not env_map:
        print(f"警告：{args.env_file} 中没有可同步的键。", file=sys.stderr)
        return 1

    public = _parse_public_keys(args.public_keys)

    if not args.dry_run:
        try:
            from huggingface_hub import HfApi
            from huggingface_hub.utils import HfHubHTTPError
        except ImportError:
            print(
                "错误：请先安装依赖：pip install huggingface_hub python-dotenv",
                file=sys.stderr,
            )
            return 2
        api = HfApi(token=token)
    else:
        api = None

    print(f"Space: {args.space}")
    print(f".env: {args.env_file.resolve()}")
    print(f"键数量: {len(env_map)}")
    print("-" * 40)

    for key in sorted(env_map.keys()):
        value = env_map[key]
        is_public = key in public
        kind = "variable" if is_public else "secret"
        preview = "(empty)" if value == "" else f"{len(value)} chars"

        if args.dry_run:
            print(f"  [{kind}] {key} = {preview}")
            continue

        assert api is not None
        try:
            if is_public:
                api.add_space_variable(repo_id=args.space, key=key, value=value)
            else:
                api.add_space_secret(repo_id=args.space, key=key, value=value)
            print(f"  OK [{kind}] {key}")
        except HfHubHTTPError as e:
            print(f"  FAIL [{kind}] {key}: {e}", file=sys.stderr)
            return 1

    if args.dry_run:
        print("-" * 40)
        print("（dry-run，未写入 Hub）")
    else:
        print("-" * 40)
        print("已提交。Space 将自动重启以应用新环境变量。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
