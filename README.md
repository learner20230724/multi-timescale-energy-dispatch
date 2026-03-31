# Multi-Timescale Energy Dispatch

A compact Python implementation of a multi-timescale energy dispatch workflow for a coupled **wind + solar + thermal + battery storage + P2G hydrogen + P2A ammonia** system. The project keeps the original MATLAB model's main functional blocks while restructuring them into a smaller, more maintainable Python package.

一个更精简的 Python 版本，用于实现 **风电 + 光伏 + 火电 + 储能 + P2G 制氢 + P2A 制氨** 耦合系统的多时间尺度调度。该项目保留了原 MATLAB 版本的核心功能链路，同时将结构压缩为更适合阅读、维护和公开展示的 Python 项目。

## Features / 功能概览

- Multi-objective day-ahead dispatch with NSGA-II
- Pareto-front compromise solution selection with feasibility screening + TOPSIS
- 15-minute intraday rolling storage adjustment
- Synthetic scenario generation with reproducible random seeds
- Compact package layout with CLI entrypoint
- Optional plotting support for quick result inspection

- 使用 NSGA-II 进行日前多目标调度
- 使用“可行性筛选 + TOPSIS”从 Pareto 解中选取折中方案
- 支持 15 分钟尺度的日内储能滚动校正
- 内置可复现实验场景生成逻辑
- 项目结构紧凑，带命令行入口
- 可选绘图，用于快速查看结果

## System Overview / 系统概览

The workflow contains two layers:

1. **Day-ahead layer**: generates 24-hour forecasts, evaluates candidate schedules, optimizes three objectives, and selects one compromise plan from the Pareto set.
2. **Intraday layer**: expands the selected day-ahead plan to 15-minute resolution, injects forecast errors, and adjusts storage charging/discharging while keeping thermal, P2G, and P2A schedules fixed.

整个流程包含两层：

1. **日前层**：生成 24 小时预测，评估候选调度方案，对“成本、碳排放、弃电率”进行多目标优化，并从 Pareto 集中选出一个折中方案。
2. **日内层**：将日前方案扩展到 15 分钟粒度，加入预测误差，在固定火电、P2G、P2A 的前提下，通过储能进行滚动校正。

## Repository Structure / 项目结构

```text
multi-timescale-energy-dispatch/
  README.md
  pyproject.toml
  src/
    energy_dispatch/
      __init__.py
      config.py
      simulation.py
      optimization.py
      intraday.py
      cli.py
  tests/
    test_smoke.py
    test_reference.py
```

### Module summary / 模块说明

- `config.py`: default parameters, scenario generation, model dataclasses
- `simulation.py`: dispatch decoding, repair, simulation, objective evaluation
- `optimization.py`: NSGA-II workflow and Pareto compromise solution selection
- `intraday.py`: intraday rolling storage adjustment
- `cli.py`: command-line entrypoint and result export

- `config.py`：默认参数、场景生成、模型数据结构
- `simulation.py`：调度解码、修复、仿真、目标值计算
- `optimization.py`：NSGA-II 优化流程与 Pareto 折中解选择
- `intraday.py`：日内滚动储能校正
- `cli.py`：命令行入口与结果导出

## Installation / 安装

### Requirements / 环境要求

- Python 3.10+

### Install locally / 本地安装

```bash
pip install -e .
```

For development and tests:

```bash
pip install -e .[dev]
```

For plotting support:

```bash
pip install -e .[plot]
```

开发和测试安装：

```bash
pip install -e .[dev]
```

如果需要绘图支持：

```bash
pip install -e .[plot]
```

## Quickstart / 快速开始

Run a small smoke configuration:

```bash
energy-dispatch --pop-size 12 --max-gen 3
```

Run a larger default workflow and save results:

```bash
energy-dispatch --output results.json
```

Enable plots:

```bash
energy-dispatch --plots
```

快速运行一个较小配置：

```bash
energy-dispatch --pop-size 12 --max-gen 3
```

运行默认流程并导出结果：

```bash
energy-dispatch --output results.json
```

启用绘图：

```bash
energy-dispatch --plots
```

## CLI Usage / 命令行用法

```bash
energy-dispatch \
  --seed 42 \
  --pop-size 80 \
  --max-gen 100 \
  --crossover-prob 0.85 \
  --mutation-prob 0.06 \
  --intraday-error-sigma 0.02 \
  --output results.json
```

### Main options / 主要参数

- `--seed`: random seed / 随机种子
- `--pop-size`: NSGA-II population size / 种群规模
- `--max-gen`: number of generations / 迭代代数
- `--crossover-prob`: crossover probability / 交叉概率
- `--mutation-prob`: mutation probability / 变异概率
- `--intraday-error-sigma`: intraday forecast error scale / 日内预测误差尺度
- `--plots`: enable plotting / 启用绘图
- `--quiet`: suppress console summary / 静默运行
- `--output`: write JSON results / 输出 JSON 结果

## Methodology / 方法说明

### Day-ahead optimization / 日前优化

The day-ahead stage keeps the original MATLAB semantics:

- generate wind, solar, and load forecasts
- build a joint system model
- decode a decision vector into thermal / storage / curtailment / P2G / P2A schedules
- repair the schedule to respect bounds and rebalance thermal generation
- simulate power balance, storage SOC, hydrogen/ammonia production and inventory, cost, carbon, and penalties
- optimize the three objectives with NSGA-II
- choose one compromise solution from the Pareto set using feasibility scoring and TOPSIS

日前阶段基本保留原 MATLAB 版本的语义：

- 生成风电、光伏、负荷预测
- 构建统一系统模型
- 将决策向量解码为火电、储能、弃电、P2G、P2A 调度方案
- 对方案进行边界修复与火电再平衡
- 仿真功率平衡、SOC、氢/氨产供与库存、成本、碳排放及惩罚项
- 使用 NSGA-II 进行三目标优化
- 通过可行性评分与 TOPSIS 在 Pareto 集中选出折中方案

### Intraday adjustment / 日内校正

The intraday stage:

- expands the day-ahead plan to 96 quarter-hour steps
- perturbs renewable/load forecasts
- adjusts storage only
- tracks the day-ahead SOC reference
- uses fallback logic when the adjusted net imbalance is worse than simply following the day-ahead storage trajectory

日内阶段：

- 将日前方案扩展为 96 个 15 分钟时段
- 对风光负荷预测引入扰动
- 仅调整储能充放电
- 跟踪日前 SOC 参考轨迹
- 当日内调整效果劣于直接执行日前储能轨迹时，自动回退

## Outputs / 输出结果

The pipeline returns and can export:

- selected day-ahead schedule metrics
- Pareto objectives
- intraday charging/discharging trajectories
- SOC tracking results
- net imbalance diagnostics
- selection details for the chosen Pareto solution

流程运行后可返回并导出：

- 选定日前调度方案的指标
- Pareto 目标值集合
- 日内充放电轨迹
- SOC 跟踪结果
- 净不平衡诊断指标
- Pareto 折中解的选择细节

## Verification / 验证方式

Suggested local validation steps:

1. Run the smoke test suite.
2. Run a small end-to-end workflow with a fixed seed.
3. Inspect objective values, SOC trajectories, and intraday imbalance metrics.
4. Compare key outputs with the MATLAB model where necessary.

建议本地验证步骤：

1. 运行测试集。
2. 用固定随机种子执行一次小规模端到端流程。
3. 检查目标值、SOC 轨迹和日内净不平衡指标。
4. 如有需要，再与 MATLAB 结果做关键指标对比。

## Development / 开发说明

Run tests:

```bash
pytest
```

Run a quick CLI check:

```bash
energy-dispatch --pop-size 12 --max-gen 3 --quiet --output results.json
```

运行测试：

```bash
pytest
```

快速检查命令行流程：

```bash
energy-dispatch --pop-size 12 --max-gen 3 --quiet --output results.json
```

## Limitations / 局限性

- The project uses synthetic input generation by default.
- `data1.p` from the MATLAB version is opaque and is not reproduced directly.
- Using a Python NSGA-II library means optimization trajectories may differ from MATLAB even when the workflow remains functionally aligned.

- 项目默认使用合成输入数据。
- MATLAB 版本中的 `data1.p` 为不可见 P-code，本项目未直接复刻。
- 由于使用 Python 主流 NSGA-II 库，优化轨迹未必与 MATLAB 完全逐点一致，但整体流程和语义保持一致。

## License / 许可证

MIT
