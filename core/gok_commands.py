# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
import json
import shutil
import pathlib
import inspect
from pathlib import Path
from typing import Union
import asyncio

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .gok_data import GOKServer


class GOKCommands(Star):
    def __init__(self, gok_data:GOKServer):
        self.gokfun = gok_data


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


    async def gok_helps(self, event: AstrMessageEvent):
        """王者功能"""
        return await self.T2I_image_msg(event, self.gokfun.helps)
    

    async def gok_zhanji(self, event: AstrMessageEvent,name: str,option:str = 0):
        """王者战绩"""
        return await self.T2I_image_msg(event, lambda: self.gokfun.zhanji(name ,option))
    

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