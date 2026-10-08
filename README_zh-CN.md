# 遥感影像与 PS-InSAR 处理制图工具箱

[English](README.md) | **简体中文**

这是 QGIS 双语插件 `rs_psinsar_toolkit` 版本 `0.3.0-rc1` 的公开源码仓库。
工具箱集成 GCP 几何校正、SAR 强度处理与制图，以及已有 PS-InSAR 成果的
专题制图和描述性时序回查。

- 作者：**杨晨曦（Yang Chenxi）**
- 作者所属机构：**中国海洋大学（Ocean University of China）**
- 项目开展地点：**厦门大学联合遥感接收站（Xiamen University Joint Remote
  Sensing Receiving Station）**
- 公开联系邮箱：**cyang5533@gmail.com**
- 源码仓库：
  **<https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit>**
- 验证环境：**QGIS 3.44.11-Solothurn**
- 状态：**实验性预发布候选（`0.3.0-rc1`）**

作者来自中国海洋大学，本项目在厦门大学联合遥感接收站开展。

`0.3.0-rc1` 安装包已在 QGIS 3.44.11 中英文全新配置中完成 ZIP 安装、
任务中心及六模块界面检查，每种语言下均通过 39 项自动测试，并完成三类专题图的
数值与模板回归检查。上述验证范围为所用环境和参考数据，详细情况见
[版本说明](https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/releases/tag/v0.3.0-rc1)。

## 仓库结构

- [`rs_psinsar_toolkit/`](rs_psinsar_toolkit/)：插件源码、双语文档、Qt 翻译、
  资源和 QPT 模板；
- [`tests/`](tests/)：国际化、科学口径、几何校正、SAR 和时序回归测试；
- [`tools/`](tools/)：带发布门禁的本地打包和仓库审计工具；
- [`OPEN_SOURCE_AUDIT.md`](OPEN_SOURCE_AUDIT.md)：发布准备阶段的隐私、依赖、安全、
  元数据和资源审计记录；
- [`LICENSING.md`](LICENSING.md)：软件与文档许可证范围；
- [`AUTHORS.md`](AUTHORS.md)：作者、单位和公开联系方式；
- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)：从本地候选到公开发布的门禁。

## 科学边界

- 无完整定标依据时，SAR 成果仅称为强度 dB，不扩大为 Sigma0/Gamma0；
- 外部 GCP 影像到地图几何校正不等同于 Range-Doppler 地形校正；
- 垂直形变速率单位为 `mm/year`；
- PS-InSAR 模块使用预先计算且符合所需结构、单位和垂直形变约定的数据，
  不执行从 SAR 影像估计形变或将视线向形变转换为垂直形变的计算；
- 累计形变保持 `D_target - D_initial` 后进行 50 米网格有效差值中位数聚合，
  形变量单位为 `mm`，正值向上、负值向下；
- 多点时序只用于描述性人工回查，不自动识别异常、划分趋势或推断物理成因；
- 输入只读，每项任务创建独立且不覆盖既有成果的输出目录。

## 许可证

- 软件源码、测试、QPT 模板、Qt 翻译、SVG 和运行资源：
  [`GPL-2.0-or-later`](LICENSE)；
- 中英文文档：[`CC BY 4.0`](LICENSE-DOCUMENTATION.md)；
- 第三方组件继续遵守各自许可证，见
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

版权所有 (C) 2026 杨晨曦（Yang Chenxi）。

## 发布状态

本项目源码已在本仓库公开。`0.3.0-rc1` 预发布版本已提供可安装的插件 ZIP 包及
版本说明，可前往
[GitHub Releases](https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/releases/tag/v0.3.0-rc1)
获取。

当前版本为实验性发布候选，主要用于测试与反馈。用于科研或实际业务前，
请结合自己的数据和项目要求验证输出结果。

完整使用说明见[插件中文 README](rs_psinsar_toolkit/README_zh-CN.md)、
[中文安装说明](rs_psinsar_toolkit/INSTALL_zh-CN.md)和
[中文用户指南](rs_psinsar_toolkit/USER_GUIDE_zh-CN.md)。
