# Litex Chess Studio v0.9.0 发布说明

## 本版目标

v0.9.0 把国际象棋教材与工作台从“拥有自己完整导航的独立应用”改造成可以直接挂入 Litex Textbooks 页面正文区域的原生扩展。宿主 Litex 页面管理全局页头、主导航、教材树与浏览器历史；Chess 模块只管理本章内容和互动棋盘。

## 1. 无 iframe 原生嵌入

新增两个自定义元素：

```text
<litex-chess-textbook>
<litex-chess-workbench>
```

它们使用 Shadow DOM 隔离样式，但仍属于同一页面 DOM，不使用 iframe。教材组件不再带 `book-topbar` 和 `book-sidebar`；工作台组件也不再带深色独立应用头部。

## 2. Litex 风格集成路由

开发服务器默认提供：

```text
/textbook/Chess/<chapter-slug>
/textbook/Chess/workbench
/playground/chess
```

页面只有一套 Litex 风格的全局页头和左侧教材树。章节切换使用宿主路由；教材中的局面与残局可以带着 FEN、课程目标和返回地址进入同一路由下的工作台。

## 3. 可复用控制器

原先直接绑定 `document` 的前端逻辑已经拆分为：

```text
frontend/controllers/textbook.js
frontend/controllers/workbench.js
```

控制器可以挂载到普通元素、Document 或 ShadowRoot，并接受 `apiBase`、`sourceBase`、`chapterBase`、`workbenchBase` 等配置。原独立页面只剩兼容启动器。

## 4. Litex 网站开发适配器

`integration/litex-site/` 包含：

- 十五章及工作台路由清单；
- `registerLitexChess` 宿主适配器；
- 静态资源和 API 部署约定；
- Nginx 反向代理示例；
- 私有网站路由 API 未公开时的边界说明。

## 5. 原生 `textbooks/Chess` 覆盖层

`integration/golitex-overlay/textbooks/Chess/` 遵循公开 `golitex` 的 module textbook 结构，包含共享规则模块和十五个章节文件。整本覆盖层已经由随包 Litex 以 repository runner 模式编译。

## 6. 默认入口与兼容入口

默认：

```text
/textbook/Chess/position-state
/textbook/Chess/workbench
```

兼容调试页面：

```text
/standalone/textbook
/standalone/workbench
```

## 7. 既有规则能力保持不变

v0.9 没有另建浏览器棋规。工作台、教材局面实验和残局训练继续共用：

- Agent 可读 `move(...)` / `result(...)`；
- 完整 Litex 证书；
- 2—4 格精确稀疏棋盘后继；
- FEN 元数据、王安全和最终合同；
- 将军、将死、逼和、特殊着、历史规则和残局训练。

## 8. 验证

发布门禁增加：

- 自定义元素、Shadow DOM 与禁止 iframe 的静态契约；
- Litex 原生教材路由和静态资源 API；
- `textbooks/Chess` 覆盖层 repository compile；
- 十五章 manifest 与主教材目录逐项一致；
- 集成路径中的教材—工作台深链接。

## 9. 两类开发交付

发布时同时生成：

- 完整代码包：包含固定版本 Litex 二进制，可直接运行和复测；
- `LitexWeb_DevKit`：轻量网站集成包，保留 Web Component、宿主适配器、原生 `textbooks/Chess` 覆盖层、API 源码与集成测试，但不重复携带平台二进制。

开发包新增 `integration/install_web_assets.py` 与宿主合同文档。它们只复制静态资源和定义接口，不会猜测或覆写尚未公开的生产网站路由实现。
