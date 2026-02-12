# pyright: reportOptionalMemberAccess=false
# pyright: reportCallIssue=false
# pyright: reportArgumentType=false

import json
import inspect
from pathlib import Path


from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .core.sqlite import AsyncSQLiteDB
from .core.gok_data import GOKServer
from .core.gok_commands import GOKCommands


@register("astrbot_plugin_gok", 
          "fxdyz", 
          "通过接口获取王者荣耀游戏数据", 
          "1.0.1",
          "https://github.com/qsc20001102/astrbot_plugin_gok.git"
)
class GokApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        #获取配置
        self.conf = config

        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_gok")

        # SQLite本地路径
        self.sqlite_path = Path(self.local_data_dir) /"sqlite.db"
        logger.info(f"SQLite数据文件路径：{self.sqlite_path}")

        # 读取API配置文件
        self.api_file_path = Path(__file__).parent / "data" / "api_config.json"
        with open(self.api_file_path, 'r', encoding='utf-8') as f:
            self.api_config = json.load(f)  

        # 初始化数据
        # 声明指令集
        self.command_map = {}
        # 指令前缀功能
        self.prefix_en = self.conf.get("prefix").get("enable")
        self.prefix_text = self.conf.get("prefix").get("text")
        if not self.prefix_text:
            self.prefix_text = "王者"
        if self.prefix_en:
            logger.info(f"已启用指令前缀功能，前缀为：{self.prefix_text}")
        else:
            logger.info(f"未启用指令前缀功能。")

        logger.info("GOK 插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        try:
            # sqlite 实例化
            self.sql_db = AsyncSQLiteDB(self.sqlite_path)
            await self.sql_db.connect()
            await self.sql_db.execute("""
            CREATE TABLE IF NOT EXISTS users(
                gokid INTEGER,
                name TEXT                          
            )
            """)
            # 王者功能 实例化
            self.gokfun = GOKServer(self.api_config, self.conf, self.sql_db)
            # 发送消息实例化
            self.gokmag = GOKCommands(self.gokfun)
        except Exception as e:
            logger.error(f"功能模块初始化失败: {e}")
            raise

        # 指令集
        self.ini_command_map()

        logger.info("GOK 异步插件初始化完成")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        if self.gokfun:
            await self.gokfun.close()
            self.gokfun = None

        if self.sql_db:
            await self.sql_db.close()
            self.sql_db = None

        logger.info("GOK 插件已卸载/停用")


    def parse_message(self, text: str) -> list[str] | None:
        """消息解析"""
        text = text.strip()
        if not text:
            return None

        # 前缀模式
        if self.prefix_en:
            prefix = self.prefix_text
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            else:
                # 非前缀消息，直接忽略
                return None

        return text.split()


    async def _call_with_auto_args(self, handler, event: AstrMessageEvent, args: list[str]):
        """指令执行函数"""
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())

        call_args = []
        arg_index = 0

        for p in params:
            if p.name == "self":
                continue

            if p.name == "event":
                call_args.append(event)
                continue

            if arg_index < len(args):
                raw = args[arg_index]
                arg_index += 1
                try:
                    if p.annotation is int:
                        call_args.append(int(raw))
                    elif p.annotation is float:
                        call_args.append(float(raw))
                    else:
                        call_args.append(raw)
                except Exception:
                    call_args.append(p.default)
            else:
                if p.default is not inspect._empty:
                    call_args.append(p.default)
                else:
                    raise ValueError(f"缺少参数: {p.name}")

        # 只允许 coroutine
        return await handler(*call_args)
    

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """解析所有消息"""
        if not self.command_map:
            logger.debug("插件尚未初始化完成，忽略消息")
            return
        parts = self.parse_message(event.message_str)
        if not parts:
            logger.debug("未触发指令，忽略消息")
            return

        cmd, *args = parts
        handler = self.command_map.get(cmd)
        if not handler:
            logger.debug("指令函数为空，忽略消息")
            return

        try:
            event.stop_event()
            ret = await self._call_with_auto_args(handler, event, args)
            if ret is not None:
                yield ret
        except Exception as e:
            logger.exception(f"指令执行失败: {cmd}, error={e}")
            yield event.plain_result("参数错误或执行失败")


    def ini_command_map(self):
        """初始化指令集"""
        self.command_map = {
            "王者功能": self.gokmag.gok_helps,
            "王者战绩": self.gokmag.gok_zhanji,
            "王者资料": self.gokmag.gok_ziliao,
            "上榜战力": self.gokmag.gok_zhanli,
            "角色查看": self.gokmag.gok_user_all,
            "角色添加": self.gokmag.gok_user_add,
            "角色修改": self.gokmag.gok_user_update,
            "角色删除": self.gokmag.gok_user_delete,
            "角色查询": self.gokmag.gok_user_select
        }



