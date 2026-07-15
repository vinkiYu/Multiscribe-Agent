# Plugin 契约（硬约束）

> 四类插件（Adapter / Publisher / Storage / Tool）的统一契约与自动发现规则。Codex 新增任何插件必须遵守。

## 1. 四类插件总览

| 类型 | 职责 | 抽象基类 | 必须实现 |
| :--- | :--- | :--- | :--- |
| Adapter | 外部数据采集 + 转换为 UnifiedData | `BaseAdapter` | `fetch`, `transform` |
| Publisher | 内容发布到外部渠道 | `BasePublisher` | `async publish` |
| Storage | 媒体文件存储（返回公网 URL） | `BaseStorageProvider` | `async upload` |
| Tool | Agent 可调用的函数工具 | `BaseTool` | `parameters`(JSON Schema), `async handler` |

## 2. 通用 metadata（所有插件必须有）

每个插件类必须定义 `metadata` 类属性（dataclass 实例），用于自动发现与前端配置表单渲染：

```python
@dataclass(frozen=True)
class PluginMetadata:
    id: str                    # 唯一标识（Adapter 用 type 作 id）
    type: PluginType           # ADAPTER/PUBLISHER/STORAGE/TOOL
    name: str                  # 显示名
    description: str
    icon: str = ""             # 图标名/emoji
    config_fields: list[ConfigField] = field(default_factory=list)
    is_builtin: bool = True
```

### ConfigField

```python
@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    type: Literal["text", "password", "textarea", "select", "boolean", "number", "url"]
    required: bool = False
    default: Any = None
    options: list[str] | None = None     # type=select 时
    placeholder: str = ""
    help_text: str = ""
    scope: Literal["adapter", "item"] = "adapter"  # adapter级共享 vs 每条目独立
```

`scope` 区分：`adapter` = 适配器/发布器级共享配置（如 RSS 的 feed url）；`item` = 每个抓取/发布条目独立配置。

## 3. BaseAdapter 契约

```python
class BaseAdapter(ABC):
    metadata: ClassVar[PluginMetadata]

    @abstractmethod
    async def fetch(self, config: Mapping[str, Any]) -> Any:
        """从外部源拉取原始数据。失败应抛异常或返回空。"""

    @abstractmethod
    def transform(self, raw: Any, config: Mapping[str, Any] | None = None) -> list[UnifiedData]:
        """把原始数据转换为 UnifiedData 列表。必须是同步纯转换。"""

    async def fetch_and_transform(self, config: Mapping[str, Any]) -> list[UnifiedData]:
        """模板方法：fetch → transform（→ 可选翻译）。子类一般不重写。
        错误被捕获后返回空列表（容错，不让单源失败拖垮全量抓取）。"""
```

- `fetch` 与外部交互（HTTP/解析），必须 async。
- `transform` 是纯转换，同步、可单测。
- 错误容错：单 adapter 失败返回 `[]`，由上层记录 task_log。

## 4. BasePublisher 契约

```python
class BasePublisher(ABC):
    metadata: ClassVar[PluginMetadata]

    @abstractmethod
    async def publish(self, content: Any, options: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """发布内容，返回 {status, ...}。失败抛异常。"""

    async def get_item_url(self, item: Any) -> str | None:
        """可选：返回发布项的访问 URL。"""
        return None
```

- 飞书/企微机器人：`content` 是渲染好的卡片/Markdown；`options` 含 webhook/secret。
- 公众号发文：`content` 是 HTML + 素材信息。
- 必须有超时与重试（指数退避）。

## 5. BaseStorageProvider 契约

```python
class BaseStorageProvider(ABC):
    metadata: ClassVar[PluginMetadata]

    @abstractmethod
    async def upload(self, local_path: str, target_path: str) -> str | None:
        """上传文件，返回公网 URL；失败返回 None。"""
```

最简契约。R2 用 boto3 S3 兼容；GitHub 用 Content API（每次产生 commit）。

## 6. BaseTool 契约

```python
class BaseTool(ABC):
    metadata: ClassVar[PluginMetadata]
    id: ClassVar[str]                # 与 metadata.id 一致
    name: ClassVar[str]              # 暴露给 LLM 的函数名（[a-zA-Z0-9_-]）
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]]   # JSON Schema，暴露给 LLM 做 function calling
    is_builtin: ClassVar[bool] = False

    @abstractmethod
    async def handler(self, args: Mapping[str, Any]) -> Any:
        """执行工具，返回结果（任意可序列化对象）。"""
```

- `parameters` 必须是合法 JSON Schema（含 `type/properties/required`）。
- `name` 是 LLM 看到的函数名，必须合法（字母开头，仅 `[a-zA-Z0-9_-]`）。
- `handler` 必须可序列化返回（dict/list/str/number/bool）；复杂对象转 dict。
- 工具一般通过依赖注入或 `ServiceContext` 拿服务引用，不在构造时硬连。
- `ExecuteCommandTool` 类必须有白名单/黑名单。

## 7. 自动发现机制

- 扫描路径：`plugins/builtin/{adapters,publishers,storages,tools}/**` 与 `plugins/custom/**`。
- 用 `importlib` + 目录扫描（备选：entry-points）。
- 识别规则：模块中带 `metadata: ClassVar[PluginMetadata]` 属性的类即插件。
- 跳过：文件名含 `base`/`_base` 的基类文件、`__init__.py`、`*_test.py`。
- 注册到对应 Registry（单例 Map）。
- **无运行时热加载**：新增/改插件需重启或 `ServiceContext.reload()`（重新扫描实例化）。

## 8. 注册中心（Registry）

四个单例 Registry：`AdapterRegistry`/`PublisherRegistry`/`StorageRegistry`/`ToolRegistry`。
- API：`register(key, cls, metadata)` / `get(key)` / `get_metadata(key)` / `list()` / `list_metadata()`。
- `ToolRegistry` 双注册：`register(cls)`（发现）+ `register_tool(instance)`（实例化），`get_tool(id)`/`call_tool(id, args)`/`get_all_tools()`。
- 「禁用」靠配置黑名单 `CLOSED_PLUGINS` 在实例化阶段跳过。

## 9. 新增插件步骤（清单）

1. 在 `plugins/builtin/<类型>/<名字>.py` 创建类，继承对应基类。
2. 定义 `metadata: ClassVar[PluginMetadata]`，填 config_fields。
3. 实现必须的方法（fetch/transform 或 publish 或 upload 或 handler）。
4. Tool 的 `parameters` 用 JSON Schema 描述入参。
5. 写单元测试（mock 外部 I/O）。
6. 启动确认自动发现注册成功（出现在 `list_metadata()`）。
7. 更新本文件如契约有扩展。

## 10. 命名与隔离

- 插件 id 全局唯一（建议 `<source>_<kind>`，如 `rss`、`feishu_bot`、`wecom_bot`、`r2`、`github_storage`）。
- MCP 工具对外名做隔离：`<safe_config_id>__<safe_tool_name>`，强制合法字符。
- Adapter 的 UnifiedData.source 字段填来源名，便于下游归类。
