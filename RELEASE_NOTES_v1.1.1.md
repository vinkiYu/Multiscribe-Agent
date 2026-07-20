# Multiscribe-Agent v1.1.1

> 面向控制台易用性与产品展示的补丁版本。

**发布日期**：2026-07-20
**版本类型**：补丁发布
**兼容运行时**：Python 3.12+

## 本次更新

### 更易理解的控制台

- 将控制台导航和页面文案统一为更直白的用户语言：内容来源、摘要与发布、AI 摘要规则、内容偏好、扩展功能、定时任务和系统日志。
- 明确摘要编辑、重新生成、发送、定时执行、知识库检索和系统配置的实际行为与生效方式。
- 将知识库的内部检索术语替换为用户可理解的说明，同时保留必要的配置变量名。

### 可排序的工作区导航

- 左侧导航支持长按拖动排序。
- 自定义顺序会保存到当前浏览器，刷新后继续生效，并同步到移动端抽屉导航。
- 普通点击导航保持原有跳转行为。

### 项目展示

- 更新 README 的产品介绍、技术栈展示和项目截图。
- 允许发布仓库包含 README 使用的图片资源。

## 验证结果

```text
frontend: npm run lint 通过（保留 2 条既有 Fast Refresh 警告）
frontend: npm run build 通过
git diff --check 通过
```

## 升级

```bash
git checkout v1.1.1
uv sync --extra dev --extra text
```

前端静态资源随发布提交更新。部署静态资源或容器后，请重新构建或重启对应服务。

## 发布内容

- Git commit：`release: Multiscribe-Agent v1.1.1`
- Git tag：`v1.1.1`
- GitHub Release：`Multiscribe-Agent v1.1.1`
