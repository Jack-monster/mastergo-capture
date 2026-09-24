# Agent Bundle 输出格式

采集产物为 Agent Bundle 1.0.0。所有路径相对输出目录根。

## 文件清单

| 文件 | 内容 |
|---|---|
| `AGENT_README.md` | 资料包说明、数据边界、读取顺序 |
| `manifest.json` | 版本、来源 URL、采集范围、节点/页面/资源数量、错误与缺失列表 |
| `pages.json` | 每个设计页面的 ID、名称、根画板节点 ID 列表、树是否完整 |
| `nodes.json` | 节点数组：id、parent_id、tree_depth、name、design.bounds、design.css_properties、design.text |
| `assets.json` | 资源数组：id、node_id、path、sha256、width、height、format、original_name |
| `tokens.json` | 从实际 CSS 汇总的颜色值、字体家族、字号，按使用频次排序 |
| `interactions.json` | 原型交互状态与待补项（本版多为占位） |
| `evidence/` | 每个节点一个文本文件，含右侧标注面板的完整文本，按节点 ID 命名 |
| `assets/` | 实际下载的 PNG，文件名是内容 SHA256；同内容去重 |
| `index.html` | 图片目录预览页，可双击打开 |
| `run.json` | 运行退出码与适配器版本 |

## nodes.json 节点结构

```json
{
  "id": "76:14960",
  "parent_id": null,
  "tree_depth": 0,
  "name": "02.3.1 播放页面_无歌词",
  "design": {
    "bounds": {
      "x": 24442.0, "y": 2888.0,
      "width": 1920.0, "height": 1080.0,
      "unit": "px",
      "coordinate_space": "as_displayed_by_mastergo"
    },
    "css_properties": {
      "position": "absolute",
      "left": "174px",
      "top": "338px",
      "width": "730px",
      "height": "404px",
      "background": "linear-gradient(0deg, #6b4747 0%, #361717 100%)",
      "color": "rgba(255,255,255,0.9)",
      "font-size": "40px",
      "font-family": "Poppins",
      "border-radius": "50%"
    },
    "text": "Live Live Live"
  }
}
```

关键字段：

- `id`：MasterGo 节点 ID，格式 `页面号:节点号` 或 `父ID/子ID`
- `parent_id`：父节点 ID，根画板为 `null`
- `tree_depth`：树深度，0 为根画板
- `design.bounds`：位置尺寸，坐标空间为 `as_displayed_by_mastergo`，不是页面绝对坐标
- `design.css_properties`：从标注面板提取的可用 CSS 属性，直接可用于 H5
- `design.text`：文本节点的实际文字内容

## pages.json 结构

```json
[
  {
    "id": "4:1931",
    "name": "设计文件",
    "root_ids": ["76:14960", "391:00374", "..."],
    "node_ids": ["..."],
    "tree_complete": true
  }
]
```

- `root_ids`：该页面下所有根画板节点 ID（顶层 frame/canvas）
- `tree_complete`：`false` 表示达到节点上限或时间上限，后续节点未展开

## assets.json 结构

```json
{
  "id": "b6fe11b809ab446437a1",
  "node_id": "76:14960",
  "path": "assets/xxx.png",
  "sha256": "xxx",
  "width": 1920,
  "height": 1080,
  "format": "png",
  "original_name": "02.3.1 播放页面_无歌词.png",
  "role": "design_export",
  "source": "browser_ui"
}
```

- `node_id`：对应的设计节点，可与 `nodes.json` 交叉引用
- `path`：相对输出目录的图片路径
- `original_name`：导出时的原始文件名，可识别图片用途（如"唱片-7.png"、"金属内环.png"）

## manifest.json 关键字段

```json
{
  "bundle_version": "1.0.0",
  "source_url": "https://mastergo.com/file/...",
  "coverage": {
    "scope": "layer",
    "status": "partial",
    "errors": []
  },
  "counts": {
    "pages": 1,
    "nodes": 62,
    "assets": 24
  }
}
```

`coverage.status` 为 `partial` 是正常状态，表示本版不采集原型连线、组件变体等高级信息。

## Agent 读取顺序

1. 读 `AGENT_README.md` 了解边界
2. 读 `manifest.json` 确认范围和错误
3. 读 `pages.json` 找到目标画板的 `root_ids`
4. 在 `nodes.json` 中按 `root_ids` 取目标节点及其子树
5. 用 `assets.json` 把 `node_id` 映射到 `assets/` 下的 PNG
6. 需要完整标注面板文本时读 `evidence/` 下对应文件

## 派生布局产物

新增 `layout.json`（独立 schema_version=1.0.0）、`layout.schema.json`、`preview.html`、`skeleton.html` 与 `LAYOUT_GUIDE.md`。原始资料包格式保持兼容；旧包可用 prepare 离线补生成。详细字段语义见 [layout-consumption.md](layout-consumption.md)。
