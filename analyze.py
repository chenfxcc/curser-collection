#模拟的电池数据（电压，电流，温度）
battery_data = [
    (12.5, 1.2, 25),
    (12.3, 1.5, 26),
    (12.1, 1.8, 27),
]

# 计算所有数据点的平均电压
voltages = [data[0] for data in battery_data]
average_voltage = sum(voltages) / len(voltages) if voltages else 0
print(f"平均电压为: {average_voltage:.2f} V")