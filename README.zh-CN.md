# Multi-Timescale Energy Dispatch

[English](./README.md)

这是一个更精简的 Python 版本，用于实现 **风电 + 光伏 + 火电 + 储能 + P2G 制氢 + P2A 制氨** 耦合系统的多时间尺度调度。仓库保留了原 MATLAB 模型的核心功能链路，同时将结构重构为更小、更清晰、更适合阅读和维护的 Python 项目。

## 功能特性

- 使用 NSGA-II 进行日前多目标调度
- 通过可行性筛选和 TOPSIS 从 Pareto 解中选择折中方案
- 支持 15 分钟尺度的日内储能滚动校正
- 支持固定随机种子的可复现场景生成
- 项目结构紧凑，提供命令行入口
- 可选绘图，便于快速查看调度结果

## 项目结构

```text
multi-timescale-energy-dispatch/
  README.md
  README.zh-CN.md
  LICENSE
  pyproject.toml
  src/
    energy_dispatch/
      __init__.py
      config.py
      simulation.py
      optimization.py
      intraday.py
      cli.py
      gui.py
  tests/
    test_smoke.py
    test_reference.py
```

## 安装

### 环境要求

- Python 3.10+

### 安装项目

```bash
pip install -e .
```

安装开发依赖：

```bash
pip install -e .
python -m pip install pytest
```

## 快速开始

运行一个较小规模的冒烟流程：

```bash
energy-dispatch --pop-size 12 --max-gen 3
```

运行默认流程并导出结果：

```bash
energy-dispatch --output results.json
```

启用弹窗绘图：

```bash
energy-dispatch --plots
```

## 图形界面

启动桌面图形界面：

```bash
energy-gui
```

或

```bash
energy-dispatch --gui
```

图形界面提供：

- **摘要标签页**：全部关键指标和 Pareto 解表格
- **日志标签页**：实时运行输出
- **Pareto 与调度标签页**：内嵌 Pareto 前沿和调度曲线图
- **日内标签页**：内嵌储能和净不平衡对比图
- **运行**：用自定义 Pop / Gen / Seed 参数开始优化
- **保存结果**：将结果导出为 JSON
- **保存图片**：将所有图表导出为 PDF 或 PNG
- **清除**：重置界面
```

## 命令行用法

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

### 主要参数

- `--seed`：随机种子
- `--pop-size`：NSGA-II 种群规模
- `--max-gen`：迭代代数
- `--crossover-prob`：交叉概率
- `--mutation-prob`：变异概率
- `--intraday-error-sigma`：日内预测误差尺度
- `--plots`：启用绘图
- `--quiet`：关闭控制台摘要输出
- `--output`：导出 JSON 结果文件

## 方法说明

### 日前优化

日前阶段基本保持了 MATLAB 版本的语义：

- 生成风电、光伏和负荷预测
- 构建统一系统模型
- 将决策向量解码为火电、储能、弃电、P2G、P2A 调度方案
- 对调度方案进行边界修复和火电再平衡
- 仿真功率平衡、储能 SOC、氢/氨产供与库存、成本、碳排放和惩罚项
- 使用 NSGA-II 对三个目标进行优化
- 通过可行性评分和 TOPSIS 从 Pareto 集中选出折中方案

### 日内校正

日内阶段会：

- 将选中的日前方案扩展为 96 个 15 分钟时段
- 对风光和负荷预测加入扰动
- 仅调整储能充放电
- 跟踪日前 SOC 参考轨迹
- 当日内调整后的净不平衡更差时，回退到日前储能轨迹

## 输出内容

这个项目可以产生三类输出：

### 1. 控制台摘要
默认情况下，命令行会打印：

- 总成本
- 总碳排放
- 弃电率
- 最大功率平衡误差
- 最终 SOC
- 日内 RMS 偏差指标
- 是否触发 fallback

### 2. JSON 结果文件
如果传入 `--output results.json`，项目会导出 JSON 文件，其中包含：

- 选中的日前调度方案指标
- Pareto 目标值
- Pareto 解选择细节
- 日内充放电轨迹
- SOC 轨迹
- 净不平衡诊断指标

### 3. 可选可视化图形
如果使用 `--plots` 且已安装 `matplotlib`，程序会弹出图形窗口，展示：

- Pareto 前沿
- 日前调度曲线
- 灵活资源出力曲线
- SOC 跟踪曲线
- 净不平衡对比图

## 开发说明

运行测试：

```bash
python -m pytest tests
```

快速检查命令行流程：

```bash
energy-dispatch --pop-size 12 --max-gen 3 --quiet --output results.json
```

## 局限性

- 项目默认使用合成输入数据。
- MATLAB 版本中的 `data1.p` 为不可见 P-code，本项目未直接复刻。
- Python 版本的 NSGA-II 优化轨迹未必与 MATLAB 完全逐点一致，但整体流程与功能语义保持一致。

## 许可证

MIT
