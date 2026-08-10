# GXR 1.51 USB 与启动入口研究（第三阶段）

## 结论摘要

本阶段已经把“USB 下为什么报告两个 Configuration”还原到代码级，并用当前连接的 GXR 实机枚举结果进行了交叉验证。

当前相机运行的是固件 USB **模式 2**：

- USB VID：`0x05CA`
- USB PID：`0x0133`
- `bNumConfigurations = 2`
- 当前激活 Configuration：`1`
- USB 速度：High Speed，480 Mbit/s

两个 Configuration 分别是：

| Configuration | 接口类型 | 端点 | 已确认用途 |
|---|---|---|---|
| 1 | Mass Storage `08/06/50` | Bulk IN、Bulk OUT | 当前公开的 FAT16 `RICOHDCI` |
| 2 | Vendor Specific `FF/00/00` | Bulk IN、Bulk OUT、Interrupt IN | 私有通信接口；不是第二个 FAT 磁盘 |

因此，普通连接时 DiskGenius 只显示一个 91 MB 照片盘是正常现象。第二个 USB Configuration 确实存在，但它不是“隐藏分区”，操作系统不会把它自动显示成盘符。

## 一、固件与实机基线

分析文件：

```text
GXR Update/Firmware rel 1.51/ilaunch3
SHA-256:
da1980e9d6f3996ede4953b8311cf0ce2abeb4bb300b6ee60a38f38e29a3cdf7
```

升级包：

```text
gxr-151.zip
SHA-256:
3705984b8433c40d2ed4fd2600c11f03ed8a6de7dbe7f66efd38ee5ca15fc898
```

当前实机公开磁盘：

```text
物理设备：/dev/disk4（本次连接时的临时编号）
总长度：91,013,632 字节
分区：DOS FAT16
卷名：RICOHDCI
分区起点：第 47 个 512 字节扇区
介质状态：只读
卷挂载状态：只读
```

卷中当前只有：

```text
/DCIM/100RICOH/
/CLIPINFO/
```

没有可见的：

```text
LAUNCHA
IROM.DAT
IROM2.DAT
CONFIG.TST
CONFIG.BAK
BADJRAM.DAT
BKIZROM.DAT
```

## 二、USB 描述符模板

设备描述符位于：

```text
文件偏移：0x35FADE
运行地址：0x203AA8DE
```

固件中保留了多组 Configuration 模板：

| 运行地址 | 文件偏移 | 接口类 | 速度 |
|---|---:|---|---|
| `0x203AA8FA` | `0x35FAFA` | Vendor `FF/00/00` | Full Speed |
| `0x203AA922` | `0x35FB22` | Vendor `FF/00/00` | High Speed |
| `0x203AA94A` | `0x35FB4A` | Still Image/PTP `06/01/01` | Full Speed |
| `0x203AA972` | `0x35FB72` | Still Image/PTP `06/01/01` | High Speed |
| `0x203AA99A` | `0x35FB9A` | Mass Storage `08/06/50` | Full Speed |
| `0x203AA9BA` | `0x35FBBA` | Mass Storage `08/06/50` | High Speed |
| `0x203AA9DA` | `0x35FBDA` | Video `0E` 简化模板 | Full Speed |
| `0x203AAA12` | `0x35FC12` | Video `0E` 简化模板 | High Speed |

完整 UVC Configuration 还位于：

```text
High Speed：0x203AACF8（文件偏移 0x35FEF8）
Full Speed：0x203AAE1E（文件偏移 0x36001E）
总长度均为 292 字节
```

## 三、USB 模式选择

USB 模式字节：

```text
运行地址：0x203AAAA5
文件偏移：0x35FCA5
```

设备描述符修补函数：

```text
0x20394228
```

该函数根据模式值 `0..3` 动态修改：

- VID/PID；
- `bNumConfigurations`；
- Device Qualifier 的配置数量；
- 模式 3 的设备类 `EF/02/01`。

已还原模式：

| 模式 | Configuration 数量 | 主要用途 |
|---:|---:|---|
| 0 | 2 | 另一组复合/私有 USB 工作方式 |
| 1 | 1 | PTP/Still Image 路径 |
| 2 | 2 | Mass Storage + Vendor Specific |
| 3 | 1 | UVC/IAD 视频模式 |

模式 2 的回退 PID 为 `0x0133`，与当前实机完全一致。

模式赋值代码：

```text
0x2038D878：根据运行配置选择模式 0、2 或 3
0x2038D96C：设置模式 1
```

## 四、Configuration 1 与 2 的精确映射

描述符指针初始化函数：

```text
0x20394688
```

GET_DESCRIPTOR 处理函数：

```text
0x20398D04
```

在 High Speed 下，指针表被设置为：

```text
0x203A98FC -> 0x203AA922  Vendor Specific
0x203A9904 -> 0x203AA9BA  Mass Storage
```

模式 2 的 GET_DESCRIPTOR 分派为：

```text
Configuration index 0 -> 0x203A9904 -> Mass Storage
Configuration index 1 -> 0x203A98FC -> Vendor Specific
```

换成 USB 规范中从 1 开始的 Configuration Value，就是：

```text
Configuration 1 -> Mass Storage
Configuration 2 -> Vendor Specific
```

当前 macOS 实机信息还显示：

```text
kUSBCurrentConfiguration = 1
UsbDeviceSignature 末尾包含：
08 06 50
ff 00 00
```

它同时验证了两个接口类。

## 五、Configuration 2 现在能确认什么

其描述符为：

```text
bNumInterfaces = 1
bInterfaceClass = 0xFF
bInterfaceSubClass = 0x00
bInterfaceProtocol = 0x00

Endpoint 0x81: Bulk IN
Endpoint 0x02: Bulk OUT
Endpoint 0x83: Interrupt IN
```

可以确认：

1. 它是双向私有协议接口；
2. 它不是 USB Mass Storage；
3. 它不是标准 PTP；
4. 它具备承载调试、遥控、调整或工厂通信协议的物理条件。

现在还不能确认：

1. 它是否直接承载调试 shell；
2. 它是否承载 `COMMAND.NS1` 同一套命令；
3. 它能否读取 IROM；
4. 仅切换 Configuration 是否会触发相机侧状态迁移；
5. 第一个合法命令、握手和校验格式。

所以暂不向 Configuration 2 切换，也不发送 Bulk/Interrupt 数据。

## 六、启动按键与调试标志

启动输入扫描函数：

```text
0x2005C538
```

按键/输入状态读取函数：

```text
0x2006439C
```

启动标志累加函数：

```text
0x20068A68
```

调试入口已确认：

```text
输入 ID 19 有效，且 ID 21、22 均无效
    -> 启动标志 0x00100000
    -> DBGMODE.key 存在时调用 0x2036D4E8(2)

输入 ID 20 有效，且 ID 21、22 均无效
    -> 启动标志 0x00080000
    -> DBGMODE.key 存在时调用 0x2036D4E8(1)
```

ID 19/20 与 ID 21/22 还组成四种两键组合：

```text
22 + 19 -> 0x0200
22 + 20 -> 0x0100
21 + 19 -> 0x0080
21 + 20 -> 0x0800
```

这证明两组 ID 各自是相反方向的一对输入。结合 GXR 的实体布局，它们高度疑似：

```text
19/20 -> + / -
21/22 -> Fn1 / Fn2
```

但当前还没有足够证据判断：

- 19 是 `+` 还是 `-`；
- 21 是 Fn1 还是 Fn2。

在映射完全确认前，不制作 `DBGMODE.key` 实机启动卡。

## 七、本次没有执行的动作

没有：

- 写相机内存；
- 写 SD 卡触发文件；
- 创建 `DBGMODE.key`；
- 创建 `INCOPY.KEY`；
- 切换 USB Configuration；
- 发送厂商私有 USB 请求；
- 启动固件升级；
- 修改或解除设备只读状态。

第一次直接读取 `/dev/rdisk4` 制作全盘镜像时，macOS 返回：

```text
Permission denied
```

随后通过 macOS 管理员授权弹窗再次执行只读 `dd`，系统隐私层仍返回：

```text
Operation not permitted
```

这表明阻止读取的是当前 Codex 应用进程的可移动设备/完全磁盘访问权限，而不是普通 Unix 管理员权限。两次尝试都只以相机为输入设备，没有向相机写入。

因此没有获得包含空闲簇和已删除目录项的 91 MB 原始镜像。文件级目录读取成功，但它不能替代扇区镜像。

## 八、下一步

优先顺序：

1. 用管理员权限只读备份当前 91 MB 物理设备；
2. 在镜像上解析 FAT16 已删除目录项和空闲簇；
3. 继续反汇编 Configuration 2 的端点回调和握手状态机；
4. 找到只读的版本/能力查询命令后，才考虑临时切换 Configuration 2；
5. 继续通过普通 UI 事件代码确认 ID 19/20/21/22 的实体按键方向；
6. 最后才评估 `DBGMODE.key`。

当前最安全、最有信息量的实机材料仍是完整的 91 MB 扇区镜像。
