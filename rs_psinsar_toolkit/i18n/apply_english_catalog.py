"""Apply reviewed English translations to the generated Qt TS catalog."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from modules12_english import MODULE_TRANSLATIONS as MODULES12_TRANSLATIONS
from modules456_english import MODULE_TRANSLATIONS as MODULES456_TRANSLATIONS


CATALOG = Path(__file__).with_name("rs_psinsar_toolkit_en.ts")

TRANSLATIONS: dict[str, dict[str, str]] = {
    "RsPsInsarToolkitPlugin": {
        "&遥感影像与 PS-InSAR 处理制图工具箱": "&Remote Sensing and PS-InSAR Processing & Mapping Toolkit",
        "打开工具箱": "Open Toolkit",
        "打开“遥感影像与 PS-InSAR 处理制图工具箱”": "Open “Remote Sensing and PS-InSAR Processing & Mapping Toolkit”",
        "遥感影像与 PS-InSAR 处理制图工具箱已加载": "Remote Sensing and PS-InSAR Processing & Mapping Toolkit loaded",
        "遥感影像与 PS-InSAR 处理制图工具箱已卸载": "Remote Sensing and PS-InSAR Processing & Mapping Toolkit unloaded",
    },
    "@default": {
        "SAR 模板缺少布局项：{item_id}": "SAR template is missing layout item: {item_id}",
        "SAR QPT XML 错误 {line}:{column}：{message}": "SAR QPT XML error at {line}:{column}: {message}",
        "QGIS 无法加载 SAR 专题图模板。": "QGIS could not load the SAR thematic-map template.",
        "SAR 强度 dB 专题图（可编辑）": "SAR Intensity Map in dB (Editable)",
        "VV 极化 SAR 强度": "VV-polarized SAR Intensity",
        "单位：dB": "Unit: dB",
        "PNG 导出失败，QGIS 代码：{code}": "PNG export failed with QGIS code {code}.",
        "PNG 导出后无法重新读取。": "The exported PNG could not be read back.",
        "PDF 导出失败，QGIS 代码：{code}": "PDF export failed with QGIS code {code}.",
        "# SAR 强度 dB 专题图导出报告\n\n": "# SAR Intensity Map Export Report (dB)\n\n",
        "- 状态：`{status}`\n": "- Status: `{status}`\n",
        "- 插件版本：`{version}`\n": "- Plugin version: `{version}`\n",
        "- 输入：`{path}`\n": "- Input: `{path}`\n",
        "- 输入 SHA-256：`{value}`\n": "- Input SHA-256: `{value}`\n",
        "- 模板 SHA-256：`{value}`\n": "- Template SHA-256: `{value}`\n",
        "- 坐标参考系：`{crs}`\n": "- Coordinate reference system: `{crs}`\n",
        "- 显示范围：`{minimum:.6f}` 至 `{maximum:.6f}` dB\n": "- Display range: `{minimum:.6f}` to `{maximum:.6f}` dB\n",
        "- 显示方式：2%—98% 分位数，黑—白线性拉伸\n": "- Display method: 2nd–98th percentile black-to-white linear stretch\n",
        "- 原始 dB 栅格未重算，输入文件哈希在导出前后保持一致。\n": "- The source dB raster was not recomputed; its file hash remained unchanged before and after export.\n",
        "- QGZ 为正式可编辑成果；PNG/PDF 为本次导出快照。\n": "- The QGZ is the editable product; PNG/PDF files are export snapshots.\n",
        "SAR 专题图模板或来源报告缺失。": "The SAR thematic-map template or its provenance report is missing.",
        "SAR 灰度色标资源缺失。": "The SAR grayscale color-bar resource is missing.",
        "SAR 专题图模板未通过来源审查。": "The SAR thematic-map template did not pass provenance review.",
        "SAR 专题图模板哈希与来源报告不一致。": "The SAR thematic-map template hash does not match its provenance report.",
        "SAR 专题图输入必须是单波段栅格。": "The SAR thematic-map input must be a single-band raster.",
        "SAR 专题图输入缺少有效坐标参考系。": "The SAR thematic-map input has no valid coordinate reference system.",
        "用户取消了 SAR 专题图导出。": "The user cancelled SAR thematic-map export.",
        "复制 dB 栅格到新的便携式 run": "Copying the dB raster into a new portable run",
        "dB 栅格副本哈希与输入不一致。": "The copied dB raster hash does not match the input.",
        "计算 2%—98% 显示分位数": "Calculating the 2nd–98th display percentiles",
        "创建独立 QGIS 工程和灰度渲染": "Creating an isolated QGIS project and grayscale renderer",
        "BC2 VV SAR 强度（dB）": "BC2 VV SAR Intensity (dB)",
        "QGIS 无法加载 dB 栅格副本。": "QGIS could not load the copied dB raster.",
        "绑定 SAR 强度专题图模板和七项可选信息": "Binding the SAR intensity map template and seven optional information fields",
        "SAR 专题图布局缺少主地图范围。": "The SAR thematic-map layout has no main map extent.",
        "保存可人工微调的 QGZ": "Saving an editable QGZ for manual refinement",
        "QGZ 保存失败。": "Failed to save the QGZ.",
        "导出 PNG/PDF": "Exporting PNG/PDF",
        "执行输入完整性与工程结构复核": "Checking input integrity and project structure",
        "输入 dB 栅格在制图前后哈希发生变化。": "The input dB raster hash changed during map production.",
        "写出的 QGZ 重新读取检查未通过。": "The written QGZ failed the read-back check.",
        "写出的 QGZ 缺少可用的独立灰度色标资源。": "The written QGZ has no usable independent grayscale color-bar resource.",
        "SAR 强度 dB 专题图导出完成：PASS": "SAR intensity map export in dB completed: PASS",
        "# SAR 专题图导出失败\n\n": "# SAR Thematic-map Export Failed\n\n",
        "- 错误类型：`{error_type}`\n": "- Error type: `{error_type}`\n",
        "- 错误信息：{error}\n\n": "- Error: {error}\n\n",
        "本次任务目录保留用于诊断；输入 dB 栅格和模板未被覆盖。\n\n": "This run directory has been retained for diagnosis. The input dB raster and template were not overwritten.\n\n",
        "请选择单波段 SAR 强度 dB GeoTIFF。": "Select a single-band SAR intensity GeoTIFF in dB.",
        "SAR 强度专题图输入必须为 TIF 或 TIFF。": "The SAR intensity map input must be a TIF or TIFF file.",
        "选择的 SAR 强度 dB GeoTIFF 不存在。": "The selected SAR intensity GeoTIFF in dB does not exist.",
        "请选择输出根目录。": "Select an output root directory.",
        "输出根目录不存在或不是文件夹。": "The output root does not exist or is not a directory.",
        "专题图标题不能为空。": "The thematic-map title cannot be empty.",
        "坐标参考系": "Coordinate Reference System",
        "空间分辨率": "Spatial Resolution",
        "显示方法": "Display Method",
        "数据来源": "Data Source",
        "数据拍摄时间": "Acquisition Time",
        "制作单位": "Produced By",
        "已勾选显示“{label}”，请填写相应内容。": "Display is enabled for “{label}”; enter the corresponding text.",
        "已勾选显示制图时间，请选择日期。": "Map-production date is enabled; select a date.",
        "制图时间必须是有效的公历日期。": "The map-production date must be a valid calendar date.",
        "请至少选择一种输出：QGZ、PNG 或 PDF。": "Select at least one output format: QGZ, PNG, or PDF.",
        "DPI 必须在 72 到 1200 之间。": "DPI must be between 72 and 1200.",
        "右侧说明自动换行后超过 {maximum} 行，请精简坐标参考系、空间分辨率或显示方法。": "The wrapped right-side information exceeds {maximum} lines. Shorten the coordinate reference system, spatial resolution, or display method.",
        "制图时间": "Map-production Date",
        "BC2 VV SAR 强度 dB 专题图": "BC2 VV SAR Intensity Map in dB",
        "2%—98%线性拉伸": "2nd–98th Percentile Linear Stretch",
    },
    "SarMapDialog": {
        "SAR 强度 dB 专题制图": "SAR Intensity Mapping in dB",
        "本模块使用已完成预处理的单波段 SAR 强度 dB GeoTIFF，生成可编辑 QGZ 工程、PNG/PDF 专题图及质量检查报告。专题图标题、右侧说明和底部制图信息均可由用户设置，较长文字支持自动换行。": "Use a preprocessed single-band SAR intensity GeoTIFF in dB to generate an editable QGZ project, PNG/PDF thematic maps, and a quality assurance report. The title, right-side notes, and map-production information are configurable, with automatic wrapping for longer text.",
        "输入要求：影像应已完成必要的镶嵌、裁剪和线性功率转 dB 处理。本模块不重复执行影像镶嵌、掩膜裁剪或 10 × log10(P) 转换，也不修改原始输入影像。缺少完整 Sigma0/Gamma0 定标证据时，成果仅表述为 SAR 强度 dB。": "Input requirement: the image must already have undergone any required mosaicking, clipping, and linear-power-to-dB conversion. This module does not repeat mosaicking, mask clipping, or 10 × log10(P), and it does not modify the source image. Without complete Sigma0/Gamma0 calibration evidence, the product is described only as SAR intensity in dB.",
        "数据与输出": "Data and Output",
        "专题图设置": "Thematic-map Settings",
        "导出与日志": "Export and Log",
        "关闭": "Close",
        "SAR 强度 dB 专题制图模块已就绪。请确认输入影像、专题图设置和导出选项。": "The SAR intensity mapping module in dB is ready. Confirm the input image, thematic-map settings, and export options.",
        "SAR 强度 dB 影像": "SAR Intensity Image (dB)",
        "选择单波段 SAR 强度 dB GeoTIFF": "Select a Single-band SAR Intensity GeoTIFF in dB",
        "浏览…": "Browse…",
        "读取影像信息": "Read Image Information",
        "输入影像：": "Input Image:",
        "输出位置": "Output Location",
        "选择输出根目录；任务将自动创建时间戳子目录": "Select an output root; the task will create a timestamped subdirectory",
        "每次任务均在输出根目录中创建独立的时间戳子目录，并复制一份输入 SAR 强度 dB 影像，以便 QGZ 工程移动和后续人工调整；原始影像及已有成果不会被覆盖。": "Each task creates an isolated timestamped subdirectory and copies the input SAR intensity image in dB so that the QGZ can be moved and refined later. The source image and existing products are not overwritten.",
        "标题": "Title",
        "专题图标题：": "Thematic-map Title:",
        "右侧说明信息": "Right-side Information",
        "显示": "Show",
        "例如：WGS 84 / UTM zone 50N（EPSG:32650）": "Example: WGS 84 / UTM zone 50N (EPSG:32650)",
        "坐标参考系：": "Coordinate Reference System:",
        "例如：3 m": "Example: 3 m",
        "空间分辨率：": "Spatial Resolution:",
        "例如：2%—98%线性拉伸": "Example: 2nd–98th percentile linear stretch",
        "显示方法：": "Display Method:",
        "底部制图信息": "Map-production Information",
        "例如：BC2 SM ORG VV": "Example: BC2 SM ORG VV",
        "数据来源：": "Data Source:",
        "可填写单日、日期范围或多期说明": "Enter one date, a date range, or a multi-epoch description",
        "数据拍摄时间：": "Acquisition Time:",
        "使用当前日期": "Use Current Date",
        "制图时间：": "Map-production Date:",
        "请输入制作单位": "Enter the producing organization",
        "制作单位：": "Produced By:",
        "较长内容将根据模板宽度自动换行；取消显示后，其余内容自动上移，不保留空行。": "Longer text wraps automatically to the template width. When a field is hidden, the remaining fields move up without leaving a blank line.",
        "右侧说明预览": "Right-side Information Preview",
        "输出": "Output",
        "可编辑 QGZ": "Editable QGZ",
        "输出类型：": "Output Types:",
        "导出分辨率（DPI）：": "Export Resolution (DPI):",
        "请检查当前设置": "Check the Current Settings",
        "检查当前设置": "Check Current Settings",
        "生成专题图": "Generate Thematic Map",
        "取消任务": "Cancel Task",
        "打开输出目录": "Open Output Folder",
        "清空日志": "Clear Log",
        "（右侧三项全部隐藏）": "(All three right-side fields are hidden)",
        "当前占用 {line_count}/{maximum} 行；超过 {maximum} 行时需要精简右侧说明内容。": "Currently using {line_count}/{maximum} lines. Shorten the right-side information if it exceeds {maximum} lines.",
        "设置已变化，请重新检查": "Settings changed; check them again",
        "选择输出根目录": "Select Output Root",
        "[检查] 请先选择存在的 GeoTIFF。": "[Check] Select an existing GeoTIFF first.",
        "QGIS 无法读取该栅格。": "QGIS could not read this raster.",
        "[读取] {crs}；分辨率 {resolution}；{width}×{height}；{bands} 波段。": "[Read] {crs}; resolution {resolution}; {width}×{height}; {bands} band(s).",
        "CRS 未知": "Unknown CRS",
        "[读取失败] {error}": "[Read failed] {error}",
        "设置快照：": "Settings snapshot:",
        "设置检查未通过：{count} 项": "Settings check failed: {count} item(s)",
        "[需要处理] {error}": "[Action required] {error}",
        "设置检查通过，可以生成专题图": "Settings check passed; the thematic map can be generated",
        "[PASS] 当前设置通过只读检查。": "[PASS] The current settings passed the read-only check.",
        "开始生成 SAR 强度 dB 专题图。": "Starting SAR intensity map generation in dB.",
        "SAR 强度 dB 专题图完成：{status}": "SAR intensity map in dB completed: {status}",
        "[{status}] 输出目录：{directory}": "[{status}] Output directory: {directory}",
        "生成失败，请查看日志和失败记录": "Generation failed; review the log and failure record",
        "已请求取消；将在当前步骤结束后停止": "Cancellation requested; the task will stop after the current step",
        "[取消] 已收到取消请求。": "[Cancel] Cancellation request received.",
    },
}

for _module_catalog in (MODULES12_TRANSLATIONS, MODULES456_TRANSLATIONS):
    for _context_name, _messages in _module_catalog.items():
        TRANSLATIONS.setdefault(_context_name, {}).update(_messages)


def main() -> None:
    tree = ET.parse(CATALOG)
    root = tree.getroot()
    found: set[tuple[str, str]] = set()
    for context in root.findall("context"):
        context_name = context.findtext("name", default="")
        translations = TRANSLATIONS.get(context_name, {})
        for message in list(context.findall("message")):
            existing = message.find("translation")
            if existing is not None and existing.get("type") in {
                "obsolete",
                "vanished",
            }:
                context.remove(message)
                continue
            source = message.findtext("source", default="")
            if source not in translations:
                continue
            translation = message.find("translation")
            if translation is None:
                translation = ET.SubElement(message, "translation")
            translation.attrib.pop("type", None)
            translation.text = translations[source]
            found.add((context_name, source))
    expected = {
        (context_name, source)
        for context_name, values in TRANSLATIONS.items()
        for source in values
    }
    missing = sorted(expected - found)
    if missing:
        contexts = {
            context.findtext("name", default=""): context
            for context in root.findall("context")
        }
        for context_name, source in missing:
            context = contexts.get(context_name)
            if context is None:
                context = ET.SubElement(root, "context")
                ET.SubElement(context, "name").text = context_name
                contexts[context_name] = context
            message = ET.SubElement(context, "message")
            ET.SubElement(message, "source").text = source
            ET.SubElement(message, "translation").text = TRANSLATIONS[
                context_name
            ][source]
    ET.indent(tree, space="    ")
    xml_body = ET.tostring(root, encoding="unicode")
    CATALOG.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE TS>\n'
        + xml_body
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
