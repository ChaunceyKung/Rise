"""actio 包的导入边界(P1 起)。

合并方案 D5/D7(docs/merge/plan.md §3.2)给 actio 定的纪律,在 P1 只落两条:

1. **合同层纯度**:`src/actio/contracts` 只许标准库白名单,禁止 os/subprocess/
   sqlite3/socket 等一切 I/O 与第三方依赖——这是它"跨仓字节兼容"的前提,
   做法沿用 Actio 仓 tests/test_modularity.py 的 AST 检查。
2. **双向隔离**:干净子进程里导入合同层不得连带载入 Rise 的任何包与 grpc/yaml;
   反向,P1 阶段 Rise 现有包还**不许** import actio——接线属于 P2 的 factory,
   在那之前谁也不许偷偷耦合。

actio 包 __init__ 保持零导入的原则也在此一并钉住。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
CONTRACTS = SRC / "actio" / "contracts"

# 合同层观察到的标准库闭包;新文件要引入新顶层模块时,必须在这里显式加白并给理由
STDLIB_ALLOWLIST = {"__future__", "json", "hashlib", "re", "dataclasses", "enum", "typing", "urllib"}
FORBIDDEN = {"os", "sys", "subprocess", "sqlite3", "socket", "threading", "pathlib", "grpc", "yaml", "jsonschema"}


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [node.module or ""]
    return names


def test_the_contracts_layer_imports_only_the_stdlib_allowlist():
    files = sorted(CONTRACTS.glob("*.py"))
    assert files, "contracts 目录不应为空"
    for path in files:
        for name in _imports_of(path):
            top = name.split(".")[0]
            assert top not in FORBIDDEN, f"{path.name}:{name} 禁止出现在合同层"
            if name.startswith("actio."):
                assert name.startswith("actio.contracts"), f"{path.name}:{name} 合同层不许依赖上层"
            else:
                assert top in STDLIB_ALLOWLIST, f"{path.name}:{name} 不在标准库白名单,新增需给理由扩白名单"


def test_the_actio_package_init_stays_import_free():
    text = (SRC / "actio" / "__init__.py").read_text(encoding="utf-8")
    assert _imports_of(SRC / "actio" / "__init__.py") == [], "actio/__init__.py 必须零导入"
    assert "零导入" in text


def _probe(body: str) -> subprocess.CompletedProcess:
    code = f"import sys\nsys.path.insert(0, {str(SRC)!r})\n" + body
    return subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False, timeout=60)


_HEAVY = ("grpc", "yaml", "jsonschema", "factory", "simple_actio", "mindagent", "recipestore", "controlplane")


@pytest.mark.parametrize("module", ["actio.contracts.json", "actio.contracts.memory", "actio.contracts.ports"])
def test_importing_the_contracts_does_not_pull_any_rise_package_or_heavy_dep(module):
    """干净子进程里只导入合同模块;Rise 的包与三件重依赖都不该被连带载入。"""
    body = (
        f"import {module}\n"
        f"heavy = {_HEAVY!r}\n"
        "print(sorted(k for k in sys.modules if any(k == h or k.startswith(h + '.') for h in heavy)))\n"
    )
    out = _probe(body)
    assert out.returncode == 0, f"importing {module} failed: {out.stderr[-500:]}"
    assert out.stdout.strip() == "[]", f"{module} 拉进了 {out.stdout.strip()}"


def test_no_existing_rise_package_imports_actio_yet():
    """P1 阶段的双向隔离另一半:Rise 现有包不许 import actio。

    P2 把 dsh backend 接进 factory 时,这条会按方案改成"只许 factory 导入";
    在此之前它防止任何提前耦合。
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "actio" in path.parts:
            continue
        for name in _imports_of(path):
            if name.split(".")[0] == "actio":
                offenders.append(f"{path.relative_to(SRC)}:{name}")
    assert offenders == [], f"P1 尚不允许导入 actio: {offenders}"
