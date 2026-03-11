# 电池监控与数据分析项目

本项目包含一个电池监控模块、数据记录、以及简单的数据分析脚本，支持模拟及真实BMS数据源。支持对电池SOC、电压、SOH的实时监控与验证，
并可将数据记录至CSV文件。

---

## 目录结构

- `battery.py` —— 电池监控主模块，包含 BatteryMonitor 类，可模拟或读取真实电池数据。
- `test.py` —— 用于测试 BatteryMonitor 的功能，包含基本数据验证和终端输出。
- `battery_log.csv` —— 电池状态自动记录的CSV日志（自动生成）。
- `analyze.py` —— 简单数据分析示例，计算平均电压。

---

## 依赖

本项目需要 Python 3.x，并使用了标准库模块：
- `threading`
- `random`
- `time`
- `csv`
- `datetime`
- `os`

无需额外安装第三方库。

---

## 主要功能说明

### 1. 电池监控（battery.py）

- 支持数据源选择 (`simulator`/真实`BMS`)
- 定时动态更新电池SOC、SOH、电压数据
- 支持多线程后台监控
- `get_status()` 提供最新电池数据
- `start_monitoring()` 启动监控线程

### 2. 日志记录（battery_log.csv）

- 可将电池的每次状态自动追加到CSV文件中（需在 `BatteryMonitor` 中调用 `_log_data` 方法）

### 3. 测试与验证（test.py）

- 启动电池监控，模拟10轮状态获取
- 输出当前SOC, 电压, SOH
- 简单断言验证数据范围有效性

### 4. 数据分析（analyze.py）

- 演示如何读取电池数据并计算平均电压

---

## 快速开始

1. 运行电池监控测试：

```bash
python test.py
```
运行期间将输出10轮电池状态。

2. 如需查看或分析日志数据，可直接用 Excel 或文本编辑器打开 `battery_log.csv`。

3. 用 `analyze.py` 进行数据分析：

```bash
python analyze.py
```

---

## 后续扩展建议

- 实现 `_read_from_bms` 与真实BMS通讯
- 集成日志记录自动化到`BatteryMonitor`
- 增加更多分析和可视化功能

---

如有建议或BUG欢迎反馈！
