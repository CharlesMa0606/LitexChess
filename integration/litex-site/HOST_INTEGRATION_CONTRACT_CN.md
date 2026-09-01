# Litex 宿主网站集成合同

本合同把国际象棋模块限制为一个**正文扩展**。宿主网站继续拥有全局页头、主导航、教材树、登录状态和浏览器路由；Chess 模块不得建立第二套顶层应用壳层。

## 必需静态资源

宿主应把开发包中的 `frontend/` 发布为：

```text
/extensions/chess/
```

并加载一次：

```html
<script type="module" src="/extensions/chess/embed/litex-chess-elements.js"></script>
```

## 必需数据与服务

```text
/textbook-source/chapters.json
/textbook-source/chess_rules_textbook_cn.lit
/api/health
/api/textbook/*
/api/sessions/*
/api/import-pgn
```

`api-base` 与 `source-base` 都可以通过元素属性改写，因此 API 也可以部署在 Litex 主站的子路径下。

## 宿主路由

推荐注册：

```text
/textbook/Chess/:chapterSlug
/textbook/Chess/workbench
/playground/chess              可选别名
```

章节路由在宿主的普通教材正文 outlet 中挂载：

```html
<litex-chess-textbook
  api-base="/api"
  source-base="/textbook-source"
  chapter-base="/textbook/Chess"
  workbench-base="/textbook/Chess/workbench"
  chapter="position-state">
</litex-chess-textbook>
```

工作台路由挂载：

```html
<litex-chess-workbench
  api-base="/api"
  textbook-base="/textbook/Chess"
  search="?fen=...&lesson=...">
</litex-chess-workbench>
```

当工作台路由的查询参数变化时，宿主需要更新 `search` 属性；组件会重新建立对应训练局面。

## 导航事件

组件内部需要切换章节或进入工作台时会发出：

```js
new CustomEvent("litex-chess-navigate", {
  bubbles: true,
  composed: true,
  detail: { url, kind, chapter }
})
```

宿主应截获该事件并使用自己的 router/history 导航。`frontend/site/site.js` 与 `register-chess.js` 都给出了实现。

## 不变量

集成后的页面必须满足：

1. 不使用 iframe；
2. 只有一套全局页头和教材侧栏；
3. 教材实验、残局训练和工作台共享同一后端 Litex 门禁；
4. URL 可以深链到章节、FEN 与课程上下文；
5. 组件卸载时应销毁局部控制器，不污染其他教材页面；
6. 生产站点的真实路由 API 未公开时，不假定任何私有框架函数名。
