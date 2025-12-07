import json
import asyncio
from pathlib import Path
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .core.async_mysql import AsyncMySQL
from .core.WZRYFunction import WZRYFunction



@register("astrbot_plugin_gok", 
          "飞翔大野猪", 
          "通过接口接口获取王者荣耀游戏数据", 
          "1.0.0",
          "https://github.com/qsc20001102/astrbot_plugin_gok"
)
class GokApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        #获取配置
        self.conf = config
        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_gok")
        # api数据文件
        self.api_file_path = Path(__file__).parent / "api_config.json"
        # 读取文件内容
        with open(self.api_file_path, 'r', encoding='utf-8') as f:
            self.api_config = json.load(f)  
        # 初始化数据
        logger.info("王者荣耀插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        # 数据库配置
        db_config = {
            'host': '38.12.28.24',
            'port': 3306,
            'user': 'asrtbot',
            'password': 'qsc123456',
            'db': 'asrtbot',  
            'charset': 'utf8mb4',
            'autocommit': True
        }        
        #创建类实例
        self.db = AsyncMySQL(db_config)
        self.wzry = WZRYFunction(self.api_config,self.db)
        # 周期函数调用
    

        logger.info("王者荣耀插件创建实例完成")


    @filter.command_group("王者")
    def wz(self):
        pass


    @wz.command("列表")
    async def wz_yingdilist(self, event: AstrMessageEvent):
        """王者 用户列表"""
        try:
            data = await self.wzry.all_user()
            logger.info(f"王者荣耀营地列表查询结果{data}")
            yield event.plain_result(data)
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 

    @wz.command("添加")
    async def wz_adduesr(self, event: AstrMessageEvent,id: str,name: str):
        """王者 添加用户"""
        try:
            data = await self.wzry.add_user(id,name)
            yield event.plain_result(data)
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 

    @wz.command("修改")
    async def wz_updateuser(self, event: AstrMessageEvent,id: str,name: str):
        """王者 修改用户"""
        try:
            data = await self.wzry.update_user(id,name)
            yield event.plain_result(data)
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 
    
    @wz.command("删除")
    async def wz_deleteuser(self, event: AstrMessageEvent,id: str):
        """王者 删除用户"""
        try:
            data = await self.wzry.delete_user(id)
            yield event.plain_result(data)
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 

    @wz.command("战绩")
    async def wz_zhanji(self, event: AstrMessageEvent,name: str = "飞翔大野猪",option: str = "0"):
        """王者 战绩 营地ID 对局类型"""
        
        try:
            data = await self.wzry.zhanji(name,option)
            # logger.info(f"王者荣耀战绩查询结果{data}")
            #prompt = f"{data['data']}\n"
            #prompt += f"以上数据是获取到的王者荣耀战绩信息，请根据这些数据生成一两句话的战绩总结，突出玩家的优势和特点，语言风格轻松幽默，适合在游戏群内分享。"
            if data["code"] == 200:
                url = await self.html_render(data["temp"],{"data":data["data"]}, options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
                return
            #provider_id = await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)
            #llm_resp = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt,)
            #out = llm_resp.completion_text
            #yield event.plain_result(f"{out}") 
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @wz.command("资料")
    async def wz_ziliao(self, event: AstrMessageEvent,name: str = "489048724"):
        """王者 战绩 营地ID 对局类型"""
        try:
            data = await self.wzry.ziliao(name)
            logger.info(f"输出结果{data}")
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 

    @filter.command_group("仇人")
    def bilei(self):
        pass

    @bilei.command("列表")
    async def bilei_list(self, event: AstrMessageEvent,):
        """仇人 列表"""
        try:
            data = await self.wzry.bilei_all()
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @bilei.command("添加")
    async def bilei_add(self, event: AstrMessageEvent,name: str, text: str):
        """仇人 添加 名称 备注"""
        try:
            data = await self.wzry.bilei_add(name, text, event.get_sender_name())
            yield event.plain_result(data["msg"])
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @bilei.command("查找")
    async def bilei_select(self, event: AstrMessageEvent,name: str):
        """仇人 查找 名称（模糊查找）"""
        try:
            data = await self.wzry.bilei_select(name)
            if data["code"] == 200:
                url = await self.html_render(data["temp"], data["data"], options={})
                yield event.image_result(url)
            else:
                yield event.plain_result(data["msg"])
            return
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    @bilei.command("修改")
    async def bilei_update(self, event: AstrMessageEvent,id:int, name: str, text: str):
        """仇人 修改 ID 名称 备注"""
        try:
            data = await self.wzry.bilei_update(id, name, text, event.get_sender_name())
            yield event.plain_result(data["msg"])
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 

    @bilei.command("删除")
    async def bilei_delete(self, event: AstrMessageEvent,id:int):
        """仇人 删除 ID """
        try:
            data = await self.wzry.bilei_delete(id)
            yield event.plain_result(data["msg"])
        except Exception as e:
            logger.error(f"功能函数执行错误: {e}")
            yield event.plain_result("猪脑过载，请稍后再试") 


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await self.db.close_pool()
        # 后台进程销毁
        logger.info("王者荣耀插件已卸载/停用")