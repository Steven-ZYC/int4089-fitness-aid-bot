# FitCoach AI logo

![FitCoach AI symbol](fitcoach-symbol.svg)

## 文件

- `fitcoach-logo.svg`：包含品牌文字和副标题的完整横版标识，与 `docs/assets/fitcoach-logo.svg` 保持一致。
- `fitcoach-symbol.svg`：橙蓝色运动人形原始矢量图，透明背景，600 × 600 默认尺寸，`viewBox="0 0 60 60"`，可无损缩放。

## 来源与核对范围

最初检查的本地版本没有独立 logo 图片；随后同步检查远端更新，发现已新增 `docs/assets/fitcoach-logo.svg`。本目录同时归档该完整标识和独立人形图标。人形图形源代码已随前端保存在 repo 的 `app/web/index.html` 中，位于侧栏品牌链接内的 `<svg class="brand-symbol">`。

本文件直接提取该 SVG，保留原来的圆形、路径坐标和颜色，仅添加独立 SVG 所需的命名空间、默认尺寸及可访问标题。提取时逐项校验了绘图元素的属性与源代码一致。运行时无需从外部网站下载此标识。

前端的 `FitCoach AI` 字样及 `YOUR FITNESS COMPANION` 副标题由 HTML 文本和 `app/web/styles.css` 排版，不属于该图形文件。

PDF 来源已从远端原稿核实：`docs/guide/fitcoach-user-manual.tex` 中的 `\fitmark` 宏使用 TikZ 绘制同造型的人形，`\brand` 宏组合图形与品牌文字；成品为 `docs/guide/fitcoach-user-manual.pdf`。PDF 的标识由本地 LaTeX 代码绘制，并非运行时从外部网站获取。本目录的 SVG 是前端矢量和完整品牌资源的独立归档，不是从 PDF 截图裁出的图片。现有代码可以确定绘制来源，但不能据此认定最早设计的作者。

## 使用

网页可使用 `<img src=".../fitcoach-symbol.svg" alt="FitCoach AI">`。用于 PDF 时，可通过支持 SVG 的排版工具导入，或先转换成矢量 PDF。

本次只归档独立资源；现有前端继续使用原内嵌 SVG。若修改 logo，需同步核对前端、此目录、`docs/assets/fitcoach-logo.svg` 与 PDF 的 TikZ 宏，避免出现不同版本。
