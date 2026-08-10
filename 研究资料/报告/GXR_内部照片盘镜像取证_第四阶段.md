# GXR 内部照片盘镜像取证（第四阶段）

日期：2026-07-30
对象：当前通过 USB 暴露的 `RICOHDCI` 物理设备
原则：全程只读分析原始镜像，不挂载写入，不修改相机

## 一、镜像身份

- 文件：`GXR_RICOHDCI_public_disk_2026-07-30.img`
- 长度：`91,037,696` 字节（`177,808` 个 512 字节扇区）
- SHA-256：`65934bda9b1cbd86aca8f0023c93c146ae824ef7636ad5f140c13557832d3f5d`
- `dd` 完成记录：`86+1 records in / 86+1 records out`

MBR 中只有一个分区：

| 项目 | 值 |
|---|---:|
| 类型 | `0x06`（FAT16） |
| 起始 LBA | `47` |
| 起始字节 | `24,064` |
| 扇区数 | `177,761` |
| 结束位置 | 正好是镜像最后一个扇区 |

因此这份镜像是完整 USB 物理设备，不是只复制了分区内容；设备末尾也没有未分区空间。

LBA 1–46 全部为 `0xFF`。除 MBR 外，分区前间隙不存在第二个分区头、目录或隐藏数据。

## 二、FAT16 文件系统

| 项目 | 值 |
|---|---:|
| OEM | `RICOH104` |
| 卷标 | `JYAGARANDY` |
| 每扇区字节数 | `512` |
| 每簇扇区数 | `32` |
| 每簇字节数 | `16,384` |
| FAT 数量 | `2` |
| 两份 FAT | 完全一致 |
| 数据簇数 | `5,552` |
| 已分配簇 | `5,302` |
| 空闲簇 | `250` |

现存目录树只有：

```text
/
├── DCIM/
│   └── 100RICOH/
│       ├── RIMG0001.JPG ...
│       ├── RIMG0020.JPG
│       ├── RIMG0020.DNG
│       └── RIMG0021.JPG
└── CLIPINFO/
```

共解析到 25 个现存目录/文件记录，没有发现删除标记 `0xE5` 的标准 8.3 目录项。

## 三、空闲簇与已删除内容

250 个空闲簇全部逐字节为 `0xFF`：

```text
all_ff_count = 250
non_erased_count = 0
```

也就是说约 4 MiB 的未分配区域已经处于闪存擦除态，不存在可恢复的旧文件内容、目录页、JPEG、DNG、ZIP 或程序头。

这与“文件删除后仍留下数据”的普通磁盘情况不同：当前镜像里没有残留可供恢复。

## 四、系统文件名检索

同时检索了普通字符串和 FAT 8.3 原始目录格式，例如：

```text
IROM.DAT       / IROM    DAT
IROM2.DAT      / IROM2   DAT
PARAM.DAT      / PARAM   DAT
CONFIG.TST     / CONFIG  TST
CONFIG.BAK     / CONFIG  BAK
BADJRAM.DAT
BADJROM.DAT
BKIZRAM.DAT
BKIZROM.DAT
COMMAND.NS1
DBGMODE.KEY
INCOPY.KEY
SCINST.TST
LAUNCHA
```

没有发现任何完整文件名或目录记录。

只有四个短词偶然命中：

| 短词 | 所属现存文件 |
|---|---|
| `IROM` | `RIMG0009.JPG` |
| `IROM` | `RIMG0020.DNG` |
| `IROM` | `RIMG0020.DNG` |
| `BKIZ` | `RIMG0016.JPG` |

它们前后均为图像压缩数据中的随机字节，不是目录项、路径字符串或文件内容标识。

## 五、可以排除的假设

当前证据可以排除：

1. `RICOHDCI` 的 FAT16 后面还有隐藏分区；
2. 分区前 46 个扇区保存着 IROM 文件系统；
3. 当前公开照片盘上还残留可恢复的 `IROM.DAT`、`CONFIG.*` 或调整数据；
4. DiskGenius 只因“没有显示分区”而漏掉同一物理设备上的第二分区。

因此固件中的 `/IROM` 不是当前 USB 公开的 `RICOHDCI` FAT16。两者是不同的逻辑存储对象。

用户以前看到系统文件的记忆仍可能成立，但入口应是：

- 另一种 USB 配置或维修状态；
- SD 卡上的导出镜像；
- 升级/工厂工具创建的临时维护视图；
- 另一台系统或专用驱动识别到的私有接口。

## 六、第二 USB 配置的新判断

固件和实机 USB 描述符均确认设备有两个配置：

- Configuration 1：Mass Storage，当前公开 `RICOHDCI`
- Configuration 2：Vendor Specific，Bulk IN、Bulk OUT、Interrupt IN

进一步检查 Configuration 2 附近的固件数据，发现：

- 字符串 `PTP_USB_DEVICE`
- 传输对象名 `tPtpTran`、`tPtpData`
- PictBridge/DPS 文件与 XML
- PTP 操作码表：`0x1002`、`0x1003`、`0x1004`、`0x1005`、`0x1006`、`0x1007`、`0x1008`、`0x1009`、`0x100A`、`0x100C`、`0x100D`、`0x101B`

这说明 Configuration 2 的私有类接口底层高度确定是 PTP/PictBridge 家族，而不是一个直接暴露的第二 FAT 磁盘。

PTP 的只读 `GetDeviceInfo (0x1001)` 因而是最小风险探针。实机执行结果：

1. `libusb` 成功打开设备；
2. 成功临时切换到 Configuration 2；
3. 成功占用 interface 0；
4. 向 Bulk OUT `0x02` 发送 12 字节标准 PTP 命令容器；
5. Bulk IN `0x81` 在 3 秒内无返回，得到 `LIBUSB_ERROR_TIMEOUT`；
6. 清理流程成功恢复 Configuration 1；
7. macOS 随后重新识别 `/dev/disk4` 和 `RICOHDCI`，目录读取正常；
8. `ioreg` 再次确认 `kUSBCurrentConfiguration = 1`，设备 `active, busy 0`。

这次超时表明 Configuration 2 虽复用了 PTP/PictBridge 组件，但不是“切换后即可直接发送普通 PTP 命令”的接口。它可能还需要控制请求、状态通知、会话初始化或理光自己的 DCX 握手。不能继续盲试其他操作码。

本阶段没有发送任何写配置、擦除、升级或调整命令；唯一的 Bulk OUT 数据是语义只读的 `GetDeviceInfo` 命令。USB 配置切换是易失状态，且已经实机验证恢复。

## 七、产物

- 原始镜像：`GXR_RICOHDCI_public_disk_2026-07-30.img`
- 只读取证脚本：`analysis/analyze_gxr_fat16_image.py`
- 结构化报告：`analysis/gxr_fat16_forensic_report.json`
- USB 枚举与最小 PTP 探针源码：`analysis/gxr_usb_probe.c`
- 已编译本机探针：`analysis/gxr_usb_probe`
