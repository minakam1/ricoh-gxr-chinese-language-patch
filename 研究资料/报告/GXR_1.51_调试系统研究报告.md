# Ricoh GXR 1.51 调试系统研究报告

分析对象：官方 `gxr-151.zip`。本轮全部为静态、只读分析，没有修改或生成任何可刷写固件。

## 一句话结论

GXR 里保留的不是普通隐藏菜单，而是一套工厂级维修平台：

1. **系统调试壳**：直接查看版本、内存、ROM、端口，亦可擦写闪存、改内存和调用任意函数。
2. **机身—镜头远程控制层**：调试控制权可在 Body Unit 与 Lens Unit 间切换。
3. **维修脚本解释器**：可模拟按键和拨轮、读取变量、循环和分支、发送调整命令、安装脚本、备份/恢复配置。
4. **相机调整系统**：覆盖曝光、对焦、白平衡、传感器/ISP、镜头变焦/光圈、闪光灯、防抖等工厂校准。
5. **文件触发入口**：固件会检查若干 SD 卡文件，但确切触发条件尚未完全还原。

它有能力完成中文地区配置迁移，但也有能力在一条命令内擦除 ROM，因此入口和命令必须分层研究。

---

## 1. 系统调试壳：25 个明确命令

固件中存在一张完整命令表，每项都包含命令名、帮助文本和实际函数地址。以下不是猜测，而是直接从命令表解析所得。

### 只读或以诊断为主

| 命令 | 固件帮助文本 | 作用判断 |
|---|---|---|
| `help` | list command. | 列出命令 |
| `log` | flush syslog. | 刷出系统日志，可能改变日志缓冲状态但不改校准 |
| `calc` | show calculation time. -t[0-2] | 性能/耗时统计 |
| `sys` | system debug. | 进入系统调试子层，具体子命令待拆 |
| `rmt` | Command Remote Control. `[-bODY][-lENS][-nONE mesSAGE]` | 把命令控制权切到机身或镜头单元 |
| `avu` | indicate version with auto version up | 显示自动升级相关版本 |
| `ver` | indicate version. `[-moni][-main][-bkup][-extd][-adjd]` | 显示监控、主程序、备份、扩展、调整数据版本 |
| `hdr` | indicate header. `[-moni][-main][-bkup][-extd]` | 显示各固件头 |
| `ram` | indicate ram map. | 显示 RAM 分区 |
| `rom` | indicate rom map. | 显示 ROM 分区 |
| `fc` | indicate rom device info. | 显示闪存器件信息、坏块等 |
| `fd` | exec. rom dump. `[(start)][(end)][-bLOCK/-sECTOR]` | 读取/转储 ROM；范围填错仍可能卡死 |
| `md` | exec. memory dump. `[(start)][(end)][-aSCII]` | 读取内存 |
| `port` | indicate port status. `[num]` | 查看 I/O 端口状态 |

### 会改变状态或直接高危

| 命令 | 固件帮助文本 | 风险 |
|---|---|---|
| `up` | exec. card version up. | 从卡执行升级，可能写入程序区 |
| `reboot` | reboot. `[-bkup][-main(default)][raml]` | 切换主程序、备份程序或 RAMLOAD 启动 |
| `ex` | exec func. arg1,,arg8 | 调用任意函数，最多八个参数；极高风险 |
| `fe` | exec. rom erase. `[-eXTEND][-fORCED]` | 擦除 ROM；致命风险 |
| `fbe` | exec. rom erase by block. | 按块擦除；致命风险 |
| `ft` | exec. rom WR test. | 闪存读写测试，可能破坏内容 |
| `me` | exec. memory edit. | 直接改内存 |
| `mf` | exec. memory fill. | 批量填充内存 |
| `mc` | exec. memory copy. | 内存复制，可能覆盖代码或参数 |
| `mt` | exec. memory WR test. | 内存写测试 |
| `ddr` | exec. DDR test. | DDR 压力/写测试，运行中可能破坏工作区 |

`rmt` 是本项目最关键的命令：同一套调试终端可以从机身切到相机模块。所有 1.51 模块主程序中都存在同一张 25 命令系统表。

---

## 2. 低层调试模块：41 个子系统

系统会注册 41 个底层模块，每个模块都有初始化和注销函数：

`trace, assert, library, debug, event, error, cache, adjvalue, sysvalue, clock, port, interrupt, timer, system, device, dmac, mft, sio, hsio, i2c, hsp, serial, console, shell, bios, power, control, unit, exchange, hid, rtc, led, gear, sleep, operation, date, command, syslog, asio, display, service`

这些模块说明其调试范围包括：

- CPU 缓存、异常、事件、时钟、中断、定时器；
- DMA、串口、I²C、高速串行总线、端口；
- 电源、睡眠、LED、RTC、按键/HID；
- 控制台和命令壳；
- 机身—模块通信与数据交换；
- 系统参数 `sysvalue` 与调整参数 `adjvalue`；
- 文件系统、显示和服务层。

另外还有 10 个大类域：Mechanical、RIP & MX1、MiddleWare、Library、Management、FileSystem、Osd、Application、Network、Adjust。

### 关于接入方式

固件明确注册了 `serial`、`console`、`shell`，并出现任务/组件名 `JTserial`、`Pdebug`。这强烈表明工厂主入口之一是内部串行控制台。

但当前仍不能证明：

- 普通 USB 数据线是否能直接得到该命令行；
- 串口焊盘位置、电平和波特率；
- 是否必须先由按键组合或文件触发打开控制台。

固件里虽然有 USB/PTP 调试项，但这只能证明 USB 子系统可被诊断，不能直接推出 shell 已暴露在标准 USB 接口上。

---

## 3. 维修脚本解释器：40 个命令

GXR 还有一套文本脚本语言，明显用于自动化工厂测试和维修调整。命令包括：

### 操作相机

- `keyset`、`key`、`keyhold`、`keyrel`：定义并模拟按键。
- `dialset`、`dial`：定义并模拟拨轮。
- `wait`：等待。
- `poff`：关机。

### 流程控制

- `repeat`、`repeat2`、`next`；
- `goto`、`gosub`、`return`；
- `if==gosub`、`if!=gosub`、`if>gosub`、`if<gosub`；
- `end`、`rem`。

### 变量与运算

- `var=`、`var+=`、`var-=`、`var*=`、`var/=`、`var%=`、`var>>=`、`var<<=`。

### 日志与状态

- `logon`、`logoff`、`logtime`、`logbatt`、`logstr`；
- `version`。

### 调整和安装

- `adjcom`、`adjcom2`：向调整系统发送命令并取得返回值；
- `install`、`uninstall`：安装或卸载维修脚本。

这说明维修脚本可以完成“按键操作 → 读取参数 → 判断结果 → 调用校准命令 → 写日志 → 关机”的完整自动流程。

### 相关路径

固件出现：

- `/ATA1/RADJ/sadj`
- `/ATA1/RADJ/n1rf`
- `/IROM/RADJ`
- `/SCRIPT.`
- `/SCINST.TST`
- `/CONFIG.TST`
- `/CONFIG.BAK`
- `/SCRP`、`/CFGT`、`/CFGB`、`/SINS`

配置代码会生成编号化的 `.TST` 和 `.BAK` 文件，并发送 `Z4000`、`Z4100`、`Z4200`、`Z5000`、`ZB4xx`、`Z51xx` 等调整协议命令。

**对中文改区最重要的就是这一层。** 正常方法更可能是读取/恢复一小组系统或调整参数，而非修改菜单资源或整块擦写 ROM。

---

## 4. 调整系统具体能碰哪些硬件

机身调整代码中能直接看到以下项目：

- AE 曝光调整；
- AF/CCD AF；
- AWB 白平衡和 AWB ISP 数据；
- 传感器/CCD 接口与同步；
- ISP、WDR、LUT、滤波等图像处理寄存器转储；
- 防抖/Shake 同步偏移；
- 闪光灯初始化和闪光计数；
- G-sensor；
- 分辨率、显示和 LCD 接口；
- 灰尘检查；
- RAW/DNG 测试和 SD 卡读写速度测试。

镜头/相机模块还额外包含：

- Zoom、Focus、Iris 数据；
- 变焦方向、原点传感器、边缘、超时检测；
- 对焦原点和驱动；
- 光圈/快门/ND 等机械控制；
- 相机模块自身的传感器、ISP、AWB、AE/AF；
- 模块固件发送和重写。

可见 GXR 的相机模块不是被动镜头，内部也运行完整的系统和调整程序。官方系统设计同样把镜头、传感器和图像处理引擎集中在可更换相机单元中。

---

## 5. 能导出或恢复什么

机身固件出现以下内部/SD 文件：

- `/IROM/BADJRAM.DAT`
- `/ATA1/BADJROM.DAT`
- `/IROM/BKIZRAM.DAT`
- `/ATA1/BKIZROM.DAT`
- `/ATA1/BFPROM.DAT`
- `/ATA1/BIFPROM.DAT`

相机模块则出现：

- `/IROM/LADJRAM.DAT`
- `/ATA1/LADJRAM.DAT`
- `/IROM/LADJROM.DAT`

从命名看，`BADJ`/`LADJ`高度可能分别是 Body/Lens Adjustment 数据；其余缩写尚不能可靠解释。固件还明确显示 `Backup restore`，因此至少支持：

- 把调整 RAM/ROM 区导出到 SD；
- 把备份恢复回内部存储；
- 查看调整数据版本和是否完成过出厂调整。

这也是为什么不能粗暴复制一整个中文模块配置：里面可能混有对焦、白平衡、坏点、传感器和机械校准。

---

## 6. 调整命令文件与直接读写控制台

### `/ATA1/COMMAND.NS1`

机身调整程序会打开这个文件，并带有十六进制解析、`unsupported value` 错误和大量硬编码调整命令序列。因此它很可能是 SD 卡批处理调整命令入口。

目前只确认“它能执行调整命令”，没有还原完整文件格式。不要自行放入猜测内容。

### 直接调试模式

固件中存在明确帮助文本：

```text
X = Addr, Y = Data
wXXXX00YY : Write Mode (1 byte write)
wXXXXYYYY : Write Mode (2 byte write)
rXXXXYYYY : Read Mode
q or Q    : Exit Debug Mode
```

这看起来是一个面向调整寄存器或参数存储的简易十六进制读写终端。它能直接写一字节或两字节，足以修改地区码，也足以破坏校准。

---

## 7. 启动触发文件

在机身主程序中找到：

- `/ATA1/DBGMODE.key`：3 处引用；
- `/ATA1/INCOPY.KEY`：1 处引用；
- `/ATA1/COMMAND.NS1`；
- `/ATA1/SCRIPT.MG1`；
- `/CONFIG.TST`、`/CONFIG.BAK`、`/SCINST.TST`。

### 当前判断

- `DBGMODE.key`：大概率进入某种升级/调试分支，但不能确认只检查“文件存在”，也可能校验文件内容。
- `INCOPY.KEY`：靠近内部 ROM、固件兼容和复制代码，可能启动 internal copy 流程；风险最高。
- `COMMAND.NS1`：调整命令批处理文件。
- `SCRIPT.MG1`、`SCINST.TST`：维修脚本及安装触发。
- `CONFIG.TST/BAK`：配置导出/恢复路径。

`DBGMODE.key` 和 `INCOPY.KEY` 不是同一个功能。当前不要创建空文件试机；特别是 `INCOPY.KEY`，它可能覆盖内部 ROM 或调整区。

---

## 8. 日志和诊断能力

固件可生成或读取：

- `/ATA1/SYSTEM.LOG`
- `/IROM/DCTRACE.LOG`
- `MECH.CSV`、`OPE.CSV`、`FALL.CSV`
- `/ATA1/DCIM/ADJTRACE/...`
- `.log`、`.csv`、`.rom`、`.ram`、`.jpg`

还能显示：

- SHOT COUNT；
- REBOOT COUNT；
- 电池结束、接近结束、半按等计数；
- 温度；
- 闪光次数；
- 系统错误和 CPU RAM dump；
- NAND 坏块、擦除/写入错误。

因此调试系统不仅用于工厂校准，也可用于故障诊断和寿命计数读取。

---

## 9. 对“改中文”最有价值的能力

按价值排序：

1. **`CONFIG.TST/CONFIG.BAK` 导出和恢复**：最适合做改中文前后差分。
2. **`adjvalue` / `sysvalue` 子系统**：可能直接查看地区和语言参数。
3. **`adjcom/adjcom2`**：确认命令编号后，可只读/只写目标参数。
4. **`rmt -lens/-body`**：观察中文模块向机身发送了什么命令或数据。
5. **直接十六进制读写模式**：最后手段，知道地址后才使用。
6. **ROM/内存命令**：不应作为第一路线。

最合理的实验是：

```text
日版状态导出配置 A
→ 插入中文模块并执行已知配置读取
→ 导出配置 B
→ 二进制比较 A/B
→ 找候选语言/地区字段
→ 只修改候选字段并验证
```

这比修改固件资源或复制完整模块 EEPROM安全得多。

---

## 10. 下一步怎么接近真机入口

### 阶段 A：完全只读

1. 拆机或找高清主板照片，确认测试焊盘。
2. 先用高阻逻辑分析仪监听，不向任何焊盘送电。
3. 分别记录：无模块、日版模块、中文模块接入时的开机通信。
4. 寻找 ASCII 启动日志、`DEBUG>`、`Body Unit System` 等字符串。
5. 确认电平和波特率后，再考虑串口连接。

### 阶段 B：命令行只读命令

初次只尝试：

`help`、`ver`、`hdr`、`ram`、`rom`、`fc`、`port`。

不要先试：

`ex`、`up`、`fe`、`fbe`、`ft`、`me`、`mf`、`mc`、`mt`、`ddr`。

### 阶段 C：配置差分

先弄清 CONFIG 导出，得到备份文件；没有备份和可恢复路径之前，不进行任何写入。

---

## 当前研究边界

已经确定：

- 调试壳和命令表是真实可执行代码；
- 机身与模块均有同类调试系统；
- 存在完整维修脚本语言和调整协议；
- 存在配置备份/恢复和多个 SD 触发文件；
- 这些功能足以实现地区配置迁移。

仍未确定：

- 真机调试串口位置、电平、波特率；
- `DBGMODE.key` 的内容与启动组合；
- `INCOPY.KEY` 的准确复制方向；
- `CONFIG.TST/BAK` 的实际二进制格式；
- 地区/语言参数对应的调整命令编号。

这几个问题中，优先级最高的是取得一份真实的 `CONFIG.TST/BAK` 或改中文前后的配置转储。
