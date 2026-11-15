"""harness:actio 在 Rise 侧的新组合层。

移植件保留上游包路径(adapters/profiles/domain/evidence/interfaces/tasks);
本包只放**新写**的组合代码——P2 的预算制网关运行时与 D7 身份边界。
按 docs/merge/plan.md §3.2 的"三刀",这里只承接 store-free 的半边:
worker 生命周期 + campaign 无关的 profile 装配 + Ledger 记账;
Store 编排(fence/intent/op_update/Facts 认证)随 P3/P4 落地。
"""
