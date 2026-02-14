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
            "王者功能": self.gok_helps,
            "王者战绩": self.gok_zhanji,
            "王者资料": self.gok_ziliao,
            "上榜战力": self.gok_zhanli,
            "角色查看": self.gok_user_all,
            "角色添加": self.gok_user_add,
            "角色修改": self.gok_user_update,
            "角色删除": self.gok_user_delete,
            "角色查询": self.gok_user_select
        }


    async def plain_msg(self, event: AstrMessageEvent, action):
        """最终将数据整理成文本发送"""
        data= await action()
        try:
            if data["code"] == 200:
                await event.send( event.plain_result(data["data"]))
            else:
                await event.send(event.plain_result(data["msg"])) 
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def T2I_image_msg(self, event: AstrMessageEvent, action):
        """最终将数据渲染成图片发送"""
        data = await action()
        try:
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                await event.send(event.image_result(url)) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def image_msg(self, event: AstrMessageEvent, action):
        """最终将数据整理成图片发送"""
        data = await action()
        try:
            if data["code"] == 200:
                await event.send(event.image_result(data["data"])) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def T2I_image_and_plain_msg(self, event: AstrMessageEvent, action):
        """战绩定制功能"""
        data = await action()
        # 发送渲染战绩图片
        try:
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                await event.send(event.image_result(url)) 
            else:
                await event.send(event.plain_result(data["msg"])) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 
        # 对战绩进行锐评
        try:
            if data["code"] == 200 and data["comment"]["en"]:
                # 确定使用模型
                if data["comment"]["provider"] =="":
                    umo = event.unified_msg_origin
                    provider_id = await self.context.get_current_chat_provider_id(umo=umo)
                else:
                    provider_id = data["comment"]["provider"]

                # 模型提示词构建
                prompt = "请根据下面提供的王者荣耀最近10把的战绩数据，用简短的一句话进行锐评吐槽。"
                prompt += f"这是战绩列表\n{data['comment']['data']}\n"
                prompt += f"gametime 字段 对局开始时间\n"
                prompt += f"killcnt 字段 击杀数\n"
                prompt += f"deadcnt 字段 死亡数\n"
                prompt += f"assistcnt 字段 助攻数\n"
                prompt += f"gameresult 字段 1代表胜利 2代表失败 3代表平局\n"
                prompt += f"mvpcnt 字段 1代表是胜利方MVP 0表示不是\n"
                prompt += f"losemvp 字段 1代表是失败方MVP 0表示不是\n"
                prompt += f"gradeGame 字段 系统给的评分，满分16分\n"

                # 调用模型
                llm_resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
                # 发送消息
                await event.send(event.plain_result(llm_resp.completion_text)) 

        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            await event.send(event.plain_result("猪脑过载，请稍后再试")) 


    async def gok_helps(self, event: AstrMessageEvent):
        """王者功能"""
        return await self.T2I_image_msg(event, self.gokfun.helps)
    
    async def gok_zhanji(self, event: AstrMessageEvent,name: str,option:str = 0):
        """王者战绩"""
        return await self.T2I_image_and_plain_msg(event, lambda: self.gokfun.zhanji(name ,option))
    
    async def gok_ziliao(self, event: AstrMessageEvent,name: str):
        """王者资料"""
        return await self.T2I_image_msg(event, lambda: self.gokfun.ziliao(name))
    
    async def gok_zhanli(self, event: AstrMessageEvent, hero: str, type: str = "aqq"):
        """英雄战力 名称 大区"""
        return await self.plain_msg(event, lambda: self.gokfun.zhanli(hero,type))
    
    async def gok_user_all(self, event: AstrMessageEvent):
        """角色查看"""
        return await self.T2I_image_msg(event, self.gokfun.all)
    
    async def gok_user_add(self, event: AstrMessageEvent, gokid: int, name: str):
        """角色添加 王者营地ID 名称"""
        return await self.plain_msg(event, lambda: self.gokfun.add(gokid,name))
    
    async def gok_user_update(self, event: AstrMessageEvent, gokid: int, name: str):
        """角色修改 王者营地ID 名称"""
        return await self.plain_msg(event, lambda: self.gokfun.update(gokid,name))
    
    async def gok_user_delete(self, event: AstrMessageEvent, gokid:int):
        """角色删除 王者营地ID"""
        return await self.plain_msg(event, lambda: self.gokfun.delete(gokid))
    
    async def gok_user_select(self, event: AstrMessageEvent, gokid):
        """角色查询 王者营地ID"""
        return await self.T2I_image_msg(event, lambda: self.gokfun.select(gokid))