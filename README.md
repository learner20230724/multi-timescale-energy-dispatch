# Multi-Timescale Energy Dispatch

[简体中文](./README.zh-CN.md)

A compact Python implementation of a multi-timescale energy dispatch workflow for a coupled **wind + solar + thermal + battery storage + P2G hydrogen + P2A ammonia** system. This repository keeps the original MATLAB model's core functional blocks while restructuring them into a smaller, easier-to-read, and easier-to-maintain Python project.

## Features

- Multi-objective day-ahead dispatch with NSGA-II
- Pareto compromise solution selection with feasibility screening and TOPSIS
- 15-minute intraday rolling storage adjustment
- Reproducible synthetic scenario generation with fixed random seeds
- Compact Python package layout with a CLI entrypoint
- Optional plotting for quick inspection of dispatch results

## Project Structure

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

## Installation

### Requirements

- Python 3.10+

### Install

```bash
pip install -e .
```

Install development dependencies:

```bash
pip install -e .
python -m pip install pytest
```

## Quick Start

Run a small smoke workflow:

```bash
energy-dispatch --pop-size 12 --max-gen 3
```

Run the default workflow and save results:

```bash
energy-dispatch --output results.json
```

Enable popup plots (separate windows):

```bash
energy-dispatch --plots
```

## GUI

Launch the graphical desktop interface:

```bash
energy-gui
```

or

```bash
energy-dispatch --gui
```

The GUI provides:

- **Summary tab**: all key metrics and the Pareto solution table
- **Log tab**: live run output
- **Pareto & Dispatch tab**: embedded Pareto front and dispatch curves
- **Intraday tab**: embedded storage and imbalance charts
- **Run**: start optimization with custom Pop / Gen / Seed parameters
- **Save Results**: export results as JSON
- **Save Figures**: export all charts as PDF or PNG
- **Clear**: reset the interface
```

## CLI Usage

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

### Main Options

- `--seed`: random seed
- `--pop-size`: NSGA-II population size
- `--max-gen`: number of generations
- `--crossover-prob`: crossover probability
- `--mutation-prob`: mutation probability
- `--intraday-error-sigma`: intraday forecast error scale
- `--plots`: enable plots
- `--quiet`: suppress console summary
- `--output`: export results to a JSON file

## Methodology

### Day-Ahead Optimization

The day-ahead stage keeps the original MATLAB semantics:

- generate wind, solar, and load forecasts
- build a joint system model
- decode a decision vector into thermal, storage, curtailment, P2G, and P2A schedules
- repair schedules to respect bounds and rebalance thermal generation
- simulate power balance, storage SOC, hydrogen/ammonia production and inventory, cost, carbon, and penalties
- optimize three objectives with NSGA-II
- select a compromise solution from the Pareto set using feasibility scoring and TOPSIS

### Intraday Adjustment

The intraday stage:

- expands the selected day-ahead plan to 96 quarter-hour steps
- perturbs renewable and load forecasts
- adjusts storage charging/discharging only
- tracks the day-ahead SOC reference
- falls back to the day-ahead storage trajectory if the adjusted net imbalance becomes worse

## Outputs

The workflow can produce three kinds of outputs:

### 1. Console summary
By default, the CLI prints a summary of:

- total cost
- total carbon emissions
- curtailment ratio
- maximum power-balance error
- final SOC
- intraday RMS deviation metrics
- fallback usage

### 2. JSON results
If `--output results.json` is provided, the project exports a JSON file containing:

- selected day-ahead solution metrics
- Pareto objectives
- Pareto selection details
- intraday charging/discharging trajectories
- SOC trajectories
- net imbalance diagnostics

### 3. Optional plots
If `--plots` is enabled and `matplotlib` is installed, the project opens visualization windows for:

- Pareto front
- day-ahead dispatch curves
- flexible asset schedules
- SOC tracking
- net imbalance comparison

## Development

Run tests:

```bash
python -m pytest tests
```

Run a quick CLI check:

```bash
energy-dispatch --pop-size 12 --max-gen 3 --quiet --output results.json
```

## Limitations

- The project uses synthetic input generation by default.
- `data1.p` from the MATLAB version is opaque and is not reproduced directly.
- The Python NSGA-II implementation may not match the MATLAB optimization trajectory exactly, even when the workflow remains functionally aligned.

## License

MIT
