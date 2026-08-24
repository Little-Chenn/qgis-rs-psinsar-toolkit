# 遥感影像与 PS-InSAR 处理制图工具箱

[English](README.md) | **简体中文**

这是 QGIS 双语插件 `rs_psinsar_toolkit` 版本 `0.3.0-rc1` 的独立本地开源准备仓库。

- 作者：**杨晨曦（Yang Chenxi）**
- 作者单位：**厦门大学联合遥感接收站（Xiamen University Joint Remote
  Sensing Receiving Station）**
- 公开联系邮箱：**cyang5533@gmail.com**
- 拟用公开仓库：
  **<https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit>**
- 验证环境：**QGIS 3.44.11-Solothurn**
- 状态：**实验性预发布候选，尚未公开发布**

单位信息用于说明作者隶属关系，本身不表示厦门大学或接收站拥有、赞助、认证或
官方认可本软件及其科学成果。

`0.3.0-rc1` 从本地资格验证通过的 `0.3.0-dev.8-bilingual-rc3` 提升而来。
dev.8 RC3 已通过全新原生 ZIP 安装、39 项自动测试、英文六模块界面检查、中英文
六模块轻量回归、双语数值比较、三类专题图回归，以及作者的人工安装和图件验收。
版本号和许可证提升后仍将在本地重新验证，外部发布前不会连接远程仓库。

## 仓库结构

- [`rs_psinsar_toolkit/`](rs_psinsar_toolkit/)：插件源码、双语文档、Qt 翻译、
  资源和 QPT 模板；
- [`tests/`](tests/)：国际化、科学口径、几何校正、SAR 和时序回归测试；
- [`tools/`](tools/)：带发布门禁的本地打包和仓库审计工具；
- [`OPEN_SOURCE_AUDIT.md`](OPEN_SOURCE_AUDIT.md)：隐私、依赖、安全、元数据和
  资源审计；
- [`LICENSING.md`](LICENSING.md)：软件与文档许可证范围；
- [`AUTHORS.md`](AUTHORS.md)：作者、单位和公开联系方式；
- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)：从本地候选到公开发布的门禁。

## 科学边界

- 无完整定标依据时，SAR 成果仅称为强度 dB，不扩大为 Sigma0/Gamma0；
- 外部 GCP 影像到地图几何校正不等同于 Range-Doppler 地形校正；
- 垂直形变速率单位为 `mm/year`；
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

当前未配置远程 Git 仓库，也未创建提交、推送、GitHub Release、QGIS 插件仓库
提交或任何公开上传。GitHub 所有者和最终元数据 URL 已确认，可用于本地打包；
任何外部连接或发布仍需再次取得明确授权。

完整使用说明见[插件中文 README](rs_psinsar_toolkit/README_zh-CN.md)、
[中文安装说明](rs_psinsar_toolkit/INSTALL_zh-CN.md)和
[中文用户指南](rs_psinsar_toolkit/USER_GUIDE_zh-CN.md)。
