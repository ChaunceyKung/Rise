# P0 基线记录（BASELINE）

> 记录时间：2026-11-15。机器：Windows 10/11 x64（原生，非 WSL），Python 3.12.x，uv 0.12.3。
> 用途：合并期间所有回归对比以本文件数字与失败名单为基准。**门槛 = 不出现"新的"失败**，而非"全绿"。

## 1. Rise（upstream main @ 7323c22）

- 环境：`uv sync --extra dev`（未装 `memory` extra；`memory_live` 标记默认不跑）。
- 命令：`uv run pytest -q --basetemp=<工作区>/.pytest-tmp-run3`（57:07）。
- 结果：**4864 passed / 189 failed / 130 skipped / 12 errors**（收集 5189 条；README 的"4811 passed"为 WSL 上的历史数字）。
- 已定性的失败簇（全部为 **Windows 环境不兼容**，非代码回归；upstream 开发环境为 WSL/Linux）：

| 簇 | 数量 | 根因 |
|---|---|---|
| factory memory/eval 配置类（test_factory_memory_config 56、memory_wiring 29、eval_config 15、wire_someval 9、memory_runtime 9 等） | ≈118 | `src/factory/memory_config.py::_check_private` 检查 POSIX 属主权限位，Windows `st_mode` 恒为宽权限 → 全部拒绝 |
| compute 远程层（test_compute_assistant 31、test_smoke_compute 10、test_compute_roll_deploy 12 errors） | ≈53 | `src/compute/endpoint.py::is_clean_abs_path` 只接受 POSIX 绝对路径（`/...`），`D:\...` 被拒 |
| 仓库锁（test_repo_lock 2） | 2 | Windows 对 `.git` 目录/锁文件独占打开语义不同 → `RepoLockedError` |
| 其余散点（test_bridge_cli 7、各文件 1 条共约 16） | ≈23 | 未逐一定性，量小；与合并模块交集时再triage |

- 平台差异备忘：仓库作者在 WSL 上开发（docs 明示"inotify 跨 WSL 不稳"）；本机无 WSL。
- 退出陷阱：`%TEMP%\pytest-of-CausalRider\pytest-current` 存在无法删除的陈旧 WSL 风格符号链接，令默认临时目录收尾崩溃并吞掉摘要行；**必须使用 `--basetemp` 指到干净目录**。

## 2. Actio-RSI-infra（main @ a718e7f）

- 环境：`powershell scripts/environment_setup.ps1`（pinned Python 3.12.13 于 `.local/python`、venv `.local/phase1-env`、哈希锁定 requirements*.lock、`.[environments]`+gin-config、pinned Concordia b71d202 源码闭包 242 文件）。
- 命令：`.local/phase1-env/Scripts/python -X utf8 -m unittest discover -s tests -p "test_*.py"`（≈41 分钟）。
- 结果：**186 tests / 9 failures / 6 errors / 2 skipped**（≈41 分钟，两轮结果一致，确定性失败；名单见 `baseline-failures-actio.txt`）。
- 环境踩坑记录（复现必需）：
  1. 仅装 requirements.lock 不够——测试内 episode 用 `.local/phase1-env` 解释器跑 worker，缺 Concordia 时报 `No module named 'concordia'`（首跑 65F+26E 即此因）。
  2. Concordia 不在 lock 中，必须 `scripts/bootstrap_concordia.py`（哈希校验的源码闭包直装 site-packages）。
- 失败定性（15 条，三类）：
  | 类 | 数量 | 判定 |
  |---|---|---|
  | A. 仓库自带缺陷：`test_evaluation_candidate_runtime.py:18` 导入 `SOURCE`，但 `test_evaluation_candidate.py` 无此名字 | 1 | **真缺陷**，P3 移植 evaluation 系列时须修复 |
  | B. Windows 权限语义：`PermissionError: [Errno 13] 'tests'`（evidence/suite_evidence 2 条 ERROR） | 2 | 环境性 |
  | C. gateway/pilot 回环 receives 为空（`0 != 4`/`0 != 2`，test_gateway 6、test_gateway_lifecycle 1、test_pilot_runtime 2、test_evidence 1） | 12 | 疑环境性（loopback/mjs 插件在 Windows 的行为差异），**P2 移植 gateway 时根治**（对应 T-A 用例） |

## 3. 凭据与安全

- TokenKey 凭据：`merge_project_2611/api_key/tokenkey.txt` → 已复制到 Actio 仓 `.local/credentials/token_key.txt`（git 确认忽略）。
- Rise fork 为 public 仓库：**任何凭据不得进入 Rise 工作树**；本轮全部测试为 stub/rehearsal，零真实付费调用（方案 R5 纪律）。
- 两仓均无顶层 LICENSE；Actio 内嵌第三方许可（SOTOPIA_LICENSE、DSH_LICENSE.txt）须随对应代码迁移。

## 4. 回归门槛（合并期间生效）

1. Rise：与本次 Windows 基线的失败名单做集合对比，不允许新增（`docs/merge/` 下维护对比脚本/清单）。
2. Actio 移植套件：以本基线的 186 条为准，移植后同套件在 Rise 下全绿（允许 skip 标记差异）。
3. B0/C1 golden：P3 起以 Actio 仓当前输出为 golden file。

## 5. 阶段门禁记录

| 阶段 | 日期 | 结果 | 对比 |
|---|---|---|---|
| P0 | 2026-11-15 | 基线建立 | Rise 4864P/189F/130S/12E;Actio 186T/9F/6E/2S |
| P1 | 2026-11-15 | **通过** | Rise 4914P/188F/130S/12E(+49 契约/边界测试);新增失败 0(docs/merge/compare_failures.py);消失 1 条为已知易抖的 test_repo_lock 文件锁用例 |
| P2 | 2026-11-15 | Actio 侧:gateway 12 失败根因(80 字符上限)已修复全绿 | 剩余已知失败=1 真缺陷(SOURCE 导入,P3 修)+2 Windows 权限语义 |
| P2 | 2026-11-15 | **通过** | Rise 4924P/188F/130S/12E:新增失败 0(+10 测试:契约 49 已在 P1 计入,本轮 harness/memory/边界);消失 1 条仍为易抖文件锁用例 |
| P3 | 2026-11-15 | **通过** | Rise 4940P/189F/130S/12E:新增失败 0(+16 测试:T-M 15+D1 桥 2,golden 跨仓一致);B0/C1/POLICY 摘要两仓一致 |
| P4a | 2026-11-15 | **通过** | Rise 4943P/189F/130S/12E:新增失败 0(+3 测试:迁移链/生命周期/候选谱系);P4b=envelope 桥/evaluation 谱系/SOURCE 修复 |
| P4b | 2026-11-16 | **通过** | Rise 4947P/190F→修正后无新增(+12 测试:outbox/evaluation 链/envelope 桥);新增 1 条为上游旧边界测试,已按合并语义放行 actio |
| P5 | 2026-11-16 | **通过(合并完成)** | 文档收尾+源仓 SOURCE 修复;actio 组 87 条全绿;全量回归 4948P/189F/130S/12E,新增失败 0(201=201) |
| M1 | 2026-11-16 | **通过** | Rise 4958P/190F/130S/12E:新增 11 测试全绿;唯一新增失败经父提交 worktree 复现实锤为环境性句柄竞态,已单独修复(基线名单注明) |
| M2 | 2026-11-16 | **通过** | Rise 4977P/188F/130S/12E:新增失败 0(+17 测试);消失 2 条=历史易抖文件锁+本分支已修复的 starling 句柄竞态转绿;首跑 exit=127 原生偶发崩溃,重跑全程绿(P0 期已知形态) |
| M3 | 2026-11-16 | **通过** | Rise 4984P/189F/130S/12E:新增失败 0(+8 测试);已修 starling 竞态转绿;代理 7993 持续断连,2 个提交待补推 |
| M4 | 2026-11-16 | **通过** | Rise 4991P/189F/130S/12E:新增失败 0(+7 测试);agent_backend 接线一度破 11 条既有测试(frozen setattr),已按正规字段修复并全绿 |
