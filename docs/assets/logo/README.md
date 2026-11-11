# FitCoach AI logo

![FitCoach AI symbol](fitcoach-symbol.svg)

## 文件

- `fitcoach-symbol.svg`：橙蓝色运动人形原始矢量图，透明背景，600 × 600 默认尺寸，`viewBox="0 0 60 60"`，可无损缩放。

## 来源与核对范围

此前没有独立的 logo 图片文件。图形源代码已经随前端保存在 repo 的 `app/web/index.html` 中，位于侧栏品牌链接内的 `<svg class="brand-symbol">`。

本文件直接提取该 SVG，保留原来的圆形、路径坐标和颜色，仅添加独立 SVG 所需的命名空间、默认尺寸及可访问标题。提取时逐项校验了绘图元素的属性与源代码一致。运行时无需从外部网站下载此标识。

前端的 `FitCoach AI` 字样及 `YOUR FITNESS COMPANION` 副标题由 HTML 文本和 `app/web/styles.css` 排版，不属于该图形文件。

PDF 封面预览 `docs/guide/qa/verified-01.png` 中可见同造型的橙蓝运动人形。当前工作区没有找到 `fitcoach-user-manual.tex` 或成品 PDF；`docs/guide/build.txt` 仅记录了 XeLaTeX 构建过程。因此尚不能确认 PDF 的图形是由 TikZ 重绘还是通过其他资源引入，也无法据此确定最早的设计来源。本目录保存的是可核验的前端原始矢量，不是从 PDF 截图裁出的图片。

## 使用

网页可使用 `<img src=".../fitcoach-symbol.svg" alt="FitCoach AI">`。用于 PDF 时，可通过支持 SVG 的排版工具导入，或先转换成矢量 PDF。

本次只归档独立资源；现有前端继续使用原内嵌 SVG。若修改 logo，需同时更新前端及此文件，避免出现两个版本。
