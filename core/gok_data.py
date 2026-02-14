# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportCallIssue=false

from datetime import datetime
from typing import Dict, Any, Optional, List, Union
import base64

from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .request import APIClient
from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template,extract_fields

class GOKServer:
    def __init__(self, api_config, config:AstrBotConfig, sqlite:AsyncSQLiteDB ):
        self._api = APIClient()
        # 引用API配置文件
        self._api_config = api_config
        # 引用插件配置文件
        self._config = config
        # 引用数据库类
        self._sql_db = sqlite

        # 获取配置中的 Token
        self.token = self._config.get("ytapi_token", "")
        if  self.token == "":
            logger.info("获取配置token失败，请正确填写token,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置token成功。{self.token}")


    async def close(self):
        """释放底层 APIClient 资源"""
        if self._api:
            await self._api.close()
            self._api = None


    def _init_return_data(self) -> Dict[str, Any]:
        """初始化标准的返回数据结构"""
        return {
            "code": 0,
            "msg": "功能函数未执行",
            "data": {}
        }
    

    async def _base_request(
            self, 
            config_key: str, 
            method: str, 
            params: Optional[Dict[str, Any]] = None, 
            out_key: Optional[str] = "data"
        ) -> Optional[Any]:
            """
            基础请求封装，处理配置获取和API调用。
            
            :param config_key: 配置字典中对应 API 的键名。
            :param method: HTTP方法 ('GET' 或 'POST')。
            :param params: 请求参数或 Body 数据。
            :param out_key: 响应数据中需要提取的字段。
            :return: 成功时返回提取后的数据，失败时返回 None。
            """
            try:
                api_config = self._api_config.get(config_key)
                if not api_config:
                    logger.error(f"配置文件中未找到 key: {config_key}")
                    return None
                
                # 复制 params，避免修改原始配置模板
                request_params = api_config.get("params", {}).copy()
                if params:
                    request_params.update(params)

                url = api_config.get("url", "")
                if not url:
                    logger.error(f"API配置缺少 URL: {config_key}")
                    return None
                    
                if method.upper() == 'POST':
                    data = await self._api.post(url, data=request_params, out_key=out_key)
                else: # 默认为 GET
                    data = await self._api.get(url, params=request_params, out_key=out_key)
                
                if not data:
                    logger.warning(f"获取接口信息失败或返回空数据: {config_key}")
                
                return data
                
            except Exception as e:
                logger.error(f"基础请求调用出错 ({config_key}): {e}")
                return None


    # --- 业务功能函数 ---
    async def helps(self) -> Dict[str, Any]:
        """功能"""
        return_data = self._init_return_data()
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("helps.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
            
        return_data["code"] = 200
   
        return return_data


    async def add(self,gokid: int, name: str) -> Dict[str, Any]:
        """角色添加 王者营地ID 角色"""
        return_data = self._init_return_data()
        
        # 添加数据
        try:
            await self._sql_db.insert(
                "users",
                {
                    "gokid": gokid,
                    "name": name,
                }
            )

        except FileNotFoundError as e:
            logger.error(f"添加角色失败: {e}")
            return_data["msg"] = "添加角色失败"
            return return_data

        return_data["data"] = (
            "角色添加成功\n"
            f"王者营地ID：{gokid}\n"
            f"角色名称：{name}\n"
        )  

        return_data["code"] = 200
   
        return return_data
    

    async def all(self) -> Dict[str, Any]:
        """角色查看"""
        return_data = self._init_return_data()
        

        # 查询数据
        try:
            data = await self._sql_db.select_all("users")
        except FileNotFoundError as e:
            logger.error(f"查看角色失败: {e}")
            return_data["msg"] = "查看角色失败"
            return return_data

        if not data:
            return_data["msg"] = "未找到角色数据"
            return return_data
        

        # 加载模板
        try:
            return_data["temp"] = await load_template("jueshe.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        # 数据处理
        return_data["data"]["lists"] = data
        
        return_data["code"] = 200
   
        return return_data
    

    async def select(self, name) -> Dict[str, Any]:
        """角色查询 名称"""
        return_data = self._init_return_data()
        
        # 判断输入是否为整数
        try:
            int(name)
            if int(name) >=100000000:
                like = "gokid LIKE ?"
            else:
                raise Exception("id数据异常")
        except (ValueError, TypeError, Exception):
            like = "name LIKE ?"

        # 模糊拼接
        like_name = f"%{name}%"

        # 查询数据
        try:
            data = await self._sql_db.select_all(
                "users",
                like,
                (like_name,)
            )
        except FileNotFoundError as e:
            logger.error(f"查询角色失败: {e}")
            return_data["msg"] = "查询角色失败"
            return return_data

        if not data:
            return_data["msg"] = "未查询到角色数据"
            return return_data
        

        # 加载模板
        try:
            return_data["temp"] = await load_template("jueshe.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        # 数据处理
        return_data["data"]["lists"] = data
        
        return_data["code"] = 200
   
        return return_data
    

    async def update(self, gokid:int, name: str) -> Dict[str, Any]:
        """角色修改 王者营地ID 角色"""
        return_data = self._init_return_data()
        
        data = await self._sql_db.select_one(
                "users",
                "gokid=?",
                (gokid,)
            )

        if not data:
            return_data["msg"] = "没有当前ID"
            return return_data
        

        # 修改数据
        try:
            await self._sql_db.update(
                "users",
                {
                    "name": name,
                },
                "gokid=?",
                (gokid,)
            )

        except FileNotFoundError as e:
            logger.error(f"避雷修改失败: {e}")
            return_data["msg"] = "避雷修改失败"
            return return_data

        return_data["data"] = (
            "角色修改成功\n"
            f"王者营地ID：{gokid}\n"
            f"角色名称：{name}\n"
        )  

        return_data["code"] = 200
   
        return return_data
    

    async def delete(self, gokid:int) -> Dict[str, Any]:
        """角色删除 王者营地ID"""
        return_data = self._init_return_data()
        
        data = await self._sql_db.select_one(
                "users",
                "gokid=?",
                (gokid,)
            )

        if not data:
            return_data["msg"] = "没有当前ID"
            return return_data

        # 删除
        try:
            await self._sql_db.delete(
                "users",
                "gokid=?",
                (gokid,)
            )

        except FileNotFoundError as e:
            logger.error(f"角色删除失败: {e}")
            return_data["msg"] = "角色删除失败"
            return return_data

        return_data["data"] = f"角色删除成功。王者营地ID：{gokid}"
 
        return_data["code"] = 200
   
        return return_data


    async def get_gokid(self,name: str):
        # 判断输入是否为整数
        try:
            # 直接返回输入
            int(name)
            if int(name) >=100000000:
                gokid = name
                return gokid
            else:
                raise Exception("输入不是ID")
        except (ValueError, TypeError, Exception):
            # 查询数据
            try:
                data = await self._sql_db.select_one(
                    "users",
                    "name=?",
                    (name,)
                )

                if not data:
                    gokid = None
                    return gokid
                
                gokid = data['gokid']
                return gokid
            except FileNotFoundError as e:
                logger.error(f"查询角色失败: {e}")
                gokid = None
                return gokid
   

    async def zhanji(self,name: str ,option: str):
        """
        战绩查询
        """
        return_data = self._init_return_data()

        # 获取配置中的 Token
        token = self._config.get("ytapi_token", "")
        if  token == "":
            return_data["msg"] = "系统未配置API访问Token"
            return return_data
        
        self.comment_en = self._config.get("comment").get("enable")
        logger.debug(self.comment_en)
        self.comment_provider = self._config.get("comment").get("select_provider")
        logger.debug(self.comment_provider)
        
        # ID查询
        gokid = await self.get_gokid(name)

        if not gokid :
            return_data["msg"] = "未查询到该用户，请确认输入正确的角色或营地ID"
            return  return_data
        
        #更新参数
        params = {"id": gokid, "option": option, "key": token}
        
        # 需要提取的字段
        fields = ["gametime","killcnt","deadcnt","assistcnt","gameresult","mvpcnt","losemvp","mapName",
                  "oldMasterMatchScore","newMasterMatchScore","usedTime","winNum","failNum","roleJobName","stars","desc",
                  "gradeGame","heroIcon","godLikeCnt", "firstBlood","hero1TripleKillCnt","hero1UltraKillCnt","hero1RampageCnt","evaluateUrlV3","mvpUrlV3"]
        
        

        # 获取数据
        data: Optional[List[Dict[str, Any]]] = await self._base_request("gok_zhanji", "GET", params=params)       
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return  return_data  

        # 处理返回数据
        try:
            # 提取锐评数据
            if self.comment_en:
                return_data["comment"] = {}
                comment = ["gametime","killcnt","deadcnt","assistcnt","gameresult","mvpcnt","losemvp","gradeGame"]
                comments = extract_fields(data['list'], comment)
                comments = comments[:10]
                return_data["comment"]["data"] = comments 
                return_data["comment"]["provider"] = self.comment_provider  
                return_data["comment"]["en"] = self.comment_en  

            # 提取字段
            result = extract_fields(data['list'], fields)
            result = result[:25]
            # 数据处理
            for m in result:
                minutes = m["usedTime"] // 60
                seconds = m["usedTime"] % 60
                m["time_str"] = f"{minutes}:{seconds:02d}"
                
            return_data["data"]["data"] = result  
            
        except Exception as e:
            logger.error(f"处理数据时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data

        # 加载模板
        try:
            return_data["temp"] = await load_template("wangzhezhanji.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data 
          
        return_data["code"] = 200  

        return return_data


    async def ziliao(self, name: str):
        return_data = self._init_return_data()
        # 获取配置中的 Token
        token = self._config.get("ytapi_token", "")
        if  token == "":
            return_data["msg"] = "系统未配置API访问Token"
            return return_data
        
        # ID查询
        gokid = await self.get_gokid(name)

        if not gokid :
            return_data["msg"] = "未查询到该用户，请确认输入正确的角色或营地ID"
            return  return_data

        #更新参数
        params = {"id": gokid, "key": token}

        # 获取数据
        data: Optional[List[Dict[str, Any]]] = await self._base_request("gok_ziliao", "GET", params=params, out_key="")   
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return  return_data  

        try:
            # 转 base64
            return_data["data"]["img_base64"] = base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.error(f"处理数据时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return  return_data

        # 加载模板
        try:
            return_data["temp"] = await load_template("wzry_zl.html")
        except FileNotFoundError:
            logger.error(f"加载模板失败")
            return_data["msg"] = "系统错误：模板文件不存在"
            return  return_data

        return_data["code"] = 200

        return return_data


    async def zhanli(self,hero: str, type: str):
        return_data = self._init_return_data()
        # 获取配置中的 Token
        token = self._config.get("nyapi_token", "")
        if  token == "":
            return_data["msg"] = "系统未配置API访问Token"
            return return_data

        #更新参数
        params = {"hero": hero, "type": type, "apikey": token}

        # 获取数据
        data: Optional[List[Dict[str, Any]]] = await self._base_request("gok_zhanli", "GET", params=params)   
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return  return_data  

        try:
            data0 = data['info']
            msg = "英雄的最低上榜地区战力\n"
            msg += f"英雄：{data0['name']}\n"
            msg += f"省标：{data0['province']}--战力：{data0['provincePower']}\n"
            msg += f"市标：{data0['city']}--战力：{data0['cityPower']}\n"
            msg += f"区标：{data0['area']}--战力：{data0['areaPower']}\n"
            msg += f"数据更新时间：{data0['updatetime']}\n"
            return_data["data"] = msg
        except Exception as e:
            logger.error(f"处理数据时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return  return_data

        return_data["code"] = 200

        return return_data
