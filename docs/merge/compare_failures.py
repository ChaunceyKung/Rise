#!/usr/bin/env python
"""对比新一次 pytest 全量日志与基线失败名单(BASELINE.md §4 门槛检查)。
两边的行都归一成"测试 id"(切掉 pytest 的 " - 消息"尾巴),再比集合。
用法: python compare_failures.py <new_log> <baseline_file>
"""
import re
import sys
from pathlib import Path

new_log, baseline_file = sys.argv[1], sys.argv[2]


def ids_from_log(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out = set()
    for line in text.splitlines():
        # 摘要行形如 "FAILED <id>" / "ERROR <id>";有的环境会再附 " - 消息",一并切掉
        for prefix in ("FAILED ", "ERROR "):
            if line.startswith(prefix):
                tid = line[len(prefix):].split(" - ")[0].strip()
                # teardown 错误文本可能无分隔符粘在 id 尾部(session ... join failed)
                tid = re.sub(r"session sess-[0-9a-f]+ lingering resources join failed: \w+$", "", tid).strip()
                out.add(tid)
                break
    return out


def ids_from_baseline(path: Path) -> set[str]:
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.add(line.split(" - ")[0].strip())
    return out


new = ids_from_log(Path(new_log))
base = ids_from_baseline(Path(baseline_file))
added = sorted(new - base)
removed = sorted(base - new)
print(f"baseline={len(base)} new={len(new)}")
print(f"NEW failures ({len(added)}):")
for m in added:
    print("  +", m)
print(f"DISAPPEARED ({len(removed)}):")
for m in removed:
    print("  -", m)
sys.exit(1 if added else 0)
