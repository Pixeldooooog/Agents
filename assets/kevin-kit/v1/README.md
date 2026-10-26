# Kevin 素材盒 · v1

8 张独立 PNG，由内置 imagegen 基于 `../../design-drafts/kevin-doodle-antenna-v1.png` 生成。使用原图参考保持角色一致；所有旧稿保留。

打开 `index.html` 可以按用途筛选、检查透明背景、预览输入框摆放并下载原图。也可以在仓库根目录运行：

```sh
python3 -m http.server 5181 --bind 127.0.0.1 --directory assets/kevin-kit/v1
```

浏览器打开 `http://127.0.0.1:5181/`。

| 文件 | 用途 |
| --- | --- |
| composer-rest.png | 输入框边缘，趴着等候 |
| composer-listen.png | 输入或补充要求时，抬耳倾听 |
| state-thinking.png | 思考提示 |
| state-working.png | 正在阅读或执行工作的提示 |
| state-approval.png | 等待用户决定 |
| result-delivery.png | 成果卡、完成提示 |
| empty-folder.png | 暂无资料、等待添加文件 |
| state-paused.png | 用户主动暂停 |

## 接入建议

- 使用 PNG 的透明通道；脸与爪子保留不透明的暖白色。
- 建议按 96–240 CSS px 展示，具体取决于场景。这组不是为 16px favicon 制作的。
- 黑色耳朵在纯深色背景下对比偏弱，深色界面优先给角色一块浅色承托区域。预览页提供黑底检查，不代表已单独绘制深色版本。
- 所有图片为静态姿态，不是逐帧动画；独立生成的轮廓、尺寸存在细微变化，不应直接连续播放来模拟平滑动画。
- 不把素材标签当运行时状态：产品仍需绑定真实事件与可读状态文字。
- 本批只加入素材与预览页，未替换现有应用界面，也未改动其他正在进行的开发。

每张图旁的 `*-prompt.md` 保存完整生成提示词。`manifest.json` 提供文件清单；`quality.json` 记录尺寸和透明通道检查。
