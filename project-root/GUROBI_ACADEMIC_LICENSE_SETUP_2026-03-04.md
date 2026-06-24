# Gurobi 学术 License 配置记录（2026-03-04）

## 目标
在 Mac mini 上完成 Gurobi 学术许可激活，并验证在 Revenue Management 项目中可正常求解。

---

## 前置信息

- 机器用户：`sensen`（非 root/administrator，符合学术许可要求）
- 操作系统：macOS (arm64)
- 激活码：`2cdd98df-4555-4730-ac95-8a0c34c87381`

---

## 执行过程

### 1) 环境检查

- 检查当前用户：`whoami` → `sensen`
- 检查 Gurobi 是否已安装：`gurobi_cl --version` → 未安装（命令不存在）
- 通过 pip 安装 Python 接口：`gurobipy==12.0.3`（用于后续求解验证）

### 2) 获取官方安装包与工具

- 发现可用安装包地址：
  - `https://packages.gurobi.com/12.0/gurobi12.0.3_macos_universal2.pkg`
- 下载后，因无 root 权限无法系统级安装 pkg。
- 采用替代方案：解包 pkg 并提取官方 `grbgetkey` 工具：
  - 路径：
    - `/tmp/gurobi_pkg_expanded/gurobi12.0.3_macos_universal2.component.pkg/Payload/Library/gurobi1203/macos_universal2/bin/grbgetkey`

### 3) 执行激活

- 创建本地 license 目录：`/Users/sensen/.gurobi`
- 使用激活码执行：
  - `grbgetkey 2cdd98df-4555-4730-ac95-8a0c34c87381`
- 激活成功，输出关键结果：
  - License ID: `2784353`
  - 到期时间：`2027-03-03`
  - 生成文件：`/Users/sensen/.gurobi/gurobi.lic`

### 4) 配置环境变量

- 设置：
  - `GRB_LICENSE_FILE=/Users/sensen/.gurobi/gurobi.lic`
- 持久化：写入 `~/.zshrc`
- 会话级生效：`launchctl setenv GRB_LICENSE_FILE /Users/sensen/.gurobi/gurobi.lic`

---

## 验证结果

执行最小 LP 求解测试（`gurobipy`）：

- 日志显示：`Set parameter LicenseID to value 2784353`
- 模型求解成功：`status = 2`（Optimal）
- 结论：学术 license 已生效，可正常求解。

---

## 最终状态清单

- [x] 学术激活码已成功绑定当前机器
- [x] `gurobi.lic` 已生成
- [x] 环境变量 `GRB_LICENSE_FILE` 已配置并持久化
- [x] 求解测试通过（可用于项目计算）

---

## 备注

- 未使用系统默认路径 `/Library/gurobi`（需 root）
- 使用官方支持的环境变量方式等效替代：`GRB_LICENSE_FILE`
- 后续在终端新会话中可用 `echo $GRB_LICENSE_FILE` 快速自检
