# 王者营地接口扩展参考

本文件记录 `ningxiaoxiao/hok_camp_api` 中可供本插件扩展参考的接口、协议与调用流程。它是开发参考，接口的在线可用性仍需用实际登录态验证。

- 记录日期：2026-10-07。
- 来源项目：[ningxiaoxiao/hok_camp_api](https://github.com/ningxiaoxiao/hok_camp_api)。
- 来源快照：[`13177c122bbf684cc793aab17089754978e66f93`](https://github.com/ningxiaoxiao/hok_camp_api/tree/13177c122bbf684cc793aab17089754978e66f93)，提交日期为 2026-08-01。
- 初始对照基线：v2.4.2，提交 `597a1f4`；随后开发版已接入昵称搜索、独立别名和战绩模式筛选。
- 初始记录范围：阅读源码、请求构造、字段读取与路由调用链；随后按用户要求实测了昵称搜索，结果见第 14 节。其他新增接口尚未进行真实请求验证。

文中的“源码已实现”表示来源项目存在对应代码；“源码读取”表示代码使用了该字段，但仓库没有提供真实响应样本供本次核验；“待实测”表示协议语义或线上行为尚未确认。请求中的 `<CAMP_ID>` 等均为占位符，响应结构示意也不代表一次真实请求结果。

## 1. 能力范围与扩展顺序

| 优先级建议 | 能力 | 腾讯远程接口 | 本插件 v2.4.2 状态 | 参考价值 |
| --- | --- | --- | --- | --- |
| 高 | 按昵称搜索营地用户 | `POST /search/getbytype` | 开发版已接入；先查别名、游戏昵称，再在线搜索 | 帮助用户找到营地 ID，展示候选用户供选择 |
| 高 | 按营地 ID 获取角色列表 | `POST /game/allrolelistv3` | 未接入；资料接口的 `roleList` 只选一个角色 | 获取角色列表、角色名称、区服描述与在线状态线索 |
| 中 | 按模式查询战绩 | `POST /game/morebattlelist` | 开发版支持全部、排位、巅峰（0/1/4） | 标准与娱乐模式仍可留作后续扩展 |
| 中 | 补充对局详情字段 | `POST /game/battledetail` | 已接入，只规范化部分字段 | 扩展分路、评分、治疗、控制、推塔等对局分析 |
| 中 | 对局回顾 | `POST /game/battleanalyze/old` | 未接入 | 经济曲线、关键事件、移动轨迹与复盘建议线索 |
| 中 | 角色英雄资料 | `POST /game/profile/herolist` | 未接入；已有赛季常用英雄数据 | 比较其与赛季接口的覆盖范围，再决定是否新增展示 |
| 低 | 营地用户资料 | `POST /userprofile/profile` | 未接入；已有新版综合资料查询 | 比较补充字段，作为兼容性研究对象 |
| 低 | 旧版角色概况 | `POST /game/profile/index` | 使用的是 `/game/koh/profile` | 比较旧版与新版字段和指定角色行为 |

来源：[接口客户端][S2]、[昵称搜索][S1]。优先级是结合本插件现状提出的开发建议。

### 必须保留的能力边界

1. 来源项目没有实现“仅凭数字游戏角色 `roleId` 反查营地 ID”的独立接口。
2. 昵称搜索的入参是 `name`，返回字段注释为 `nickname` 和 `friendUid`；不能仅凭这些名称断言它支持按游戏内角色名搜索。营地昵称、游戏角色名、纯数字 ID 的匹配行为均需验证。
3. 获取角色列表的方向是“营地 ID → 角色列表”，不能据此推断接口支持相反方向。
4. 上游路由通常取角色列表的第一个元素；完整的角色选择流程仍需要我们设计和实现。
5. 来源项目没有移植按英雄名或单英雄筛选战绩所需的 `historydetails` 功能，也没有给出足够的请求参数可直接参考。[已知限制][S4]

## 2. ID、域名与鉴权约定

### 2.1 ID 对照

| 名称 | 在来源项目中的用途 | 注意点 |
| --- | --- | --- |
| `uid` / `yd_user_id` / `friendUserId` / `targetUserId` | 被查询用户的营地 ID | `uid` 是服务层的命名，不应在产品中模糊地标成游戏角色 ID |
| `friendUid` | 搜索结果中的用户标识，来源代码映射为 `uid` | 需在实测中用角色列表或资料接口验证结果对应的营地账号 |
| `userId` / 请求头 `userId` / 配置 `user` | 发起请求的登录账号 ID | 查询他人时，它与目标营地 ID 可以不同 |
| `roleId` / `targetRoleId` | 营地角色接口返回或使用的角色标识 | 不自动等同于游戏内个人主页显示的数字 ID |
| `playerId` | 对局详情角色中的玩家标识，用于对局回顾请求 | 来源代码单独提取，不能用 `roleId` 直接替代 |
| `playerID` | 回顾轨迹条目中的标识拼写 | 来源分析脚本用它匹配 `matchInfo[].playerId`，大小写需区分 |
| `gameSeq` | 对局标识 | 回顾和详情使用；保留原值，避免浮点数转换 |
| `gameSvr` / `gameSvrId` | 对局服务器参数 | 战绩返回读取 `gameSvrId`，详情请求发送 `gameSvr` |
| `relaySvr` / `relaySvrId` | 对局中继服务器参数 | 战绩返回读取 `relaySvrId`，请求发送 `relaySvr` |
| `sid` | 来源服务自己的绑定键 | 仅用于本地 `sid → uid` 绑定，不是腾讯接口参数 |

来源：[搜索结果映射][S1]、[回顾参数解析][S2]、[绑定配置][S5]、[轨迹匹配脚本][S8]。

### 2.2 腾讯远程域名

| 基础地址 | 用途 |
| --- | --- |
| `https://kohcamp.qq.com` | 搜索、战绩、资料、英雄资料、对局详情和对局回顾 |
| `https://ssl.kohsocialapp.qq.com:10001` | `allrolelistv3` 角色列表 |
| `https://pvp.qq.com` | 静态英雄目录，见第 10 节 |

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

| 字段号 | Wire type | 编码类型 | 来源发送值 | 已确认含义 |
| --- | --- | --- | --- | --- |
| 1 | 0 | varint | `1011` | 固定常量；搜索分类含义待确认 |
| 2 | 2 | 长度前缀字节串 | `name` 的 UTF-8 字节 | 搜索词 |
| 3 | 0 | varint | `1` | 固定常量；是否为页码待确认 |
| 4 | 0 | varint | `10` | 固定常量；是否为每页数量待确认 |
| 7 | 2 | 长度前缀字节串 | 字符串 `"0"` | 固定常量；是否为游标待确认 |

来源只实现这组固定参数。后续不能直接将字段 3、4、7 宣称为完整分页协议，应先比较多组真实搜索响应。[请求构造][S1]

### 3.3 响应结构与输出映射

来源解析沿以下嵌套字段路径读取用户详情，每层都支持重复字段：

```text
root.field[3] → data.field[1] → userGroup.field[25] → user.field[2] → detail
```

这些层级名称来自源码注释，不代表已取得腾讯的正式 schema。

| `detail` 字段号 | 来源读取类型 | 输出键 | 源码注释 / 用途 |
| --- | --- | --- | --- |
| 17 | varint | `uid` | `friendUid`，转换为字符串 |
| 2 | 字节串 | `name` | `nickname`，UTF-8 文本 |
| 3 | 字节串 | `avatar` | `avatarUrl` |
| 10 | varint | `level` | 等级，输出为字符串 |
| 28 | 字节串 | `dw` | `title1`，展示文字；具体段位语义待实测 |
| 37 | 字节串 | `region` | 地区文字；是否等同游戏区服待实测 |

来源缺失字符串输出空串，数字 `uid` / `level` 经过 `or ""` 后也可能输出空串。其结果不是游戏角色列表，里面没有解析 `roleId`。[响应映射][S1]

来源 `GET /query/show` 遇到空结果会返回一个带 `uid="---"` 的提示对象。这个占位对象是包装层生成的提示，不是腾讯返回的用户，不能用于后续角色查询。[包装行为][S3]

### 3.4 本插件接入位置

| 现有模块 | 需要处理的差异 |
| --- | --- |
| `core/http.py` | 开发版已在 `HttpResponse.body` 保留响应字节，同时兼容已有 `text` |
| `core/camp_client.py` | 开发版使用 `protobuf=True` 发送二进制并解析业务状态，沿用账号池重试 |
| `core/camp_api.py` | 开发版 `search_users` 返回去重后的候选用户集合 |
| `core/service.py` / `core/webui.py` | 开发版优先查精确别名与游戏昵称，处理多候选和空结果 |
| 页面 / 消息入口 | 开发版展示编号、昵称、地区、段位和营地 ID，支持 60 秒选择 |

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

| 表单字段 | 取值来源 | 说明 |
| --- | --- | --- |
| `friendUserId` | 用户输入或搜索结果中的营地 ID | 被查询用户 |
| `token` | 本次选中的登录账号 | 与请求头 token 一致 |
| `userId` | 本次选中的登录账号 ID | 与请求头 userid 一致 |

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

| 字段 | 来源代码的使用方式 | 扩展用途 |
| --- | --- | --- |
| `data[].roleId` | 转成字符串传给资料、英雄与详情接口 | 保留角色标识 |
| `data[].roleName` | 资料、战绩和绑定列表显示 | 角色选择项名称 |
| `data[].roleDesc` | 绑定列表读取 | 区服或角色描述线索；具体格式待确认 |
| `data[].gameOnline` | 绑定列表读取 | 在线状态线索；值类型与含义待确认 |

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

| `option` | 来源包装层的模式映射 | 验证状态 |
| --- | --- | --- |
| 0 | 全部 | 本插件已支持全部模式 |
| 1 | 排位 | 开发版已接入；本次真实请求返回的 30 条均归类为排位 |
| 2 | 标准 | 来源映射已实现，不应自行改称只包含某一种匹配模式 |
| 3 | 娱乐 | 来源映射已实现，具体模式集合待验证 |
| 4 | 巅峰 | 开发版已接入；本次真实请求为空，非空响应另有离线分类验证 |

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

| 路径（均在 `data.redRoles[]` / `data.blueRoles[]` 内） | 来源用途或线索 | 对本插件的价值 |
| --- | --- | --- |
| `basicInfo.roleId` | 匹配角色 | 严格定位用户选中的目标角色 |
| `basicInfo.playerId` | 回顾参数 | 获取对局回顾需要的玩家标识 |
| `basicInfo.isMe` | 来源参数补全中的匹配条件 | 查询他人时语义需确认，优先核对选中的 `roleId` |
| `battleRecords.position` | 来源转换为 `lane` | 展示该场实际分路 |
| `battleStats.healCnt` | 分析脚本读取 | 治疗数据线索 |
| `battleStats.ctrlTime` | 分析脚本读取 | 控制时长线索；单位待确认 |
| `battleStats.towerCnt` | 分析脚本读取 | 推塔数据线索 |
| `battleStats.buildingDamage` | 分析脚本读取 | 建筑伤害线索 |
| `battleStats.gradeGame` | 分析脚本读取 | 对局评分线索 |
| `battleStats.hurtTransRate` | 分析脚本读取 | 伤害转化相关字段；定义与比例尺度待确认 |
| `battleStats.sabchurthero` / `sabcbattle` / `sabcgrow` / `sabcsurvive` | 分析脚本组合输出 | 对局维度评级线索；枚举与准确名称待确认 |
| `heroBehavior` | 调试脚本输出 | 本人英雄历史表现相关结构线索 |
| `dataBehavior` / `dataBehaviorV2` | 调试脚本输出 | 更细的表现数据结构线索 |
| `dataBehaviorV2[].title` / `dataCounts[].name,data,dataNote` | 分析脚本读取 | 标题、指标、值和对照说明；单位待确认 |

来源：[参数补全与详情][S2]、[详情分析脚本][S9]、[统计结构探索][S10]。

来源的 `battleRecords.position` 映射如下，其注释称作者曾人工核对，本次没有重新核对真实对局：

| 值 | 来源映射 |
| --- | --- |
| 0 | 对抗路 |
| 1 | 中路 |
| 2 | 发育路 |
| 3 | 打野 |
| 4 | 游走 |

来源：[分路映射][S2]。这套编号与本插件英雄目录的 `roles`、奖牌的 `branchEvaluate` 是不同字段，不能共用一个编号表。

## 9. 对局回顾：`/game/battleanalyze/old`

### 9.1 地址与变体

```http
POST https://kohcamp.qq.com/game/battleanalyze/old
Content-Type: application/json; charset=UTF-8
```

来源函数还提供两个分支，分支存在于源码并不代表本次已确认线上可用：

| 条件 | 路径 | 状态 |
| --- | --- | --- |
| 默认 | `/game/battleanalyze/old` | 有参数补全与调试调用代码 |
| `beta=True` | `/game/betabattleanalyze/old` | 仅记录来源分支，范围与可用性待验证 |
| `kpl=True` | `/game/kplbattleanalyze/old` | 仅记录来源分支，范围与可用性待验证 |

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

| 字段 | 参数来源 | 来源发送行为 |
| --- | --- | --- |
| `gameSeq` | 战绩列表目标对局 | 转为字符串，总是发送 |
| `gameSvr` | 目标对局的 `gameSvrId` | 转为字符串，总是发送 |
| `relaySvr` | 目标对局的 `relaySvrId` | 非空时发送 |
| `playerId` | 详情中目标角色的 `basicInfo.playerId` | 非空时发送；README 与服务路由将其视为必要定位条件 |
| `h5Get` | 常量 | 数字 `1` |

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

| 路径（均在外层 `data` 中） | 源码读取或说明 | 可能的功能 |
| --- | --- | --- |
| `matchInfo[]` | 阵容、英雄、KDA、`userId`、`playerId` 等 | 对局成员信息与轨迹关联 |
| `camp1GoldArr` / `camp2GoldArr` | 双方经济序列 | 双方经济曲线 |
| `ecoDistance` | 经济差序列 | 优势变化与经济差图 |
| `camp1Gold` / `camp2Gold` | 分析脚本读取 | 终局经济线索 |
| `winCamp` | 分析脚本读取 | 胜方线索 |
| `keyEventArr[]` | README 说明包含关键事件及坐标 / 时间线索 | 关键事件时间线 |
| `keyEventArr[].eventType` | 分析脚本计数 | 事件分类；完整枚举待确认 |
| `keyEventArr[].viewX,viewY,killTime` | README 说明 | 坐标与时间字段；单位和适用事件待确认 |
| `extendEventArr[].eventList[]` | 调试脚本探索 | 更多事件线索 |
| `reportData.playerPosInfo[]` | 玩家轨迹结构 | 地图轨迹 |
| `reportData.playerPosInfo[].playerID` | 分析脚本匹配玩家 | 与 `matchInfo[].playerId` 关联 |
| `reportData.playerPosInfo[].posArr` | 位置序列，README 描述为 `[x,y]` | 移动轨迹；坐标尺度与采样间隔待确认 |
| `playBaseInfoArr[].deathPosArr` | README 说明 / 调试脚本探索 | 死亡位置分析 |
| `reportData.skillUsedInfo` | 调试脚本检查类型和内容 | 技能使用结构线索，schema 未确认 |
| `reportData.noMistakeText` | 分析脚本读取 | 复盘文字线索 |
| `reportData.adviceList` / `personBehaviorAdvices` | 分析脚本读取 | 建议结构线索 |

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

| 上游服务路由 | 输入 | 内部流程 / 返回 |
| --- | --- | --- |
| `GET /query/show` | `name` | Protobuf 昵称搜索，返回候选用户或包装层提示对象 |
| `GET /user/` | `uid` 或绑定的 `sid` | 角色列表取一个角色，再组合 `profile`、`profileIndex`、`heroList` |
| `GET /battle/history` | `uid` / `sid`，可带 `opt` | 返回角色名、角色 ID、场数与战绩列表；未逐局获取装备详情 |
| `GET /battle/preview` | `uid` / `sid`，可带 `opt` | 基于返回战绩计算场次、胜率、MVP 与模式统计 |
| `GET /battle/replay` | 自动模式 `uid` + 可选 `gameSeq`；直接模式对局参数 + `playerId` | 自动补齐参数或直接调用回顾接口 |
| `GET /bind/`、`/bind/un`、`/bind/switch`、`/bind/get`、`/bind/reload` | `sid` / `uid` 等 | 上游自己的本地账号绑定与配置操作 |
| `GET /health` | 无 | 服务健康状态 |

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

| 层 | 扩展职责 |
| --- | --- |
| `HttpClient` / `HttpResponse` | 二进制体和原始字节、现有超时 / 完整分块读取 / 响应大小限制 |
| `CampClient` | 固定目标域名、编码选择、按响应类型解析、当前账号凭据、频控与失效换号 |
| `CampDataApi` | 搜索、角色列表、英雄资料、回顾等业务封装，以及已有战绩查询选项 |
| 模型解析 | 区分营地 ID / 角色 ID / 玩家 ID，规范化字段，保留缺失状态 |
| `GokService` | 候选与角色选择、调用编排、已有对局定位和统计 |
| 页面 / 消息层 | 展示选择、图表和文本，不承担请求鉴权或原始协议解析 |
| `GokStorage` | 继续只保存用户设置和名称映射；角色选择持久化需先确定契约 |

### 12.3 保留现有约束

- 日志器统一从 `astrbot.api` 导入；日志和响应不包含 `token`、`userKey` 或完整鉴权头。
- 玩家资料、搜索候选、战绩与回顾实时获取，不新增玩家数据缓存。
- 网络或解析失败不自动判定为登录失效；隐藏资料与战绩遵循已有错误提示。
- 表单与二进制支持应补充到现有传输层，保留旧 JSON 调用的行为与账号重试。
- 原始二进制响应需要保持字节完整，不能经 UTF-8 解码后再编码还原。
- 本插件现有赛季接口与新版资料接口继续保留；新接口是否替代它们取决于实测字段覆盖。

## 13. 后续实现的验证记录模板

验证新功能时，可以为每个接口记录以下信息。样本应脱敏，凭据仍只保存在插件数据目录。

| 项目 | 需要记录的内容 |
| --- | --- |
| 接口版本 | 地址、客户端版本、验证日期、来源快照 |
| 输入身份 | 目标营地 ID / 角色 ID / 对局参数，示例使用占位符或脱敏值 |
| 请求编码 | JSON、表单或 Protobuf；具体字段和值类型 |
| 响应处理 | HTTP 状态、关键业务头、业务码、响应类型、是否解密或解压 |
| 正常行为 | 实际返回的字段路径、类型、单位与缺失条件 |
| 异常行为 | 登录失效、频控、隐藏信息、空列表、无匹配角色、参数缺失 |
| 账号一致性 | 换号后头与体的凭据仍一致，没有冷却有效账号 |
| 回归范围 | 原有资料、战绩、对局详情、名称映射和消息降级仍正常 |

有意义的离线验证包括 Protobuf 编码向量与截断响应、重复候选解析、角色空数组、跨域表单凭据随账号切换、筛选值跨页保持、正确匹配 `playerId`、复盘字段缺失时降级，以及解密后的压缩样本。真实接口验证应使用单独的主动联调入口，避免导入测试模块就发起联网请求。

本文件初始创建时没有新接口的真实验证结果；后续实测记录在第 14 节，未覆盖的验证项继续保留待实测状态。

## 14. 昵称搜索实测记录

2026-10-07，按用户要求使用“祈无恙”作为搜索词，通过本插件现有微信扫码登录取得登录态后，直接请求 `/search/getbytype`。

| 验证项 | 实际结果 |
| --- | --- |
| 请求编码 | 使用来源 `build_request` 构造 Protobuf，`Content-Type: application/x-protobuf` |
| 鉴权与客户端头 | 使用本插件 `CampClient._build_headers`，含当前登录态安全参数；客户端版本为 `10.111.0323` / `2057957801` |
| HTTP 状态 | `200` |
| 响应 Content-Type | `application/x-protobuf` |
| 响应体长度 | 2538 字节 |
| 业务状态 | 根字段 2，wire type 2，UTF-8 字符串 `success`；本次不是整型状态码 |
| 用户解析 | 按 `3 → 1 → 25 → 2` 路径解析出 2 个同名用户 |
| 已验证输出键 | `uid`、`name`、`avatar`、`level`、`dw`、`region` |
| 原始字节 | 二进制附件与结果中的 Base64 解码值一致 |

这次请求验证了当前扫码登录态、本插件请求头与来源搜索编码可以配合使用，也验证了上表中的一次成功响应结构。原始响应与用户明细作为此次聊天的文件输出交付，文档不保存玩家明细或登录凭据。

集成后的复验仍返回 2 个候选；使用其中一个 `uid` 调用现有 `/game/koh/profile`，确认得到同名游戏角色及有效 `roleId`。该次战绩首屏请求的 `option=0` 返回 30 条，`option=1` 返回 30 条且均归类为排位，`option=4` 返回空列表。结果用于协议验证，不保存玩家明细到本库。

仍待确认：搜索词精确匹配营地昵称还是游戏角色名、字段 1/3/4/7 的完整业务含义、分页、其他错误状态，以及数字 `roleId` 是否有独立反查能力。

## 15. 固定源码索引

以下链接固定到本次读取的提交，便于后续复核，避免仓库更新后行号与含义发生变化。

| 编号 | 文件 | 主要参考内容 |
| --- | --- | --- |
| S1 | [app/search.py][S1] | Protobuf 搜索请求、嵌套响应、输出映射 |
| S2 | [app/camp_api.py][S2] | 腾讯接口常量、请求头、角色 / 资料 / 战绩 / 回顾调用 |
| S3 | [app/main.py][S3] | 包装路由、模式选项、组合资料和绑定结果 |
| S4 | [README.md][S4] | 回顾字段说明与尚未实现的能力 |
| S5 | [app/config.py][S5] | 登录凭据来源与本地绑定语义 |
| S6 | [app/crypto.py][S6] | XXTEA、gzip / zlib 解密处理 |
| S7 | [dbg_search.py][S7] | 搜索响应结构探索；其中早期探测请求未覆盖 Protobuf Content-Type，正式实现以 S1 为准 |
| S8 | [analyze2.py][S8] | 回顾成员 `userId` / `playerId` 与轨迹关联 |
| S9 | [dbg_all.py][S9] | 详情统计和 `dataBehaviorV2` 字段读取 |
| S10 | [dbg_stats.py][S10] | `battleStats` / `heroBehavior` 等结构探索 |
| S11 | [analyze.py][S11] | 回顾经济、事件与建议字段探索 |
| S12 | [dbg_events.py][S12] | 事件与技能信息结构探索 |

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
