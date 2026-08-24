"""Reviewed English translations for geometry correction and SAR processing."""

from __future__ import annotations


MODULE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "GeometryCorrectionDialog": {
        "GCP 几何校正与精度检查": "GCP Geometric Correction and Accuracy Assessment",
        "本模块包含“GCP 几何校正”和“流程验证”两种模式。GCP 几何校正使用外部训练控制点完成影像到地图坐标的校正，并通过独立检查点评估精度；流程验证仅用于检查控制点读取、变换计算、RMSE 统计和报告输出。所有任务均创建独立输出目录，不修改输入数据。": "This module provides GCP Geometric Correction and Workflow Validation modes. GCP Geometric Correction uses external training control points for image-to-map correction and independent check points for accuracy assessment. Workflow Validation only checks control-point reading, transform calculation, RMSE statistics, and report output. Every task creates a separate output directory and does not modify the input data.",
        "GCP 几何校正": "GCP Geometric Correction",
        "流程验证": "Workflow Validation",
        "请填写参数并检查当前设置": "Enter the parameters and check the current settings",
        "检查当前设置": "Check Current Settings",
        "开始几何校正": "Start Geometric Correction",
        "取消任务": "Cancel Task",
        "打开输出目录": "Open Output Folder",
        "清空日志": "Clear Log",
        "GCP 几何校正模块已就绪。请选择待校正影像、训练 GCP、独立检查点和输出目录，然后检查当前设置。": "The GCP geometric-correction module is ready. Select the source image, training GCPs, independent check points, and output directory, then check the current settings.",
        "适用范围：本模式基于外部 GCP 执行影像到地图坐标的几何校正，支持一阶仿射、二阶/三阶多项式和薄板样条（TPS），并使用独立检查点评估 RMSE。本模式不使用 SAR 轨道、传感器模型或 DEM，不属于 Range-Doppler 地形校正。": "Scope: this mode performs image-to-map geometric correction from external GCPs. It supports first-order affine, second- and third-order polynomial, and thin-plate spline (TPS) transforms, and evaluates RMSE with independent check points. It does not use SAR orbit data, a sensor model, or a DEM and is not Range-Doppler terrain correction.",
        "GCP 几何校正输入": "GCP Geometric-correction Inputs",
        "选择待校正 PNG、TIFF 或其他 GDAL 栅格": "Select a PNG, TIFF, or other GDAL raster to correct",
        "待校正影像：": "Source Image:",
        "选择训练 GCP CSV 或 QGIS Georeferencer .points 文件": "Select a training-GCP CSV or QGIS Georeferencer .points file",
        "训练GCP：": "Training GCPs:",
        "选择独立检查点 CSV 或 .points 文件": "Select an independent check-point CSV or .points file",
        "独立检查点：": "Independent Check Points:",
        "选择输出根目录；任务将自动创建时间戳子目录": "Select an output root; the task creates a timestamped subdirectory",
        "输出根目录：": "Output Root:",
        "例如 EPSG:32650": "For example, EPSG:32650",
        "目标坐标参考系（CRS）：": "Target Coordinate Reference System (CRS):",
        "一阶仿射": "First-order Affine",
        "二阶多项式": "Second-order Polynomial",
        "三阶多项式": "Third-order Polynomial",
        "薄板样条（TPS）": "Thin-plate Spline (TPS)",
        "变换模型：": "Transform Model:",
        "输出像元大小：": "Output Pixel Size:",
        "双线性（连续影像推荐）": "Bilinear (recommended for continuous imagery)",
        "最近邻（分类影像）": "Nearest Neighbour (categorical imagery)",
        "三次卷积（平滑影像）": "Cubic Convolution (smooth imagery)",
        "重采样：": "Resampling:",
        "仅报告，人工判定": "Report only; manual decision",
        "独立检查点 RMSE 阈值（像素）：": "Independent Check-point RMSE Threshold (pixels):",
        "我确认训练 GCP 与独立检查点来自外部参考，且两组点相互独立；并了解本功能不执行基于 SAR 轨道与 DEM 的地形校正。": "I confirm that the training GCPs and independent check points come from external reference data and are mutually independent, and understand that this function does not perform SAR orbit- and DEM-based terrain correction.",
        "完成后加载校正 GeoTIFF，并缩放至结果图层范围": "Load the corrected GeoTIFF when complete and zoom to the result layer",
        "支持标准 CSV（point_id、pixel、line、x、y）及 QGIS Georeferencer .points 文件。pixel/line 采用左上角为原点的 GDAL 像素坐标。": "Supports standard CSV files (point_id, pixel, line, x, y) and QGIS Georeferencer .points files. pixel/line use GDAL pixel coordinates with the upper-left origin.",
        "导出标准GCP CSV空模板…": "Export Blank Standard GCP CSV Template…",
        "控制点格式：": "Control-point Format:",
        "选择训练GCP": "Select Training GCPs",
        "选择独立检查点": "Select Independent Check Points",
        "选择几何校正输出根目录": "Select Geometric-correction Output Root",
        "本页根据参考 GeoTIFF 的 GeoTransform 自动构造控制点，用于验证控制点读取、变换计算、独立检查、RMSE 统计和报告输出流程。由于控制点由参考影像自身信息生成，所得近零误差不能代表真实影像的校正精度。": "This page constructs control points automatically from the reference GeoTIFF GeoTransform to validate control-point reading, transform calculation, independent checking, RMSE statistics, and report output. Because the control points are derived from the reference image itself, the resulting near-zero error does not represent real-image correction accuracy.",
        "流程验证输入": "Workflow-validation Inputs",
        "选择单波段Byte、EPSG:4326参考GeoTIFF": "Select a single-band Byte reference GeoTIFF in EPSG:4326",
        "参考GeoTIFF：": "Reference GeoTIFF:",
        "双线性（教学基线）": "Bilinear (teaching baseline)",
        "最近邻": "Nearest Neighbour",
        "三次卷积": "Cubic Convolution",
        "我已了解：控制点由参考 GeoTIFF 的 GeoTransform 自动构造，本页仅用于流程验证。": "I understand that the control points are constructed automatically from the reference GeoTIFF GeoTransform and that this page is only for workflow validation.",
        "选择流程验证输出根目录": "Select Workflow-validation Output Root",
        "浏览…": "Browse…",
        "自动": "Auto",
        "选择待校正原始影像": "Select Source Image to Correct",
        "栅格影像 (*.tif *.tiff *.png *.jpg *.jpeg *.img);;所有文件 (*)": "Raster images (*.tif *.tiff *.png *.jpg *.jpeg *.img);;All files (*)",
        "选择教学参考GeoTIFF": "Select Teaching Reference GeoTIFF",
        "控制点文件 (*.csv *.points);;所有文件 (*)": "Control-point files (*.csv *.points);;All files (*)",
        "导出标准GCP CSV空模板": "Export Blank Standard GCP CSV Template",
        "GCP模板导出失败": "GCP Template Export Failed",
        "[失败] 无法导出GCP模板：{error}": "[Failed] Could not export the GCP template: {error}",
        "[模板] 已导出标准GCP CSV空模板：{path}": "[Template] Blank standard GCP CSV template exported: {path}",
        "开始流程验证": "Start Workflow Validation",
        "输入已改变，请重新检查": "Inputs changed; check them again",
        "输入检查未通过": "Input check failed",
        "[拒绝] {error}": "[Rejected] {error}",
        "输入检查通过，可以开始": "Input check passed; ready to start",
        "[通过/{mode}] {width}×{height} | {band_type} | 原坐标系={crs}": "[Pass/{mode}] {width}×{height} | {band_type} | source CRS={crs}",
        "无/未知": "None/Unknown",
        "[提醒] {warning}": "[Notice] {warning}",
        "[控制点] 训练GCP={train_count}；独立检查点={check_count}；目标坐标系={target_crs}。": "[Control points] training GCPs={train_count}; independent check points={check_count}; target CRS={target_crs}.",
        "[限制] 控制点地图坐标来自参考GeoTransform，RMSE 仅用于验证计算和报告流程。": "[Limitation] Control-point map coordinates come from the reference GeoTransform; RMSE only validates the calculation and reporting workflow.",
        "任务运行中": "Task running",
        "[开始] 正在创建独立任务目录。": "[Start] Creating a separate task directory.",
        "正在取消……": "Cancelling…",
        "[取消] 已发出取消请求，当前安全检查点后停止。": "[Cancel] Cancellation requested; the task will stop after the current safe checkpoint.",
        "几何校正完成：{status}": "Geometric correction complete: {status}",
        "[完成] {run_dir}": "[Complete] {run_dir}",
        "[独立检查] RMSE={rmse:.6f}像素；最大误差={maximum:.6f}像素。": "[Independent check] RMSE={rmse:.6f} pixels; maximum error={maximum:.6f} pixels.",
        "流程验证完成：PASS": "Workflow validation complete: PASS",
        "[独立检查/流程验证] RMSE={rmse:.12g}像素；最大误差={maximum:.12g}像素。": "[Independent check/workflow validation] RMSE={rmse:.12g} pixels; maximum error={maximum:.12g} pixels.",
        "任务已取消": "Task cancelled",
        "[已取消] 任务目录保留取消记录，不作为正式成果。": "[Cancelled] The task directory retains the cancellation record and is not a formal result.",
        "任务失败": "Task failed",
        "[失败/{mode}] {error_type}：{error}": "[Failed/{mode}] {error_type}: {error}",
        "未知错误": "Unknown error",
        "几何校正成果": "Geometric-correction Result",
        "[提醒] 成果已生成，但自动加载图层失败。": "[Notice] The result was generated, but the layer could not be loaded automatically.",
        "[加载] 校正GeoTIFF已加载并缩放到图层。": "[Load] The corrected GeoTIFF was loaded and the map zoomed to the layer.",
        "[提醒] 自动加载成果失败：{error}": "[Notice] Could not load the result automatically: {error}",
    },
    "SarProcessingDialog": {
        "SAR 影像镶嵌、裁剪与显示增强": "SAR Image Mosaicking, Clipping, and Display Enhancement",
        "本模块支持递归扫描 ORG 产品目录，处理单景或多景单波段线性功率 GeoTIFF，完成覆盖顺序检查、影像镶嵌、掩膜裁剪、线性功率转 dB，以及灰度或伪彩色显示产品生成。": "This module recursively scans ORG product directories and processes one or more single-band linear-power GeoTIFFs. It checks source order, mosaics imagery, clips by a mask, converts linear power to dB, and creates grayscale or pseudocolour display products.",
        "处理约束：多景镶嵌时，列表中靠后的影像以有效像元覆盖靠前影像；升轨与降轨混用、强度尺度异常需由用户确认。显示增强和外缘羽化仅作用于独立的 8 位显示产品，不改变线性功率或 dB 成果。本模块不执行自动接缝线、物理辐射平衡或专题图排版。": "Processing constraints: in a multi-scene mosaic, valid pixels from later images in the list overwrite valid pixels from earlier images. Mixing ascending and descending passes and intensity-scale anomalies require user confirmation. Display enhancement and outer-edge feathering affect only the separate 8-bit display product and do not change the linear-power or dB results. This module does not perform automatic seamline generation, physical radiometric balancing, or thematic-map layout.",
        "输入影像与覆盖顺序": "Input Images and Overwrite Order",
        "选择ORG总目录、产品目录或包含GeoTIFF的文件夹": "Select an ORG root, product directory, or folder containing GeoTIFFs",
        "浏览…": "Browse…",
        "扫描 GeoTIFF": "Scan GeoTIFFs",
        "从上到下依次处理；列表后面的有效像元覆盖前面的有效像元。": "Process from top to bottom; valid pixels in later list items overwrite those in earlier items.",
        "上移": "Move Up",
        "下移": "Move Down",
        "仅保留升轨": "Keep Ascending Only",
        "仅保留降轨": "Keep Descending Only",
        "恢复全部": "Restore All",
        "裁剪与输出": "Clipping and Output",
        "选择Polygon/MultiPolygon裁剪面": "Select a Polygon/MultiPolygon clipping mask",
        "裁剪面：": "Clipping Mask:",
        "选择输出根目录；任务将自动创建时间戳子目录": "Select an output root; the task creates a timestamped subdirectory",
        "输出根目录：": "Output Root:",
        "处理参数": "Processing Parameters",
        "X 方向": "X direction",
        "Y 方向": "Y direction",
        "目标像元大小：": "Target Pixel Size:",
        "镶嵌重采样：": "Mosaic Resampling:",
        "裁剪重采样：": "Clip Resampling:",
        "低值": "Low",
        "高值": "High",
        "百分位范围：": "Percentile Range:",
        "显示增强与外缘羽化": "Display Enhancement and Outer-edge Feathering",
        "2%—98%累计百分比拉伸": "2nd–98th Cumulative-percentile Stretch",
        "最小值—最大值拉伸": "Minimum–Maximum Stretch",
        "均值—标准差拉伸": "Mean–Standard-deviation Stretch",
        "直方图均衡化": "Histogram Equalization",
        "均值居中的8位归一化": "Mean-centred 8-bit Normalization",
        "增强方法：": "Enhancement Method:",
        "整体增亮或压暗 8 位显示产品。": "Brighten or darken the entire 8-bit display product.",
        "扩大或压缩明暗差异。": "Expand or compress tonal contrast.",
        "调整中间亮度层次；1.00 表示不调整。": "Adjust midtone brightness; 1.00 applies no adjustment.",
        "亮度": "Brightness",
        "对比度": "Contrast",
        "亮度与层次调整：": "Brightness and Tone Adjustments:",
        "灰度": "Grayscale",
        "单波段伪彩色": "Single-band Pseudocolour",
        "显示模式": "Display Mode",
        "色带": "Colour Ramp",
        "颜色设置：": "Colour Settings:",
        " 像素": " pixels",
        "关闭": "Off",
        "仅淡化8位显示产品的有效数据外缘；不生成seamline，不改变科学栅格。": "Only fade the outer edge of valid data in the 8-bit display product; this does not create a seamline or change the scientific raster.",
        "0 表示关闭": "0 means off",
        "外缘羽化：": "Outer-edge Feathering:",
        "生成独立的 RGBA 8 位显示产品": "Create a separate RGBA 8-bit display product",
        "我确认输入为非负线性功率数据，可执行 10 × log10 转换。": "I confirm that the inputs contain non-negative linear-power data and may be converted with 10 × log10.",
        "我确认影像覆盖顺序正确，并了解后列影像覆盖前列影像。": "I confirm that the image overwrite order is correct and understand that later images overwrite earlier images.",
        "我确认需要混合升轨与降轨影像，并了解其几何和强度差异。": "I confirm that ascending and descending imagery must be mixed and understand their geometric and intensity differences.",
        "我已检查影像间的强度尺度异常，并决定保留当前输入。": "I have reviewed intensity-scale anomalies between images and decided to retain the current inputs.",
        "我确认使用三次卷积，并了解其可能产生非正功率像元。": "I confirm the use of cubic convolution and understand that it may produce non-positive power pixels.",
        "完成后将结果加载至当前 QGIS 工程，优先加载 8 位显示产品。": "Load the result into the current QGIS project when complete, preferring the 8-bit display product.",
        "科学语义与操作确认": "Scientific Semantics and Operation Confirmations",
        "输入与顺序": "Inputs and Order",
        "处理与显示": "Processing and Display",
        "科学确认": "Scientific Confirmations",
        "请选择或扫描输入影像，并检查当前设置": "Select or scan input images and check the current settings",
        "检查当前设置": "Check Current Settings",
        "开始影像处理": "Start Image Processing",
        "取消任务": "Cancel Task",
        "打开输出目录": "Open Output Folder",
        "清空日志": "Clear Log",
        "SAR 影像处理模块已就绪。请选择或扫描输入影像，并检查影像覆盖顺序。": "The SAR image-processing module is ready. Select or scan input images and review the overwrite order.",
        "[安全设置] 已把旧重采样偏好迁移为最近邻；如重新选择三次卷积，必须显式确认风险。": "[Safe setting] The previous resampling preference was migrated to nearest neighbour. Selecting cubic convolution again requires explicit risk confirmation.",
        "自动": "Auto",
        "最近邻": "Nearest Neighbour",
        "双线性": "Bilinear",
        "三次卷积": "Cubic Convolution",
        "选择SAR GeoTIFF文件夹": "Select SAR GeoTIFF Folder",
        "选择裁剪面": "Select Clipping Mask",
        "矢量裁剪面 (*.gpkg *.shp *.geojson);;": "Vector clipping masks (*.gpkg *.shp *.geojson);;",
        "所有文件 (*.*)": "All files (*.*)",
        "选择输出根目录": "Select Output Root",
        "扫描失败": "Scan failed",
        "[拒绝] {error}": "[Rejected] {error}",
        "已扫描{count}幅影像，请检查顺序": "Scanned {count} image(s); review the order",
        "[输入顺序]": "[Input order]",
        "[ORG目录识别] 产品{product_count}景 | 任务标识{families} | 元数据任务{missions} | 极化{polarisations} | 轨道{directions}": "[ORG directory recognition] products={product_count} | folder families={families} | metadata missions={missions} | polarizations={polarisations} | passes={directions}",
        "未知": "Unknown",
        "  {index}. {date} | {orbit} | 入射角{angle} | 伴随文件{completeness}": "  {index}. {date} | {orbit} | incidence angle {angle} | companion files {completeness}",
        "日期未知": "Date unknown",
        "轨道未知": "Pass unknown",
        "完整": "complete",
        "不完整": "incomplete",
        "[轨向筛选] 未发现{direction}产品。": "[Pass filter] No {direction} products found.",
        "升轨": "ascending",
        "降轨": "descending",
        "已保留{orbit}{count}景，请检查顺序": "Kept {count} {orbit} scene(s); review the order",
        "[轨向筛选] 已保留{orbit}{count}景；未复制、移动或修改源数据。": "[Pass filter] Kept {count} {orbit} scene(s); no source data were copied, moved, or modified.",
        "已恢复全部{count}景，请检查顺序": "Restored all {count} scene(s); review the order",
        "[轨向筛选] 已恢复扫描结果全部{count}景。": "[Pass filter] Restored all {count} scanned scene(s).",
        "设置已改变，请重新检查": "Settings changed; check them again",
        "正在只读检查输入……": "Checking inputs read-only…",
        "组间中位强度异常": "between-group median-intensity anomaly",
        "输入检查未通过": "Input check failed",
        "输入检查通过，可以开始": "Input check passed; ready to start",
        "[通过] {count}幅 | {crs} | {x_resolution}×{y_resolution}": "[Pass] {count} image(s) | {crs} | {x_resolution}×{y_resolution}",
        "  {order}. {file} | 正值比例 {ratio:.6f}": "  {order}. {file} | positive-value ratio {ratio:.6f}",
        "[科学预检警告] {warning}": "[Scientific preflight warning] {warning}",
        "[资源估算] 掩膜包络网格 {width}×{height}，三阶段未压缩约{size_gib:.3f} GiB": "[Resource estimate] mask-envelope grid {width}×{height}; approximately {size_gib:.3f} GiB uncompressed across three stages",
        "影像处理任务运行中": "Image-processing task running",
        "正在取消……": "Cancelling…",
        "[取消] 已发出请求，将在安全检查点停止。": "[Cancel] Request sent; the task will stop at a safe checkpoint.",
        "影像处理完成：PASS": "Image processing complete: PASS",
        "[完成] {run_dir}": "[Complete] {run_dir}",
        "[显示范围] {minimum:.6f} — {maximum:.6f} dB": "[Display range] {minimum:.6f}–{maximum:.6f} dB",
        "[加载结果失败] {error}": "[Result load failed] {error}",
        "影像处理任务已取消": "Image-processing task cancelled",
        "[已取消] 任务目录保留取消记录，不作为正式成果。": "[Cancelled] The task directory retains the cancellation record and is not a formal result.",
        "影像处理任务失败": "Image-processing task failed",
        "[失败] {error_type}：{error}": "[Failed] {error_type}: {error}",
        "未知错误": "Unknown error",
        "SAR显示增强结果（8位，仅用于显示）— {run_label}": "SAR Display-enhancement Result (8-bit, display only) — {run_label}",
        "SAR镶嵌裁剪结果（dB）— {run_label}": "SAR Mosaic-and-clip Result (dB) — {run_label}",
        "QGIS无法加载SAR处理结果。": "QGIS could not load the SAR processing result.",
        "[QGIS] 自动坐标转换缩放失败，改用QGIS活动图层缩放：{error}": "[QGIS] Automatic transformed-extent zoom failed; using QGIS active-layer zoom instead: {error}",
        "[QGIS] 已加载{product}并按工程坐标系缩放；未清空现有图层。": "[QGIS] Loaded {product} and zoomed in the project CRS; existing layers were retained.",
        "8位显示产品": "8-bit display product",
        "Float32 dB结果": "Float32 dB result",
    },
    "@default": {},
}


_DEFAULT_TSV = r"""
用户取消了几何校正任务。	The user cancelled the geometric-correction task.
正在导出无地理信息PNG……	Exporting the PNG without georeferencing…
正在执行GCP Warp……	Running GCP Warp…
用户在GCP Warp过程中取消了任务。	The user cancelled the task during GCP Warp.
正在比较参考影像与恢复影像……	Comparing the reference and restored images…
参考影像（GeoTIFF）	Reference Image (GeoTIFF)
空间参考恢复结果（GeoTIFF）	Georeferencing-restored Result (GeoTIFF)
棋盘格叠加对比	Checkerboard Overlay Comparison
绝对像元差值（8位灰度）	Absolute Pixel-value Difference (8-bit grayscale)
绝对灰度差值	Absolute Grayscale Difference
有效像元范围内无灰度差异\n最大绝对差：0\n灰度差异 RMSE：0	No grayscale difference within valid pixels\nMaximum absolute difference: 0\nGrayscale-difference RMSE: 0
几何校正结果对比与像元差异检查	Geometric-correction Result Comparison and Pixel-value Difference Check
8位灰度预览；几何精度以独立检查点 RMSE 报告为准	8-bit grayscale preview; geometric accuracy is determined by the independent check-point RMSE report
注：像元差异用于检查影像显示一致性，不替代独立检查点几何精度评价。	Note: pixel-value differences check display consistency and do not replace geometric-accuracy assessment with independent check points.
叠加比较图已生成。	The overlay comparison figure has been generated.
用户取消了 GCP 几何校正任务。	The user cancelled the GCP geometric-correction task.
一阶仿射	First-order Affine
二阶多项式	Second-order Polynomial
三阶多项式	Third-order Polynomial
薄板样条（TPS）	Thin-plate Spline (TPS)
控制点文件不存在：{path}	Control-point file does not exist: {path}
未知控制点子集：{subset}	Unknown control-point subset: {subset}
控制点文件缺少表头：{path}	Control-point file has no header: {path}
控制点文件缺少必要字段{missing}：{filename}；需要pixel,line,x,y，或QGIS的sourceX,sourceY,mapX,mapY。	Control-point file {filename} is missing required fields {missing}; use pixel,line,x,y or QGIS sourceX,sourceY,mapX,mapY.
控制点文件没有启用的点：{path}	Control-point file has no enabled points: {path}
{filename}第{row}行含非数值控制点坐标。	Row {row} of {filename} contains non-numeric control-point coordinates.
{filename}第{row}行含非有限数值。	Row {row} of {filename} contains non-finite values.
无法识别目标坐标系：{value}	Unrecognized target coordinate reference system: {value}
不支持的几何变换模型：{model}	Unsupported geometric transform model: {model}
{model_label}至少需要{minimum}个启用的训练GCP，其中包含用于稳定性检查的冗余点。	{model_label} requires at least {minimum} enabled training GCPs, including redundant points for stability checks.
独立精度检查至少需要3个检查点。	Independent accuracy assessment requires at least 3 check points.
训练点与检查点的point_id必须全局唯一。	point_id values must be unique across training and check points.
训练点和检查点不能使用相同的影像像素位置。	Training and check points must not use the same image-pixel locations.
{point_id}的pixel={pixel}超出影像宽度0…{maximum}。	{point_id}: pixel={pixel} is outside the image width 0…{maximum}.
{point_id}的line={line}超出影像高度0…{maximum}。	{point_id}: line={line} is outside the image height 0…{maximum}.
训练GCP空间分布较差，模型解算条件数偏大。	Training GCPs are poorly distributed and the model solution has a high condition number.
训练GCP未覆盖影像至少50%的宽度或高度，外推区域可能不稳定。	Training GCPs do not span at least 50% of the image width or height; extrapolated areas may be unstable.
仿射模型至少需要3个训练GCP。	The affine model requires at least 3 training GCPs.
训练GCP在行或列方向没有足够分布，无法拟合仿射模型。	Training GCPs lack sufficient row or column spread to fit an affine model.
训练GCP共线或分布退化，仿射设计矩阵秩不足。	Training GCPs are collinear or degenerate, leaving the affine design matrix rank-deficient.
训练GCP仿射解算失败。	The affine solution for the training GCPs failed.
{model_label}至少需要{minimum}个训练GCP。	{model_label} requires at least {minimum} training GCPs.
训练GCP在行或列方向没有足够分布。	Training GCPs lack sufficient row or column spread.
{model_label}设计矩阵秩不足；请增加分布均匀且不共线的训练GCP。	The {model_label} design matrix is rank-deficient; add well-distributed, non-collinear training GCPs.
薄板样条（TPS）至少需要{minimum}个训练GCP。	Thin-plate spline (TPS) requires at least {minimum} training GCPs.
TPS控制点分布退化；请增加分布均匀且不重合的训练GCP。	The TPS control-point distribution is degenerate; add well-distributed, non-coincident training GCPs.
无法预测未知模型：{model}	Cannot predict with unknown model: {model}
残差计算没有控制点。	No control points were supplied for residual calculation.
没有可写入的残差记录：{path}	There are no residual records to write: {path}
无法读取预览栅格：{path}	Could not read preview raster: {path}
训练 GCP（{count}）	Training GCPs ({count})
独立检查点（{count}）	Independent Check Points ({count})
输入栅格与控制点分布	Input Raster and Control-point Distribution
校正 GeoTIFF 快视图	Corrected GeoTIFF Preview
训练点	Training Points
独立检查点	Independent Check Points
控制点残差大小	Control-point Residual Magnitudes
点序号	Point Index
误差（输出像素）	Error (output pixels)
真实几何校正质量检查\n\n模型：{model_label}\n训练 GCP：{train_count}\n独立检查点：{check_count}\n训练 RMSE：{train_rmse:.6f} 像素\n检查 RMSE：{check_rmse:.6f} 像素\n检查最大误差：{max_check:.6f} 像素\n\n只有当检查点独立于训练 GCP，且两者均来自\n可靠外部参考时，精度评价才有效。\n\n本流程不是 SAR 轨道/DEM 地形校正。	Real Geometric-correction Quality Check\n\nModel: {model_label}\nTraining GCPs: {train_count}\nIndependent check points: {check_count}\nTraining RMSE: {train_rmse:.6f} pixels\nCheck RMSE: {check_rmse:.6f} pixels\nMaximum check error: {max_check:.6f} pixels\n\nAccuracy assessment is valid only when the check points are independent of the training GCPs and both come from reliable external reference data.\n\nThis workflow is not SAR orbit/DEM terrain correction.
外部 GCP 几何校正与独立精度检查	External-GCP Geometric Correction and Independent Accuracy Assessment
输出已存在：{path}	Output already exists: {path}
临时输出已存在：{path}	Temporary output already exists: {path}
无法将外部训练GCP附加到输入影像。	Could not attach the external training GCPs to the input image.
正在执行外部GCP几何校正Warp……	Running external-GCP geometric-correction Warp…
用户在真实GCP Warp过程中取消了任务。	The user cancelled the task during real-GCP Warp.
GDAL外部GCP几何校正Warp失败。	GDAL external-GCP geometric-correction Warp failed.
校正成果缺少坐标系或GeoTransform。	The corrected result has no coordinate reference system or GeoTransform.
请选择待校正原始影像。	Select the source image to correct.
请选择训练GCP文件。	Select a training-GCP file.
请选择独立检查点文件。	Select an independent check-point file.
不支持的重采样方法：{resampling}	Unsupported resampling method: {resampling}
目标X/Y分辨率必须同时为0（自动）或同时大于0。	Target X/Y resolutions must both be 0 (auto) or both be greater than 0.
目标分辨率不能为负数。	Target resolution cannot be negative.
检查点RMSE阈值不能为负数。	The check-point RMSE threshold cannot be negative.
请确认训练GCP和检查点来自独立外部参考，并理解本模式不等同于SAR轨道/地形校正。	Confirm that the training GCPs and check points come from independent external reference data and understand that this mode is not SAR orbit/terrain correction.
待校正影像没有可用波段。	The source image has no usable bands.
待校正影像尺寸过小。	The source image is too small.
输入影像已有空间参考；本模式仍会以外部GCP重新解算，原文件不会被覆盖。	The input image already has spatial reference information; this mode will still recompute it from external GCPs, without overwriting the source file.
请输入目标坐标系。	Enter a target coordinate reference system.
请选择已存在的输出根目录：{path}	Select an existing output root directory: {path}
`{threshold:.6g}`像素	`{threshold:.6g}` pixels
未设置（仅报告，需人工判定）	Not set (report only; manual decision required)
# 几何校正与独立精度检查报告\n\n	# Geometric Correction and Independent Accuracy Assessment Report\n\n
## 结论\n\n	## Conclusion\n\n
- 运行状态：`{status}`\n	- Run status: `{status}`\n
- 模型：外部训练GCP、{model_label}；\n	- Model: external training GCPs, {model_label};\n
- 训练GCP：{point_count}个；\n	- Training GCPs: {point_count};\n
- 独立检查点：{point_count}个；\n	- Independent check points: {point_count};\n
- 训练RMSE：`{rmse_pixel:.6f}`像素 / `{rmse_m:.6f}`米；\n	- Training RMSE: `{rmse_pixel:.6f}` pixels / `{rmse_m:.6f}` metres;\n
- 独立检查RMSE：`{rmse_pixel:.6f}`像素 / `{rmse_m:.6f}`米；\n	- Independent-check RMSE: `{rmse_pixel:.6f}` pixels / `{rmse_m:.6f}` metres;\n
- 独立检查最大误差：`{max_pixel:.6f}`像素 / `{max_m:.6f}`米；\n	- Maximum independent-check error: `{max_pixel:.6f}` pixels / `{max_m:.6f}` metres;\n
- 用户阈值：{threshold_text}。\n\n	- User threshold: {threshold_text}.\n\n
## 输入\n\n	## Inputs\n\n
- 待校正影像：`{path}`\n	- Source image: `{path}`\n
- 训练GCP：`{path}`\n	- Training GCPs: `{path}`\n
- 独立检查点：`{path}`\n	- Independent check points: `{path}`\n
- 目标坐标系：`{target_crs}`\n	- Target coordinate reference system: `{target_crs}`\n
- 重采样：`{resampling}`\n\n	- Resampling: `{resampling}`\n\n
## 输出\n\n	## Outputs\n\n
- 校正GeoTIFF：`{path}`\n	- Corrected GeoTIFF: `{path}`\n
- 训练残差：`03_质量检查/train_residuals.csv`\n	- Training residuals: `03_质量检查/train_residuals.csv`\n
- 检查点残差：`03_质量检查/check_residuals.csv`\n\n	- Check-point residuals: `03_质量检查/check_residuals.csv`\n\n
## 科学边界\n\n	## Scientific Boundary\n\n
本结果是基于外部控制点的普通影像到地图几何校正。检查点必须与训练GCP\n互相独立，且两者都必须来自可靠外部参考。该流程不包含SAR轨道参数、\n传感器成像模型、DEM或Range-Doppler Terrain Correction，不能替代严格的\nSAR几何/地形校正。本报告仅评价基于外部GCP的影像到地图坐标校正及独立检查点精度。\n	This result is an ordinary image-to-map geometric correction based on external control points. Check points must be independent of the training GCPs, and both sets must come from reliable external reference data. The workflow does not include SAR orbit parameters, a sensor imaging model, a DEM, or Range-Doppler Terrain Correction and cannot replace rigorous SAR geometric/terrain correction. This report evaluates only external-GCP image-to-map correction and independent check-point accuracy.\n
步骤1/5：读取外部训练GCP和独立检查点。	Step 1/5: Read external training GCPs and independent check points.
步骤2/5：拟合外部训练GCP变换模型。	Step 2/5: Fit the transform model from external training GCPs.
步骤3/5：计算训练残差和独立检查点RMSE。	Step 3/5: Calculate training residuals and independent check-point RMSE.
步骤4/5：写入质量检查报告。	Step 4/5: Write the quality-assessment report.
02_校正成果：校正后的GeoTIFF\n	02_校正成果: corrected GeoTIFF\n
03_质量检查：训练点与独立检查点残差\n	03_质量检查: training-point and independent-check-point residuals\n
04_报告：JSON和Markdown质量报告\n	04_报告: JSON and Markdown quality reports\n
注意：本模式不是SAR轨道/DEM地形校正。\n	Note: this mode is not SAR orbit/DEM terrain correction.\n
步骤5/5：GCP 几何校正任务完成，等待人工精度判定。	Step 5/5: GCP geometric-correction task complete; awaiting manual accuracy decision.
"""


for _line in _DEFAULT_TSV.strip().splitlines():
    _source, _english = _line.split("\t", 1)
    MODULE_TRANSLATIONS["@default"][_source.replace(r"\n", "\n")] = _english.replace(
        r"\n", "\n"
    )


_DEFAULT_TSV_2 = r"""
请选择参考GeoTIFF。	Select a reference GeoTIFF.
参考影像必须是.tif或.tiff文件。	The reference image must be a .tif or .tiff file.
参考GeoTIFF不存在。	The reference GeoTIFF does not exist.
请选择已有的输出根目录。	Select an existing output root directory.
重采样方法必须是near、bilinear或cubic。	The resampling method must be near, bilinear, or cubic.
请确认已了解本功能仅用于几何校正流程验证。	Confirm that you understand this function is only for geometric-correction workflow validation.
参考影像预检失败：{error}	Reference-image preflight failed: {error}
输入预检已通过，正在记录manifest……	Input preflight passed; recording the manifest…
步骤1/6：导出无地理信息PNG。	Step 1/6: Export a PNG without georeferencing.
步骤2/6：生成训练点和独立检查点。	Step 2/6: Generate training points and independent check points.
步骤3/6：仅用训练点拟合一阶仿射模型。	Step 3/6: Fit a first-order affine model using training points only.
步骤4/6：使用训练GCP恢复GeoTIFF。	Step 4/6: Restore a GeoTIFF using the training GCPs.
步骤5/6：计算网格、像元值和叠加比较。	Step 5/6: Compare grids, pixel values, and overlays.
步骤6/6：验证源文件完整性并生成报告。	Step 6/6: Verify source-file integrity and generate the report.
一个或多个几何校正验收门未通过。	One or more geometric-correction acceptance gates failed.
几何校正教学任务完成。	Geometric-correction teaching task complete.
用户取消了SAR处理任务。	The user cancelled the SAR-processing task.
正在计算哈希：{name}	Calculating hash: {name}
数据缺少坐标系。	The dataset has no coordinate reference system.
未知坐标系	Unknown coordinate reference system
栅格缺少仿射变换。	The raster has no affine transform.
无法抽样读取栅格。	Could not sample the raster.
栅格没有有效像元。	The raster has no valid pixels.
GDAL无法打开栅格：{path}	GDAL could not open raster: {path}
栅格没有波段：{name}	Raster has no bands: {name}
SAR处理至少需要一幅影像。	SAR processing requires at least one image.
输入影像列表包含重复路径。	The input-image list contains duplicate paths.
{name}不是单波段影像。	{name} is not a single-band image.
{name}含旋转项，当前版本不支持。	{name} contains rotation terms, which are not supported by this version.
{name}的CRS与第一幅影像不一致。	The CRS of {name} does not match the first image.
{name}含有效负值，可能已是dB或语义不明；当前版本拒绝自动10log10转换。	{name} contains valid negative values and may already be in dB or have unclear semantics; this version refuses automatic 10log10 conversion.
{name}没有正值，不能执行线性功率转dB。	{name} contains no positive values and cannot be converted from linear power to dB.
已检查 {index}/{count}：{name}	Checked {index}/{count}: {name}
输入产品包含不同极化方式，不能直接镶嵌：{values}	Input products have different polarizations and cannot be mosaicked directly: {values}
检测到升轨/降轨混合；默认应分组处理，强制混合必须由用户确认。	A mixture of ascending and descending passes was detected. Process them separately by default; forced mixing requires user confirmation.
入射角跨度为{span:.2f}°，可能造成明显辐射差异。	The incidence-angle span is {span:.2f}°, which may cause substantial radiometric differences.
检测到中位强度相对组中位数偏差超过6 dB的影像；仅报警，不自动剔除或归一化。	Images whose median intensity differs from the group median by more than 6 dB were detected. This is a warning only; no image is removed or normalized automatically.
存在未声明NoData的NaN边缘；处理时将使用临时VRT保护有效像元。	NaN edges without declared NoData were found; temporary VRTs will protect valid pixels during processing.
未发现完整Sigma0/Gamma0等辐射定标信息；输出语义限定为“强度dB”。	Complete radiometric-calibration information such as Sigma0/Gamma0 was not found; output semantics are limited to “intensity in dB”.
裁剪面不存在：{path}	Clipping mask does not exist: {path}
OGR无法打开裁剪面。	OGR could not open the clipping mask.
裁剪数据中没有可用要素。	The clipping dataset has no usable features.
裁剪图层必须是Polygon或MultiPolygon。	The clipping layer must be Polygon or MultiPolygon.
裁剪图层没有坐标系。	The clipping layer has no coordinate reference system.
裁剪面CRS与栅格不一致：{actual}；栅格为{expected}。	The clipping-mask CRS does not match the raster: {actual}; raster CRS is {expected}.
无法为NaN保护创建临时VRT：{name}	Could not create a temporary VRT for NaN protection: {name}
无法创建镶嵌临时输出。	Could not create the temporary mosaic output.
正在写入第{index}/{count}景……	Writing scene {index}/{count}…
GDAL写入第{index}景失败。	GDAL failed while writing scene {index}.
用户在镶嵌过程中取消了任务。	The user cancelled the task during mosaicking.
正在按掩膜裁剪……	Clipping by mask…
用户在裁剪过程中取消了任务。	The user cancelled the task during clipping.
GDAL裁剪失败。	GDAL clipping failed.
dB转换要求有效单波段栅格。	dB conversion requires a valid single-band raster.
无法创建dB临时输出。	Could not create the temporary dB output.
读取线性栅格块失败。	Failed to read a linear-power raster block.
正在执行10log10线性功率转dB……	Converting linear power to dB with 10log10…
裁剪结果没有正值，无法转换为dB。	The clipped result has no positive values and cannot be converted to dB.
显示分位数必须满足0≤低值<高值≤100。	Display percentiles must satisfy 0 ≤ low < high ≤ 100.
无法读取dB栅格：{path}	Could not read dB raster: {path}
dB栅格没有有效像元。	The dB raster has no valid pixels.
显示拉伸范围无效或数据缺少变化。	The display stretch range is invalid or the data have no variation.
无法识别显示增强方法：{method}	Unrecognized display-enhancement method: {method}
无法读取单波段显示源：{path}	Could not read the single-band display source: {path}
显示源没有有效像元。	The display source has no valid pixels.
显示统计含非有限数值。	Display statistics contain non-finite values.
无法识别颜色模式：{mode}	Unrecognized colour mode: {mode}
无法识别伪彩色色带：{ramp}	Unrecognized pseudocolour ramp: {ramp}
亮度须为-100—100，对比度须为-99—99。	Brightness must be between -100 and 100, and contrast between -99 and 99.
Gamma必须为正数。	Gamma must be positive.
基础外缘羽化距离必须为0—1000像素。	The basic outer-edge feather distance must be 0–1000 pixels.
8位显示产品要求有效单波段栅格。	The 8-bit display product requires a valid single-band raster.
正在生成8位显示产品……	Generating the 8-bit display product…
8位显示产品生成完成。	The 8-bit display product has been generated.
输入文件夹不存在：{path}	Input folder does not exist: {path}
输入文件夹及其子文件夹中没有GeoTIFF。	No GeoTIFF was found in the input folder or its subfolders.
请至少选择一幅SAR GeoTIFF。	Select at least one SAR GeoTIFF.
输入不是GeoTIFF：{path}	Input is not a GeoTIFF: {path}
输入影像不存在：{path}	Input image does not exist: {path}
请选择Polygon或MultiPolygon裁剪面。	Select a Polygon or MultiPolygon clipping mask.
裁剪面应为GPKG、SHP或GeoJSON。	The clipping mask must be GPKG, SHP, or GeoJSON.
裁剪面不存在。	The clipping mask does not exist.
请选择已有输出根目录。	Select an existing output root directory.
X分辨率	X resolution
Y分辨率	Y resolution
{label}必须为0（自动）或正数。	{label} must be 0 (auto) or a positive number.
无法识别镶嵌重采样方法。	Unrecognized mosaic resampling method.
无法识别裁剪重采样方法。	Unrecognized clipping resampling method.
三次卷积可能使非负线性功率产生非物理负值。建议改用最近邻；如确需使用，请勾选风险确认。	Cubic convolution may produce non-physical negative values from non-negative linear power. Nearest neighbour is recommended; if cubic is required, acknowledge the risk explicitly.
输出NoData必须是有限数值。	Output NoData must be finite.
无法识别显示增强方法。	Unrecognized display-enhancement method.
无法识别颜色模式。	Unrecognized colour mode.
无法识别单波段伪彩色色带。	Unrecognized single-band pseudocolour ramp.
亮度必须在-100—100之间。	Brightness must be between -100 and 100.
对比度必须在-99—99之间。	Contrast must be between -99 and 99.
请确认输入为线性功率值并同意执行10log10转换。	Confirm that the inputs contain linear-power values and approve 10log10 conversion.
请确认输入顺序规则：后输入有效像元覆盖先输入有效像元。	Confirm the input-order rule: valid pixels from later inputs overwrite valid pixels from earlier inputs.
裁剪面与输入影像联合范围不相交。影像范围 [{raster_xmin:.6f}, {raster_ymin:.6f}, {raster_xmax:.6f}, {raster_ymax:.6f}]；裁剪面范围 [{mask_xmin:.6f}, {mask_ymin:.6f}, {mask_xmax:.6f}, {mask_ymax:.6f}]。请改选空间相交的单景或裁剪面。	The clipping mask does not intersect the combined input-image extent. Image extent: [{raster_xmin:.6f}, {raster_ymin:.6f}, {raster_xmax:.6f}, {raster_ymax:.6f}]; mask extent: [{mask_xmin:.6f}, {mask_ymin:.6f}, {mask_xmax:.6f}, {mask_ymax:.6f}]. Select a spatially intersecting scene or clipping mask.
检测到升轨/降轨混合。建议分组处理；如确需混合，请勾选科学风险确认。	A mixture of ascending and descending passes was detected. Separate processing is recommended; if mixing is required, acknowledge the scientific risk.
检测到超过6 dB的组间中位强度异常。插件不会自动归一化；请检查报告并勾选风险确认。	A between-group median-intensity anomaly greater than 6 dB was detected. The plugin will not normalize automatically; review the report and acknowledge the risk.
目标分辨率无效。	The target resolution is invalid.
已确认使用三次卷积；质量报告将精确记录因此产生或保留下来的负线性功率像元。	Cubic convolution was acknowledged; the quality report will record any negative linear-power pixels created or retained as a result.
- 8位显示产品：`{display_dir}/sar_display_rgba_8bit.tif`\n	- 8-bit display product: `{display_dir}/sar_display_rgba_8bit.tif`\n
- 本次未生成可选8位显示产品。\n	- The optional 8-bit display product was not generated.\n
- 未发现需要人工确认的科学一致性警告。	- No scientific-consistency warning requiring manual confirmation was found.
未生成	Not generated
正在计算输入文件SHA-256……	Calculating input-file SHA-256 hashes…
步骤1/4：统一网格并镶嵌线性功率影像。	Step 1/4: Align grids and mosaic the linear-power images.
步骤2/4：按矢量掩膜裁剪。	Step 2/4: Clip by the vector mask.
步骤3/4：线性功率转dB。	Step 3/4: Convert linear power to dB.
步骤4/4：计算显示范围与质量门。	Step 4/4: Calculate the display range and quality gates.
正在复核输入文件完整性……	Rechecking input-file integrity…
一个或多个质量门未通过。	One or more quality gates failed.
SAR 影像镶嵌、裁剪与显示增强任务完成。	SAR image mosaicking, clipping, and display-enhancement task complete.
"""


for _line in _DEFAULT_TSV_2.strip().splitlines():
    _source, _english = _line.split("\t", 1)
    MODULE_TRANSLATIONS["@default"][_source.replace(r"\n", "\n")] = _english.replace(
        r"\n", "\n"
    )


MODULE_TRANSLATIONS["@default"].update(
    {
        """# 几何校正流程验证报告

运行 ID：`{run_id}`  
脚本版本：`{script_version}`  
状态：`{status}`

## 结论

- 已完成 `GeoTIFF → 无地理信息 PNG → 训练 GCP → 一阶多项式 GeoTIFF → 独立检查点 RMSE → 叠加比较`。
- 训练点 {train_count} 个，独立检查点 {check_count} 个，两组互斥。
- 独立检查二维 RMSE：`{check_rmse_m:.9f} m` / `{check_rmse_pixel:.9f} pixel`。
- 独立检查最大误差：`{check_max_m:.9f} m` / `{check_max_pixel:.9f} pixel`。
- 恢复影像与参考影像的像元值 RMSE：`{raster_rmse:.9f}`（Byte 灰度值）。

## 重要限制

本次 GCP 的地图坐标由原始 GeoTransform 自动生成，因此这是软件流程、像元坐标约定和可复现性的教学验证。理论误差应接近零，**不能代表人工选点或真实外部控制点条件下的配准精度**。源 TIFF 与 PNG 均为 Byte 快速预览，不用于替代原始浮点 SAR 定量数据。

## 输入

- 源文件：`{input_path}`
- SHA-256：`{input_sha256}`
- 尺寸：{input_width} × {input_height}
- 波段/类型：{band_count} / {band_type}
- CRS：{input_crs}
- GeoTransform：`{input_geotransform}`

## 方法

- 像元约定：{pixel_convention}
- 候选点：5×5 规则网格，共 {all_points} 个。
- 拆分方式：棋盘格；训练 {train_points} 个，检查 {check_points} 个。
- 模型：一阶二维仿射；仅训练点参与拟合和 GDAL Warp。
- 重采样：`{resampling}`。
- 输出网格：显式约束为参考影像的 CRS、范围、宽度和高度。

## 精度

| 指标 | 训练点 | 独立检查点 |
|---|---:|---:|
| 二维 RMSE（度） | {train_rmse_degree:.12g} | {check_rmse_degree:.12g} |
| 二维 RMSE（米，EPSG:32650） | {train_rmse_m:.9f} | {check_rmse_m:.9f} |
| RMSE（像素） | {train_rmse_pixel:.9f} | {check_rmse_pixel:.9f} |
| 最大误差（米） | {train_max_m:.9f} | {check_max_m:.9f} |
| 最大误差（像素） | {train_max_pixel:.9f} | {check_max_pixel:.9f} |

## 输出与对比

- 恢复 GeoTIFF：`{output_path}`
- 输出 CRS：{output_crs}
- 输出尺寸：{output_width} × {output_height}
- GeoTransform 最大绝对差：`{geotransform_max_difference:.12g}`
- 像元平均绝对差：`{mean_absolute_difference:.9f}`
- 像元最大绝对差：`{max_absolute_difference:.9f}`
- 叠加/差异图：`comparison_preview.png`

## 验收与保护

- 源 TIFF 运行前 SHA-256：`{source_sha256_before}`
- 源 TIFF 运行后 SHA-256：`{source_sha256_after}`
- 源文件未变化：`{source_unchanged}`
- PS-InSAR语义不参与本几何校正计算；项目已确认velocity单位为mm/年、
  displacement单位为mm，正值表示垂直向上，负值表示垂直向下。
""": """# Geometric-correction Workflow-validation Report

Run ID: `{run_id}`  
Script version: `{script_version}`  
Status: `{status}`

## Conclusion

- Completed `GeoTIFF → ungeoreferenced PNG → training GCPs → first-order polynomial GeoTIFF → independent check-point RMSE → overlay comparison`.
- {train_count} training points and {check_count} independent check points; the sets are disjoint.
- Independent-check 2D RMSE: `{check_rmse_m:.9f} m` / `{check_rmse_pixel:.9f} pixel`.
- Maximum independent-check error: `{check_max_m:.9f} m` / `{check_max_pixel:.9f} pixel`.
- Pixel-value RMSE between the restored and reference images: `{raster_rmse:.9f}` (Byte grayscale values).

## Important Limitation

The GCP map coordinates in this run are generated automatically from the source GeoTransform. This is therefore a teaching validation of the software workflow, pixel-coordinate convention, and reproducibility. The theoretical error should be near zero and **does not represent registration accuracy with manually selected or real external control points**. The source TIFF and PNG are Byte quick-look images and do not replace the original floating-point quantitative SAR data.

## Input

- Source file: `{input_path}`
- SHA-256: `{input_sha256}`
- Dimensions: {input_width} × {input_height}
- Bands/type: {band_count} / {band_type}
- CRS: {input_crs}
- GeoTransform: `{input_geotransform}`

## Method

- Pixel convention: {pixel_convention}
- Candidate points: 5×5 regular grid, {all_points} points total.
- Split: checkerboard; {train_points} training points and {check_points} check points.
- Model: first-order 2D affine; only training points are used for fitting and GDAL Warp.
- Resampling: `{resampling}`.
- Output grid: explicitly constrained to the reference-image CRS, extent, width, and height.

## Accuracy

| Metric | Training points | Independent check points |
|---|---:|---:|
| 2D RMSE (degrees) | {train_rmse_degree:.12g} | {check_rmse_degree:.12g} |
| 2D RMSE (metres, EPSG:32650) | {train_rmse_m:.9f} | {check_rmse_m:.9f} |
| RMSE (pixels) | {train_rmse_pixel:.9f} | {check_rmse_pixel:.9f} |
| Maximum error (metres) | {train_max_m:.9f} | {check_max_m:.9f} |
| Maximum error (pixels) | {train_max_pixel:.9f} | {check_max_pixel:.9f} |

## Output and Comparison

- Restored GeoTIFF: `{output_path}`
- Output CRS: {output_crs}
- Output dimensions: {output_width} × {output_height}
- Maximum absolute GeoTransform difference: `{geotransform_max_difference:.12g}`
- Mean absolute pixel-value difference: `{mean_absolute_difference:.9f}`
- Maximum absolute pixel-value difference: `{max_absolute_difference:.9f}`
- Overlay/difference figure: `comparison_preview.png`

## Acceptance and Protection

- Source TIFF SHA-256 before run: `{source_sha256_before}`
- Source TIFF SHA-256 after run: `{source_sha256_after}`
- Source file unchanged: `{source_unchanged}`
- PS-InSAR semantics are not used in this geometric-correction calculation. The project defines velocity in mm/year and displacement in mm, with positive values vertically upward and negative values vertically downward.
""",
        """# 几何校正流程验证成果说明

运行状态：`PASS`  
运行ID：`{run_id}`  
源影像：`{source}`  
源影像SHA-256：`{source_hash}`

## 首先查看

- 最终校正GeoTIFF：`{result_dir}/{restored_name}`
- 图像对比与差异检查：`{quality_dir}/comparison_preview.png`
- 精度报告：`{quality_dir}/geometry_correction_report.md`

## 精度摘要

- 训练GCP：13个；
- 独立检查点：12个；
- 独立检查二维RMSE：`{check_rmse_m:.9f} m`；
- 独立检查像素RMSE：`{check_rmse_pixel:.12g} pixel`；
- 独立检查最大误差：`{check_max_pixel:.12g} pixel`。

## 文件夹含义

- `{run_info_dir}`：输入清单、参数、运行状态和机器可读结果；
- `{control_point_dir}`：全部控制点、训练点和独立检查点CSV；
- `{intermediate_dir}`：去除空间参考的教学中间PNG；
- `{result_dir}`：最终恢复空间参考的GeoTIFF；
- `{quality_dir}`：训练/检查残差、对比图和完整质量报告。

## 重要限制

本模式的GCP地图坐标由源GeoTIFF原有GeoTransform自动生成。近零RMSE
只证明软件流程、训练/检查拆分和像元坐标约定可复现，不能代表真实
人工选点或外部控制点条件下的配准精度。Byte PNG和恢复GeoTIFF不
替代原始浮点SAR定量数据。
""": """# Geometric-correction Workflow-validation Result Guide

Run status: `PASS`  
Run ID: `{run_id}`  
Source image: `{source}`  
Source-image SHA-256: `{source_hash}`

## Start Here

- Final corrected GeoTIFF: `{result_dir}/{restored_name}`
- Image comparison and difference check: `{quality_dir}/comparison_preview.png`
- Accuracy report: `{quality_dir}/geometry_correction_report.md`

## Accuracy Summary

- Training GCPs: 13;
- Independent check points: 12;
- Independent-check 2D RMSE: `{check_rmse_m:.9f} m`;
- Independent-check pixel RMSE: `{check_rmse_pixel:.12g} pixel`;
- Maximum independent-check error: `{check_max_pixel:.12g} pixel`.

## Folder Contents

- `{run_info_dir}`: input manifest, parameters, run status, and machine-readable results;
- `{control_point_dir}`: CSV files for all control points, training points, and independent check points;
- `{intermediate_dir}`: teaching intermediate PNG without spatial reference;
- `{result_dir}`: final GeoTIFF with restored spatial reference;
- `{quality_dir}`: training/check residuals, comparison figure, and full quality report.

## Important Limitation

In this mode, GCP map coordinates are generated automatically from the source GeoTIFF GeoTransform. Near-zero RMSE demonstrates only the reproducibility of the software workflow, training/check split, and pixel-coordinate convention. It does not represent registration accuracy with manually selected or external control points. The Byte PNG and restored GeoTIFF do not replace the original floating-point quantitative SAR data.
""",
    }
)


MODULE_TRANSLATIONS["@default"].update(
    {
        """# SAR 影像镶嵌、裁剪与显示增强成果说明

运行状态：`PASS`  
运行ID：`{run_id}`  
输入影像：{input_count}幅（顺序见 `{run_info_dir}/input_manifest.json`）

## 首先查看

- 最终dB栅格：`{db_dir}/sar_mosaic_clip_db.tif`
- 线性裁剪结果：`{clip_dir}/sar_mosaic_clip_linear.tif`
- 处理与质量报告：`{quality_dir}/sar_processing_report.md`
{display_product}

## 显示建议

- 单位：dB；
- 公式：`10*log10(linear_power)`；
- 显示方法：`{display_method}`；
- 显示范围：
  `{display_min:.6f} — {display_max:.6f} dB`；
- 该范围只用于显示，不改变栅格像元值。

## 文件夹含义

- `{run_info_dir}`：输入顺序、哈希、参数和任务状态；
- `{mosaic_dir}`：统一网格后的线性功率镶嵌；
- `{clip_dir}`：按矢量掩膜得到的线性功率裁剪结果；
- `{db_dir}`：最终Float32 dB栅格；
- `{quality_dir}`：处理报告和质量检查。
- `{display_dir}`：可选RGBA 8位显示产品，仅用于可视化。

## 重要规则

输入顺序具有科学含义：后输入影像的有效像元覆盖先输入影像的有效
像元；未声明NoData的NaN边缘由临时只读VRT保护，不覆盖已有有效值。
本版本不做自动seamline或物理辐射平衡。基础外缘羽化仅作用于8位
显示产品，不改变Float32线性功率或dB成果，也不表示自动无缝拼接。
""": """# SAR Image Mosaicking, Clipping, and Display-enhancement Result Guide

Run status: `PASS`  
Run ID: `{run_id}`  
Input images: {input_count} (order recorded in `{run_info_dir}/input_manifest.json`)

## Start Here

- Final dB raster: `{db_dir}/sar_mosaic_clip_db.tif`
- Linear-power clipped result: `{clip_dir}/sar_mosaic_clip_linear.tif`
- Processing and quality report: `{quality_dir}/sar_processing_report.md`
{display_product}

## Display Recommendations

- Unit: dB;
- Formula: `10*log10(linear_power)`;
- Display method: `{display_method}`;
- Display range:
  `{display_min:.6f}–{display_max:.6f} dB`;
- This range is for display only and does not change raster pixel values.

## Folder Contents

- `{run_info_dir}`: input order, hashes, parameters, and task status;
- `{mosaic_dir}`: linear-power mosaic on the common grid;
- `{clip_dir}`: linear-power result clipped by the vector mask;
- `{db_dir}`: final Float32 dB raster;
- `{quality_dir}`: processing report and quality checks;
- `{display_dir}`: optional RGBA 8-bit display product for visualization only.

## Important Rules

Input order has scientific meaning: valid pixels from later inputs overwrite valid pixels from earlier inputs. NaN edges without declared NoData are protected by temporary read-only VRTs and do not overwrite existing valid values. This version does not perform automatic seamline generation or physical radiometric balancing. Basic outer-edge feathering affects only the 8-bit display product; it does not change the Float32 linear-power or dB results and does not represent automatic seamless mosaicking.
""",
        """# ORG真实数据SAR处理报告

状态：`{status}`  
运行ID：`{run_id}`  
输入数量：{raster_count}  
CRS：`{crs}`

## 处理链

```text
显式输入顺序
→ {x_resolution} × {y_resolution} 目标网格镶嵌
→ Polygon裁剪
→ 10*log10(linear_power)
→ {display_method}显示增强
```

后输入有效像元覆盖先输入有效像元；不做自动seamline或物理辐射平衡。

## 真实产品科学预检

{warning_text}

- dB语义：`{db_value_semantics}`
- NaN安全VRT：`{nan_safe_vrt}`
- 掩膜范围预计三阶段未压缩空间：`{estimated_gib:.3f} GiB`

## 输出

- 线性镶嵌：`{mosaic_linear}`
- 线性裁剪：`{clip_linear}`
- dB栅格：`{db_raster}`
- 8位显示产品：`{display_raster}`
- 显示范围：`{display_minimum:.6f}` 至
  `{display_maximum:.6f} dB`

## 质量门

- 裁剪与dB网格一致：`{clip_db_grid_equal}`
- 输入完整性：`{source_integrity_pass}`
- dB有效像元数：`{valid_pixel_count}`
- dB前有限线性像元数：`{finite_linear_pixel_count}`
- 负线性功率像元数：`{negative_linear_pixel_count}`
- 零值线性功率像元数：`{zero_linear_pixel_count}`

## 限制

- 输入必须是单波段、非负线性功率值；
- 所有栅格与裁剪面必须使用相同CRS；
- 显示增强只作用于独立8位产品，不改变Float32科学像元；
- 本阶段不输出最终SAR专题图。
""": """# ORG Real-data SAR Processing Report

Status: `{status}`  
Run ID: `{run_id}`  
Input count: {raster_count}  
CRS: `{crs}`

## Processing Chain

```text
Explicit input order
→ mosaic on a {x_resolution} × {y_resolution} target grid
→ Polygon clipping
→ 10*log10(linear_power)
→ {display_method} display enhancement
```

Valid pixels from later inputs overwrite valid pixels from earlier inputs. No automatic seamline generation or physical radiometric balancing is performed.

## Real-product Scientific Preflight

{warning_text}

- dB semantics: `{db_value_semantics}`
- NaN-safe VRT: `{nan_safe_vrt}`
- Estimated uncompressed space for three mask-bounded stages: `{estimated_gib:.3f} GiB`

## Outputs

- Linear-power mosaic: `{mosaic_linear}`
- Linear-power clip: `{clip_linear}`
- dB raster: `{db_raster}`
- 8-bit display product: `{display_raster}`
- Display range: `{display_minimum:.6f}` to
  `{display_maximum:.6f} dB`

## Quality Gates

- Clipped and dB grids match: `{clip_db_grid_equal}`
- Input integrity: `{source_integrity_pass}`
- Valid dB pixel count: `{valid_pixel_count}`
- Finite linear-power pixel count before dB conversion: `{finite_linear_pixel_count}`
- Negative linear-power pixel count: `{negative_linear_pixel_count}`
- Zero linear-power pixel count: `{zero_linear_pixel_count}`

## Limitations

- Inputs must be single-band, non-negative linear-power values;
- All rasters and the clipping mask must use the same CRS;
- Display enhancement affects only the separate 8-bit product and does not change Float32 scientific pixels;
- This stage does not produce a final SAR thematic map.
""",
    }
)
