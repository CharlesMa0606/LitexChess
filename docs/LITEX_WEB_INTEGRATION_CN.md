# Litex 网站原生嵌入方案

## 1. 本版解决的问题

上一版虽然已经把工作台与教材做在同一个项目中，但它们仍各自拥有完整页面头部、导航和应用外壳。把这样的页面直接链接到 Litex 官网时，用户会感觉自己离开了 Litex 教材站点，进入了另一个应用。

v0.9 将国际象棋部分拆成可挂载的内容模块：

```text
Litex 全局页头、Textbooks 导航、左侧教材树
                    │
                    ▼
        Litex 正常的 route outlet
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
<litex-chess-textbook>  <litex-chess-workbench>
```

宿主页面只保留一套全局导航。两个国际象棋组件都通过 Shadow DOM 直接进入宿主 DOM；没有 iframe，也没有第二套顶层应用壳层。

## 2. 路由

建议由 Litex 网站注册：

```text
/textbook/Chess/position-state
/textbook/Chess/move-pipeline
...
/textbook/Chess/certificate-audit
/textbook/Chess/workbench
/playground/chess                  可选别名
```

开发包自身已经提供同样的 Litex 风格集成预览，因此本地启动后可以直接检查这些路径。

## 3. Web Component 接口

教材章节：

```html
<litex-chess-textbook
  api-base="/api"
  source-base="/textbook-source"
  chapter-base="/textbook/Chess"
  workbench-base="/textbook/Chess/workbench"
  chapter="position-state">
</litex-chess-textbook>
```

棋局工作台：

```html
<litex-chess-workbench
  api-base="/api"
  textbook-base="/textbook/Chess">
</litex-chess-workbench>
```

入口脚本：

```html
<script type="module" src="/extensions/chess/embed/litex-chess-elements.js"></script>
```

组件内部复用原有控制器、教材目录和正式后端，不复制另一套国际象棋规则。

## 4. 宿主站点适配器

`integration/litex-site/register-chess.js` 提供两个入口：

```js
registerLitexChess(host, options)
mountLitexChessRoute(outlet, route, options)
```

其中 `outlet` 是 Litex 页面已有的正文容器。适配器只替换正文容器的子节点，不操作页头和侧栏。

若宿主提供：

```js
host.registerTextbook(descriptor)
host.registerRoute(path, handler)
```

则 `registerLitexChess` 会从 `manifest.json` 注册十五章和工作台路由。若私有网站的路由 API 不同，可以只调用 `mountLitexChessRoute`。

## 5. 原生 Litex 教材覆盖层

`integration/golitex-overlay/textbooks/Chess/` 可以复制到公开 `golitex` 仓库的 `textbooks/Chess/`。其中包括：

- `litex.config`；
- 唯一共享规则模块 `chess_rules.lit`；
- 十五个章节 `.lit` 文件；
- `book.extension.json`。

每章同时含有教材正文和可独立运行的最小 Litex 检查。网页交互组件没有加载时，仍有原生教材内容可读、可验证。

安装到本地 `golitex` checkout：

```bash
python integration/install_into_golitex.py /path/to/golitex
/path/to/golitex/target/release/litex \
  -compact -runner -r /path/to/golitex/textbooks/Chess
```

本开发包按公开仓库 commit `2e457026928e009344d35f363e721c2540c410b6` 的教材模块约定制作。生产网站源码并未公开，因此最终合并时需要把适配器接入网站自身的真实路由/教材注册接口；开发包没有假装修改不可见的私有代码。

## 6. 服务部署

同域部署最简单：

```text
/extensions/chess/   → frontend/
/textbook-source/    → textbook/
/api/                → litex_chess FastAPI 服务
```

也可以把整个 Chess FastAPI 应用挂在宿主服务的一个子路径，此时只需同步修改组件的 `api-base`。`integration/litex-site/nginx-location.conf` 给出反向代理示例。

## 7. 兼容页面

为了便于独立调试，旧完整页面仍保留在：

```text
/standalone/textbook
/standalone/workbench
```

它们不再是默认入口，也不应作为官网导航目标。默认根路径会跳转到 `/textbook/Chess`。

## 8. 开发包与安装器

轻量 `LitexWeb_DevKit` 提供两个彼此独立的安装步骤：

```bash
python integration/install_into_golitex.py /path/to/golitex
python integration/install_web_assets.py /path/to/site/public
```

第一步安装可由 repository runner 编译的原生 `textbooks/Chess`；第二步只发布无 iframe 组件、控制器、样式和宿主适配器。生产网站仍需按照 `integration/litex-site/HOST_INTEGRATION_CONTRACT_CN.md` 将路由接到自己的正文 outlet。
