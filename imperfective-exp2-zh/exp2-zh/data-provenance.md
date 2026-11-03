# 实验 2（中文版）数据与来源核对（S0）

## 1. 锁定资产 SHA-256
- `clusters_100_curated.json`：`963636a2a74a38f8b8fe6363a079be38f5f2f1b35ef37f1cf3fc89dd7fd6c437`
- `seed_clusters_18.json`：`6f31e854e1b34e01315bb8804bc0f70d93995d81cee6fc1e39264fe24ba92db5`
- `split.json`：`6382d84a293107215ab034d565415adc8f0a438d90152f4c2b2e9a8d868c3973`
- `exact-tango-tables-e2.npz`：`2eb9bfd0db577301c44e5a49ad5ed1d4296b33031db7b54c78710e11043115a6`

## 2. 簇与条目结构核验
- 事件簇总数：`100`（终结类 `60` 簇：建造/创制 `26`、状态改变 `18`、消耗 `10`、趋向目标位移 `6`；非终结活动类 `40` 簇：纯无界活动 `20`、带常见计划活动 `20`）。
- 展开条目总数：`600`（主实验题 `400` 条 + 诊断语境题 `200` 条）。
- `validate_materials.py` 机械与形态校验：`100/100` 簇零错误通过。
