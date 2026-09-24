# 布局资料消费指南

先读 manifest.json，再读 layout.json。nodes.json / evidence 保留原始证据；layout.json 是派生描述，不能替代原始数据。preview.html 和 skeleton.html 可离线打开，无网络资源、无脚本。

## 坐标

geometry.absolute_bounds 统一相对本次采集根节点左上角，单位 px。root_id 是采集子树的根，不保证是整个设计画板。多个根各自有原点。
默认 unknown：根节点归零；子节点 absolute_bounds 为 null，candidate_parent_relative_bounds 仅供人工比较，预览不使用候选位置。
确认坐标后用 prepare --coordinate-mode parent-relative（逐级累加）、root-relative（子节点直接相对采集根）或 canvas-absolute（所有节点减根的 X/Y）。这些是用户指定的换算约定，不是采集器识别出的事实；status=derived，confidence=conditional。
混合坐标用 --layout-overrides 的 nodes[id].coordinate_space 逐节点指定。根的位置为 (0,0)，原始全局位置保留在 raw_bounds；不能用数值大小猜坐标空间。缺尺寸、缺父级或存在未解析 transform 时不生成绝对框。负坐标允许存在。旋转和嵌套变换需要明确的绝对框覆盖。

## 语义及交互

semantics.role 从文本、名称、CSS 和图片推断，附 source/confidence/evidence。button 只是角色建议，interactive 默认 null；不要据此接入跳转或点击事件。覆写 interactive=true 才表示用户明确确认。名称 01.x / 02.3.x / 04.x 没有跨项目统一含义，不能硬编码成模块。用户确认的标签可通过 overrides 写入。

## 层叠和效果

stacking.z_index 优先使用标注 CSS 中的整数，其次采用“图层树从上到下对应前景到背景”的假设（source=tree_top_is_front_assumption）。它只在父级内部有效，不是全页面 z-index。stack_path 保留祖先路径；兄弟渲染顺序按 z_index 从小到大，平局按假定的树顺序。复杂 blend/mask/transform 无法单靠一个扁平 z-index 表达。
effects 中 null 表示没有采到，不表示关闭。叫“蒙版”的层只是 role 提示，不会自动设置 CSS mask。观察到的 mix-blend-mode、mask、clip-path、overflow、transform 单独列出；未采到的遮罩关系不补造。

## CSS

css.observed 原样保留标注声明，css.recovered 是缺分号的保守修复候选，附问题列表。css.generated 只提供可以计算的绝对定位尺寸及兄弟层级值；它不是响应式布局。若按树构造嵌套 DOM，使用 css.generated_parent_relative；若读取 generated，则 left/top 是相对根的值，不能直接套到嵌套 DOM 上。不要把 position:static 和 left/top 原样拼在一起，也不要额外叠加 flex/padding 导致二次偏移。
预览只应用有限的安全视觉属性；不加载 CSS url() 外部资源，不执行设计文本。不推断 display:flex、transform、字体文件或隐藏节点。可读 CSS 仍需 Agent 结合导出效果图拆组件、设计响应式规则。

## 图片

assets.items 中每一项都是一次工具导出的候选，不保证是同一个节点的独立图层。download_order 仅表示下载记录顺序，paint_order/offset 默认 null。多个 PNG 可能是导出配置/尺寸变体或多个图层；不能按 ZIP 顺序叠加。
composition=single_node_export 表示单张节点导出；multiple_unresolved 表示关系未知。只有 overrides 明确选定 asset_id 后才选用多图中的一张。
预览优先选尺寸与节点框相符的单张 PNG，作为整棵子树的复合截图；子节点不再重复绘制。尺寸不符时不强行拉伸，文字优先用真实 text 和字体 CSS。导出边界可能包含阴影或裁掉透明区，未确认的 offset 不设为 0。HTML 中的 img 仅在尺寸匹配假设下对齐；preview.assumptions 会说明。
PNG 已包含颜色、透明度和效果，预览不再向它重复施加 opacity、阴影或背景。没有可用截图才退回子层/文本骨架；不支持的复杂效果会列在 diagnostics 中。
skeleton.html 强制展开容器，尽量使用叶子图片和真实文字；它是可编辑的结构草稿，不保证视觉一致。隐藏节点/组件变体状态尚未采到，可能多出图层；未知蒙版候选在骨架中省略，避免把蒙版当作普通实色块。该省略也会计入 omitted_node_ids。

## 覆写格式

```json
{
  "coordinate_mode": "parent-relative",
  "nodes": {
    "节点ID": {
      "coordinate_space": "root-relative",
      "absolute_bounds": {"x": 32, "y": 32, "width": 180, "height": 180},
      "role": "button",
      "interactive": true,
      "z_index": 3,
      "asset_id": "从 assets.json 选一个 ID"
    }
  }
}
```

字段全部可选，absolute_bounds 为相对采集根的完整框；它优先于坐标模式。覆写使用精确节点 ID，不匹配名称。不把身份凭证或链接令牌写入覆写文件。prepare 会在 layout.json 保存所用覆写，方便复现。

## 推荐交付

将整份资料包交付 Agent：AGENT_README.md → layout.json → preview.html → 根截图 → 必要时 nodes/evidence。检查 diagnostics 和 preview.omitted_node_ids；有预览不意味着全部节点已可渲染。skeleton.omitted_node_ids 也必须检查。业务逻辑和响应式适配仍需实现。
