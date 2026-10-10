# 王者营地接口扩展参考

本文件汇总 `ningxiaoxiao/hok_camp_api` 与 `wzq10314/astrbot_plugin_gloryofkings` 中可供本插件扩展参考的接口、协议与调用流程。它是开发参考，登录接口与游戏数据接口的在线可用性仍需用实际登录态验证。

- 最近补充日期：2026-10-10。
- 当前插件版本：**v2.5.4**。第 1～25 节保留来源审阅及对应阶段的状态，历史“未接入 / 开发版”描述不代表当前版本；基础接入与真实联调范围见[第 26 节](#26-当前版本接入与真实联调记录)，后续缓存、订阅、推送格式与登录错误处理变更见第 27～30 节。
- 第 1～15 节：原有 `hok_camp_api` 记录与昵称搜索实测，保留原来源和验证范围。
- 第 16～25 节：新增 `astrbot_plugin_gloryofkings` 源码审阅、详细接口资料、官网 / 第三方只读实测与接入差异。
- 快速入口：[新增能力与证据范围](#16-gloryofkings-来源与证据范围)、[接口总表](#17-gloryofkings-接口总表)、[营地协议](#18-营地公共请求协议与错误处理)、[游戏数据](#19-营地游戏数据接口详解)、[登录](#20-微信与-qq-登录接口)、[公开数据](#21-官网与第三方公开接口)、[观战与消息服务](#22-观战与营地消息外置服务)、[共享库与分发](#23-共享库与服务包分发接口)、[验证结果](#24-接入建议与本次验证结果)、[新增源码索引](#25-gloryofkings-固定源码索引)。

以下原始记录的日期与快照只对应 `hok_camp_api`，不代表新增来源的版本。

- 记录日期：2026-10-07。
- 来源项目：[ningxiaoxiao/hok_camp_api](https://github.com/ningxiaoxiao/hok_camp_api)。
- 来源快照：[`13177c122bbf684cc793aab17089754978e66f93`](https://github.com/ningxiaoxiao/hok_camp_api/tree/13177c122bbf684cc793aab17089754978e66f93)，提交日期为 2026-08-01。
- 初始对照基线：v2.4.2，提交 `597a1f4`；随后开发版已接入昵称搜索、独立别名和战绩模式筛选。
- 初始记录范围：阅读源码、请求构造、字段读取与路由调用链；随后按用户要求实测了昵称搜索，结果见第 14 节。其他新增接口尚未进行真实请求验证。

文中的“源码已实现”表示来源项目存在对应代码；“源码读取”表示代码使用了该字段，但仓库没有提供真实响应样本供本次核验；“待实测”表示协议语义或线上行为尚未确认。请求中的 `<CAMP_ID>` 等均为占位符，响应结构示意也不代表一次真实请求结果。

## 1. 能力范围与扩展顺序

| 优先级建议 | 能力                   | 腾讯远程接口                   | 本插件 v2.4.2 状态                           | 参考价值                                       |
| ---------- | ---------------------- | ------------------------------ | -------------------------------------------- | ---------------------------------------------- |
| 高         | 按昵称搜索营地用户     | `POST /search/getbytype`       | 开发版已接入；先查别名、游戏昵称，再在线搜索 | 帮助用户找到营地 ID，展示候选用户供选择        |
| 高         | 按营地 ID 获取角色列表 | `POST /game/allrolelistv3`     | 未接入；资料接口的 `roleList` 只选一个角色   | 获取角色列表、角色名称、区服描述与在线状态线索 |
| 中         | 按模式查询战绩         | `POST /game/morebattlelist`    | 开发版支持全部、排位、巅峰（0/1/4）          | 标准与娱乐模式仍可留作后续扩展                 |
| 中         | 补充对局详情字段       | `POST /game/battledetail`      | 已接入，只规范化部分字段                     | 扩展分路、评分、治疗、控制、推塔等对局分析     |
| 中         | 对局回顾               | `POST /game/battleanalyze/old` | 未接入                                       | 经济曲线、关键事件、移动轨迹与复盘建议线索     |
| 中         | 角色英雄资料           | `POST /game/profile/herolist`  | 未接入；已有赛季常用英雄数据                 | 比较其与赛季接口的覆盖范围，再决定是否新增展示 |
| 低         | 营地用户资料           | `POST /userprofile/profile`    | 未接入；已有新版综合资料查询                 | 比较补充字段，作为兼容性研究对象               |
| 低         | 旧版角色概况           | `POST /game/profile/index`     | 使用的是 `/game/koh/profile`                 | 比较旧版与新版字段和指定角色行为               |

来源：[接口客户端][S2]、[昵称搜索][S1]。优先级是结合本插件现状提出的开发建议。

### 必须保留的能力边界

1. 来源项目没有实现“仅凭数字游戏角色 `roleId` 反查营地 ID”的独立接口。
2. 昵称搜索的入参是 `name`，返回字段注释为 `nickname` 和 `friendUid`；不能仅凭这些名称断言它支持按游戏内角色名搜索。营地昵称、游戏角色名、纯数字 ID 的匹配行为均需验证。
3. 获取角色列表的方向是“营地 ID → 角色列表”，不能据此推断接口支持相反方向。
4. 上游路由通常取角色列表的第一个元素；完整的角色选择流程仍需要我们设计和实现。
5. 来源项目没有移植按英雄名或单英雄筛选战绩所需的 `historydetails` 功能，也没有给出足够的请求参数可直接参考。[已知限制][S4]

## 2. ID、域名与鉴权约定

### 2.1 ID 对照

| 名称                                                   | 在来源项目中的用途                         | 注意点                                                    |
| ------------------------------------------------------ | ------------------------------------------ | --------------------------------------------------------- |
| `uid` / `yd_user_id` / `friendUserId` / `targetUserId` | 被查询用户的营地 ID                        | `uid` 是服务层的命名，不应在产品中模糊地标成游戏角色 ID   |
| `friendUid`                                            | 搜索结果中的用户标识，来源代码映射为 `uid` | 需在实测中用角色列表或资料接口验证结果对应的营地账号      |
| `userId` / 请求头 `userId` / 配置 `user`               | 发起请求的登录账号 ID                      | 查询他人时，它与目标营地 ID 可以不同                      |
| `roleId` / `targetRoleId`                              | 营地角色接口返回或使用的角色标识           | 不自动等同于游戏内个人主页显示的数字 ID                   |
| `playerId`                                             | 对局详情角色中的玩家标识，用于对局回顾请求 | 来源代码单独提取，不能用 `roleId` 直接替代                |
| `playerID`                                             | 回顾轨迹条目中的标识拼写                   | 来源分析脚本用它匹配 `matchInfo[].playerId`，大小写需区分 |
| `gameSeq`                                              | 对局标识                                   | 回顾和详情使用；保留原值，避免浮点数转换                  |
| `gameSvr` / `gameSvrId`                                | 对局服务器参数                             | 战绩返回读取 `gameSvrId`，详情请求发送 `gameSvr`          |
| `relaySvr` / `relaySvrId`                              | 对局中继服务器参数                         | 战绩返回读取 `relaySvrId`，请求发送 `relaySvr`            |
| `sid`                                                  | 来源服务自己的绑定键                       | 仅用于本地 `sid → uid` 绑定，不是腾讯接口参数             |

来源：[搜索结果映射][S1]、[回顾参数解析][S2]、[绑定配置][S5]、[轨迹匹配脚本][S8]。

### 2.2 腾讯远程域名

| 基础地址                                | 用途                                           |
| --------------------------------------- | ---------------------------------------------- |
| `https://kohcamp.qq.com`                | 搜索、战绩、资料、英雄资料、对局详情和对局回顾 |
| `https://ssl.kohsocialapp.qq.com:10001` | `allrolelistv3` 角色列表                       |
| `https://pvp.qq.com`                    | 静态英雄目录，见第 10 节                       |

来源客户端使用请求头中的 `token` 与 `userId`，部分表单还在请求体中携带相同凭据。我们已有的 `CampAuthStore`、扫码登录和账号池是接入时的登录态来源；每次换号后，请求头与表单凭据都要来自本次实际选中的同一个账号。

### 2.3 客户端头与解密差异

来源客户端固定了 `User-Agent=okhttp/4.9.1`、`cGameId=20001`、`cChannelId=10003391` 等营地客户端头。其默认版本是 `10.112.0603` / `2057965009`；`userprofile/profile` 另有旧版本头 `8.92.0125` / `2037857908`。[请求头实现][S2]

这些值是来源快照中的选择，不是所有接口必须使用该版本的证明。源码中旧头覆盖版本号时还混用了大小写；接入时应规范化头名称，避免同时发送两个语义相同的版本头。

来源项目通过外部配置读取 `key`、`user`、`token`，未构造本插件现有的 `encodeParam`。它还使用同步 `httpx.Client`、`verify=False`，以及随机生成的 `gameOpenId`。参考接口时沿用本插件的异步请求、TLS 设置、扫码登录、真实账号字段与安全参数，不直接替换整套客户端。

来源解密器的处理流程是 Base64 → XXTEA → 按内容尝试 gzip 或默认 zlib 解压 → 文本。[解密实现][S6] 本插件的 `decode_camp_payload` 当前没有这一层解压。后续只有在真实响应或脱敏样本确认需要时，再增加兼容处理，保留现有加密向量验证。

## 3. 昵称搜索：`/search/getbytype`

### 3.1 地址、编码与鉴权

```http
POST https://kohcamp.qq.com/search/getbytype
Content-Type: application/x-protobuf
```

- 来源入口：`app/search.py` 的 `search(name)`。
- 请求体：Protobuf 原始二进制，通过 `content=` 发送，不是 JSON，也不是表单。
- 请求头：复用来源 `request_headers()`，其中含登录账号的 `token` 与 `userId`，然后覆盖 `Content-Type`。
- 响应：来源实现按 Protobuf 原始字节解析，没有走其 XXTEA 解密器。
- 来源服务包装：`GET /query/show?name=<搜索词>`，这个路径属于该项目自己的 FastAPI 服务，不属于腾讯。

来源：[搜索实现][S1]、[包装路由][S3]。

### 3.2 请求字段

来源仓库没有提交 `.proto` 文件，而是手写以下字段。字段编号、wire type 和常量可以确认；除搜索词外，各常量的完整业务含义没有在源码中定义。

| 字段号 | Wire type | 编码类型       | 来源发送值           | 已确认含义                     |
| ------ | --------- | -------------- | -------------------- | ------------------------------ |
| 1      | 0         | varint         | `1011`               | 固定常量；搜索分类含义待确认   |
| 2      | 2         | 长度前缀字节串 | `name` 的 UTF-8 字节 | 搜索词                         |
| 3      | 0         | varint         | `1`                  | 固定常量；是否为页码待确认     |
| 4      | 0         | varint         | `10`                 | 固定常量；是否为每页数量待确认 |
| 7      | 2         | 长度前缀字节串 | 字符串 `"0"`         | 固定常量；是否为游标待确认     |

来源只实现这组固定参数。后续不能直接将字段 3、4、7 宣称为完整分页协议，应先比较多组真实搜索响应。[请求构造][S1]

### 3.3 响应结构与输出映射

来源解析沿以下嵌套字段路径读取用户详情，每层都支持重复字段：

```text
root.field[3] → data.field[1] → userGroup.field[25] → user.field[2] → detail
```

这些层级名称来自源码注释，不代表已取得腾讯的正式 schema。

| `detail` 字段号 | 来源读取类型 | 输出键   | 源码注释 / 用途                        |
| --------------- | ------------ | -------- | -------------------------------------- |
| 17              | varint       | `uid`    | `friendUid`，转换为字符串              |
| 2               | 字节串       | `name`   | `nickname`，UTF-8 文本                 |
| 3               | 字节串       | `avatar` | `avatarUrl`                            |
| 10              | varint       | `level`  | 等级，输出为字符串                     |
| 28              | 字节串       | `dw`     | `title1`，展示文字；具体段位语义待实测 |
| 37              | 字节串       | `region` | 地区文字；是否等同游戏区服待实测       |

来源缺失字符串输出空串，数字 `uid` / `level` 经过 `or ""` 后也可能输出空串。其结果不是游戏角色列表，里面没有解析 `roleId`。[响应映射][S1]

来源 `GET /query/show` 遇到空结果会返回一个带 `uid="---"` 的提示对象。这个占位对象是包装层生成的提示，不是腾讯返回的用户，不能用于后续角色查询。[包装行为][S3]

### 3.4 本插件接入位置

| 现有模块                            | 需要处理的差异                                                      |
| ----------------------------------- | ------------------------------------------------------------------- |
| `core/http.py`                      | 开发版已在 `HttpResponse.body` 保留响应字节，同时兼容已有 `text`    |
| `core/camp_client.py`               | 开发版使用 `protobuf=True` 发送二进制并解析业务状态，沿用账号池重试 |
| `core/camp_api.py`                  | 开发版 `search_users` 返回去重后的候选用户集合                      |
| `core/service.py` / `core/webui.py` | 开发版优先查精确别名与游戏昵称，处理多候选和空结果                  |
| 页面 / 消息入口                     | 开发版展示编号、昵称、地区、段位和营地 ID，支持 60 秒选择           |

来源的 `_parse` 没有完整的长度边界、varint 长度限制和未知 wire type 错误处理；`search()` 也未显式检查 HTTP 成功状态或 Protobuf 业务状态。移植时需要补齐这些错误路径，继续复用账号失效与频控处理，避免把错误响应解析成“未找到用户”。

### 3.5 待验证事项

- 用已知营地昵称、已知游戏角色名和营地数字 ID 分别搜索，验证匹配对象和搜索类型。
- 搜索结果 `uid` 能否用于 `allrolelistv3` 或现有资料接口定位同一用户。
- 同名、特殊字符、空关键词、非 ASCII 昵称与多页结果行为。
- `region` 和 `dw` 的准确业务含义。
- Protobuf 状态字段与频控 / 鉴权失败响应。来源调试脚本会观察根字段 2，但没有提供其错误码定义。[调试入口][S7]
- 当前登录态的 `encodeParam`、客户端版本与该搜索接口的兼容性。

## 4. 角色列表：`/game/allrolelistv3`

### 4.1 请求

```http
POST https://ssl.kohsocialapp.qq.com:10001/game/allrolelistv3
Host: ssl.kohsocialapp.qq.com:10001
Content-Type: application/x-www-form-urlencoded
```

| 表单字段       | 取值来源                      | 说明                 |
| -------------- | ----------------------------- | -------------------- |
| `friendUserId` | 用户输入或搜索结果中的营地 ID | 被查询用户           |
| `token`        | 本次选中的登录账号            | 与请求头 token 一致  |
| `userId`       | 本次选中的登录账号 ID         | 与请求头 userid 一致 |

来源 `get_user_role(yd_user_id)` 用 `data=` 发送表单并直接解析 JSON；请求头同时携带账号凭据。[请求实现][S2]

### 4.2 响应消费方式

来源业务层按外层 `returnCode` 判断结果，再从 `data` 数组取角色。以下是结构示意，字段的实际存在性和类型需通过响应样本确认：

```json
{
  "returnCode": 0,
  "data": [
    {
      "roleId": "<ROLE_ID>",
      "roleName": "<角色名>",
      "roleDesc": "<角色描述>"
    }
  ]
}
```

| 字段                | 来源代码的使用方式                 | 扩展用途                           |
| ------------------- | ---------------------------------- | ---------------------------------- |
| `data[].roleId`     | 转成字符串传给资料、英雄与详情接口 | 保留角色标识                       |
| `data[].roleName`   | 资料、战绩和绑定列表显示           | 角色选择项名称                     |
| `data[].roleDesc`   | 绑定列表读取                       | 区服或角色描述线索；具体格式待确认 |
| `data[].gameOnline` | 绑定列表读取                       | 在线状态线索；值类型与含义待确认   |

来源：[资料与绑定路由][S3]。

### 4.3 与本插件当前行为的区别

本插件已经在 `/game/koh/profile` 响应中读取 `roleList`，但 `parse_profile` 只保留响应 `targetRoleId` 对应的角色，匹配不到时取第一个；内部 `PlayerProfile` 和查询结果没有完整角色集合。

来源 `allrolelistv3` 可以作为专门角色列表接口的参考，但要比较它与现有 `roleList` 的覆盖范围，不能仅凭名称断言哪一个一定包含所有跨区角色。

接入需要在 `CampClient` 支持上述固定腾讯域名与表单编码，不能把这个路径直接拼在当前 `MAIN_BASE=https://kohcamp.qq.com` 后面。与 JSON 接口一样，换号重试时表单中的 `userId` / `token` 必须重新生成。

角色列表成功返回后应保留整个数组，并处理空数组、重复角色、缺失角色 ID、角色解绑和角色改名。来源的多处 `data[0]` 没有充分处理空数组，不能直接沿用为用户选择逻辑。

### 4.4 多角色选择的后续设计约束

- 保留“营地账号 ID”和“所选角色 ID”两个独立字段。
- 明确用户选择是否只作用于本次请求，还是保存为默认选择；这是后续功能设计，不是来源协议规定。
- 本地名称表当前按营地 ID 记录一个名称。若要同时保存同一营地账号的多个角色，需要先确定名称映射与角色选择的数据契约。
- 资料和赛季查询已有 `targetRoleId` / `roleId` 的参考方向；战绩列表的来源请求仍只有 `friendUserId`，没有提供指定角色的有效请求示例。
- 在战绩接口的角色选择参数验证前，不能承诺“切换角色后战绩也一定切换”，也不能将 `option` 当成角色选择参数。

## 5. 战绩模式筛选：`/game/morebattlelist`

本插件已有此接口，主要参考价值是请求选项与上游模式映射。[客户端][S2]、[模式映射][S3]

```http
POST https://kohcamp.qq.com/game/morebattlelist
Content-Type: application/json; charset=UTF-8
```

来源请求结构示意：

```json
{
  "option": 0,
  "isMultiGame": 1,
  "apiVersion": 5,
  "lastTime": 0,
  "recommendPrivacy": 0,
  "friendUserId": "<CAMP_ID>"
}
```

| `option` | 来源包装层的模式映射 | 验证状态                                                 |
| -------- | -------------------- | -------------------------------------------------------- |
| 0        | 全部                 | 本插件已支持全部模式                                     |
| 1        | 排位                 | 开发版已接入；本次真实请求返回的 30 条均归类为排位       |
| 2        | 标准                 | 来源映射已实现，不应自行改称只包含某一种匹配模式         |
| 3        | 娱乐                 | 来源映射已实现，具体模式集合待验证                       |
| 4        | 巅峰                 | 开发版已接入；本次真实请求为空，非空响应另有离线分类验证 |

`isMultiGame=1` 是来源增加的常量，源码没有给出它的完整语义。应独立比较开启 / 不开启的响应，避免与角色切换混淆。

来源固定 `lastTime=0`，没有实现本插件现有的多页游标拉取。接入筛选时保留本插件的 `hasMore` / `lastTime` 翻页、节流、去重和最大数量限制，并让筛选值在每页请求保持一致。

来源读取战绩列表的 `data.list`，以及 `gameSeq`、`gameSvrId`、`relaySvrId`、`battleType`，这些也可继续用于本插件已有的按对局标识定位。[回顾参数链路][S2]

源码按 Base64 + XXTEA 处理响应。我们已有的响应头 `campencrypt` 检查应继续作为实际响应解析依据，不根据接口名称强行将所有响应视为密文。

## 6. 用户资料与旧版角色概况

### 6.1 `/userprofile/profile`

```http
POST https://kohcamp.qq.com/userprofile/profile
Content-Type: application/json; charset=UTF-8
```

请求结构：

```json
{
  "friendUserId": "<CAMP_ID>",
  "roleId": "<ROLE_ID>",
  "scenario": 0
}
```

来源 `get_user_profile` 使用旧客户端版本头并直接解析 JSON。[客户端实现][S2] 外层 `data` 被来源 `/user/` 原样作为 `profile` 返回；该仓库没有完整解析每个资料字段，不能从函数名推定新增字段。

参考用途是与现有 `/game/koh/profile` 比较用户资料覆盖范围。先收集实际字段差异，再决定是否作为补充，避免增加一个没有新增有效数据的请求。

### 6.2 `/game/profile/index`

```http
POST https://kohcamp.qq.com/game/profile/index
Content-Type: application/json; charset=UTF-8
```

请求结构：

```json
{
  "targetUserId": "<CAMP_ID>",
  "recommendPrivacy": 0,
  "targetRoleId": "<ROLE_ID>"
}
```

来源 `get_user_profile_index` 对响应做 Base64 + XXTEA 解密，再将 `data` 作为 `profileIndex` 返回。[客户端实现][S2]、[用户资料组合路由][S3]

本插件当前使用 `/game/koh/profile`，另有 `apiVersion=2`、`resVersion=3` 等参数。两个路径是不同接口，字段兼容性和指定角色后的行为需要分别核验；不能仅因为功能名称相似就替换。

## 7. 英雄资料：`/game/profile/herolist`

```http
POST https://kohcamp.qq.com/game/profile/herolist
Content-Type: application/json; charset=UTF-8
```

请求结构：

```json
{
  "targetUserId": "<CAMP_ID>",
  "recommendPrivacy": 0,
  "targetRoleId": "<ROLE_ID>"
}
```

- 来源函数：`get_user_profile_hero_list(yd_user_id, role_id)`。
- 来源响应处理：Base64 → XXTEA → JSON。
- 来源服务仅将其 `data` 作为 `heroList` 返回，没有规范化英雄字段。
- 来源请求没有赛季、排序、分页或分路筛选参数。

来源：[客户端实现][S2]、[组合资料路由][S3]。

本插件 `/game/seasonpage` 已提供本赛季常用英雄数据。新增这个接口前，需要核对英雄集合、统计时间范围、场次、胜率、战力字段，以及是否包含本赛季之外的信息。字段未知时保留缺失状态，不能把它自动合并成已有赛季统计。

## 8. 对局详情字段扩展：`/game/battledetail`

### 8.1 已有请求与新增线索

```http
POST https://kohcamp.qq.com/game/battledetail
Content-Type: application/json; charset=UTF-8
```

请求结构：

```json
{
  "recommendPrivacy": 0,
  "battleType": "<BATTLE_TYPE>",
  "gameSvr": "<GAME_SVR>",
  "relaySvr": "<RELAY_SVR>",
  "targetRoleId": "<ROLE_ID>",
  "gameSeq": "<GAME_SEQ>"
}
```

示意中的 `battleType` 是占位字符串。来源调用链将其转换为字符串，本插件当前接口使用整数；参数类型是否都被服务端接受应由实际请求确认。

本插件已具备这个查询及双方阵容、装备、召唤师技能、KDA、等级、经济和伤害等部分解析。值得参考的是来源调试脚本探索的额外字段，以及回顾所需的 `basicInfo.playerId`。[详情实现][S2]、[调试字段读取][S9]

### 8.2 字段记录

下列字段来自源码读取或调试探索，仓库没有提交对应真实响应文件；字段可选性、类型、单位和数值范围需实测确认。

| 路径（均在 `data.redRoles[]` / `data.blueRoles[]` 内）                 | 来源用途或线索           | 对本插件的价值                                |
| ---------------------------------------------------------------------- | ------------------------ | --------------------------------------------- |
| `basicInfo.roleId`                                                     | 匹配角色                 | 严格定位用户选中的目标角色                    |
| `basicInfo.playerId`                                                   | 回顾参数                 | 获取对局回顾需要的玩家标识                    |
| `basicInfo.isMe`                                                       | 来源参数补全中的匹配条件 | 查询他人时语义需确认，优先核对选中的 `roleId` |
| `battleRecords.position`                                               | 来源转换为 `lane`        | 展示该场实际分路                              |
| `battleStats.healCnt`                                                  | 分析脚本读取             | 治疗数据线索                                  |
| `battleStats.ctrlTime`                                                 | 分析脚本读取             | 控制时长线索；单位待确认                      |
| `battleStats.towerCnt`                                                 | 分析脚本读取             | 推塔数据线索                                  |
| `battleStats.buildingDamage`                                           | 分析脚本读取             | 建筑伤害线索                                  |
| `battleStats.gradeGame`                                                | 分析脚本读取             | 对局评分线索                                  |
| `battleStats.hurtTransRate`                                            | 分析脚本读取             | 伤害转化相关字段；定义与比例尺度待确认        |
| `battleStats.sabchurthero` / `sabcbattle` / `sabcgrow` / `sabcsurvive` | 分析脚本组合输出         | 对局维度评级线索；枚举与准确名称待确认        |
| `heroBehavior`                                                         | 调试脚本输出             | 本人英雄历史表现相关结构线索                  |
| `dataBehavior` / `dataBehaviorV2`                                      | 调试脚本输出             | 更细的表现数据结构线索                        |
| `dataBehaviorV2[].title` / `dataCounts[].name,data,dataNote`           | 分析脚本读取             | 标题、指标、值和对照说明；单位待确认          |

来源：[参数补全与详情][S2]、[详情分析脚本][S9]、[统计结构探索][S10]。

来源的 `battleRecords.position` 映射如下，其注释称作者曾人工核对，本次没有重新核对真实对局：

| 值  | 来源映射 |
| --- | -------- |
| 0   | 对抗路   |
| 1   | 中路     |
| 2   | 发育路   |
| 3   | 打野     |
| 4   | 游走     |

来源：[分路映射][S2]。这套编号与本插件英雄目录的 `roles`、奖牌的 `branchEvaluate` 是不同字段，不能共用一个编号表。

## 9. 对局回顾：`/game/battleanalyze/old`

### 9.1 地址与变体

```http
POST https://kohcamp.qq.com/game/battleanalyze/old
Content-Type: application/json; charset=UTF-8
```

来源函数还提供两个分支，分支存在于源码并不代表本次已确认线上可用：

| 条件        | 路径                          | 状态                               |
| ----------- | ----------------------------- | ---------------------------------- |
| 默认        | `/game/battleanalyze/old`     | 有参数补全与调试调用代码           |
| `beta=True` | `/game/betabattleanalyze/old` | 仅记录来源分支，范围与可用性待验证 |
| `kpl=True`  | `/game/kplbattleanalyze/old`  | 仅记录来源分支，范围与可用性待验证 |

来源代码在两个开关都开启时优先选 `kpl`。[回顾请求][S2]

### 9.2 请求参数

```json
{
  "gameSeq": "<GAME_SEQ>",
  "gameSvr": "<GAME_SVR>",
  "relaySvr": "<RELAY_SVR>",
  "playerId": "<PLAYER_ID>",
  "h5Get": 1
}
```

| 字段       | 参数来源                              | 来源发送行为                                      |
| ---------- | ------------------------------------- | ------------------------------------------------- |
| `gameSeq`  | 战绩列表目标对局                      | 转为字符串，总是发送                              |
| `gameSvr`  | 目标对局的 `gameSvrId`                | 转为字符串，总是发送                              |
| `relaySvr` | 目标对局的 `relaySvrId`               | 非空时发送                                        |
| `playerId` | 详情中目标角色的 `basicInfo.playerId` | 非空时发送；README 与服务路由将其视为必要定位条件 |
| `h5Get`    | 常量                                  | 数字 `1`                                          |

来源按文本是否以 `{` 开始决定直接解析 JSON，其他情况尝试解密。我们应将这一行为当作兼容性线索，结合 HTTP 状态、响应头与解密结果明确处理错误，避免将任意非 JSON 文本都判成有效密文。

来源：[客户端实现][S2]、[参数说明][S4]。

### 9.3 参数补全链路

来源 `resolve_replay_params(uid, game_seq)` 的步骤：

1. 使用营地 ID 请求角色列表，取一个角色的 `roleId`。
2. 请求战绩列表；给定 `gameSeq` 时匹配指定局，否则取最近一局。
3. 从战绩提取 `battleType`、`gameSvrId`、`relaySvrId`、`gameSeq`。
4. 请求 `battledetail`，合并双方角色。
5. 使用 `isMe` 或 `roleId` 匹配角色，取得 `basicInfo.playerId`。
6. 将对局参数和 `playerId` 发给回顾接口。

接入时可以复用本插件已有的资料、战绩翻页、对局标识定位和详情链路。来源只在第一页中找指定局，本插件的已有游标翻页更适合保留。

需要特别处理空列表、角色 ID 不匹配、已不在近期列表中的对局，以及缺失 `playerId`。来源代码存在 `str(None)` 生成字符串 `"None"` 的可能，不能将其当成有效玩家标识。

### 9.4 回顾字段线索

| 路径（均在外层 `data` 中）                        | 源码读取或说明                           | 可能的功能                           |
| ------------------------------------------------- | ---------------------------------------- | ------------------------------------ |
| `matchInfo[]`                                     | 阵容、英雄、KDA、`userId`、`playerId` 等 | 对局成员信息与轨迹关联               |
| `camp1GoldArr` / `camp2GoldArr`                   | 双方经济序列                             | 双方经济曲线                         |
| `ecoDistance`                                     | 经济差序列                               | 优势变化与经济差图                   |
| `camp1Gold` / `camp2Gold`                         | 分析脚本读取                             | 终局经济线索                         |
| `winCamp`                                         | 分析脚本读取                             | 胜方线索                             |
| `keyEventArr[]`                                   | README 说明包含关键事件及坐标 / 时间线索 | 关键事件时间线                       |
| `keyEventArr[].eventType`                         | 分析脚本计数                             | 事件分类；完整枚举待确认             |
| `keyEventArr[].viewX,viewY,killTime`              | README 说明                              | 坐标与时间字段；单位和适用事件待确认 |
| `extendEventArr[].eventList[]`                    | 调试脚本探索                             | 更多事件线索                         |
| `reportData.playerPosInfo[]`                      | 玩家轨迹结构                             | 地图轨迹                             |
| `reportData.playerPosInfo[].playerID`             | 分析脚本匹配玩家                         | 与 `matchInfo[].playerId` 关联       |
| `reportData.playerPosInfo[].posArr`               | 位置序列，README 描述为 `[x,y]`          | 移动轨迹；坐标尺度与采样间隔待确认   |
| `playBaseInfoArr[].deathPosArr`                   | README 说明 / 调试脚本探索               | 死亡位置分析                         |
| `reportData.skillUsedInfo`                        | 调试脚本检查类型和内容                   | 技能使用结构线索，schema 未确认      |
| `reportData.noMistakeText`                        | 分析脚本读取                             | 复盘文字线索                         |
| `reportData.adviceList` / `personBehaviorAdvices` | 分析脚本读取                             | 建议结构线索                         |

来源：[README 字段说明][S4]、[经济与事件分析][S11]、[成员与轨迹关联][S8]、[事件结构探索][S12]。

这些是需要验证的字段路径，不是必定完整返回的 schema。来源调试脚本读取了 `/tmp/replay_latest.json` 等文件，但这些真实响应没有提交到仓库，本次不能确认字段的完整性。

绘制曲线前需要确认时间序列的采样间隔与时间单位；数组索引不自动等于秒数。绘制轨迹前需要确认坐标原点、轴方向、尺度与阵营关系。某个字段缺失时应省略对应分析，不能补成实际发生的事件或数据。

### 9.5 与营地 ID 反查的关系

来源分析脚本读取 `matchInfo[].userId` 并与登录账号 ID 比较，这为“已知对局内关联玩家信息”提供了线索。[成员分析][S8] 但来源项目没有实现一个接受任意 `roleId` 并返回营地 ID 的独立流程，不能把回顾成员字段等同于通用反查接口。

## 10. 静态英雄目录

来源定义了静态地址：`https://pvp.qq.com/web201605/js/herolist.json`。[接口常量][S2] 本插件已有离线 `data/heroes.json` 和 `HeroRepository`，主要用途是未来核对或更新目录，无需为每次玩家查询增加一次目录请求。

来源声明按英雄筛选战绩尚未移植；静态目录本身不能补出 `historydetails` 的请求协议。[已知限制][S4]

## 11. 来源服务自己的路由

下面的路径属于上游 FastAPI 服务。后续直接接入腾讯时，应参考其远程调用，而非把这些路由附在腾讯域名后。[路由源码][S3]

| 上游服务路由                                                          | 输入                                                           | 内部流程 / 返回                                                  |
| --------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------- |
| `GET /query/show`                                                     | `name`                                                         | Protobuf 昵称搜索，返回候选用户或包装层提示对象                  |
| `GET /user/`                                                          | `uid` 或绑定的 `sid`                                           | 角色列表取一个角色，再组合 `profile`、`profileIndex`、`heroList` |
| `GET /battle/history`                                                 | `uid` / `sid`，可带 `opt`                                      | 返回角色名、角色 ID、场数与战绩列表；未逐局获取装备详情          |
| `GET /battle/preview`                                                 | `uid` / `sid`，可带 `opt`                                      | 基于返回战绩计算场次、胜率、MVP 与模式统计                       |
| `GET /battle/replay`                                                  | 自动模式 `uid` + 可选 `gameSeq`；直接模式对局参数 + `playerId` | 自动补齐参数或直接调用回顾接口                                   |
| `GET /bind/`、`/bind/un`、`/bind/switch`、`/bind/get`、`/bind/reload` | `sid` / `uid` 等                                               | 上游自己的本地账号绑定与配置操作                                 |
| `GET /health`                                                         | 无                                                             | 服务健康状态                                                     |

本插件已有本地名称映射、管理页和账号管理。参考远程协议即可，绑定与 HTTP 服务结构没有必要整体迁移。

## 12. 接入现有架构的工作顺序

### 12.1 先验证协议，再定义产品行为

1. 搜索：确认匹配营地昵称还是游戏角色名、候选 ID 类型、重复昵称与错误响应。
2. 角色列表：比较 `allrolelistv3` 与现有 `roleList`，确认跨区角色范围与角色字段。
3. 指定角色资料：验证现有 `/game/koh/profile` 传入已确认的 `targetRoleId` 后是否返回该角色。
4. 战绩筛选：验证模式编号，另行确认多角色战绩选择参数。
5. 回顾：从已有详情取得正确 `playerId`，确认不同对局的字段、单位与数据可用范围。

协议确认后，再决定昵称搜索指令、同名候选选择、默认角色保存与复盘展示方式。这里记录的是扩展建议，不是已实现或已确认的产品需求。

### 12.2 复用边界

| 层                            | 扩展职责                                                             |
| ----------------------------- | -------------------------------------------------------------------- |
| `HttpClient` / `HttpResponse` | 二进制体和原始字节、现有超时 / 完整分块读取 / 响应大小限制           |
| `CampClient`                  | 固定目标域名、编码选择、按响应类型解析、当前账号凭据、频控与失效换号 |
| `CampDataApi`                 | 搜索、角色列表、英雄资料、回顾等业务封装，以及已有战绩查询选项       |
| 模型解析                      | 区分营地 ID / 角色 ID / 玩家 ID，规范化字段，保留缺失状态            |
| `GokService`                  | 候选与角色选择、调用编排、已有对局定位和统计                         |
| 页面 / 消息层                 | 展示选择、图表和文本，不承担请求鉴权或原始协议解析                   |
| `GokStorage`                  | 继续只保存用户设置和名称映射；角色选择持久化需先确定契约             |

### 12.3 保留现有约束

- 日志器统一从 `astrbot.api` 导入；日志和响应不包含 `token`、`userKey` 或完整鉴权头。
- 玩家资料、搜索候选、战绩与回顾实时获取，不新增玩家数据缓存。
- 网络或解析失败不自动判定为登录失效；隐藏资料与战绩遵循已有错误提示。
- 表单与二进制支持应补充到现有传输层，保留旧 JSON 调用的行为与账号重试。
- 原始二进制响应需要保持字节完整，不能经 UTF-8 解码后再编码还原。
- 本插件现有赛季接口与新版资料接口继续保留；新接口是否替代它们取决于实测字段覆盖。

## 13. 后续实现的验证记录模板

验证新功能时，可以为每个接口记录以下信息。样本应脱敏，凭据仍只保存在插件数据目录。

| 项目       | 需要记录的内容                                           |
| ---------- | -------------------------------------------------------- |
| 接口版本   | 地址、客户端版本、验证日期、来源快照                     |
| 输入身份   | 目标营地 ID / 角色 ID / 对局参数，示例使用占位符或脱敏值 |
| 请求编码   | JSON、表单或 Protobuf；具体字段和值类型                  |
| 响应处理   | HTTP 状态、关键业务头、业务码、响应类型、是否解密或解压  |
| 正常行为   | 实际返回的字段路径、类型、单位与缺失条件                 |
| 异常行为   | 登录失效、频控、隐藏信息、空列表、无匹配角色、参数缺失   |
| 账号一致性 | 换号后头与体的凭据仍一致，没有冷却有效账号               |
| 回归范围   | 原有资料、战绩、对局详情、名称映射和消息降级仍正常       |

有意义的离线验证包括 Protobuf 编码向量与截断响应、重复候选解析、角色空数组、跨域表单凭据随账号切换、筛选值跨页保持、正确匹配 `playerId`、复盘字段缺失时降级，以及解密后的压缩样本。真实接口验证应使用单独的主动联调入口，避免导入测试模块就发起联网请求。

本文件初始创建时没有新接口的真实验证结果；后续实测记录在第 14 节，未覆盖的验证项继续保留待实测状态。

## 14. 昵称搜索实测记录

2026-10-07，按用户要求使用“祈无恙”作为搜索词，通过本插件现有微信扫码登录取得登录态后，直接请求 `/search/getbytype`。

| 验证项            | 实际结果                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------- |
| 请求编码          | 使用来源 `build_request` 构造 Protobuf，`Content-Type: application/x-protobuf`                          |
| 鉴权与客户端头    | 使用本插件 `CampClient._build_headers`，含当前登录态安全参数；客户端版本为 `10.111.0323` / `2057957801` |
| HTTP 状态         | `200`                                                                                                   |
| 响应 Content-Type | `application/x-protobuf`                                                                                |
| 响应体长度        | 2538 字节                                                                                               |
| 业务状态          | 根字段 2，wire type 2，UTF-8 字符串 `success`；本次不是整型状态码                                       |
| 用户解析          | 按 `3 → 1 → 25 → 2` 路径解析出 2 个同名用户                                                             |
| 已验证输出键      | `uid`、`name`、`avatar`、`level`、`dw`、`region`                                                        |
| 原始字节          | 二进制附件与结果中的 Base64 解码值一致                                                                  |

这次请求验证了当前扫码登录态、本插件请求头与来源搜索编码可以配合使用，也验证了上表中的一次成功响应结构。原始响应与用户明细作为此次聊天的文件输出交付，文档不保存玩家明细或登录凭据。

集成后的复验仍返回 2 个候选；使用其中一个 `uid` 调用现有 `/game/koh/profile`，确认得到同名游戏角色及有效 `roleId`。该次战绩首屏请求的 `option=0` 返回 30 条，`option=1` 返回 30 条且均归类为排位，`option=4` 返回空列表。结果用于协议验证，不保存玩家明细到本库。

仍待确认：搜索词精确匹配营地昵称还是游戏角色名、字段 1/3/4/7 的完整业务含义、分页、其他错误状态，以及数字 `roleId` 是否有独立反查能力。

## 15. 固定源码索引

以下 S 系列链接固定到 `hok_camp_api` 本次读取的提交，便于后续复核，避免仓库更新后行号与含义发生变化。新增项目的 G 系列索引见第 25 节。

| 编号 | 文件                  | 主要参考内容                                                                       |
| ---- | --------------------- | ---------------------------------------------------------------------------------- |
| S1   | [app/search.py][S1]   | Protobuf 搜索请求、嵌套响应、输出映射                                              |
| S2   | [app/camp_api.py][S2] | 腾讯接口常量、请求头、角色 / 资料 / 战绩 / 回顾调用                                |
| S3   | [app/main.py][S3]     | 包装路由、模式选项、组合资料和绑定结果                                             |
| S4   | [README.md][S4]       | 回顾字段说明与尚未实现的能力                                                       |
| S5   | [app/config.py][S5]   | 登录凭据来源与本地绑定语义                                                         |
| S6   | [app/crypto.py][S6]   | XXTEA、gzip / zlib 解密处理                                                        |
| S7   | [dbg_search.py][S7]   | 搜索响应结构探索；其中早期探测请求未覆盖 Protobuf Content-Type，正式实现以 S1 为准 |
| S8   | [analyze2.py][S8]     | 回顾成员 `userId` / `playerId` 与轨迹关联                                          |
| S9   | [dbg_all.py][S9]      | 详情统计和 `dataBehaviorV2` 字段读取                                               |
| S10  | [dbg_stats.py][S10]   | `battleStats` / `heroBehavior` 等结构探索                                          |
| S11  | [analyze.py][S11]     | 回顾经济、事件与建议字段探索                                                       |
| S12  | [dbg_events.py][S12]  | 事件与技能信息结构探索                                                             |

[S1]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/app/search.py
[S2]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/app/camp_api.py
[S3]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/app/main.py
[S4]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/README.md
[S5]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/app/config.py
[S6]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/app/crypto.py
[S7]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/dbg_search.py
[S8]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/analyze2.py
[S9]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/dbg_all.py
[S10]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/dbg_stats.py
[S11]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/analyze.py
[S12]: https://github.com/ningxiaoxiao/hok_camp_api/blob/13177c122bbf684cc793aab17089754978e66f93/dbg_events.py

## 16. GloryOfKings 来源与证据范围

### 16.1 固定快照

| 项目         | 本次记录                                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 来源项目     | [wzq10314/astrbot_plugin_gloryofkings](https://github.com/wzq10314/astrbot_plugin_gloryofkings)                                                     |
| 读取日期     | 2026-10-08，Asia/Shanghai                                                                                                                           |
| GitHub 快照  | [`4d4238d2c9c2c37af7007d40dd0723308c006bb4`](https://github.com/wzq10314/astrbot_plugin_gloryofkings/tree/4d4238d2c9c2c37af7007d40dd0723308c006bb4) |
| 提交时间     | 2026-10-06 23:08:36 +08:00                                                                                                                          |
| 适配版版本   | README 标注 v1.0.15；不要与打包业务核心的版本混用                                                                                                   |
| 打包业务核心 | `engine/upstream`；`UPSTREAM.json` 标注 `longhengmu/GloryOfKings-Plugin`、版本 `1.0.7`、提交 `2cb07250a1ff3ac0930b16c563b76f597995e4c1`             |
| 来源追踪     | [UPSTREAM.json][G0] 保存 241 个上游文件的 SHA-256；本次按清单核对                                                                                   |
| 核心请求实现 | [utils/api.js][G1]；登录见 [wechatLogin.js][G2]、[qqLogin.js][G3]                                                                                   |
| 许可来源     | [项目 LICENSE][G29]、[打包上游 LICENSE][G30]；实质复制源码时保留对应 MIT 版权与许可声明                                                             |

### 16.2 如何理解字段与验证标记

- **源码构造**：从请求代码确认方法、地址、参数名、发送类型和默认值；不是正式接口 schema，也不证明每个参数都是服务端必填。
- **源码读取**：业务代码确实读取这些响应字段；没有真实样本时，不承诺字段必定出现、类型固定或数据完整。
- **上游声称实测**：来源注释或验证记录写了测试结果，本次没有复现；数量、期限、频控与权限结论均按来源经验记录。
- **本次只读实测**：2026-10-08 实际请求公开数据得到的结果，范围见 24.2；只验证列出的请求与字段形态。
- **客户端可见协议**：外置服务的 HTTP 请求和消费字段可以确认，但公开仓库缺少服务端，不能据此补写腾讯 WebSocket / IM / 取流协议。

下文 JSON 均为请求模板或字段示意，占位符不是真实凭据。来源中的 `requesterBotUserId`、`targetUserId` 方法参数经常只用于选择本地登录账号；只有显式写进 JSON / 表单 / 请求头的字段才会发给远端。第 1 节的能力边界对应旧来源；本次新增单英雄详情与皮肤协议以第 19 节为准。

## 17. GloryOfKings 接口总表

### 17.1 腾讯营地游戏数据

以下 15 个业务入口都需要可用营地登录态。`J` 表示 `POST https://kohcamp.qq.com` + JSON + 第 18 节的营地鉴权头；`F` 表示 `POST https://ssl.kohsocialapp.qq.com:10001` + URL 编码表单 + 18.2 的头和公共表单字段。[请求门面][G1]

| 编号 | 路径                                       | 协议              | 能力 / 核心入参                                      | 详解  |
| ---- | ------------------------------------------ | ----------------- | ---------------------------------------------------- | ----- |
| C01  | `/game/morebattlelist`                     | J                 | 战绩分页；`friendUserId`、`option`、`lastTime`       | 19.1  |
| C02  | `/game/battledetail`                       | J                 | 单局详情；对局坐标、`targetRoleId`、`friendUserId`   | 19.2  |
| C03  | `/game/koh/profile`                        | J                 | 主页、默认角色、角色列表；`targetUserId`             | 19.3  |
| C04  | `/game/profile/herolist`                   | J                 | 生涯常用英雄；`targetUserId`、`targetRoleId`         | 19.4  |
| C05  | `/play/h5getherolist`                      | F                 | 我的英雄全表；`friendUserId`                         | 19.5  |
| C06  | `/hero/getseasonusaullyherolist`           | J                 | 英雄赛季 / 历史最高战力；`roleId`、`seasonId`        | 19.6  |
| C07  | `/gametoolbox/hero/record/pagedetails`     | J + `serverId` 头 | 单英雄详情、称号、近局、战力曲线；`roleId`、`heroid` | 19.7  |
| C08  | `/play/h5getheroskinlist`                  | F                 | 拥有皮肤、全量配置、统计；`friendUserId`             | 19.8  |
| C09  | `/gametoolbox/equip/hero/getherobestequip` | J                 | 英雄核心装备推荐；`heroId`                           | 19.9  |
| C10  | `/gametoolbox/hero/getherofringedata`      | J                 | 铭文组合与技能；`heroId`；响应直接为顶层数据         | 19.10 |
| C11  | `/game/seasonpage`                         | J                 | 赛季汇总、历史赛季索引；`roleId`、`seasonId`         | 19.11 |
| C12  | `/game/getfightdata`                       | J                 | 模式 / 分路 / 统计周期的五维；`roleId` 等            | 19.12 |
| C13  | `/hero/getdetailranklistbyid`              | J                 | 英雄梯度榜；`rankId`、`segment`、`position`          | 19.13 |
| C14  | `/info/tv/choiceitem`                      | J                 | 大神观战池；发送空 JSON `{}`                         | 19.14 |
| C15  | `/user/getcampfriends`                     | J                 | 保活查询；发送空 JSON `{}`；来源没有解析好友 schema  | 19.15 |

这个来源没有实现原文档中的 Protobuf 昵称搜索、`allrolelistv3` 专用角色列表或 `battleanalyze/old` 对局回顾；这些能力仍参考第 3、4、9 节。来源的“按英雄查战绩”命令另有本地筛选近期列表的路径，不能当作已经掌握任意分页的远程 `historydetails` 协议。[战绩命令][G20]

### 17.2 登录、公开数据与辅助服务

| 类别            | 远端 / 基址                                                                      | 内容                                       | 凭据                                    | 详解       |
| --------------- | -------------------------------------------------------------------------------- | ------------------------------------------ | --------------------------------------- | ---------- |
| 微信 / 营地登录 | `ssl.kohsocialapp.qq.com:10001`、`open.weixin.qq.com`、`long.open.weixin.qq.com` | SDK ticket、二维码、轮询、`user/login`     | 扫码授权；登录前设备安全参数            | 第 20 节   |
| QQ / 营地登录   | `openmobile.qq.com`、`ysdk.qq.com`、营地游戏域名                                 | 浏览器授权、YSDK 换票、`openSdk` 登录      | 同一浏览器会话、授权 code、来源签名     | 第 20 节   |
| 官网公开数据    | `pvp.qq.com`、`apps.game.qq.com`                                                 | 4 个 JSON 表、英雄 HTML、资讯列表和正文    | 无营地登录；列表有公开签名常量          | 第 21 节   |
| 第三方战力查询  | `www.sapi.run`                                                                   | 英雄四大区称号战力门槛                     | 来源客户端未发送账号凭据                | 21.7       |
| 图像资源        | `game.gtimg.cn`、腾讯云图片 CDN、`qlogo.cn`                                      | 英雄、皮肤、装备、技能、QQ 头像            | 公开静态资源；以响应 URL 为准           | 21.8       |
| 观战控制服务    | 配置 `watchApiUrl`                                                               | 好友、开播、房间、停止、提示坐标、账号接收 | 本地服务；远端账号上报需配置授权        | 22.2       |
| 营地消息服务    | 配置 `campImApiUrl`                                                              | 消息轮询、好友、发消息、连接管理           | 本地服务；远端账号上报需配置授权        | 22.3       |
| ID 共享库       | 配置 `shareApiUrl`                                                               | 绑定查询 / 更新 / 删除、接入令牌管理       | `Bearer shareToken` 或 `X-Admin-Secret` | 23.1～23.2 |
| 服务包分发      | 配置 `distUrl`                                                                   | `watch` / `im` 包版本与下载                | `Bearer distToken`                      | 23.3       |

## 18. 营地公共请求协议与错误处理

### 18.1 主站 JSON 协议

来源发送 `Content-Type: application/json; charset=UTF-8`，请求体通过 `JSON.stringify` 构造。下表列出来源默认头；每个账号可覆盖客户端参数，不能把快照默认值当成腾讯永久要求。[签名与请求头][G1]

| 请求头                                                | 来源默认 / 取值                                                |
| ----------------------------------------------------- | -------------------------------------------------------------- |
| `Host`                                                | `kohcamp.qq.com`                                               |
| `User-Agent`                                          | `okhttp/4.9.1`                                                 |
| `Content-Encrypt`、`Accept-Encrypt`                   | 空串                                                           |
| `NOENCRYPT`、`X-Client-Proto`                         | `1`、`https`；仍须按响应头判断加密                             |
| `x-log-uid`                                           | 账号已有值或宿主生成的会话值                                   |
| `traceparent`                                         | 已有值或 `00-<32位hex>-<16位hex>-01`                           |
| `istrpcrequest`                                       | `true`                                                         |
| `cchannelid`                                          | `10003391`                                                     |
| `cclientversioncode`、`cclientversionname`            | `2057957801`、`10.111.0323`                                    |
| `ccurrentgameid`、`cgameid`、`gameid`                 | `20001`                                                        |
| `cgzip`、`cisarm64`、`csupportarm64`                  | `1`、`true`、`true`                                            |
| `crand`                                               | 当前毫秒时间戳字符串                                           |
| `csystem`、`csystemversioncode`、`csystemversionname` | `android`、`34`、`14`                                          |
| `cpuhardware`                                         | `qcom`                                                         |
| `tinkerid`                                            | `2057957801_64_0`                                              |
| `gameareaid`、`gameusersex`、`kohdimgender`           | `1`、`1`、`2`                                                  |
| `token`、`userid`                                     | 本次请求的登录账号 token 与营地账号 ID                         |
| `openid`、`gameopenid`、`gameroleid`、`gameserverid`  | 账号保存了对应值时发送                                         |
| `encodeParam`                                         | 有 `userKey` 时发送 XXTEA 安全参数                             |
| `specialEncodeParam`                                  | 无 `userKey` 时来源尝试 RSA 安全参数；不表示可匿名读取游戏数据 |

HTTP 头名称本身不区分大小写，但私有字段拼写和表单 / JSON 键名必须保持来源协议。`serverId` 是 C07 额外的目标区服请求头，与公共 `gameserverid` 登录账号区服头分开记录。

### 18.2 游戏侧表单协议

```http
POST https://ssl.kohsocialapp.qq.com:10001/<ENDPOINT>
Host: ssl.kohsocialapp.qq.com:10001
content-type: application/x-www-form-urlencoded
content-encrypt:
accept-encrypt:
noencrypt: 1
x-client-proto: https
accept-encoding: gzip
user-agent: okhttp/4.9.1
token: <LOGIN_TOKEN>
userid: <LOGIN_CAMP_ID>
x-log-uid: <SESSION_ID>
kohdimgender: 2
```

公共表单字段也必须发送，不能只提交业务入参：

| 字段组      | 内容                                                                                                                                                                                                                         |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 客户端      | `cChannelId`、`cClientVersionCode`、`cClientVersionName`、`cCurrentGameId`、`cGameId`、`cGzip`、`cIsArm64`、`cSupportArm64`、`cSystem`、`cSystemVersionCode`、`cSystemVersionName`、`cpuHardware`、`tinkerId`；默认值同 18.1 |
| 时间        | `cRand` = 当前毫秒时间戳字符串                                                                                                                                                                                               |
| 游戏 / 账号 | `gameAreaId`、`gameId`、`gameUserSex`、`gameRoleId`、`gameServerId`、`openId`、`token`、`userId`                                                                                                                             |
| 缺失值      | 来源把 `gameRoleId` / `gameServerId` 缺失值设为字符串 `"0"`；`openId` 缺失时使用宿主会话值，这是来源回退策略，非本次确认的服务端规则                                                                                         |
| 业务扩展    | C05 / C08 加入 `noCache="0"`、`recommendPrivacy="0"`、`friendUserId=<TARGET_CAMP_ID>`                                                                                                                                        |

所有字段经字符串化和 `URLSearchParams` 编码。此传输路径没有构造 `encodeParam`，也没有主站的完整设备请求头；响应直接解析 JSON，不走主站 XXTEA 读取器。切换候选账号时，头与体中的 `token` / `userId` / 账号游戏字段必须重建。[表单实现][G1]

### 18.3 加密、业务错误与重试

1. 优先使用登录保存的 `userKey`；没有时，Base64 解码 `encodeRes`，用营地 RSA 公钥执行与 Node `publicDecrypt` / PKCS#1 v1.5 等价的恢复，解析 JSON 的 `userKey`。公钥见现有 `core/camp_crypto.py`，与来源相同。
2. `encodeParam` 明文是 `{"timestamp":<毫秒>,"nonce":"<LOGIN_CAMP_ID>:<去横线UUID>:<毫秒>"}`；来源对明文 UTF-8 字节用 `userKey` 的 UTF-8 字节做 XXTEA，再 Base64。时间可加配置的 `serverTimeOffsetMs`。
3. 普通查询的 RSA 回退明文仍为 `timestamp` / `nonce`，nonce 前缀是 `:`。登录用的设备指纹 RSA 负载更长，见 20.2；不能混为同一模板。
4. 主站响应 `campencrypt=true` 时：Base64 → 同一登录账号的 XXTEA 解密 → UTF-8 → 去尾部 NUL → JSON。此来源没有实现第 2 节旧来源的额外 gzip / zlib 内容解压。
5. 先检查 `encryptparamerr`；空体时从响应头 `returncode` / `returnmsg` 还原业务结果，`returnmsg` 按 URI 编码文本解码。HTTP 成功、业务成功、可用数据分别判断。
6. 并非所有接口有 `returnCode/data`：C10 顶层直接为数据；表单接口缺少 `returnCode` 时来源也接受，业务代码再检查所需结构。

| 信号                                                               | 来源处理与语义范围                  | 本插件接入时的注意点                                                        |
| ------------------------------------------------------------------ | ----------------------------------- | --------------------------------------------------------------------------- |
| `returnCode=0`                                                     | 来源营地业务成功                    | 仍检查空壳、角色、列表与隐私字段                                            |
| `returnCode=-30107`                                                | 账号频控                            | 不把频控当登录失效；不要立刻重复同号请求                                    |
| `returnCode=-30003` 或确定的“登录态失效 / 请重新登录”              | 来源将账号标记失效                  | 与客户端配置错误、疑似鉴权文案分开                                          |
| `encryptparamerr`                                                  | 来源按安全参数 / 客户端配置错误处理 | 不能据此认定整个账号池失效；本插件当前将其归入 `auth`，实现扩展前应单独评估 |
| `/game/koh/profile` 的 `-10107`                                    | 来源标记隐藏主页                    | 不泛化为所有接口均不可读                                                    |
| `/game/seasonpage` 的 `-30408`                                     | 上游记录为赛季表现隐私              | 主页与战绩仍可能可读                                                        |
| `/game/getfightdata` 的 `-10110`                                   | 上游记录为赛季表现隐私              | 不能把降级近期统计标成完整赛季统计                                          |
| `invisible`、`isHideMatch`、`isHideMatchDetail` 或角色 `hideMatch` | 不同数据路径的隐藏标记              | 各字段按所在接口读取，不能只用“列表为空”判断隐藏                            |

来源按账号组织请求队列，最小请求间隔 `1200ms`，请求发出后的超时 `10000ms`，普通网络重试最多 2 次并使用指数退避；命中频控后冷却 `12h`。这些是来源项目策略 / 经验，**不是腾讯公布的限额或解封时间**。公开资料请求另用 `12000ms` 超时，不占营地队列。我们目前的分页间隔与冷却配置不同，文档记录不代表修改本插件运行策略。[传输层][G1]、[隐私降级][G11]

## 19. 营地游戏数据接口详解

本节请求均叠加第 18 节的公共协议。目标营地 ID 使用 `<TARGET_CAMP_ID>`，登录账号 ID 使用 `<LOGIN_CAMP_ID>`，游戏角色使用 `<ROLE_ID>`；保持字符串以免长 ID 丢精度。

### 19.1 C01 战绩列表：`/game/morebattlelist`

**请求 J**，来源 `getMoreBattleList`：

```json
{
  "lastTime": 0,
  "recommendPrivacy": 0,
  "apiVersion": 5,
  "friendUserId": "<TARGET_CAMP_ID>",
  "option": 0
}
```

| `option` | 上游注释 / 命令映射 |
| -------- | ------------------- |
| `0`      | 全部                |
| `1`      | 5v5 排位            |
| `16`     | 10v10 排位          |
| `2`      | 5v5 标准            |
| `4`      | 巅峰赛              |
| `19`     | 2v2 巅峰            |

来源读取 `data.list[]`、`data.hasMore`、`data.lastTime`、`data.options`、`data.invisible` / `data.invisDes`；列表项消费 `gameSeq`、`gameSvrId`、`relaySvrId`、`battleType`、`heroId` / `heroIcon`、`mapName`、`gametime` / `dtEventTime`、`usedtime`、`gameresult`、`killcnt`、`deadcnt`、`assistcnt`、`gradeGame`、MVP / 评价等字段。部分展示读取的是来源本地归一化结果，接入仍保留原始字段。

第一页 `lastTime=0`，下一页使用响应游标，并保持 `option`；遇到 `hasMore=false`、空 / 重复游标停止，按 `gameSeq` 去重。来源注释称服务端每页 30 场；本次没有验证其他模式页长，应优先读取 `options`。`option`、列表 `gametype`、详情 `battleType` 与 C12 `gameBattleType` 属于不同枚举，不能混用。

来源的英雄筛选是多页列表与本地归档按 `heroId` 匹配，**本次没有取得任意历史的远程按英雄分页协议**。[请求][G1]、[消费与分页][G20]；既有本插件实测见第 14 节。

### 19.2 C02 单局详情：`/game/battledetail`

**请求 J**，来源 `getBattledetail`：

```json
{
  "recommendPrivacy": 0,
  "battleType": 32,
  "gameSvr": "<GAME_SVR_ID>",
  "relaySvr": "<RELAY_SVR_ID>",
  "targetRoleId": "<ROLE_ID>",
  "gameSeq": "<GAME_SEQ>",
  "friendUserId": "<TARGET_CAMP_ID>"
}
```

`battleType=32` 只是模板值，实际使用列表返回值。`gameSvr` / `relaySvr` 分别来自列表的 `gameSvrId` / `relaySvrId`；来源详情调用从列表 `battleDetailUrl` 的 `toAppRoleId` 参数提取 `targetRoleId`。它表示目标玩家角色，不能填登录账号角色；链接缺字段时应显式补全或报错，不把缺失值当有效角色。

相比本插件现有请求，来源额外发送 `friendUserId`。未证明它对所有详情请求都是必填。这个来源的详情消费路径为：

| 路径                              | 源码消费字段 / 含义                                                                                      |
| --------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `data.head`                       | `acntCamp`、`gameResult`、`roleId`、`heroName` 等；缺 `acntCamp` 时来源认为详情暂不可用                  |
| `data.redTeam` / `blueTeam`       | 队伍汇总、`acntCamp`、`pickHeros[]`；不能默认每队固定 5 个玩家                                           |
| `data.redRoles[]` / `blueRoles[]` | 玩家集合，隐私或对局刚结束时可能残缺                                                                     |
| 玩家 `basicInfo`                  | `isMe`、`roleId`；定位被查询玩家                                                                         |
| 玩家 `battleRecords`              | `usedHero.heroName/heroIcon`、`usedSkin`、`skill.skillIcon`、`finalEquips[]`                             |
| 玩家 `battleStats`                | `gradeGame`、`mvp`、`evaluateIconV3/V2`、`evaluateIcon`、`fightPower`、`addFightPower`                   |
| 玩家 `battleStats` 伤害           | `totalHeroHurtCnt` 对英雄伤害、`totalHurtCnt` 总伤害、`totalBeheroHurtCnt` 对英雄承伤；不能混用          |
| 玩家 `battleStats` 补充           | `joinGamePercent`（来源按比例乘 100）、`ctrlTime`（来源按秒展示）、`killSoldier`                         |
| 玩家五维评级                      | `sabchurthero`、`sabcbattle`、`sabcgrow`、`sabcsurvive`、`sabcKDA`；来源读取小写 `s/a/b/c`               |
| 玩家 `dataBehaviorV2[]`           | `title`、`icon`、`dataCounts[]`；项目内 `name`、`data`、`dataNote`、`dataHighlight`、`dataNoteHighlight` |
| 全场最高标志                      | `maxKill`、`maxHurt`、`maxTower`、`maxMoney`、`maxHeroHurt`、`maxBeheroHurt`；来源按数值真假读取         |

`dataNote` 在来源注释里是排名百分位文字，不是统计值 `data` 的单位。队伍缺人时，源码只以实际返回玩家计算输出占比；这种派生占比不等于完整队伍的远端原始统计。详情字段不足应降级，不能补造玩家或把缺失统计当实测 0。更多旧版线索见第 8 节。[请求][G1]、[详情展示][G21]

### 19.3 C03 主页：`/game/koh/profile`

**请求 J**，来源 `getProfile`：

```json
{
  "targetUserId": "<TARGET_CAMP_ID>",
  "targetRoleId": "0",
  "resVersion": "3",
  "recommendPrivacy": "0",
  "apiVersion": "2"
}
```

来源读取 `data.targetRoleId`，再用字符串比较在 `data.roleList[]` 中找到同 ID 的角色；角色包含 `roleId`、`roleName`、`roleIcon`、`areaName`、`gameLevel`、`gameOnline`、`serverId` 等消费字段。主页摘要位于 `data.head.mods[]`，按 `modId` 选择模块，其段位 / 巅峰资源不是固定在角色对象里。

| `modId`               | 来源读取 / 展示                                                                                                 |
| --------------------- | --------------------------------------------------------------------------------------------------------------- |
| `701` / `708`         | 5v5 / 10v10 段位：`name`，`param1` JSON 内 `rankingStar`                                                        |
| `702`                 | 巅峰：`content` 数值                                                                                            |
| `304`                 | 战斗力：`content` 数值                                                                                          |
| `401` / `408` / `409` | 总场次 / MVP / 胜率：`content`；胜率可能为带 `%` 的文本                                                         |
| `201` / `202`         | 英雄 / 皮肤数量：`content` 为类似“拥有数/总数”的文本                                                            |
| `601`                 | 当前最高战力英雄：`param1` JSON 的 `heroId`、`heroFightPower`、`playNum`、`winRate`；缺战力时来源回退 `content` |

`param1` 在这些模块中是需要另做 JSON 解析的字符串；模块可能缺失，以上映射来自来源读取 / 注释，本次未用登录态复验。[主页摘要][G19]

当前资料模型补充 `game_online`（0 / 1 / 2 / null）与 `game_status`（离线 / 在线 / 游戏中 / 未知），WebUI 与资料指令图片、文本共用该模型。按 `targetRoleId` 匹配角色读取 `gameOnline`，合法的数值零保留为离线，字段缺失或未知码不默认补零。2026-10-08 使用已保存 QQ 登录态查询 `489048724`，真实响应返回整数 `gameOnline=0`，并包含 `onlineTime`、`offlineTime` 与空 `battleId`；在线 / 游戏中映射依照来源代码和用户指定规则，未进行实际上下线切换测试。

后续链路为：营地 ID → `targetRoleId` → 对应角色的 `serverId` / `roleName` → C07 / C11 / C12。`targetRoleId="0"` 是来源默认角色查询；有角色列表不等于已经验证任意跨区战绩切换。在线状态和当前对局线索按资料响应消费，不是好友观战取流协议。

### 19.4 C04 生涯英雄：`/game/profile/herolist`

**请求 J**，来源 `getProfileHeroList`：

```json
{
  "targetUserId": "<TARGET_CAMP_ID>",
  "targetRoleId": "<ROLE_ID>",
  "recommendPrivacy": 0
}
```

这个来源使用主站 JSON；第 7 节旧来源使用表单，两套已实现请求不能合并成“唯一编码”。来源读取 `data.heroList[]`：

| 路径                                     | 源码用途                                 |
| ---------------------------------------- | ---------------------------------------- |
| `basicInfo.heroId`、`basicInfo.title`    | 英雄编号和名称                           |
| `basicInfo.playNum`、`basicInfo.winRate` | 生涯场次与胜率展示；胜率直接按字符串展示 |
| `basicInfo.heroFightPower`               | 战力排序 / 展示                          |
| `honorTitle.type`、`honorTitle.desc`     | 荣耀称号                                 |

来源把它作为赛季常用英雄缺失时的生涯榜降级数据；C05 的字段布局与统计口径不同，不直接拼接场次。[请求][G1]、[英雄榜消费][G8]

### 19.5 C05 我的英雄：`/play/h5getherolist`

**请求 F**，来源 `getGameHeroList`，业务表单：

```text
noCache=0&recommendPrivacy=0&friendUserId=<TARGET_CAMP_ID>
```

响应源码读取：`data.heroList[]`、`data.hasData.heroNum`。

| 英雄字段                 | 用途 / 类型处理                                   |
| ------------------------ | ------------------------------------------------- |
| `heroId`、`name`         | 英雄编号、名称                                    |
| `playNum`、`winNum`      | 场次、胜场；来源用 `Number` 转换                  |
| `winRate`                | 来源注明类似 `"53.8%"` 的已格式化字符串，直接展示 |
| `heroFightPower`         | 原始战力列                                        |
| `skilledLevel`           | 熟练度等级；来源只确认等级 5～8 的文案            |
| `heroTypes` / `heroType` | 定位数组 / 回退文字                               |
| `url` / `heroIcon`       | 图片候选                                          |

来源注释对 `heroFightPower` 的“当前 / 最高”描述存在冲突。本次不确认该字段等于历史最高；该项目最终展示历史最高时实际补取 C06 的 `maxHeroFightPower`，用 `heroId` 关联，只从 C06 补战力和称号，保留 C05 的场次 / 胜率。零场英雄被来源展示层过滤，不能因此宣称服务端只返回玩过的英雄。[请求][G1]、[我的英雄消费][G9]

### 19.6 C06 历史英雄战力：`/hero/getseasonusaullyherolist`

**请求 J**，来源 `getSeasonUsuallyHeroList`：

```json
{ "recommendPrivacy": 0, "seasonId": 0, "roleId": "<ROLE_ID>" }
```

路径里的 **`usaully` 就是源码中的实际拼写**。上游注释称本接口 `seasonId=0` 为历史赛季，`-1` 为当前赛季；更早负数没有得到有效数据。本次未实测，不把这些值扩展成完整分页或历史赛季枚举。它与 C11 的 `seasonId=0` 含义不能直接等同。

来源读取 `data.list[]` 的 `heroId`、`maxHeroFightPower`、`honorTitle.desc.full`；请求注释还列出 `heroFightPower`、`playNum` 等字段。历史称号表示取得历史高点时的称号，不保证当前仍在榜；其场次口径与 C05 不同。[请求][G1]、[历史战力关联][G9]

### 19.7 C07 单英雄详情：`/gametoolbox/hero/record/pagedetails`

**请求 J**，来源 `getHeroRecordDetails`，额外头：

```http
serverId: <TARGET_SERVER_ID>
```

```json
{ "roleId": "<ROLE_ID>", "heroid": 109, "roleName": "<ROLE_NAME>", "h5Get": 1 }
```

`109` 是示例英雄编号，实际从英雄表选择。源码对该入口特别注明：

- 区服 `serverId` 放请求头；上游声称放 JSON 会返回 `heroId=0` 的空壳，业务码仍为 0。
- 英雄键名是 **`heroid`**，请求构造为数值；不要换成 `heroId`。
- `roleId` 明确字符串化；上游声称传数值会返回 `returnCode=1`。
- `roleName` 源码允许空串；目标用户与发起人方法参数用于选账号，不在这个 JSON 内。

响应 `data` 的消费字段：

| 路径                                                                     | 字段 / 用途                                                                                                      |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `heroInfo`                                                               | `SzTitle`、`SzAlias`、`SzHeroType`、`SzBranchRoad`、`newSzHeroPic` / `SzHeroPic`、`skilledTitle`                 |
| `heroInfo.winNum`、`failNum`                                             | 源码将二者相加计算场次和胜率；统计周期不可只凭字段名确认                                                         |
| `heroInfo.bestCount`、`goldCount`、`silverCount`、`mvpCount`、`avgGrade` | 荣誉与平均分展示；上游按近一个月荣誉解释，待复验                                                                 |
| `medalList[]`                                                            | `UserMedalInfo`、`TitleType`；空数组表示本次未读到称号，不一定是接口失败                                         |
| `powerData[]`                                                            | 日期键实际叫 **`data`**、数值键 `value`；源码同日期取最后一点用于展示；上游声称覆盖近 30 天                      |
| `avgPerformance`                                                         | `hurhero`、`survive`、`kda`、`battle`、`grow`；来源按 0～100 画雷达                                              |
| `zjList[]`                                                               | `mapName`、`gametime`、`usedtime`、`gameresult`、KDA、`mvpcnt` / `losemvp`、`grade`、评价图片；上游声称近期 5 场 |
| `isHideMatchDetail`、`isHideMatch`                                       | 来源合并为详情隐藏标记                                                                                           |

单场五维拼写 `hurthero` 与平均五维 `hurhero` 不同；本接口使用百分制展示，C11 / C12 使用来源另一套雷达量纲。`zjList` 不能作为完整英雄历史分页；签名图片 URL 与资源哈希也不一定能直接当普通图片地址下载。[请求][G1]、[字段消费][G4]、[称号消费][G5]

### 19.8 C08 账号皮肤：`/play/h5getheroskinlist`

**请求 F**，来源 `getSkinList`，业务表单同 C05。响应消费层兼容 `response.data` 或顶层本体：

| 路径               | 源码读取字段 / 意义                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| `skinCountInfo`    | `owned`、`totalSkinNum`、`notForSell`、`totalValue`；计数 / 估值摘要，金额单位未在本次确认                   |
| `heroSkinList[]`   | `skinId`、`iBuy`、`szClass`；混有展示项，不能把列表长度当拥有数量                                            |
| `heroSkinConfList` | 按皮肤 ID 索引的全量配置对象；不是数组                                                                       |
| 配置条目           | `iSkinId`、`szTitle`、`szHeroTitle`、`classTypeName`、`classLabel`、`szLargeIcon`、`bigCover`、`szSmallIcon` |
| 价格 / 估值        | `iPrice` 为来源使用的点券原价；`skin_worth` 为来源使用的综合估值，二者不能直接视为同一量纲                   |
| 原皮判定           | 来源按 `Number(isHidden) === 1` 过滤经典原皮；不推广为所有隐藏类型的正式枚举                                 |

来源判定“拥有”的条件是 **存在 `iBuy` 键且 `szClass != null`**，不是 `Boolean(iBuy)`；需要以真实样本对 `skinCountInfo.owned` 复核。`szClass` 有前导空格和全角加号，展示前规范化。缺皮肤按全量配置减拥有集合，不能把官网售卖皮肤总表当账号拥有表。

图片顺序为营地 `szLargeIcon` → 官网同 ID 立绘 → 营地 `bigCover` / `szSmallIcon`；占位图、失效 URL、缺配置和非售卖项需分别处理。上游注释的 956 条 / 823 条只是当时样本，不作为固定数量。[皮肤墙][G6]、[配置目录][G7]、[缺皮肤判据][G10]

### 19.9 C09 核心装备：`/gametoolbox/equip/hero/getherobestequip`

**请求 J**，来源 `getHeroBestEquip`：

```json
{ "heroId": 109 }
```

响应读取 `data.list[]`：`equipId`、`szTitle`、`szIcon`、`szCate`、`szMoney`、`descLabel`、`winRate`、`showRate`；源码注释另提到 `szAttr`。`winRate` / `showRate` 按小数比例乘 100，`szMoney` 被数值化，单位仍按接口样本核对。

这是单件核心装备推荐，不能直接当六件成套出装。上游声称常见 3 件，本次未确认固定数量。数据以英雄为目标但请求仍经过登录账号池；“公共英雄资料”不表示该营地接口免登录。[请求][G1]、[攻略整理][G12]

### 19.10 C10 铭文与技能：`/gametoolbox/hero/getherofringedata`

**请求 J**，来源 `getHeroFringeData`，请求同 C09。**响应没有来源常见的 `returnCode/data` 包装**，消费如下：

```text
root.skillList1 / skillList2 / skillList3
root.RuneSetList[]
  showRate / winRate
  runeList[]
    runeId / num / iLevel / szTitle / szColor / szCate / szCommAttr / szIcon
```

组合胜率 / 出场率按小数比例展示；`num` 为组合中该铭文数量，`iLevel` 为等级。`szTitle` 可能带“5级铭文:”前缀，`szCommAttr` 可能以 `|` 分隔。上游声称通常 3 套，`skillList2/3` 在其样本中为空；这些不是接口固定约束。源码实际攻略展示主要消费铭文，没有解析完整技能 schema。[请求][G1]、[铭文消费][G12]

### 19.11 C11 赛季页：`/game/seasonpage`

**请求 J**，来源 `getSeasonpage`：

```json
{ "recommendPrivacy": 0, "seasonId": 0, "roleId": "<ROLE_ID>" }
```

方法允许 `extraBody` 覆盖，但来源没有据此证明任意新参数受支持。先请求 `seasonId=0` 取得 `data.historyList[]`，再根据条目的 `seasonName` 选择实际 `seasonId` 请求一次。**赛季 ID 不一定等于 S 后面的数字**，不要把 S44 自动转换为 44。

| 路径                                        | 消费字段 / 用途                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `historyList[]`                             | `seasonId`、`seasonName`、`startTime`、`endTime`、`rankInfo`、`masterInfo`；赛季选择与汇总                   |
| `headCard`                                  | `gameCnt`、`winRate` 等赛季头部统计                                                                          |
| `battleStats`                               | `hurtHero`、`survive`、`battle`、`grow`、`kda`；来源画五维，渲染归一化上限取 12000                           |
| `behavior.rankInfo` / `behavior.masterInfo` | `branches[]`、`heros[]`、`gameTrend[]` 等模式统计                                                            |
| `branches[]`                                | `branchName`、`branchType`、`winNum`、`loseNum`、`winRate`、`gameCnt`                                        |
| `heros[]`                                   | `heroId`、`heroName`、`heroIcon` / `heroLandscapeIcon`、`gameCnt`、`winRate`、`heroFightPower`、`honorTitle` |
| `rankInfo.gameTrend[]`                      | `time`、`totalRankStar`、`stars` 等趋势字段；来源按赛季时间窗过滤                                            |

来源指出 `seasonId=0` 的历史摘要可能没有英雄战力 / 称号，具体赛季页才有。趋势可能跨赛季；历史赛季也可能缺趋势和五维。源码的“12000 上限”是展示归一化策略，不是已取得的腾讯单位定义。[赛季表现][G13]、[常用英雄二跳][G8]、[巅峰表现][G14]

### 19.12 C12 对战五维：`/game/getfightdata`

**请求 J**，来源 `getFightData`：

```json
{
  "recommendPrivacy": 0,
  "dateType": 2,
  "roleId": "<ROLE_ID>",
  "roleFriendId": 0,
  "branchType": 0,
  "source": 1,
  "gameBattleType": 10,
  "card": 0
}
```

| 参数             | 来源定义 / 默认                                                   |
| ---------------- | ----------------------------------------------------------------- |
| `dateType`       | `1` 近 30 场、`2` 近 30 天；默认 2                                |
| `gameBattleType` | `10` 巅峰、`2` 5v5、`3` 排位；默认 10                             |
| `branchType`     | `0` 全部、`1` 对抗、`2` 中路、`3` 发育、`4` 打野、`5` 游走        |
| 其他字段         | 固定 `roleFriendId=0`、`source=1`、`card=0`、`recommendPrivacy=0` |

源码读取 `data.battleDataSelf` 的 `winNum`、`loseNum`、`winRate`、`avgScore`、`hurtHero`、`survive`、`battle`、`grow`、`kda`；`winRate` 有字符串展示路径，缺失时来源用胜负场重算。雷达按来源 12000 上限展示；`avgScore` 不应直接当 C07 的平均分同一制度。

一次请求只取一个分路；整体加五路可能要 6 次请求。来源不使用本接口查询任意历史赛季，历史表现改用 C11。**这里 4=打野 / 5=游走，与 C13 梯度榜的 4=游走 / 5=打野正好相反**。[请求][G1]、[排位分路消费][G13]、[巅峰分路消费][G14]

### 19.13 C13 英雄梯度：`/hero/getdetailranklistbyid`

**请求 J**，来源 `getdetailranklistbyid`：

```json
{
  "bottomTab": "",
  "rankId": 0,
  "segment": 3,
  "position": 0,
  "recommendPrivacy": 0
}
```

| 参数                   | 来源映射                                                     |
| ---------------------- | ------------------------------------------------------------ |
| `segment`              | `1` 所有段位、`3` 巅峰 1350+、`4` 顶端排位、`5` 赛事；默认 3 |
| `position`             | `0` 全部、`1` 对抗、`2` 中路、`3` 发育、`4` 游走、`5` 打野   |
| `rankId` / `bottomTab` | 默认 `0` / 空串；其他取值未实现                              |

消费 `data.updateTime`（来源格式化 8 位 `YYYYMMDD`）、`data.list[]` 的 `tRank`、`winRate`、`showRate`、`banRate` 与 `heroInfo.heroName` / `heroCareer` / `heroIcon`。比例乘 100 显示；来源按 T0～T3 分组，未知梯度回退 T3，这是本地展示策略。参数语义来自来源注释 / 映射，后续可对照响应筛选表复验。[请求][G1]、[梯度消费][G15]

### 19.14 C14 大神观战池：`/info/tv/choiceitem`

**请求 J**，来源 `getTvChoiceItems`，请求体 `{}`。来源兼容 `data.tvChoiceItems[]` 或顶层 `tvChoiceItems[]`：

```text
item.tvType == 2
item.battle.battleInfo
  battleID / gameType / heroName / desc
  roleInfo.roleName
  roleInfo.tag[].id / name
item.battle.liveStream.success
item.battle.liveStream.stream.liveStreamUrl
```

只有 `tvType === 2` 且流成功、地址非空的条目被当作对局；`gameType=4` 排位、`14` 巅峰；分路读 `tag.id === 4` 的 `name`。不要把它与 C01 的 `option=4` 巅峰混淆。

来源声称随机返回约 10 场、无已实现的筛选 / 翻页入参，RTMP URL 自带签名且短期有效。插件按分路本地过滤，最终把 URL 交给观战外置服务，不能永久保存为静态播放地址。数量、可用时段、URL 寿命仍需实测。[请求][G1]、[池条目解析][G16]

### 19.15 C15 保活查询：`/user/getcampfriends`

**请求 J**，来源 `keepAlive`，请求体 `{}`，目标账号选择参数用于本地候选登录态。该调用只确认请求能否成功，**来源没有解析返回好友集合，不能据此补出好友字段 schema**。

来源把它当保活只读查询；定期调用能否延长登录态没有本次验证。`expires=0` 不表示永不过期。旧 `/user/refreshweixintoken` 在来源注释中被描述为已下线，只能作为历史线索，不能作为已实现端点。[保活][G1]、[账号续期策略][G22]

## 20. 微信与 QQ 登录接口

### 20.1 微信登录四步

来源完整协议位于 [wechatLogin.js][G2]。本插件已有微信链路；下面补齐来源请求约定，方便复核。

| 步骤           | 方法与完整地址                                                | 请求 / 响应关键字段                                                                                            |
| -------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| L01 SDK ticket | `POST https://ssl.kohsocialapp.qq.com:10001/a/getwxsdkticket` | 无 body；公共登录头 + 大写 UUID `x-log-uid`；检查 `returnCode=0`，读取 `data.sdkTicket`                        |
| L02 出二维码   | `GET https://open.weixin.qq.com/connect/sdk/qrconnect`        | Query：`appid`、`noncestr`、`timestamp`、`scope`、`signature`；读取 `errcode=0`、`uuid`、`qrcode.qrcodebase64` |
| L03 轮询       | `GET https://long.open.weixin.qq.com/connect/l/qrconnect`     | Query：`f=json`、`uuid=<QR_UUID>`；读取 `wx_errcode` 或 `errcode`，以及 `wx_code` 或 `code`                    |
| L04 换营地凭据 | `POST https://ssl.kohsocialapp.qq.com:10001/user/login`       | URL 编码表单，`loginType=wx`、`code`、设备参数 / RSA 设备负载；读取 `data.userId/token/encodeRes`              |

L02 使用 `appid=wxf4b1e8a3e9aaf978`、`scope=snsapi_userinfo`、随机 8 位数字 `noncestr`、秒级时间戳。签名对以下 UTF-8 文本做 SHA-1 并输出十六进制：

```text
appid=<APPID>&noncestr=<NONCE>&sdk_ticket=<SDK_TICKET>&timestamp=<SECONDS>
```

来源严格以数值 `405` 且授权 code 非空判断成功；`402` 过期、`403` 取消、`500` 登录异常，其余状态继续等待。来源轮询间隔 2 秒，会话超时 3 分钟；本插件当前会话 TTL 为 300 秒，这是本地策略差异，不能直接确认服务端寿命。

登录公共头：`Content-Encrypt=""`、`Accept-Encrypt=""`、`NOENCRYPT=1`、`X-Client-Proto=https`、`User-Agent=okhttp/4.9.1`、同会话 `x-log-uid`。L04 另加表单 Content-Type、设备参数及 `specialEncodeParam` 到头中。

### 20.2 微信登录表单与设备 RSA 负载

L04 表单：

| 字段                                               | 来源发送值                                                                                             |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `loginType` / `code`                               | `wx` / 微信轮询取得的授权 code                                                                         |
| `delOldUser`、`lastLoginTime`、`lastGetRemarkTime` | 字符串 `"0"`                                                                                           |
| `key1`                                             | 新生成 32 位去横线 UUID                                                                                |
| 客户端参数                                         | `cChannelId` 到 `tinkerId`，同 18.2 的设备 / 游戏版本参数；登录基础版本为 `10.111.0323` / `2057957801` |
| `specialEncodeParam`                               | 下方设备 JSON → UTF-8 → RSA-PKCS#1 v1.5 分块 → 拼接密文 → Base64                                       |

来源设备 JSON 字段如下，保持真实构造而非推定必填：

```json
{
  "timestamp": 0,
  "nonce": ":<NONCE_UUID>:<TIMESTAMP_MS>",
  "cDeviceId": "<DEVICE_UUID>",
  "deviceid": "<DEVICE_UUID>",
  "cDeviceImei": "<DEVICE_UUID_FIRST_15>",
  "cDeviceMac": "02:00:00:00:00:00",
  "cDevicePPI": 480,
  "cDeviceScreenWidth": 1080,
  "cDeviceScreenHeight": 2400,
  "cDeviceBrand": "OnePlus",
  "cDeviceModel": "PHK110",
  "cDeviceMem": 12884901888,
  "cDeviceCPU": "SM8650",
  "cSystemVersionCode": "34",
  "cDeviceNet": "WIFI",
  "cDeviceSP": "China Mobile",
  "cDeviceOaid": "<DEVICE_UUID>",
  "deviceLevel": 3,
  "px": 0,
  "py": 0,
  "wifi_ssid": "unknown",
  "wifi_mac": "02:00:00:00:00:00"
}
```

`timestamp=0` 只是占位，实际为当前毫秒；`nonce` 和设备 UUID 独立生成。RSA 公钥与 18.3 相同，1024 位 / PKCS#1 v1.5 的明文单块上限 117 字节；分块按 **UTF-8 字节**，不是按字符，密文块拼接后才整体 Base64。

登录成功需同时检查 HTTP、`returnCode=0`、`data.userId` 与 `data.token`。`data.encodeRes` 恢复 `userKey`；来源另外保存 `accessToken`、`refreshToken`、`appOpenid`、`avatar` / `bigAvatar` / `icon`、`nickname` / `snsnickname` / `userName`、`sex`、`expires`、`uin`、`userSig`、`realRegisterTime`。这些是消费字段，不保证所有平台齐全；IM 服务需要的凭据不能从普通查询字段凭空生成。[登录实现][G2]

### 20.3 QQ 浏览器授权与 YSDK 换票

**L05 浏览器授权入口：**

```http
GET https://openmobile.qq.com/oauth2.0/m_authorize?client_id=1105200115&scope=all&redirect_uri=auth%3A%2F%2Ftauth.qq.com%2F&style=qr&response_type=code
```

来源使用独立浏览器上下文，手机 UA 在页面内取二维码，等待页面跳转到 `auth://tauth.qq.com/?code=...`，拦截取得 code。它没有提供可替代整套浏览器授权的独立“获取 QQ 二维码 / 轮询”HTTP 协议。不要把不同会话的二维码、Cookies 和授权 code 拼起来。[QQ 会话实现][G3]

**L06 YSDK 换票：**

```http
POST https://ysdk.qq.com/cmd/QQCodeLogin?
Content-Type: json
Auth-Secret-ID: ysdk
Auth-Request-Time: <SECONDS>
Auth-Secret-Digest: <HMAC_BASE64>

{"appID":"1105200115","loginCode":"<QQ_AUTH_CODE>"}
```

`Content-Type: json` 是来源实际发送值。签名文本为以下各行用 LF 连接，最后一行是与发送 body 完全相同的紧凑 JSON：

```text
POST
/cmd/QQCodeLogin
json
ysdk
<SECONDS>
<EXACT_JSON_BODY>
```

源码使用 HMAC-SHA256，输出 Base64；HMAC key 是该公开源码中的协议常量 `yyb@cloud_game:CQ8FA#`，并非本项目保存的真实账号 token / 用户密钥。这里记录来源值，不保证它以后仍有效。

响应检查外层 `code=0` 和 `data.ret=0`；读取 `data.accessToken`、`openID`、`payToken`、`refreshToken`、`expiresIn`。其中 `openID` 的大小写与下一步表单的 `openId` 不同。[换票实现][G3]

### 20.4 QQ 的营地 `openSdk` 登录 / 重新登录

仍为 L04 的 `POST /user/login`，头同公共登录头，表单 Content-Type 为 `application/x-www-form-urlencoded; charset=UTF-8`：

```text
loginType=openSdk
accessToken=<YSDK_ACCESS_TOKEN>
openId=<YSDK_OPEN_ID>
payToken=<YSDK_PAY_TOKEN>
delOldUser=0
key1=<NEW_UUID_HEX>
lastLoginTime=0
lastGetRemarkTime=0
specialEncodeParam=<RSA_DEVICE_PAYLOAD>
```

同时发送设备 / 渠道字段。此分支在来源中使用 `cClientVersionCode=2057971306`、`cClientVersionName=10.114.0826`、Android `35` / `15`、`tinkerId=2057971306_64_0`，与微信 / 默认查询版本不同；来源仍复用微信的设备 RSA 负载构造，不能将所有常量统一覆盖为一个版本。

源码支持保存的 `accessToken` + `appOpenid` / `openId` 重登，`payToken` 可传空串；“空串可用”和三件套有效期是上游经验，本次未实测。重登通过同一 `/user/login` 换新营地 token，来源记录旧 token 会被作废，需及时更新账号池并协调进行中的请求。不要把它称为独立 refresh 接口，也不要从 `expires=0` 推断永不过期。[QQ 登录 / 重登][G3]、[续期任务][G22]

## 21. 官网与第三方公开接口

本节均不使用营地账号 token / `userKey`。实际验证的是公开数据的有限只读请求，完整记录见 24.2。

### 21.1 P01 官网英雄表

```http
GET https://pvp.qq.com/web201605/js/herolist.json
```

顶层为 JSON 数组。源码常用 `ename`、`cname`、`skin_name`；本次样本还确认 `id_name`、`title`、`new_type`、`hero_type`、`moss_id`、`roles`、`extra_cold_lane`。`ename` 用于其他英雄接口；`skin_name` 是 `|` 分隔的名称列表，更新可能落后于新皮肤，不能替代完整皮肤目录。其类型 / 分路枚举本次未全面解释。[请求][G1]、[皮肤命令][G23]

### 21.2 P02 官网英雄与皮肤总表

```http
GET https://pvp.qq.com/zlkdatasys/heroskinlist.json
```

顶层 JSON 对象：`yxlb20_2489` 为英雄数组，`pflb20_3469` 为皮肤数组。源码字段映射与本次响应核对：

| 字段                    | 英雄数组用途                                 | 皮肤数组用途                                         |
| ----------------------- | -------------------------------------------- | ---------------------------------------------------- |
| `yxid_a7`               | 英雄编号                                     | —                                                    |
| `yxmclb_9965`           | 英雄名                                       | 所属英雄名                                           |
| `yxpymc_4614`           | 资料页拼音路径名                             | —                                                    |
| `fllb_2105`、`fzy_8576` | 主 / 次定位（来源映射）                      | —                                                    |
| `yxtxlb_8443`           | 头像图                                       | 本次也确认此键，语义按条目核对                       |
| `fmb1lb_5300`           | 英雄封面                                     | 本次也确认此键，具体图片用途按内容确认               |
| `sxsjlb_1516`           | 上线日期                                     | 上线日期；可能为空或未来日期，来源按 `YYYYMMDD` 处理 |
| `yjhjsl_5003`           | 简介                                         | 简介                                                 |
| `pfidlb_3934`           | —                                            | 皮肤 ID                                              |
| `pfmclb_7523`           | —                                            | 皮肤名                                               |
| `pfpzlb_3289`           | —                                            | 品质                                                 |
| `hqfs_8609`             | —                                            | 获取方式                                             |
| `fmlb_4536`             | 本次确认有此键，来源攻略不使用它作英雄主封面 | 皮肤横版封面                                         |
| `pfgift_4455`           | —                                            | 来源映射为礼赠信息，具体值域待确认                   |

这些带后缀字段可能随官网数据模板改变；源码 `pvpSkinImage.js` 有按值形态回退识别的逻辑。皮肤 ID 可与 C08 的 `iSkinId` 关联，这是来源实现使用的关联规则，本次未用登录账号逐项复验。官网总表不包含账号拥有状态，也不能保证包含所有经典原皮。[字段映射][G12]、[皮肤图源][G17]、[上线日历][G18]

### 21.3 P03 官网装备表

```http
GET https://pvp.qq.com/web201605/js/item.json
```

UTF-8 JSON 数组，字段：`item_id`、`item_name`、`item_type`、`price`、`total_price`、`des1`。来源用 `item_id` 建索引、`item_name` 映射出装名、`total_price` 显示价格；`des1` 可能带 HTML，展示前处理。不要按英雄 HTML 的 GB18030 解码这张表。[请求][G1]、[装备映射][G12]

### 21.4 P04 爆料站表

```http
GET https://pvp.qq.com/zlkdatasys/data_zlk_xpflby.json
```

来源实现了 `getHeroXpflby` 请求方法，但本快照没有找到业务调用方 / 字段解析，因此此前只能确认地址。本次请求补充确认顶层键 `ygzlby_00`、`ygzyxdzbjt01_48`、`ymtitle_d2`、`pcblzlby_c6`、`yddblzlby_24`；数组样本包括：

| 数组           | 本次样本字段                                                                                                                                                                                                    |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ygzlby_00`    | `YXMC_8f`、`lbytphb_0c`、`ygzlbytpsb_2c`、`ygzlbyurl_af`、`lbyrq_e5`、`lbycsficon_9b`、`lx_fe`、`yxbllx_c2`                                                                                                     |
| `pcblzlby_c6`  | `lbyrq_e5`、`pcblzlbytp_8e`、`pcblzlbybt_d3`、`pcblzlbyxqydz_c4`、`sxsj_24`、`lbycsficon_9b`、`pcblzlbyfbt_0e`、`pcblzlbydt_8b`、`pfld_45`、`pfbq_71`、`lx_fe`、`yxbllx_c2`、`sfxs_89`、`tyfzzbq_dd`、`sfsx_5e` |
| `yddblzlby_24` | `lbyrq_e5`、`yddblztp_af`、`yddblzbt_90`、`yddblzjbxqydz_d7`、`lbycsficon_9b`                                                                                                                                   |

这里确认的是字段存在性，日期、上线 / 体验服标记、图片和链接的具体含义尚未建立稳定映射，不依据缩写创造业务契约。皮肤上新功能在来源最终使用 P02 的上线日期，不依赖这个表。[地址][G1]、[上新实现][G18]

### 21.5 P05 官网英雄资料 HTML

```http
GET https://pvp.qq.com/web201605/herodetail/<PINYIN>.shtml
```

`PINYIN` 从 P02 英雄条目的 `yxpymc_4614` 读取；来源提醒不要用英雄数字 ID 代替。响应字节按 **GB18030** 解码。本次确认页面中有出装与技能标记，完整解析仍受 HTML 改版影响。

| 页面内容                 | 来源提取规则                                                                  |
| ------------------------ | ----------------------------------------------------------------------------- |
| 成套出装                 | `data-item="<装备ID>\|..."` 配合 `class="equip-tips"`；装备名由 P03 补齐      |
| 最佳搭档 / 压制 / 被压制 | 按 `hero-f1 fl` 小标题分段，`data-src` 取英雄 ID，`hero-list-desc` 取对应说明 |
| 技能图标                 | `skill-u1` 中图片，过滤空占位                                                 |
| 技能说明                 | `skill-name` 的 `<b>` / `<span>` 与 `skill-desc`；空标题 / 空内容过滤         |

这是 HTML 页面读取，仍需要解析页面，但已有字段规则可复用；它不是官方结构化攻略 JSON API。[页面请求][G1]、[解析器][G12]

### 21.6 P06 / P07 官网资讯列表与正文

**P06 列表：**

```http
GET https://apps.game.qq.com/cmc/cross
```

| Query                       | 来源值                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------- |
| `serviceId`、`source`       | `18`、`web_pc`                                                                        |
| `filter`、`sortby`、`logic` | `channel`、`sIdxTime`、`or`                                                           |
| `typeids`、`withtop`        | `1,2`、`yes`                                                                          |
| `chanid`                    | 默认 `1762` 版本公告；来源另映射 `1760` 热门、`1761` 新闻、`1763` 活动、`1766` 体验服 |
| `limit`、`start`            | 默认 `30`、`0`；偏移式分页                                                            |
| `exclusiveChannel`          | `4`                                                                                   |
| `time`                      | 当前秒级时间戳字符串                                                                  |
| `exclusiveChannelSign`      | 下述 MD5 十六进制签名                                                                 |

```text
md5("234ce0aef3020cb83887883877b64869" + "web_pc" + "18" + <SECONDS>)
```

这里的 token 是来源记录的官网前端公开常量，不是营地账号 token。响应检查 `status=0`，读取 `data.items[]`、`data.total`；消费 `iId` / `iNewsId`、`sTitle`、`sIdxTime` / `sCreated`、`sTagInfo`。本次也确认 `iTopPos`、`sUrl`、`sRedirectURL` 等键，但没有全面验证置顶排序与跳转语义。

来源按标题 / 可读标签本地排除体验服，并注明 `tagids` 在其测试中不生效，不能将过滤成功归功于服务端参数。`sTagInfo` 的来源解析支持类似 `2536|图文,610|内容形式` 的分隔文本。设置 `withtop=yes` 时不能假定响应数组长度始终等于 `limit`。

**P07 正文：**

```http
GET https://apps.game.qq.com/wmp/v3.1/public/searchNews.php?p0=18&source=web_pc&id=<NEWS_ID>
```

来源及本次响应形态为 `var searchObj={...};`，先剥变量赋值外壳和末尾分号，再 JSON 解析，**不要执行响应脚本**。检查 `status=0`，读取 `msg.sTitle`、`msg.sIdxTime` / `msg.sCreated`、`msg.sContent`；正文是 HTML，渲染前清洗，图片可能为协议相对地址 / HTTP 地址。列表也包含视频，来源没有实现视频 `search.php` 的完整协议，不能将 P07 泛化为全部视频正文接口。[列表 / 正文请求][G1]、[公告筛选与清洗][G24]

### 21.7 P08 第三方称号战力线：sapi.run

```http
GET https://www.sapi.run/hero/select.php?hero=<URL_ENCODED_HERO_NAME>&type=<REGION>
```

| `type` | 来源用途 |
| ------ | -------- |
| `aqq`  | 安卓 QQ  |
| `awx`  | 安卓微信 |
| `iqq`  | iOS QQ   |
| `iwx`  | iOS 微信 |

来源无额外鉴权头，要求 JSON `code === 200` 且 `data` 非空，读取 `msg` 作为接口提示。响应与本次成功样本确认的 `data` 字段：`uid`、`name`、`alias`、`platform`、`photo`、`province`、`provincePower`、`city`、`cityPower`、`area`、`areaPower`、`guobiao`、`stamp`、`updatetime`。

此处战力是来源用来展示各地 / 国服称号门槛的数据，**不是 C05 / C06 的某个玩家英雄战力**；`uid` 不应未经验证当营地 ID 使用。数值字段来源用 `Number` 转换，时间单位本次未确认。`hero` 用完整英雄名，元流之子形态来源用半角括号全名，如 `元流之子(法师)`。

来源并发查询四区，允许部分失败；接入时保留区服键和缺失项，不能用 0 伪装失败区域。本次只验证“妲己 / aqq”一条成功请求，不保证全部英雄与四区都可用。它是第三方数据，更新时效与稳定性需要单独处理。[请求][G1]、[战力命令][G25]

### 21.8 静态图片资源与 CDN

| 来源资源            | URL 模板 / 读取方式                                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 英雄方形图          | `https://game.gtimg.cn/images/yxzj/img201606/heroimg/<HERO_ID>/<HERO_ID>.jpg`                                                       |
| 装备图              | `https://game.gtimg.cn/images/yxzj/img201606/itemimg/<ITEM_ID>.jpg`                                                                 |
| 技能图              | `https://game.gtimg.cn/images/yxzj/img201606/heroimg/<HERO_ID>/<HERO_ID><INDEX>.png`；具体图序优先用 HTML 返回 URL                  |
| 旧式皮肤大图        | `https://game.gtimg.cn/images/yxzj/img201606/skin/hero-info/<HERO_ID>/<HERO_ID>-bigskin-<SEQ>.jpg`；来源先确认皮肤名 / 序号匹配再用 |
| 营地英雄特写        | `https://game-1255653016.file.myqcloud.com/battle_skin_1250-326/<HERO_ID>00.jpg`                                                    |
| 皮肤立绘 / 品质角标 | C08 配置里的 `szLargeIcon` / `bigCover` / `classLabel`，以及 P02 的 `fmlb_4536`；不拼未知哈希                                       |
| QQ 用户头像         | `https://q1.qlogo.cn/g?b=qq&s=<SIZE>&nk=<QQ_NUMBER>`；仅对真实数字 QQ 标识使用                                                      |
| QQ 群头像           | `https://p.qlogo.cn/gh/<GROUP_ID>/<GROUP_ID>/<SIZE>`；QQ 官方 OpenID 不能直接代替数字 QQ                                            |

腾讯云图片 URL 在来源中可带 `imageMogr2/thumbnail/1400x/format/jpg/quality/85` 等处理参数；这是特定 CDN 图源的用法，不能加到所有图片域名上。图片资源未在本次逐张请求验证，路径模板可作为回退，实际响应 URL 优先。[图片映射][G12]、[皮肤图源][G17]、[英雄头像][G9]、[QQ 头像工具][G31]

## 22. 观战与营地消息外置服务

### 22.1 服务边界、配置与账号传递

这些路径是来源作者的服务协议，**不是 `kohcamp.qq.com` 的腾讯 API**。公开仓库只有客户端，README 明确服务端另外分发；本次没有下载服务包、调用私人服务、开播或发送消息。[来源说明][G28]

- 观战地址用 `watchApiUrl`，播放页面对外地址用 `watchPublicUrl`；消息地址用 `campImApiUrl`。分发地址 `distUrl` 与这些业务地址用途不同。
- 上游最新业务代码说明观战控制端默认 `127.0.0.1:8898`，播放端 8899；但适配版根 `config.yaml` 仍写 `watchApiUrl=127.0.0.1:8899`。这是快照内的配置差异，实际部署应检查控制端，不能把根配置当正确协议依据。
- `GET /api/status` 在观战两个端都可能存在；来源用控制端独有的 `GET /api/rooms` 探测。仅 status 成功不表示能调用好友 / 开播。
- IM 基址默认 `http://127.0.0.1:8900`。相同 `/api/friends` 路径在 IM 和观战服务含义 / 入参不同。
- 客户端普通业务请求没有发送 `Authorization`。服务端要求认证时需要兼容认证接入，不能把分发 Bearer token 自动当业务凭据，也不能把“关闭公网认证”当移植方案。

远端账号上报的客户端协议：

```http
POST <WATCH_OR_IM_BASE>/api/accounts
Content-Type: application/json

{"accounts":{"<LOGIN_CAMP_ID>":{"userId":"<LOGIN_CAMP_ID>","token":"<TOKEN>","userKey":"<USER_KEY>","encodeRes":"<ENCODE_RES>","isGlobalDefault":true}}}
```

该 JSON 是结构示意，实际源码发送的是完整可用全局账号对象，可能还含 `userSig`、`uin` 等字段。源码注释称服务端只放内存 / 有 TTL，但服务端缺失，本次无法核实保存行为或 TTL。来源上报按基址 + 账号指纹节流，未改变时至少间隔 60 秒，token 指纹变时立即上报，本地回环地址通常跳过。

适配版运行时对 `remoteAccounts.js` 加入 `remoteAccountAllowedUrls` 完整地址允许列表，并对账号 POST 禁止重定向；默认空列表。这个限制由 [services/runtime.py][G27] 与 [remote-policy.mjs][G26] 实现，不能仅看未修改的 `engine/upstream` 就认为适配版会默认外传凭据。[账号上报客户端][G32]

### 22.2 W 系列：观战客户端协议

所有 body 为 JSON，通常超时 15 秒，开播超时 60 秒。来源读取 `ok` / `error` / `code`，并未把 HTTP 状态成功当充分成功条件。[观战客户端][G33]

| 编号 | 方法 / 路径               | 请求参数                                                                         | 来源消费响应                                                                   |
| ---- | ------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| W01  | `GET /api/status`         | 无                                                                               | `ok`、`accounts`；状态探测；字段完整性未知                                     |
| W02  | `GET /api/rooms`          | 无                                                                               | `ok`、`rooms[]`；控制端探测 / 在播列表                                         |
| W03  | `GET /api/friends`        | 可选 Query `watchers=<逗号分隔登录营地账号ID>`                                   | `ok`、`playing[]`、`total`、`online`、`free`、`friendCampIds[]`                |
| W04  | `POST /api/start`         | 好友坐标或 `rtmpUrl`，见下文                                                     | `ok`、`url`、`rid`、`pending`、`reused`；失败 `code=no-account` / `occupied[]` |
| W05  | `POST /api/stop`          | `{owner:<发起人标识>}` 或 `{rid:<房间ID>}`；全停 `{owner:"*"}`                   | `ok`、`stopped`、`error`                                                       |
| W06  | `POST /api/hint/remember` | `groupId`、`battleID`、`campId`、`nick`、`watcher`、`owners`、`userID`、`roleId` | 保存开播提示坐标；客户端未解析完整成功 schema                                  |
| W07  | `GET /api/hint/latest`    | Query `group`，可选 `nick`                                                       | `ok`、`hint`；提示坐标                                                         |
| W08  | `POST /api/accounts`      | `{accounts:{<营地ID>:<账号对象>}}`                                               | `ok`、`error`；账号上报                                                        |

W03 的 `playing[]` 消费字段：`watcher`、`owners[]`、`battleId`、`userId`、`roleId`、`campId`、`nick` / `campNick`、`avatar`、`jobName`、`startTs`、`canWatch`。`watcher` 是有好友关系的请求账号，`owners` 是可见账号范围；`free` 是空闲账号数，与 `canWatch=true` 的对局条数不同。

好友开播 W04：

```json
{
  "watcher": "<LOGIN_CAMP_ID>",
  "owners": ["<LOGIN_CAMP_ID>"],
  "battleID": "<SERVICE_BATTLE_ID>",
  "userID": "<FRIEND_USER_ID>",
  "roleId": "<FRIEND_ROLE_ID>",
  "nick": "<DISPLAY_NAME>",
  "owner": "<BOT_USER_ID>"
}
```

保留 W03 的返回值类型；模板中的字符串只是占位。注意 W03 返回 `battleId/userId`，W04 发 **`battleID/userID`**；取流 `userID`、轮询 `roleId`、玩家营地 `campId` 不应互换。账号被占时来源先要求确认，之后另加 `replace=true` 重试；空 owner 不发停止请求。`owner` 是来源业务归属标识，不是腾讯营地鉴权用户。

大神直连 W04：`{"rtmpUrl":"<C14_SIGNED_STREAM_URL>","nick":"<NAME>","owner":"<BOT_USER_ID>"}`；成功后服务返回专属房间 URL，页面按播放基址拼接 `/r/<RID>/`。源码提到播放端 `/api/record/*`，但没有这些端点的完整请求构造，**不补写录制接口 schema**。[观战调用][G33]、[提示写入][G34]、[控制端探测][G32]

### 22.3 I 系列：营地消息客户端协议

来源 [campImClient.js][G35]，默认 JSON 请求，普通超时 15 秒，好友 30 秒，发送 20 秒；客户端在调用前可能上报远端账号。

| 编号 | 方法 / 路径            | 请求参数                                                            | 来源消费响应                                                      |
| ---- | ---------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------- |
| I01  | `GET /api/status`      | 无                                                                  | `ok`、`clients[]`、`queue.length` / `queue.lastId`、`accounts` 等 |
| I02  | `GET /api/messages`    | Query `since=<上次消息游标>`，默认 0                                | `ok`、`messages[]`、`lastId`                                      |
| I03  | `GET /api/friends`     | Query `selfUserId=<自己已登录营地ID>`                               | `ok`、`friends[]`、`total`；来源说明只返回在游戏里的好友          |
| I04  | `POST /api/send`       | `selfUserId`、`toUserId`、可选 `toRoleId` / `fromRoleId`、`message` | `ok`，失败 `error` / `code` / `raw`                               |
| I05  | `POST /api/connect`    | `{userIds:[<营地ID>,...]}`                                          | `ok` / `error`；启动指定账号连接                                  |
| I06  | `POST /api/disconnect` | `{userIds:[<营地ID>,...]}`                                          | `ok` / `error`；停止指定账号连接                                  |
| I07  | `POST /api/accounts`   | 同 W08，但基址是 IM 服务                                            | `ok` / `error`                                                    |

源码对 I01 的 `clients[]` 读取 `userId`、`nickname`、`state`，以 `state === "online"` 计连接在线数。I02 消息读取 `id`、`selfUserId`、`fromUserId`、`fromRoleId`、`fromRoleName`、`fromRoleIcon`、`fromRoleDesc`、`text`、`raw.toRoleId`；具体字段可缺失。I03 好友读取 `userId`、`roleId`、`nick` / `campNick`、`avatar`、`jobName`、`battleId`。好友列表序号是本地映射，不是可发送的营地用户 ID。[好友 / 发送消费][G36]、[轮询 / 回复消费][G37]

I04 请求模板：

```json
{
  "selfUserId": "<OWN_CAMP_ID>",
  "toUserId": "<FRIEND_USER_ID>",
  "toRoleId": "<FRIEND_ROLE_ID>",
  "fromRoleId": "",
  "message": "<TEXT>"
}
```

来源 IM 需要账号拥有者约束，查询与发送入口限制私聊；不是用全局公共查询账号任意收发别人的消息。消息 `lastId` 是游标，不能当队列数量；数量读 `queue.length`。服务重启可能使 `lastId` 回退，来源重置游标；WebSocket 重放可分配新 ID，需要额外消息指纹去重。公开源码没有 IM WebSocket 地址、握手、帧结构或腾讯发送签名，本次无法整理为无需服务端的直连协议。

## 23. 共享库与服务包分发接口

### 23.1 SVC 系列：共享绑定库

基址 `shareApiUrl`，JSON body，鉴权为 `Authorization: Bearer <SHARE_TOKEN>`，`Content-Type: application/json`。这里共享的是用户标识与营地 ID 绑定，**不是共享营地账号 token**。[共享客户端][G38]

| 编号  | 方法 / 路径               | body                                                          | 消费 / 成功判断                                                        |
| ----- | ------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------- |
| SVC01 | `POST /api/v1/bind/query` | `{qq:<用户标识>,since:<上次更新时间，默认0>}`                 | `campIds[]`、`current`、`updatedAt`，或 `unchanged=true` / `updatedAt` |
| SVC02 | `PUT /api/v1/bind`        | `{qq:<用户标识>,campIds:[<营地ID>,...],current:<当前营地ID>}` | 来源按 HTTP 成功判断，未解析写入响应结构                               |
| SVC03 | `DELETE /api/v1/bind`     | `{qq:<用户标识>}`                                             | 同上；是 DELETE JSON body，不是 query                                  |

`current` 是选中的营地 ID 字符串，**不是数组下标**；不在 `campIds` 中时来源回退第一个。`since` 为来源缓存的 `updatedAt` 数值，具体时间单位未从缺失服务端确认。查询 404 表示没有共享记录；401 无效令牌、403 吊销、429 频控。读超时 1500ms，写 / 探测 5000ms，这是客户端设置。

`qq` 名字来自上游数字 QQ 绑定设计。QQ 官方 OpenID 与数字 QQ 是否可在该服务里互通没有公开服务端证明，不能自行承诺跨机器人 / 跨平台身份等价。

### 23.2 ADM 系列：共享库管理

同共享基址，鉴权头 **`X-Admin-Secret: <ADMIN_SECRET>`**，与客户端 Bearer token 分开。来源只在管理员命令使用。[管理客户端][G39]

| 编号  | 方法 / 路径                        | 请求                                         | 消费响应                                                            |
| ----- | ---------------------------------- | -------------------------------------------- | ------------------------------------------------------------------- |
| ADM01 | `POST /api/v1/admin/tokens`        | JSON `{name:<接入方备注>}`，默认“本机机器人” | 新接入令牌；来源随后读取 `token`，其他完整字段未确认                |
| ADM02 | `GET /api/v1/admin/tokens`         | 无 body                                      | `clients[]` 的 `id`、`name`、`enabled`、`tokenPrefix`、`lastSeenAt` |
| ADM03 | `DELETE /api/v1/admin/tokens/<ID>` | 路径为接入方 ID                              | HTTP 成功；404 找不到；401 / 403 管理密钥失败                       |
| ADM04 | `GET /api/v1/admin/stats`          | 无 body                                      | 源码整体读取统计对象，没有完整字段 schema                           |

签发超时 8 秒，其他管理探测通常 5 秒。默认管理密钥、接入令牌与实际服务地址不在此文档记录。公开仓库没有共享库服务端，不能从客户端接口直接推断数据库结构、令牌作用域或默认限额。

### 23.3 D 系列：外置服务包分发

基址 `distUrl`，`Authorization: Bearer <DIST_TOKEN>`。源码中的包名为 `watch`（观战）与 `im`（消息），不是 npm 包名；接入令牌与营地账号 token、共享库 token 各自独立。[分发客户端][G40]

| 编号 | 方法 / 路径                            | 参数                                         | 消费响应                                         |
| ---- | -------------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| D01  | `GET /api/v1/packages/<NAME>/latest`   | 路径包名；通常超时 10 秒                     | JSON `sha` 必须非空，另读取 `size`、`sha256`     |
| D02  | `GET /api/v1/packages/<NAME>/download` | 可选 Query `sha=<选定版本>`；默认超时 180 秒 | 二进制包；响应头 `x-gok-sha` 或请求 sha 作为版本 |

401 无效令牌、403 吊销、404 没有该包、429 频控。这些是服务分发客户端可见约定；没有实际分发地址 / 令牌 / 服务端源码，无法验证下载格式和服务端行为。文档整理不代表安装这些包。

### 23.4 扫描到但未纳入业务接口的地址

- `registry.npmmirror.com` 等地址用于安装 Node 依赖，不提供王者数据。
- `utils/http.py` 有 `POST https://ttwid.bytedance.com/ttwid/union/register/` 的匿名访客 Cookie 辅助方法，源码 body 包含 `aid=1768`、`union=true`、`needFid=false`、`region=cn`、`service=www.ixigua.com`、`cbUrlProtocol=https` 与 `migrate_info`。本快照未找到业务调用方，它不是王者接口，也不是已接入抖音数据 API；本次未请求。[HTTP 辅助][G41]
- `/info/listinfov2`、`/user/refreshweixintoken` 仅在说明 / 注释出现，没有本快照可复用的有效请求实现；不把它们列为可用接口。
- QQ 官方消息发送复用 AstrBot 宿主 / 可选卡片插件，不在本项目里定义新的腾讯官方机器人 HTTP API。[适配边界][G28]

## 24. 接入建议与本次验证结果

### 24.1 与本插件当前架构的对照

这里只记录后续可复用位置，本次没有实现新功能或修改账号策略。

| 能力                                          | 当前基础                                         | 后续需要补齐                                                                |
| --------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------- |
| C01 / C02 / C03 / C11                         | `CampDataApi` 已有 JSON 请求；详情已带对局坐标   | 对照新消费字段、详情 `friendUserId` 的必要性、赛季二跳与隐私差异            |
| C04 / C06 / C07 / C09 / C10 / C12 / C13 / C14 | 可复用 `CampClient` 的主站鉴权与账号池           | C07 需增加额外请求头能力；C10 接受无 `data` 包装；其余补业务模型            |
| C05 / C08                                     | 当前查询客户端固定主站 + JSON                    | 增加受控腾讯游戏域名 / 表单模式，换号时重新构造含账号凭据的表单             |
| 微信登录                                      | 已有 `CampLoginManager`、RSA / XXTEA、登录态存储 | 保留本插件既有实现，按真实问题比较设备负载 / 版本，避免整体替换             |
| QQ 登录 / 重登                                | 当前产品只提供微信扫码                           | 需要独立浏览器会话、YSDK 签名、账号归属和新旧凭据更新流程                   |
| 官网表 / 公告 / 攻略                          | `HttpClient` 与内置英雄表可作为基础              | 公共 GET / GB18030 / 赋值外壳解析、字段索引和 HTML 清洗；按需求决定缓存策略 |
| 第三方战力                                    | 当前 README 声明营地直连，无第三方数据依赖       | 若以后引入，应明确标注第三方来源、时效、部分失败和功能边界                  |
| 观战 / IM / 共享                              | 当前插件没有这些外置服务组件                     | 只有公开客户端约定；服务授权、完整协议与功能设计仍缺失                      |

建议优先考虑无需新增私人服务的英雄详情、我的英雄 / 历史最高战力、皮肤资料、分路表现、梯度、攻略与公告。这个顺序是开发参考，不代表已经确认产品需求。

后续有意义的验证包括：请求体精确键名和类型、`serverId` 的头位置、账号切换时表单凭据一致、不同分路枚举分开、带 / 不带 `returnCode/data` 的响应、各隐私开关、空角色与空壳、来源统计口径和单位。接口资料能减少重新探索请求协议的工作，**不能免除有效登录态、权限、线上可用性和返回数据验证**。

### 24.2 2026-10-08 本次只读实测

通过有限公开 GET 请求核对响应形态，没有使用本插件保存的营地凭据。JSON 表的 Content-Type 本次多为 `application/octet-stream`，不能仅凭这个头拒绝解析 JSON。数量是当日样本，不能写死在实现中。

| 入口              | HTTP / 业务结果 | 本次确认范围                                                                                    |
| ----------------- | --------------- | ----------------------------------------------------------------------------------------------- |
| P01 英雄表        | 200             | UTF-8 JSON 数组，133 条；字段见 21.1                                                            |
| P02 英雄 / 皮肤表 | 200             | 对象，两组数组；133 个英雄、828 条皮肤；21.2 的主要映射键存在                                   |
| P03 装备表        | 200             | UTF-8 JSON 数组，115 条；6 个字段与来源一致                                                     |
| P04 爆料表        | 200             | 对象；三个数组样本条数 543 / 542 / 545；结构键见 21.4，业务语义未全面验证                       |
| P05 英雄 HTML     | 200             | 使用 P02 返回的拼音请求；GB18030 可解码，含 `data-item` 和 `skill-name` 标记；未测试所有英雄    |
| P06 资讯列表      | 200，`status=0` | `chanid=1762`、`start=0`、`limit=1`、公开签名请求成功；`data.items/total` 及常用字段存在        |
| P07 单条正文      | 200，`status=0` | 使用上述列表第一项 `iId`；`var searchObj=` 外壳、`msg.sTitle/sContent/sIdxTime/sCreated` 可解析 |
| P08 第三方战力    | 200，`code=200` | 正确英雄名“妲己” + `type=aqq`；响应字段见 21.7；其他大区未测                                    |

本次没有把公告全文、第三方整表、玩家数据或任何登录凭据保存到仓库；只保存协议说明与以上验证结论。源码中的旧计数（如 132 英雄、121 装备、816 皮肤）与本次结果不同，已按各自验证日期区分。

### 24.3 未验证部分与文档核对

- C01～C15 在这次任务中未用真实登录态请求，微信 / QQ 扫码与重登也未执行；第 14 节的既有实测保留其原日期和范围。
- 观战、IM、共享库、分发服务没有真实联调；没有发营地消息、开播、写共享绑定、签发 / 吊销令牌或下载服务包。
- 参数“必填性”、平台权限、隐藏字段、完整响应 schema、历史覆盖、限流阈值与签名有效期，没有证据的继续待实测。
- 文档检查覆盖端点清单与源码构造、固定提交 / 文件引用、公共字段拼写、内部链接与 Markdown 表格。`UPSTREAM.json` 的 241 个文件摘要用于确认读取的是标注上游文件。

## 25. GloryOfKings 固定源码索引

G 系列全部固定到 GitHub 提交 `4d4238d2c9c2c37af7007d40dd0723308c006bb4`，即本次实际读取的公开源码；其打包上游快照另见 G0。请求参数优先看 G1～G3，响应字段必须结合对应业务消费文件。

| 编号      | 文件                                 | 主要内容                                     |
| --------- | ------------------------------------ | -------------------------------------------- |
| G0        | [UPSTREAM.json][G0]                  | 上游来源、提交与文件摘要                     |
| G1        | [utils/api.js][G1]                   | 15 个营地业务入口、公共协议、公开 URL 与请求 |
| G2        | [utils/wechatLogin.js][G2]           | 微信 SDK、二维码、轮询、登录、设备 RSA       |
| G3        | [utils/qqLogin.js][G3]               | QQ 浏览器授权、YSDK、openSdk 登录与重登      |
| G4        | [utils/heroDetail.js][G4]            | 单英雄详情、曲线、五维、近局字段             |
| G5        | [utils/heroMedals.js][G5]            | 当前称号查询                                 |
| G6        | [apps/skinWall.js][G6]               | 皮肤拥有判据、统计与图源                     |
| G7        | [utils/skinCatalog.js][G7]           | 皮肤全配置与原皮识别                         |
| G8        | [apps/heroList.js][G8]               | 赛季 / 生涯常用英雄字段                      |
| G9        | [apps/myHeroList.js][G9]             | 全量英雄与历史最高战力关联                   |
| G10       | [apps/skinMissing.js][G10]           | 缺皮肤计算与拥有判据                         |
| G11       | [utils/seasonFallback.js][G11]       | 分接口隐私错误与降级范围                     |
| G12       | [utils/heroGuide.js][G12]            | 官网字段、HTML 攻略、装备 / 铭文整理         |
| G13       | [apps/seasonPage.js][G13]            | 赛季二跳、分路、趋势时间窗                   |
| G14       | [apps/peakPerformance.js][G14]       | 巅峰五维与历史赛季消费                       |
| G15       | [apps/heroTierList.js][G15]          | 梯度段位 / 分路枚举和比例                    |
| G16       | [utils/masterPool.js][G16]           | 大神池流 URL / 模式 / 分路                   |
| G17       | [utils/pvpSkinImage.js][G17]         | 官网皮肤图片索引与 CDN 参数                  |
| G18       | [utils/skinNews.js][G18]             | 官网皮肤上线日期与上新                       |
| G19       | [utils/profileSummary.js][G19]       | 角色匹配与主页模块摘要                       |
| G20       | [apps/queryGameStats.js][G20]        | 模式、英雄本地筛选与游标                     |
| G21       | [utils/battleDetailImage.js][G21]    | 详情字段与图片消费                           |
| G22       | [apps/campRenew.js][G22]             | 保活与 QQ 重新登录策略                       |
| G23       | [apps/heroSkin.js][G23]              | 英雄 / 皮肤编号和图片回退                    |
| G24       | [utils/gameNews.js][G24]             | 公告字段、标签筛选与 HTML                    |
| G25       | [apps/heroFightingCapacity.js][G25]  | sapi.run 四区门槛与英雄命名                  |
| G26       | [engine/remote-policy.mjs][G26]      | 远端凭据接收地址允许列表                     |
| G27       | [services/runtime.py][G27]           | 运行副本补丁，账号 POST 禁重定向             |
| G28       | [README.md][G28]                     | 服务缺失边界与平台范围                       |
| G29 / G30 | [LICENSE][G29] / [上游 LICENSE][G30] | 许可归属                                     |
| G31       | [utils/avatar.js][G31]               | 数字 QQ 图片模板与 OpenID 区分               |
| G32       | [utils/remoteAccounts.js][G32]       | 服务探测、凭据上报与节流                     |
| G33       | [apps/watchBattle.js][G33]           | 观战服务客户端参数 / 响应                    |
| G34       | [apps/gameRecordPush.js][G34]        | 观战好友与提示坐标写入                       |
| G35       | [utils/campImClient.js][G35]         | IM 服务 HTTP 协议                            |
| G36       | [apps/campFriend.js][G36]            | IM 好友与发送字段                            |
| G37       | [apps/campIm.js][G37]                | IM 消息游标、回复与状态                      |
| G38       | [utils/shareStore.js][G38]           | 共享绑定请求 / 错误                          |
| G39       | [apps/shareDeploy.js][G39]           | 共享库管理接口                               |
| G40       | [utils/deploy.js][G40]               | 包版本 / 下载请求                            |
| G41       | [utils/http.py][G41]                 | 未发现业务调用的访客 Cookie 辅助             |

[G0]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/UPSTREAM.json
[G1]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/api.js
[G2]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/wechatLogin.js
[G3]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/qqLogin.js
[G4]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/heroDetail.js
[G5]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/heroMedals.js
[G6]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/skinWall.js
[G7]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/skinCatalog.js
[G8]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/heroList.js
[G9]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/myHeroList.js
[G10]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/skinMissing.js
[G11]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/seasonFallback.js
[G12]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/heroGuide.js
[G13]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/seasonPage.js
[G14]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/peakPerformance.js
[G15]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/heroTierList.js
[G16]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/masterPool.js
[G17]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/pvpSkinImage.js
[G18]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/skinNews.js
[G19]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/profileSummary.js
[G20]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/queryGameStats.js
[G21]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/battleDetailImage.js
[G22]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/campRenew.js
[G23]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/heroSkin.js
[G24]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/gameNews.js
[G25]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/heroFightingCapacity.js
[G26]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/remote-policy.mjs
[G27]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/services/runtime.py
[G28]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/README.md
[G29]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/LICENSE
[G30]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/LICENSE
[G31]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/avatar.js
[G32]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/remoteAccounts.js
[G33]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/watchBattle.js
[G34]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/gameRecordPush.js
[G35]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/campImClient.js
[G36]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/campFriend.js
[G37]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/campIm.js
[G38]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/shareStore.js
[G39]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/apps/shareDeploy.js
[G40]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/engine/upstream/utils/deploy.js
[G41]: https://github.com/wzq10314/astrbot_plugin_gloryofkings/blob/4d4238d2c9c2c37af7007d40dd0723308c006bb4/utils/http.py

## 26. 当前版本接入与真实联调记录

v2.5.0 当前能力如下；这是本插件的实现状态，不改变前文来源快照的验证结论。

| 能力                       | 当前状态                   | 接口 / 说明                                                                          |
| -------------------------- | -------------------------- | ------------------------------------------------------------------------------------ |
| 微信 / QQ 登录             | 已接入                     | 微信 SDK、QQ 浏览器授权 / YSDK 后通过 `/user/login` 换营地凭据                       |
| 资料、赛季与战绩           | 已接入                     | `/game/koh/profile`、`/game/seasonpage`、`/game/morebattlelist`                      |
| 昵称搜索、别名和战绩筛选   | 已接入                     | `/search/getbytype`；全部 / 排位 / 巅峰分别使用已验证选项 0 / 1 / 4                  |
| 双方详情与地图回顾         | 已接入                     | `/game/battledetail`、`/game/battleanalyze/old`；规范化轨迹、事件、死亡 / 复活和塔位 |
| AI 对局分析                | 已实现，真实模型生成未实测 | 复用详情与回顾，经 AstrBot 模型调用；不是新增营地接口，数据契约见 26.9               |
| 其他第三方、观战及外置服务 | 保留前文验证范围           | 未作为本插件当前数据来源接入                                                         |

本节记录 2026-10-08 的功能开发与新增验证，补充前面源码审阅时的状态；不将一次成功响应推广为所有模式、账号或历史对局都可用。

### 26.1 本轮接入范围

- WebUI 可选择微信 / QQ 扫码。QQ 使用独立非持久浏览器上下文，后台准备二维码，取消、过期和卸载时清理资源；YSDK 与营地 `openSdk` 参数沿用 G3，未加入自动重登。
- WebUI 新增单局“地图回顾”，实际调用第 9 节的 `/game/battleanalyze/old`，`playerId` 从同一场详情的被查询角色提取。没有玩家标识时不改用其他玩家，也不拿 `roleId` 替代。
- 详情补齐评分、参团、控制、补刀、治疗、建筑伤害、战力变化、五维评级、最高标记与 `dataBehaviorV2`，缺失值保留为空；对英雄伤害与总伤害分开。
- 本轮不新增机器人指令。`core/models.py` 保留原有导入，并统一导出详情与回顾解析；`models_player/battle/detail/replay.py` 分别维护数据，各展示端复用同一份结果。

### 26.2 微信与指定玩家的只读实测

用户在本地完成微信扫码，登录态写入本机插件数据目录，并明确指定营地 ID `489048724` 作为验证对象。使用同一登录态读到以下结果：

| 项目     | 实际结果                                                                                                         |
| -------- | ---------------------------------------------------------------------------------------------------------------- |
| 登录     | 微信授权、营地换票、`encodeRes` 解码和账号持久化成功                                                             |
| 主页     | `/game/koh/profile` 的 `returnCode=0`，得到可用于查询的角色                                                      |
| 战绩     | 第一页 30 场；网页按游标读取 50 场用于统计，展示用户指定的 10 场                                                 |
| 所选详情 | 蓝方 / 红方各 5 名玩家，成功匹配目标角色的 `playerId`                                                            |
| 回顾     | 返回 10 名玩家，每名 919 个轨迹采样；事件源包含 22 条战斗记录和 50 条建筑类别记录                                |
| 轨迹     | 原始坐标范围约为 `[-57,57]`；按当前投影接受 9093 个点，地图外点保留断点                                          |
| 击杀关联 | 从 `battle.killInfo[]` 解析 32 次击杀，用对象 ID 关联玩家，再与对应死亡时间 / 位置匹配；本次 32 次均得到死亡位置 |
| 展示模型 | 基础事件去重 / 过滤后 70 条，补充 32 次击杀，共 102 条；不将事件数量当作推塔数                                   |
| 玩家名称 | 回顾响应中的昵称可能为空，用同一详情的 `playerId` 映射补齐，本次 10 名玩家均关联成功                             |

原始响应仅保存在仓库外的临时联调目录，登录凭据不进入源码、测试样本或文档。仓库内新增测试使用合成数据。

### 26.3 本次确认的补充字段与处理

| 原始字段 / 路径                                                 | 当前处理                                                                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `battleStats.joinGamePercent`                                   | 本次为比例字符串，如 `"0.762"`，展示为百分比                                                                 |
| `battleStats.ctrlTime / killSoldier / healCnt / buildingDamage` | 控制秒数、补刀、治疗量、建筑伤害；保留真实零值，缺失不补造                                                   |
| `battleStats.addFightPower`                                     | 独立战力变化，不与累计战力混用                                                                               |
| `maxAssist / maxJoinGamePercent / maxCtrlTime / maxBehurt` 等   | 补充助攻、参团、控制与总承伤最高标记                                                                         |
| `dataBehaviorV2[].dataCounts[].dataNote`                        | 本次为类似 `"2%"` 的排名百分位；展示“前 2%”，原始 note 同时保留                                              |
| `battle.killInfo[].time`                                        | 本次毫秒时间，转换为从开局起的秒数                                                                           |
| `battle.killInfo[].objID / killerObjID`                         | 分别为被击杀者 / 击杀者在对局中的对象 ID，关联 `playBaseInfoArr[].inBattleObjID`，再关联 `playID → playerId` |
| `playBaseInfoArr[].deathPosArr[].time / coordX / coordY`        | 本次死亡时间为秒，死亡坐标沿用回顾投影                                                                       |
| `playerPosInfo[].revivePosArr`                                  | 读取 `[x,y,秒数]`，结合死亡时间处理玩家可见性与轨迹断点                                                      |
| 建筑 `dtData.viewX/viewY=0/0`                                   | 不直接画在地图中心；沿用官方 `TowerConf` / 水晶配置定位，未识别的对象不补位置                                |
| 同一建筑多次记录                                                | 保守展示“防御塔事件 / 水晶事件”，不宣称每条代表一次摧毁，不据此计算建筑摧毁次数                              |
| 战绩 `hero1RampageCnt / hero1Kill6Cnt` 等                       | 五杀与更高连击；不再使用未经此来源确认的五杀键名                                                             |
| 排位的巅峰字段均为 0                                            | 不展示“巅峰变化 0”，避免把未参与巅峰当成有效积分变化                                                         |

地图参数另对照 [营地官方回顾页面](https://camp.qq.com/h5/webdist/battle-replay/index.html) 与其 [主脚本](https://camp.qq.com/h5/webdist/battle-replay/static/js/main.b6a0acd6.js)。本次读取脚本 SHA-256 为 `302c79da6fe6bcecd960fd61a409804021cc6cee9fd5af5032cbf6bcf4d2ff44`。

官方实现中 `covertCentralPoint` 先转换坐标，`covertCoord` 按跨度 108 映射。当前公共模型将地图内点转换到 0～100 的百分比坐标；轨迹按每秒一个点，经济差序列按 30 秒索引解释。底图使用官方脚本引用的 `https://camp.qq.com/meta-data/heros/battle-replay-map.jpg`。其他地图 / 特殊模式仍需独立验证投影与建筑配置。

### 26.4 QQ 与页面验证范围

- 真实浏览器成功取得 QQ 二维码；用本地合成回调验证 Chromium 深链接导航事件能捕获授权码，并完成资源关闭。
- 用户随后完成真实 QQ 扫码。实测 QQ 移动授权页将回调改写为 `http://auth//tauth.qq.com/?code=<QQ_AUTH_CODE>`，原有解析只接受标准回调，导致扫码成功后会话过期。现兼容此固定地址，并拦截导航，避免访问改写出的 `auth` 主机；保持对其他域名、端口和路径的拒绝检查。授权码和 Cookies 不输出到日志。
- 修复后完成“扫码确认 → 捕获授权码 → YSDK 换票 → 营地 `openSdk` 登录 → 解出 `userKey` → 保存账号”的完整实测。用该 QQ 账号独立请求 `489048724` 的资料与战绩，两者 `returnCode=0`，战绩第一页 30 场；账号池中的微信、QQ 两个账号均检测有效。
- YSDK 精确 body / HMAC、异常业务响应、单次授权码只兑换一次、取消后不继续登录、保存失败重试等由离线测试覆盖。自动重登和其他浏览器环境未验证。
- 真实 WebUI 已验证查询、单局概览、地图加载、32 条击杀筛选、事件定位、时间轴拖动、播放、登录方式切换和别名弹窗；桌面 1440×1000、设计稿尺寸 1536×1024 与手机 390×844 检查布局。桌面播放控件位于首屏，手机无横向溢出，浏览器控制台无错误。
- 截图、联调脚本和诊断产物保存在仓库外。未运行作者的观战 / IM / 共享服务，也未新增任何机器人指令。

### 26.5 ZIP 安装报错与依赖核对

用户远程 AstrBot v4.28.1 在插件依赖安装阶段报 `No matching distribution found for playwright<2,>=1.51`，还未进入插件加载或浏览器启动。按用户要求，`requirements.txt` 保持 Playwright 为强制依赖，没有将其改为可选组件。

本地从官方 PyPI 以 Linux x86-64 / Python 3.12 的目标参数执行 pip 试解析，该约束成功选中 `playwright-1.63.0-py3-none-manylinux1_x86_64.whl`。此结果确认约束与包存在，不等于远程环境安装成功。远程尚未提供完整 pip 源、网络和兼容标签日志，无法确定具体原因；应在运行 AstrBot 的同一解释器 / 容器中检查实际 pip 配置，不能将扫码回调问题与 Python 包安装失败视为同一个问题。

### 26.6 QQ 登录态的补充字段与事件说明核对

使用用户保存的 QQ 凭据，独立请求营地 ID `489048724` 最近一场 `gameSeq=1791100999`，导出完整详情与回顾响应正文。正文与查询参数保存在仓库外，不导出登录凭据或鉴权头。

| 原始详情字段                        | 公共模型 / 展示                              | 本场查询玩家的值       |
| ----------------------------------- | -------------------------------------------- | ---------------------- |
| `totalHeroHurtCnt`                  | `hero_damage`，对英雄伤害及队伍占比条        | 28,461                 |
| `totalHurtCnt`                      | `total_damage`，总伤害                       | 80,168                 |
| `totalBeheroHurtCnt`                | `damage_taken`，英雄承伤及队伍占比条         | 81,670                 |
| `totalBehurtCnt`                    | `total_damage_taken`，总承伤；与英雄承伤分开 | 108,089                |
| `buildingDamage`                    | `building_damage`，建筑伤害                  | 3,339                  |
| `towerCnt`                          | `tower_count`，推塔数；不从回顾记录数量推算  | 1                      |
| `healCnt`                           | `healing`，治疗量                            | 18,766                 |
| `monsterCoin`                       | `jungle_economy`，野怪经济                   | 252                    |
| `ctrlTime / killSoldier`            | 控制秒数 / 补刀                              | 32 秒 / 9              |
| `battleRecords.finalEquips / skill` | 装备与召唤师技能分开；本次六件装备、闪现     | 6 件 / `skillId=80115` |

交战事件使用 `battle.startTime/endTime` 的毫秒值换算持续秒数，`camp1MemNum/camp2MemNum` 展示人数；缺失人数时仅根据 `joinMemInfo` 的唯一对象 ID 统计。`joinMemInfo[].objID` 与 `playBaseInfoArr[].inBattleObjID → playID → matchInfo.playerId` 关联，补齐参与英雄。击杀比分按 `killInfo[].killerCamp` 统计，重复击杀记录去重；明细缺失保留未知，不补造 `0:0`。本次最早交战为 `0:28–0:38`，蓝方 2 人 / 红方 1 人、击杀 `1:0`。

塔位沿用官方 `bs/ws` 与 `ko/Co` 映射：分路顺序下路、中路、上路，塔序高地塔、二塔、一塔；建筑所属阵营取 `dtCamp`，不能根据 `dtID` 十位数推断。推进阵营取 `killerCamp`，参与英雄通过 `dtData.kills[].killerId` 关联。

本次 50 条建筑记录中，`dtCamp=2/dtID=13` 出现 **46 次**；该字段按官方配置对应红方上路高地塔，但事件记录不能等同于 46 次摧毁。页面保留记录并展示具体塔位 / 参与信息，不据此计算摧毁数。

部分 `dtData.kills[].hurtTotal` 很大，例如第一条为 `175000`，没有足够证据将其与 `battleStats.buildingDamage` 视为同单位。公共模型保留 `hurt_total_raw`，页面仅展示该条记录内各参与对象贡献总值为分母的 `contribution_percent`，不将原值当作整数建筑伤害；未知对象的原始贡献也计入分母。

页面移除每格“已返回队员”文字，完整性提示保留在队伍摘要；占比条按实际返回的同队数值计算，缺失值不冒充零。新增四项模型回归，覆盖缺失 / 零值、交战关联与重复击杀、塔位与重复记录、未知贡献对象。

### 26.7 防御塔时间轴与宿主页面切换验证

回顾模型新增 `towers[]`：`id/camp/road/tier/name/position/destroyed_at`。位置沿用官方 5v5 配置，双方各九座塔；摧毁时刻取规范化建筑事件中同一 `dtCamp + 分路 + 塔序` 的最早 `killTime`，重复事件只影响同一座塔一次。未返回该建筑的摧毁记录时，`destroyed_at=null`，不根据对局胜负或总事件数推算。时刻为零保留为有效值，水晶和资源事件不作为防御塔处理。

页面按当前秒数决定塔是否显示，回拨到摧毁之前恢复图标；本场验证 `0:00 → 1:20 → 0:40` 时，可见塔数依次为 `18 → 17 → 18`。这反映返回记录的时刻，不将重复 / 异常记录扩大为额外摧毁事件；特殊地图仍需独立核对。玩家头像复用同一详情补齐的 `hero_icon`，保留阵营边框和选中环，播放时只移动节点。

普通本地页面导航正常，但在阻断一个 ES 功能模块时复现三页导航都失效。现将基础导航放入独立普通脚本，完整功能由分模块源码构建成 `app.bundle.js`；构建脚本记录源码摘要并支持 `--check`，避免发布旧产物。回顾播放清理在页面切换后执行，已移除的图层仍可安全停止。

联调使用工作区宿主源码中的资源重写方法、官方页面桥接 SDK，以及 `sandbox="allow-scripts allow-forms allow-downloads"` 的不透明 iframe，真实数据请求绑定保存的 QQ 账号。验证正常导航、功能脚本失败时导航、播放后导航、返回列表后导航、概览 / 回顾切换、塔位消失 / 恢复、头像点选和手机布局。该测试不等于已在用户远程 AstrBot v4.28.1 实际部署验证。

### 26.8 播放事件通知与页面布局调整

工具展示名称统一为“王者荣耀数据查询工具”，入口采用顶部横向导航。战绩英雄 / 对局列设定宽度上限；详情出装列固定为 228px，对应六个 31px 图标、五个 4px 间隔及单元格内边距，页面最多显示六件装备，公共原始模型不截断数据。伤害两列使用剩余空间展示数值和队伍占比。

回顾画面在播放与拖动时间轴时展示当前时刻之前六个对局秒内的事件，按发生时间排序；不存在事件时隐藏通知，不预告未来事件。手动点选保留指定事件，恢复播放 / 拖动后重新按时间选择。多个事件同窗发生时合并展示，最新事件在列表高亮，自动跟随只改变列表自身的滚动位置。该规则只使用既有规范化事件，不增加上游接口或改写原始响应。

轨迹范围移至地图顶部“显示轨迹”后，移除地图底部的防御塔隐藏说明，塔位时间轴行为继续沿用上一节。真实 QQ 账号验证了 `0:27 → 0:28` 的交战提示、`0:37 → 0:38` 的击杀提示和超出窗口后通知隐藏。Node 离线回归覆盖精确时间边界、同时事件、手动固定、无效时间与输入数组不可变。

### 26.9 AI 对局分析的数据契约

页面分析入口位于单局详情顶部右侧，打开单局后即可使用；分析进度和结果位于比赛摘要下方的公共区域，不挂在回放容器内。“地图回顾”标签已更名为“对局回放”。2.5.1 优先查询数据库缓存，未命中时才执行后台详情与回放查询。

AI 分析复用既有战绩定位、单局详情和地图回顾接口，不新增上游接口。通过对局标识锁定同一场，单局详情仅查询一次，再复用其中的 `player_id/game_seq/game_svr/relay_svr` 获取回顾。

程序内 `ANALYSIS_DATA_PROMPT` 作为固定系统提示词解释数据，可配置的 `analysis.prompt` 仅定义分析任务；`analysis.select_provider` 明确选择 AstrBot 模型，网页和聊天共用 `Context.llm_generate(chat_provider_id=..., system_prompt=..., prompt=...)`。原锐评路径已移除。

分析输入补充 `match.hero_name` 与 `queried_player.player_id/nickname/camp/hero_name`，明确所用英雄指被查询玩家本局使用的英雄，不能从 MVP 或队伍第一行取值。默认输出首行由程序填入 `【真实对局时间】-【真实模式】-【真实英雄】`，后续按 `【【获胜方】】/【【失败方】】` 与 `【原因】/【关键点】/【背锅】` 格式显示；模型输出的首行不作为事实来源。列表模型的 `side=blue/red` 也支持胜方交叉核对。

模型输入只保留比赛信息、胜方阵营、双方面板、营地评价和回顾数据，不发送图片地址、登录态或原始响应。全部规范化事件保留，普通轨迹每 5 秒采样，补充首尾、断点、关键事件起止、死亡与复活附近的原始秒点，坐标为左上原点的百分比并保留两位小数；原始与发送点数单独记录。`null` 不当作零值，队伍占比按实际返回范围解释，详情胜负与列表胜负冲突时拒绝分析。

说明保留已确认的限制：重复建筑记录不等于多次摧毁，`hurt_total_raw` 不冒充详情建筑伤害，交战分组与击杀不重复计数，轨迹靠近不自动等同参战，`ecoDistance` 正负对应阵营未独立确认。模型须区分数据事实和推测，不能补写视野、技能、兵线或指挥信息。

插件页面路由：`POST analysis/start` 接收 `keyword/game_seq/index`，未命中缓存时返回随机临时任务标识，2.5.1 命中缓存时直接返回 `status=done/text`；`GET analysis/status?task_id=...` 返回状态、进度提示及最终文字，不接收客户端提示词或对局 JSON。生成最长 180 秒，同时最多 3 个任务；任务状态保留 15 分钟、最多 32 条，卸载时取消。这里是本插件的页面 API，不是新增营地接口。

## 27. 2.5.1 分析缓存、订阅与页面验证

本节记录 2026-10-09 的插件实现与发布检查。新增能力复用既有营地接口，不增加外部数据源；下列页面路由由 AstrBot 插件桥接调用，不是腾讯营地接口。

### 27.1 分析缓存与存储边界

`BattleAnalysisService` 统一处理网页和聊天分析。成功且格式验证通过的最终文字写入 `battle_analyses`，`game_seq` 为主键，保存 `text/created_at`；不保存模型输入、提示词、账号凭据或原始营地响应。已知对局 ID 时直接查询缓存；聊天只提供近期序号时，先查询详情确定 ID，再读取缓存，未命中才请求回顾及模型。

`analysis.cache_retention_days` 默认 150，填写正整数；保留期从结果保存时刻计算，读取不续期。启动、每小时及缓存读取时删除过期记录。每场使用独立锁串行生成和清除；清除后同时移除该场临时任务记录，防止继续读取已删除结果。

| 页面路由              | 参数与返回                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `POST analysis/start` | `keyword/game_seq/index`；命中缓存直接返回 `status=done/text`，否则返回 `task_id/status=pending` |
| `GET analysis/status` | `task_id`；返回 `status/message/text`，任务缺失或过期时失败                                      |
| `GET analysis/cache`  | `game_seq`；返回 `available/text/created_at`，未命中时不调用模型                                 |
| `POST analysis/clear` | `game_seq`；删除该场结果并返回 `deleted`，不清理其它对局                                         |

数据库位置仍为 `data/plugin_data/astrbot_plugin_gok/gok.db`。`aliases` 保存名称映射，`battle_analyses` 保存有期限的分析文字；下面的订阅表保存订阅配置、最新快照与会话游标，不采用 AI 缓存的 150 天清理规则。标准玩家查询仍实时读取营地，登录凭据单独保存在忽略提交的 `camp_auth.json`。

### 27.2 订阅轮询与最新事件策略

`SubscriptionService` 复用 `get_profile` 和 `fetch_battles`，状态检查只取主页，不请求赛季页；战绩读取最新一页并从中选择具有有效 `game_seq` 和明确胜负的最新完成对局，不把未完成或结果未知的记录当成新战绩。没有关联会话的 `(kind,camp_id)` 不请求营地；同类订阅同一个玩家只查询一次，再分发给其接收会话。

2.5.2 修正：用户确认资料 `hideMatch` 是游戏内隐藏提示，不等同于营地战绩不可见。订阅不再以该标记提前退出，而是实际请求 `fetch_battles`；只有读到空列表后才提示可能隐藏或暂无记录，保留既有游标并继续轮询。重新有记录时仍只比较最新完成对局，不补推中间记录。

`subscriptions.status_poll_interval/battle_poll_interval` 分别默认 60 / 120 秒，必须为正整数；间隔在轮询轮次结束后计算，失败不会让整个服务退出。两类模块保留上次和下次轮询时刻，页面单独每 5 秒刷新，不增加营地查询次数。删除关联后，在下次上游请求前重新确认仍有接收会话。

- **状态**：将 `0` 归为离线，`1/2` 归为在线；只推送 `0→1/2` 和 `1/2→0`。未知码、字段缺失与查询失败不覆盖已有有效比较状态；`1↔2` 不推送。首次关联先建立基准，失败的状态消息不积压补发。
- **战绩**：每个会话独立记录已发送的 `game_seq`；发送成功才推进游标，失败时下次仍只比较那时最新的一场。例如 A 已发送，B、C 失败，恢复后最新是 D，只尝试 D，不遍历补发 B、C。临时空列表或较旧响应不会重置已有完成对局游标。
- **重启与重新关联**：配置、快照和游标存入 SQLite，重启后按已有游标比较最新一场；解除后重新关联视为新接收目标，重新建立基准，跳过暂停期间历史。

数据表为 `subscription_targets`（每种订阅/营地 ID 一份最新快照）、`push_sessions`（完整会话 ID、最近发送时刻和发送错误）、`push_links`（会话与目标的多对多关系和独立游标）。外键删除目标或会话时清理相关关联。

### 27.3 会话路由、指令与页面接口

主动发送遵循 [AstrBot 官方文档](https://docs.astrbot.app/dev/star/guides/send-message.html#主动消息)：保存发起指令的 `event.unified_msg_origin`，后台构造 `MessageChain().message(text)` 并调用 `context.send_message(session_id, chain)`。会话 ID 包含平台实例、消息类型和会话标识，不只填写群号；`GroupMessage/FriendMessage` 用于群聊/私聊，实际发送能力取决于所接入的平台。

`订阅状态/订阅战绩` 在当前会话添加关联；`查看订阅` 返回该会话的列表和完整 ID；`取消订阅 ID [状态/战绩/全部]` 默认只取消当前会话的两类关联，不影响其它会话。确认与主动推送均使用文本，不自动触发模型。

2.5.2 文字调整：三类消息分别以“【上线推送】”“【离线推送】”“【战绩推送】”开头；状态消息单独列出游戏昵称、时间和上线/离线段位，战绩消息随后列出昵称-模式-时间、胜负、战绩和荣誉。完整示例见 README，轮询与去重规则保持原定义。

| 页面路由                    | 参数与返回                                                                                                                                                                                               |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET subscriptions/list`    | 返回 `modules.status/modules.battle` 的运行状态、间隔、轮询时刻、目标快照与会话列表                                                                                                                      |
| `POST subscriptions/update` | `action=add_target/delete_target` 使用 `kind/camp_id`；`action=save_session` 使用完整 `session_id` 和字符串数组 `status_ids/battle_ids`；`action=delete_session` 使用 `session_id`。成功返回更新后的总览 |

“订阅系统”位于现有导航最后，分为状态、战绩、会话三个模块。状态与战绩目标可分别增删；一个会话可以选择多个目标。未选任何接收会话时显示暂停，并保留此前已读取的最近快照。查询、详情与其它管理页统一使用公共外层留白和标题栏，详情样式限定在查询页；切换导航回到顶部，`scrollbar-gutter: stable` 避免页面高度变化造成水平位移。

`功能/帮助` 加入 `query_output`，默认使用浅色 HTML 功能指南；模板复用配置的指令前缀与默认场数，图片失败时回退完整指令文本。

### 27.4 公开 AppID 告警核对

GitHub 告警类型 `tencent_wechat_api_app_id` 可识别 `APPID_WX`。该值是营地客户端公开的微信应用标识，既有来源 [G2] 也将其用于二维码 URL 的 `appid` 参数；本插件没有与其配套的微信 AppSecret。源码拆分前后的文件及文档引用会让同一个告警记录多个历史位置，不能据此认定发生多次个人账号凭据泄露。

本次只核对了告警与调用用途，没有修改该协议常量、轮换用户凭据或自动关闭 GitHub 告警。仓库所有者核对命中内容后，可依据 [GitHub 告警处理说明](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-secret-scanning-alerts/resolving-alerts#closing-alerts) 按误报关闭并备注公开标识用途；真实 `camp_auth.json/token/userKey` 不属于这个说明的范围。

### 27.5 发布验证范围

- 八个离线套件共 464 项检查全部通过，覆盖数据、插件装配、模板、AI 分析和订阅；订阅 20 项回归覆盖首次基准、状态切换、失败恢复只推最新、多会话隔离、暂停/恢复、重启游标、删除关联、轮询时刻及页面参数校验。
- 缓存验证使用临时 SQLite，覆盖关闭后重开、网页与指令互相复用、过期清理、清除后再分析、同场并发、失败回答和数据库保存失败。
- Playwright 使用本地页面桥接与合成数据检查缓存查看/清除、订阅目标和多会话编辑、失效/恢复、字面文字展示，以及 1920 / 1440 / 1024 / 390px 下四页切换、资料、战绩、单局详情和错误状态。页面身份、非空内容、错误遮罩、控制台、截图及交互检查通过。
- 发布前执行 Ruff、前端构建同步、JavaScript 语法及 Node 回顾时间轴检查。截图、测试桥接脚本和数据库均位于仓库外，不包含在插件发布文件中。
- 主动消息与模型使用测试桩，没有在本轮向真实群聊/私聊发送，也没有重新登录或请求真实营地玩家数据；2.5.0 的真实登录与只读查询证据保留原日期，用户远程宿主部署仍未验证。

## 28. 2.5.2 推送格式与营地战绩可见性

本节记录 2026-10-09 的两项订阅优化。复用既有营地接口与 `context.send_message`，没有新增上游接口、配置或数据库表；2.5.1 的关联、快照和游标继续使用。

### 28.1 三类推送文字

状态消息使用“【上线推送】”或“【离线推送】”作为首行，随后分别列出 `游戏昵称：`、`时间：` 和 `上线段位：`/`离线段位：`。时间为检测到状态变化的北京时间，段位来自该次资料响应；`0↔1/2` 触发规则及 `1↔2` 不推送的规则保持原定义。

战绩消息首行为“【战绩推送】”，第二行为 `游戏昵称-模式-对局时间`，第三行为 `胜利` 或 `失败`，随后为 `战绩：击杀/死亡/助攻` 与 `荣誉：...`；没有荣誉时填写 `无`。消息正文只包含真实已返回的公共模型数据，不自动调用 AI。

### 28.2 隐藏标记、空列表和恢复

旧订阅路径在读取资料后遇到 `hideMatch` 会结束本次玩家查询，定时任务虽然仍在运行，但不会调用该玩家的战绩接口。根据用户确认的业务含义，该标记属于游戏内隐藏设置，不能单独认定营地战绩不可见。

2.5.2 移除提前判断，只要目标仍有关联会话且资料包含有效角色，就实际读取战绩列表。角色对象与资料顶层的隐藏标记都不阻止请求；非空且包含有效完成对局时，按原规则建立基准或处理最新一场。

返回空列表时提示可能隐藏或暂无记录，已有完成对局及会话游标不清空，目标不删除、关联不解除、后续轮询不停止。第一次查询为空也保留订阅，之后出现新完成对局时可以正常推送。恢复多场记录时只选择最新完成的一场，不依次补推缺失记录；返回数据后清除此前的查询提示。

### 28.3 2.5.2 验证范围

订阅回归由 20 项扩展到 24 项。新增四项分别覆盖角色 `hideMatch=1` 仍可读列表并推送新对局、资料顶层标记不跳过请求、连续空列表仍轮询且恢复只推最新、首次空列表后出现完成对局可推送；原有规则、多会话隔离、暂停、重启和失败恢复用例继续执行。

本次发布八套离线测试共 468 项全部通过（含 24 项订阅回归）；Ruff、版本与文档链接校验、前端产物同步、JavaScript 语法及 Node 时间轴检查通过。推送发送和模型使用测试桩，不向真实会话发送，不重新登录或额外查询真实玩家；页面布局沿用 2.5.1 的本地桥接验证记录，本轮没有声明新的用户远程部署验证。

## 29. 2.5.3 战绩推送摘要与评分

本节记录 2026-10-09 的文字输出调整，没有新增营地请求、页面路由或数据库字段。战绩订阅仍使用当前资料昵称和最新已完成对局，保留 `hideMatch` 不提前阻断、空列表继续轮询及恢复只推最新的规则。

### 29.1 消息结构与取值

```text
【战绩推送】
飞翔小野猪-排位赛-胜利
时间：2026-10-09 18:20
英雄：妲己
战绩：8/2/9
评分：12.1
```

第二行依次读取 `profile.nickname`、`match.mode_name` 和 `match.result_text`，失败时末尾为 `失败`，昵称直接使用当前资料返回的实际游戏昵称。后续四个字段分别使用 `played_at_text`、`hero_name`、`kills/deaths/assists` 和既有 `score_text`；评分按公共模型保留一位小数，未返回有效评分时为 `-`。消息不再包含荣誉行，上线/离线格式沿用 2.5.2。

### 29.2 验证与升级

现有订阅回归同步检查胜利、失败、实际昵称和缺失评分；未完成或结果未知的记录仍不会推送。本次发布八套离线测试共 468 项全部通过（含 24 项订阅回归），Ruff、JavaScript 语法、前端产物同步及 Node 时间轴检查通过；主动发送使用测试桩，没有向真实会话实发。升级只需替换程序并重载，已有账号、关联、缓存和游标继续使用，后续新消息采用此格式。

## 30. 2.5.4 随机轮询、分钟冷却与 QQ 错误处理

本节记录 2026-10-10 的轮询配置和登录错误处理变更，复用当前营地接口、扫码会话和账号池，没有新增上游协议或数据库表。

### 30.1 随机轮询与页面截止时间

`subscriptions.status_poll_interval` / `battle_poll_interval` 继续表示基础秒数，默认 60 / 120；新增共用的 `subscriptions.poll_jitter`，默认 10 秒。每轮独立从 `[max(1, 基础间隔 - 随机范围), 基础间隔 + 随机范围]` 抽取整数秒；0 或负数使用固定间隔，非法配置回退至默认范围。状态和战绩分别抽取，暂停的订阅不会抽取或发起请求。

调度器每轮只抽取一次，同一个值同时用于异步等待与 `next_poll_at`。页面读取 `interval`、`jitter`、`interval_min`、`interval_max` 和已排定的下次时间，只显示范围而不再次随机取值，刷新不改变本轮截止时间。扫码登录、AI 任务进度和网页自动刷新间隔继续使用各自的流程。

### 30.2 分钟冷却配置

`account_cooldown_minutes` 默认 5 分钟，配置范围 0～1800 分钟（30 小时），页面步长 1 分钟，后端同步限制最大值。装配账号池前换算为秒数，继续复用现有冷却截止时间和账号选择逻辑。旧版 `account_cooldown` 秒制配置及兼容迁移已移除，升级后按新配置重新设置。

### 30.3 QQ 登录错误与宿主桥接

系统浏览器启动失败时回退到已安装的 Playwright Chromium；两次启动都失败时结束会话并关闭已创建的资源。浏览器缺失、Linux 系统库缺失、登录页网络错误或超时、HTTP 错误以及二维码未加载分别返回处理提示。后台日志包含失败阶段与脱敏原因，不记录授权 URL、授权码或账号凭据。插件不会自动下载浏览器或安装系统库。

AstrBot 的页面桥接会拒绝 `status=error` 响应，因此登录页面接口将业务终止错误映射为 `failed`，可恢复错误映射为 `retrying`，保留 `terminal` 和原错误说明；后端会话的内部状态不变。页面据此停止已终止会话的轮询，保存失败或请求暂时中断仍可重试。

### 30.4 验证范围

八套离线测试共 499 项通过，其中订阅 31 项、扩展 43 项、插件集成 118 项。新增回归覆盖随机上下界、短间隔、每轮一次抽取、显示截止时间与实际等待一致、刷新保持截止时间、暂停、分钟配置及上限、QQ 启动回退、错误脱敏、取消与资源关闭。Node 回归验证登录终止停止轮询、可重新获取以及可恢复错误继续重试；原有回顾时间轴检查继续通过。

Playwright 1.62.1 与系统 Edge 在本地模拟页面验证 1440×1000 / 390×844 的随机范围显示、刷新、0 范围、暂停和手机无横向溢出，页面有实际内容、无错误遮罩或相关控制台错误。Ruff、JavaScript 语法、前端源码 / 产物同步、版本声明和文档链接校验通过，构建校验按 UTF-8 文本统一换行。本次未在用户 Linux / Docker 环境完成真实 QQ 扫码，不发送真实会话消息；此前 2.5.0 的真实授权与查询证据仍按原日期保留。
