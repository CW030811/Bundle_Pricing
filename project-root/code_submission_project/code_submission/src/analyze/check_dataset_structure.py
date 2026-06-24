"""
检查 test_BSP_m10n15 数据集的数据结构
"""
import msgpack
import msgpack_numpy as mnp
import os

# 读取一个示例文件
file_path = 'Dataset/test_BSP_m10n15/sample_data_1_size_15_sizepricing.msgpack'

if not os.path.exists(file_path):
    print(f"文件不存在: {file_path}")
    print(f"当前工作目录: {os.getcwd()}")
    exit(1)

with open(file_path, 'rb') as f:
    data = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)

print("=" * 80)
print("数据集结构检查")
print("=" * 80)
print(f"\n文件路径: {file_path}")
print(f"\n数据键 (Keys): {list(data.keys())}")

# 检查必需的字段
required_fields = [
    'product_num', 'segment_num', 
    'unit_cs', 'ship_cs', 'unit_us', 
    'Ns', 'opt_bundles', 'opt_prices', 
    'opt_rev', 'running_time', 'gap'
]

print("\n必需字段检查:")
for field in required_fields:
    exists = field in data
    status = "[OK]" if exists else "[MISSING]"
    if exists:
        value = data[field]
        if isinstance(value, (int, float)):
            print(f"  {status} {field}: {value}")
        elif isinstance(value, (list, tuple)):
            print(f"  {status} {field}: {type(value).__name__}, length={len(value)}")
        elif hasattr(value, 'shape'):
            print(f"  {status} {field}: shape={value.shape}, dtype={value.dtype}")
        else:
            print(f"  {status} {field}: {type(value).__name__}")
    else:
        print(f"  {status} {field}: 缺失")

# 检查可选字段
optional_fields = ['cs', 'Rs']
print("\n可选字段检查:")
for field in optional_fields:
    exists = field in data
    status = "[OK]" if exists else "[MISSING - will calculate]"
    if exists:
        value = data[field]
        if hasattr(value, 'shape'):
            print(f"  {status} {field}: shape={value.shape}, dtype={value.dtype}")
        else:
            print(f"  {status} {field}: {type(value).__name__}")
    else:
        print(f"  {status} {field}")

# 检查数据维度
print("\n数据维度:")
if 'product_num' in data and 'segment_num' in data:
    print(f"  产品数 (n): {data['product_num']}")
    print(f"  客户段数 (m): {data['segment_num']}")

if 'unit_cs' in data:
    unit_cs = data['unit_cs']
    if hasattr(unit_cs, 'shape'):
        print(f"  unit_cs shape: {unit_cs.shape}")
    else:
        print(f"  unit_cs type: {type(unit_cs)}")

if 'unit_us' in data:
    unit_us = data['unit_us']
    if hasattr(unit_us, 'shape'):
        print(f"  unit_us shape: {unit_us.shape} (期望: (m, n))")

if 'ship_cs' in data:
    ship_cs = data['ship_cs']
    if hasattr(ship_cs, 'shape'):
        print(f"  ship_cs shape: {ship_cs.shape}")

if 'Ns' in data:
    Ns = data['Ns']
    if hasattr(Ns, 'shape'):
        print(f"  Ns shape: {Ns.shape} (期望: (m,) 或 (m, 1))")

if 'opt_bundles' in data:
    opt_bundles = data['opt_bundles']
    if isinstance(opt_bundles, (list, tuple)):
        print(f"  opt_bundles: list/tuple, length={len(opt_bundles)}")
        if len(opt_bundles) > 0:
            print(f"    第一个bundle: {opt_bundles[0]}")
    elif hasattr(opt_bundles, 'shape'):
        print(f"  opt_bundles shape: {opt_bundles.shape}")

print("\n" + "=" * 80)
print("结论:")
all_required = all(field in data for field in required_fields)
if all_required:
    print("[OK] 所有必需字段都存在，代码应该可以直接使用")
else:
    missing = [f for f in required_fields if f not in data]
    print(f"[ERROR] 缺少必需字段: {missing}")
    print("  需要修改代码以适配此数据集")

# 检查额外字段
extra_fields = set(data.keys()) - set(required_fields) - set(optional_fields)
if extra_fields:
    print(f"\n额外字段 (代码不会使用，但存在): {sorted(extra_fields)}")

print("=" * 80)

