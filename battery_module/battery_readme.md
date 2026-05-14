# 1 项目名称

光伏清扫机器人电池仿真模块，模拟电池电量（SOC）、电压、健康度（SOH）的动态变化，实时更新数据供上层系统使用，帮助验证电池管理策略。

---

# 2 项目背景

光伏清扫机器人在运行中需要实时掌握电池状态（电量，电压，健康度），以便优化作业策略和避免过放损坏。然而，依赖真实电池和BMS进行算法验证成本高，周期长。

本项目构建了一个电池行为仿真模块，能够动态模拟SOC、电压、SOH的实时变化，并通过统一接口向上册（如测试脚本、SCADA系统）提供数据。开发者可以基于该模块快速验证电池管理逻辑，
为后续智能运维（如充电调度、寿命预测）提供仿真基础。

---

# 3 系统架构图

battery_module/BatterySimulator系统架构图.png
---

# 4 功能模块

| 模块 | 说明 |
|------|------|
| `_simulate_data()` | 模拟数据生成器。内部模拟算法，周期性更新电池的电压，SOC，SOH。该函数不对外暴露，由后台线程 `_monitor_loop` 自动触发。 |
| `get_status()` | 对外数据接口。供上层（测试脚本，SCADA系统等）调用。返回一个包含最新电池状态的字典，格式为 `{"voltage":float, "soc":float, "soh":float, "temperature":float}` |
| `load_config()` | 配置加载。从 `battery_config.yaml` 读取运行时参数，包括更新间隔、标称容量、环境温度、电压曲线等。这些配置直接影响模拟行为的动态特性（如soc下降速度，温度对寿命的影响）。 |
| `_log_data()` | 日志记录。将每次更新的状态（含时间戳）追加到 `battery_log.csv` 文件，用于离线分析和功能验证，不干扰主数据流。 |
| `_monitor_loop()` | 后台线程循环。在 `start_monitoring()` 启动后运行，按 `update_interval` 秒的间隔重复调用 `_simulate_data()` 和 `_log_data()`，模拟电池状态的”实时“变化。线程由 `stop_monitoring()` 安全停止。 |

---

# 5 快速开始

## 环境要求

- python 3.8或更高的版本  
- 支持Windows/macOS/Linux  

## 安装依赖

打开终端（或命令提示符），进入项目根目录，执行：

```bash
pip install pyyaml
```

## 克隆仓库

```bash
git@github.com:chenfxcc/curser-collection.git
cd curser-collection
```

## 运行电池模块示例

```bash
cd battery_module
python test_battery.py
```

---

# 6 测试说明

## 运行功能测试

进入电池模块目录，执行测试脚本：

```bash
cd battery_module
python test_battery.py
```

测试脚本将：

- 创建一个Battery Monitor实例  
- 启动后台监控线程  
- 连续10次调用 `get_status()` 并打印当前电池状态（SOC、电压、SOH、温度）  
- 自动检查每次返回后  

**预期输出**

成功运行后终端会打印类似一下内容（每1秒更新一次，持续10秒）

```text
1/10 SOC=99.94% V=25.20V SOH=100.00% T=25.0C
2/10 SOC=99.94% V=25.20V SOH=100.00% T=25.0C
3/10 SOC=99.65% V=25.17V SOH=100.00% T=25.0C
...
9/10 SOC=98.14% V=25.16V SOH=100.00% T=25.1C
10/10 SOC=97.94% V=25.14V SOH=100.00% T=25.1C
```

同时目录下会生成 `battery_log.csv` 文件，记录每次更新的时间戳和数据。

**配置修改验证**

编辑 `battery_config.yaml`，例如将 `update_interval` 从0.5改为2.0,保存后再次运行 `test_battery.py`，观察打印间隔是否变长。

---

# 7 技术亮点 / 设计决策

-线程安全： 守护线程+退出标志，确保后台任务可启停  
-配置驱动： YAML文件集中管理所有模拟参数，零代码调参  
-数据隔离： 内部算法与对外接口隔离，返回标准字典，低耦合  
-健壮性： 参数边界清晰，配置文件确实时自动生成默认值  
-可扩展： 预留真实BMS接入点，支持未来硬件实际仿真  

---

# 8 文件结构

```text
battery_module/
├── battery_simulator.py
├── test_battery.py
├── battery_config.yaml
├── battery_log.csv
└── docs/
    └── readme.md
```
