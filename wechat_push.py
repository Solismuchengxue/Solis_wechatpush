# klippy status push to wechat
#
# Copyright (C) 2022 Cao Zheng <smile.caozheng@outlook.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

# 从新版本库中引用模块
from __future__ import annotations

import logging          # 引用日志
import requests         # 引用http请求
import base64           # 引用base64编码
import os               # 引用系统
import socket           # 引用套接字
import re               # 引用正则
import time             # 引用时间
from datetime import datetime  # 引用日期时间

# 字体文件路径（基于脚本实际所在目录，兼容软链接）
_FONT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fonts", "FreeMono.ttf")

# 从PIL库中引用模块
from PIL import Image, ImageFont, ImageDraw

# Annotation imports 动态引用moonranker模块的常量
from typing import (
    TYPE_CHECKING,      # 类型检查处理
    Any,                # Any类型提示对象，用于定义返回值
    Optional,           # Optional类型提示对象，用于定义返回值
    Dict,               # Dict类型提示对象，用于定义返回值
    List,               # List类型提示对象，用于定义返回值
)
if TYPE_CHECKING:       #如果类型检查true，
    from confighelper import ConfigHelper   # 从引用confighelper库引用ConfigHelper模块
    from .klippy_apis import KlippyAPI      # 从引用.klippy_apis库引用KlippyAPI模块  
    DBComp = database.MoonrakerDatabase     # 别名DBComp指向database.MoonrakerDatabase

# 微信推送类
class WechatPush:

    # 类构造器初始化（类本身，通过ConfigHelper模块创建config对象）
    def __init__(self, config: ConfigHelper) -> None:

        # 属性：服务（通过ConfigHelper模块创建服务）
        self.server = config.get_server()

        # 属性：最后打印状态（创建字符串字典）
        self.last_print_stats: Dict[str, Any] = {}

        # 属性：企业微信应用私钥（从配置文件导入并将空格替换为空）
        self.corpsecret: str = config.get('corp_secret')
        self.corpsecret = self.corpsecret.replace(" ", "")

        # 属性：企业微信应用ID（从配置文件导入并将空格替换为空）
        self.agentid: str = config.get('agent_id')
        self.agentid = self.agentid.replace(" ", "")

        # 属性：企业ID（从配置文件导入并将空格替换为空）
        self.corpid: str = config.get('corp_id')
        self.corpid = self.corpid.replace(" ", "")

        # 属性：接收消息的人（从配置文件导入并将空格替换为空）
        self.touser: str = config.get('to_user')
        self.touser = self.touser.replace(" ", "")
        
        # 属性：域名（从配置文件导入并将空格替换为空）
        self.domain: str = config.get('domain',None)
        if  self.domain is not None:
            self.domain = self.domain.replace(" ", "")

        # 属性：摄像头地址（从配置文件导入并将空格替换为空）
        self.camera: str = config.get('camera',None)
        if self.camera is not None:
            self.camera = self.camera.replace(" ", "")

        # 对象：DBComp（从服务中加载数据库组件）
        db: DBComp = self.server.load_component(config, "database")

        # 变量：数据库路径（取得数据库路径）
        db_path = db.get_database_path()

        # 属性：gcode路径（从数据库获取，失败则从file_manager组件获取，最后回退默认路径）
        self.gc_path: str = db.get_item(
            "moonraker", "file_manager.gcode_path", "").result()
        if not self.gc_path:
            try:
                fm = self.server.lookup_component('file_manager')
                if hasattr(fm, 'gcode_path'):
                    self.gc_path = fm.gcode_path
                elif hasattr(fm, '_gcode_path'):
                    self.gc_path = fm._gcode_path
            except Exception:
                pass
        if not self.gc_path:
            # 最后的回退：使用默认路径
            data_path = self.server.get_app_args().get('data_path', '')
            if data_path:
                self.gc_path = os.path.join(data_path, "gcodes")
            else:
                self.gc_path = os.path.expanduser("~/printer_data/gcodes")
        logging.info(f"G-code path: {self.gc_path}")

        # 属性：当前打印文件名（独立跟踪，所有状态推送都使用此文件名）
        self.current_filename: str = ""

        # 属性：打印实例名称（数据库中获取fluidd/mainsail的实例名称，如果失败返回hostname）
        self.print_name: str = db.get_item(
            "fluidd", "uiSettings.general.instanceName", "").result()
        if not self.print_name:
            self.print_name = db.get_item(
                "mainsail", "uiSettings.general.instanceName", "").result()
        if not self.print_name:
            self.print_name = self.server.get_host_info()['hostname']

        # 属性：最后打印状态（初始化空字典）
        self.last_print_stats: Dict[str, Any] = {}

        # 属性：当前打印统计数据（实时更新，供格式化使用）
        self.current_print_stats: Dict[str, Any] = {}

        # 属性：打印开始时间戳
        self.print_start_time: Optional[float] = None

        # 属性：当前进度（来自 virtual_sdcard）
        self.current_progress: float = 0.0

        self._token: Optional[str] = None
        self._token_expire: float = 0.0

        # 事件处理程序：处理开始（通过self.server.register_event_handler()方法注册）
        self.server.register_event_handler(
            "server:klippy_started", self._handle_started)
        
        # 事件处理程序：处理中断（通过self.server.register_event_handler()方法注册）
        self.server.register_event_handler(
            "server:klippy_shutdown", self._handle_shutdown)
        
        # 事件处理程序：状态更新（通过self.server.register_event_handler()方法注册）
        self.server.register_event_handler(
            "server:status_update", self._status_update)

        self.server.register_remote_method("send_wechat_test", self._handle_test_push)

    # 事件处理程序：处理开始的实现
    async def _handle_started(self, state: str) -> None:
        # 判断klippy的状态
        if state != "ready":
            return
        # 获取KlippyAPI组件
        kapis: KlippyAPI = self.server.lookup_component('klippy_apis')
        # 初始化订阅字典（同时订阅 print_stats 和 virtual_sdcard）
        sub: Dict[str, Optional[List[str]]] = {"print_stats": None, "virtual_sdcard": None}
        # 订阅"print_stats"对象
        try:
            result = await kapis.subscribe_objects(sub)
        except self.server.error as e:
            # 记录日志
            logging.info(f"Error subscribing to print_stats")
        # 将订阅结果存储在最后打印状态
        self.last_print_stats = result.get("print_stats", {})

        # ⭐ 从订阅初始响应中获取文件名（状态更新是diff，不会每次都发filename）
        if self.last_print_stats.get('filename'):
            self.current_filename = self.last_print_stats['filename']

        # 如果存在状态返回给变量state并记录日志
        if "state" in self.last_print_stats:
            state = self.last_print_stats["state"]
            logging.info(f"Job state initialized: {state}")

        if self._getAsToken() is None:
            self.server.add_warning(
                "[Wechat_Push] 凭证验证失败，请检查 moonraker.conf 中的"
                " corp_id / corp_secret / agent_id 是否正确。")
        else:
            logging.info("[Wechat_Push] 凭证验证成功，access_token 已缓存。")

    # 事件处理程序：处理中断的实现
    async def _handle_shutdown(self, state: str) -> None:
        # 当klippy关闭时，会调用该方法。该方法记录日志
        logging.info(f"Shutdown: {state}")

    async def _handle_test_push(self) -> None:
        self._pushState(state="complete", filename="[测试] wechat_push_test.gcode")

    # 事件处理程序：状态更新的实现
    async def _status_update(self, data: Dict[str, Any]) -> None:

        # 如果包含"webhooks"字段，则表示klippy已经关闭
        if "webhooks" in data:
            webhooks = data['webhooks']
            state = webhooks['state']
            state_message = webhooks['state_message']
            logging.info(f"Status: {state}")
            logging.info(f"Info: {state_message}")
            if state == "shutdown":
                # 报错停机
                self._pushState(state=state, text=state_message)

        # 如果包含"print_stats"字段，则表示打印状态发生了变化
        elif "print_stats" in data:
            print_stats = data['print_stats']

            # 保存最新的打印统计数据
            self.current_print_stats.update(print_stats)

            # 从 virtual_sdcard 更新进度
            if "virtual_sdcard" in data:
                vsd = data["virtual_sdcard"]
                if "progress" in vsd:
                    self.current_progress = vsd["progress"]

            # 文件名双重获取：当前更新中的 + 历史累积的，优先取非空的
            current_update_name = print_stats.get('filename', '')
            if current_update_name:
                self.current_filename = current_update_name
            history_name = self.last_print_stats.get('filename', '')
            filename = self.current_filename or history_name or ''

            state = print_stats.get('state')

            # 记录打印开始时间
            if state == "printing" and self.print_start_time is None:
                self.print_start_time = time.time()

            # 如果状态变了但文件名还是空，主动查询当前 print_stats 获取文件名
            if state and not filename:
                try:
                    kapis = self.server.lookup_component('klippy_apis')
                    result = await kapis.query_objects({"print_stats": ["filename"]})
                    ps = result.get("print_stats", {})
                    if ps.get("filename"):
                        self.current_filename = ps["filename"]
                        filename = self.current_filename
                except Exception:
                    pass

            if state == "printing":
                self._pushState(state=state, filename=filename)

            elif state == "complete":
                self._pushState(state=state, filename=filename)
                self.print_start_time = None
                self.current_progress = 0.0

            elif state == "error":
                self._pushState(state=state, text=print_stats.get('message', '未知错误'),
                                filename=filename)
                self.print_start_time = None
                self.current_progress = 0.0

            elif state == "paused":
                self._pushState(state=state, filename=filename)

            elif state in ("standby", "cancelled"):
                self._pushState(state=state, filename=filename)
                self.print_start_time = None
                self.current_progress = 0.0

            elif state:
                logging.info(f"其他状态：{state}")

            # 存储更新数据
            self.last_print_stats.update(print_stats)

    # 格式化时间戳为 HH:MM:SS
    @staticmethod
    def _fmt_time(t: Optional[float]) -> str:
        if t is None:
            return "--:--:--"
        return datetime.fromtimestamp(t).strftime("%H:%M:%S")

    # 格式化秒数为可读时长
    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        if not seconds:
            return "0秒"
        h, r = divmod(int(seconds), 3600)
        m, s = divmod(r, 60)
        parts = []
        if h: parts.append(f"{h}小时")
        if m: parts.append(f"{m}分")
        parts.append(f"{s}秒")
        return "".join(parts)

    # 方法：推送状态
    def _pushState(self, state: str, text: str = None, filename: str = None):
        logging.info(f"推送: state={state}, filename='{filename}'")
        tmp_path = f"/tmp/mwx_media_{os.getpid()}_{int(time.time() * 1000)}.png"
        dic = {}
        AsToken: str = self._getAsToken()
        if AsToken is None:
            return False

        # 初始化数据
        state_title = ""                    # 标题
        info = ""                           # 信息
        media_id = ""                       # 已上传临时图片的媒体ID
        media_path = None                   # 图片路径
        digest = ""                         # 内容
        color = ""                          # 颜色
    
        # 判断打印机状态
        if state == "shutdown":
            state_title = "停机"
            color = "red"
            now_str = self._fmt_time(time.time())
            info = f"状态：设备停机"
            info += f"\n停机时间: {now_str}"
            if text:
                info += f"\n原因: {text}"
            digest = f"设备停机: {text[:60] if text else '未知'}"

            # 创建图片
            if self.camera is None:
                im = Image.new("RGB", (300, 100), (64, 44, 46))
                dr = ImageDraw.Draw(im)
                font = ImageFont.truetype(_FONT_PATH, 12)
                dr.text((35, 5), info, font=font, fill="#FF5252")
                # im.show()
                im.save(tmp_path)
            else:
                f = open(tmp_path, "wb")
                f.write(requests.get("http://localhost" + self.camera).content)
                f.close()
                media_path = tmp_path

            # 上传临时图片
            media_id = self._uploadImage(tmp_path)

        elif state == "printing":
            state_title = "开始打印"
            color = "green"
            start_str = self._fmt_time(self.print_start_time)
            prog = self.current_progress * 100
            info = f"状态：正在打印"
            info += f"\n开始时间: {start_str}"
            info += f"\n进度: {prog:.1f}%"
            digest = f"开始打印: {filename}"

            if self.camera is None and (media_path is None or not os.path.exists(media_path)):
                # 创建图片
                im = Image.new("RGB", (300, 80), (255, 255, 255))
                dr = ImageDraw.Draw(im)
                font = ImageFont.truetype(_FONT_PATH, 12)
                dr.text((35, 5), info, font=font, fill="#00FF7F")
                # im.show()
                im.save(tmp_path)
                
            else:
                if self.camera is not None:
                    f = open(tmp_path, "wb")
                    f.write(requests.get("http://localhost" + self.camera).content)
                    f.close()
                else:
                    # 没有摄像头且无上一张图片，创建空白图
                    im = Image.new("RGB", (300, 80), (255, 255, 255))
                    dr = ImageDraw.Draw(im)
                    font = ImageFont.truetype(_FONT_PATH, 12)
                    dr.text((35, 5), info, font=font, fill="#00FF7F")
                    im.save(tmp_path)

            media_path = tmp_path
            media_id = self._uploadImage(media_path)

        elif state == "complete":
            state_title = "打印结束"
            color = "blue"
            now_str = self._fmt_time(time.time())
            elapsed = self.current_print_stats.get('print_duration', 0)
            info = f"状态：打印完成"
            if self.print_start_time:
                info += f"\n完成时间: {now_str}"
            info += f"\n用时: {self._fmt_duration(elapsed)}"
            digest = f"打印完成: {filename}"

            # 尝试获取缩略图，如果失败则使用空白图
            thumb_path = None
            try:
                files = os.listdir(self.gc_path + "/.thumbs/")
                img = ".png"
                for file in files:
                    print(file)
                    if filename is not None:
                        match = re.search(filename.replace(
                            ".gcode", "-") + "(.*?)x(.*?).png", file)
                        if match and "32x32" not in file:
                            img = file
                            break
                thumb_path = self.gc_path + "/.thumbs/" + img
                if not os.path.exists(thumb_path):
                    thumb_path = None
            except (FileNotFoundError, OSError) as e:
                logging.warning(f"Thumbnail directory not accessible: {e}")
                thumb_path = None

            camera_available = self.camera is not None
            if camera_available:
                # 有摄像头，截取快照
                try:
                    f = open(tmp_path, "wb")
                    f.write(requests.get("http://localhost" + self.camera).content)
                    f.close()
                except Exception as e:
                    logging.error(f"Failed to fetch camera image: {e}")
                    camera_available = False  # 回退到缩略图或空白图

            if not camera_available:
                if thumb_path is not None and os.path.exists(thumb_path):
                    # 使用缩略图
                    import shutil
                    shutil.copy2(thumb_path, tmp_path)
                else:
                    # 创建空白图片
                    im = Image.new("RGB", (300, 80), (255, 255, 255))
                    dr = ImageDraw.Draw(im)
                    font = ImageFont.truetype(_FONT_PATH, 12)
                    dr.text((35, 5), info, font=font, fill="#00BFFF")
                    im.save(tmp_path)
                
            media_path = tmp_path
            media_id = self._uploadImage(media_path)

        elif state == "error":
            state_title = "错误"
            color = "red"
            now_str = self._fmt_time(time.time())
            info = f"状态：打印出错"
            info += f"\n出错时间: {now_str}"
            if text:
                info += f"\n原因: {text}"
            digest = f"打印错误: {text[:60] if text else '未知'}"
            media_path = tmp_path

            # 创建图片
            if self.camera is None:
                im = Image.new("RGB", (300, 100), (64, 44, 46))
                dr = ImageDraw.Draw(im)
                font = ImageFont.truetype(_FONT_PATH, 12)
                dr.text((35, 5), info, font=font, fill="#FF5252")
                # im.show()
                im.save(tmp_path)
            else:
                f = open(tmp_path, "wb")
                f.write(requests.get("http://localhost" + self.camera).content)
                f.close()


            # 上传临时图片
            media_id = self._uploadImage(media_path)

        elif state == "paused":
            # 暂停
            state_title = "打印暂停"
            color = "yellow"
            now_str = self._fmt_time(time.time())
            prog = self.current_progress * 100
            info = f"状态：打印暂停"
            info += f"\n暂停时间: {now_str}"
            info += f"\n进度: {prog:.1f}%"
            digest = f"打印暂停: {filename}"
            
            if self.camera is None:
                # 创建图片
                im = Image.new("RGB", (300, 80), (255, 255, 255))
                dr = ImageDraw.Draw(im)
                font = ImageFont.truetype(_FONT_PATH, 12)
                dr.text((35, 5), info, font=font, fill="#00BFFF")
                # im.show()
                im.save(tmp_path)
                media_path = tmp_path
            else:
                f = open(tmp_path, "wb")
                f.write(requests.get("http://localhost" + self.camera).content)
                f.close()
                media_path = tmp_path
                            
            media_id = self._uploadImage(media_path)

        elif state in ("standby", "cancelled"):
            # 取消
            state_title = "取消打印"
            color = "red"
            now_str = self._fmt_time(time.time())
            info = f"状态：取消打印"
            info += f"\n取消时间: {now_str}"
            digest = f"取消打印: {filename}"

            if self.camera is None and (media_path is None or not os.path.exists(media_path)):
                # 创建图片
                im = Image.new("RGB", (300, 80), (255, 255, 255))
                dr = ImageDraw.Draw(im)
                font = ImageFont.truetype(_FONT_PATH, 12)
                dr.text((35, 5), info, font=font, fill="#00BFFF")
                # im.show()
                im.save(tmp_path)
            else:
                if self.camera is not None:
                    f = open(tmp_path, "wb")
                    f.write(requests.get("http://localhost" + self.camera).content)
                    f.close()
                else:
                    # 没有摄像头且无上一张图片，创建空白图
                    im = Image.new("RGB", (300, 80), (255, 255, 255))
                    dr = ImageDraw.Draw(im)
                    font = ImageFont.truetype(_FONT_PATH, 12)
                    dr.text((35, 5), info, font=font, fill="#00BFFF")
                    im.save(tmp_path)
                
            media_path = tmp_path                
            media_id = self._uploadImage(media_path)
        else:
            logging.error("unknown state")
            return

        if self.camera is not None:
            img_html = '<img src="https://qyapi.weixin.qq.com/cgi-bin/media/get?access_token={access_token}&media_id={media}" style="width:100%;border-radius:8px;margin-top:8px;" />'.format(access_token=AsToken, media=media_id)
        else:
            img_html = ''

        if self.domain is None:
            hostname = self.server.get_host_info()['hostname']
        else:
            hostname = self.domain 

        ip = self._extract_ip()
        info_html = info.replace("\n", "</br>")

        # 状态对应的颜色和图标
        state_badge_color = {
            "shutdown": "#e74c3c", "error": "#e74c3c", "standby": "#e74c3c", "cancelled": "#e74c3c",
            "printing": "#27ae60", "complete": "#2980b9", "paused": "#f39c12"
        }.get(state, "#888888")
        state_emoji = {
            "shutdown": "🔴", "error": "❌", "standby": "⏹️", "cancelled": "⏹️",
            "printing": "🟢", "complete": "✅", "paused": "⏸️"
        }.get(state, "🔔")
        state_label = {
            "shutdown": "设备停机", "error": "打印错误", "standby": "取消打印", "cancelled": "取消打印",
            "printing": "正在打印", "complete": "打印完成", "paused": "打印暂停"
        }.get(state, state_title)

        html = f"""
<div style="background:#ffffff;border-radius:10px;padding:16px;font-family:-apple-system,BlinkMacSystemFont,&#39;Helvetica Neue&#39;,&#39;PingFang SC&#39;,&#39;Microsoft YaHei&#39;,sans-serif;color:#333333;">

  <!-- 状态标题 -->
  <div style="background:{state_badge_color};color:#ffffff;padding:12px 16px;border-radius:8px;text-align:center;font-size:18px;font-weight:bold;margin-bottom:14px;">
    {state_emoji} {state_label}
  </div>

  <!-- 打印机信息 -->
  <table style="width:100%;border-collapse:collapse;font-size:14px;line-height:1.8;">
    <tr>
      <td style="padding:6px 10px;color:#999999;white-space:nowrap;width:64px;">🖨️ 设备</td>
      <td style="padding:6px 10px;font-weight:bold;color:#333333;">{self.print_name}</td>
    </tr>
    <tr style="background:#f5f6f8;">
      <td style="padding:6px 10px;color:#999999;white-space:nowrap;">📄 文件</td>
      <td style="padding:6px 10px;word-break:break-all;color:#333333;">{filename if filename else '-'}</td>
    </tr>
    <tr>
      <td style="padding:6px 10px;color:#999999;white-space:nowrap;vertical-align:top;">📋 详情</td>
      <td style="padding:6px 10px;word-break:break-all;color:#333333;">{info_html}</td>
    </tr>
  </table>

  <!-- 分隔线 -->
  <div style="border-top:1px solid #e8e8e8;margin:12px 0;"></div>

  <!-- 访问地址 -->
  <table style="width:100%;border-collapse:collapse;font-size:14px;line-height:1.8;">
    <tr>
      <td style="padding:4px 10px;color:#999999;white-space:nowrap;width:64px;">🌐 域名</td>
      <td style="padding:4px 10px;"><a href="http://{hostname}/" style="color:{state_badge_color};text-decoration:none;font-weight:bold;">{hostname}</a></td>
    </tr>
    <tr style="background:#f5f6f8;">
      <td style="padding:4px 10px;color:#999999;white-space:nowrap;">📡 IP</td>
      <td style="padding:4px 10px;"><a href="http://{ip}/" style="color:{state_badge_color};text-decoration:none;font-weight:bold;">{ip}</a></td>
    </tr>
  </table>

  {('<!-- 图片 --><div style="margin-top:10px;">' + img_html + '</div>') if img_html else ''}

  <!-- 底部提示 -->
  <div style="text-align:center;margin-top:14px;padding:10px 8px;background:#f0faf0;border-radius:8px;border:1px solid #d4edda;">
    <a href="http://{ip}/" style="color:#27ae60;font-size:14px;font-weight:bold;text-decoration:none;">👆 点击「阅读原文」进入控制台</a>
  </div>

</div>"""

        logging.info("wechat")
        article = {
            'title': f"{state_emoji} [{self.print_name}] {state_label}",
            'thumb_media_id': media_id,
            'author': self.print_name,
            'content_source_url': f"http://{ip}/",
            'content': html,
            'digest': f"{state_emoji} {state_label} - {digest}"[:120]
        }
        dic = {'touser': self.touser, 'msgtype': "mpnews", 'agentid': self.agentid, 'mpnews': {
            'articles': [article]}, 'enable_duplicate_check': 0, 'duplicate_check_interval': 1800}

        r = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=" + AsToken, json=dic)
        if r.json()['errcode'] == 0:
            logging.info(f"Message push successfully: {r.json()['msgid']}")
            return
        else:
            self.server.add_warning(
                f"[Wechat_Push] Failed to push message. ErrCode:{r.json()['errcode']},ErrMsg:{r.json()['errmsg']}"
                "\n\nIf you want to get rid of this warning, please restart MoonRaker.")
            logging.error(
                f"Failed to push message. ErrCode:{r.json()['errcode']},ErrMsg:{r.json()['errmsg']}")
            return
        
    # 方法：获取企业微信的access_token
    def _getAsToken(self):
        now = time.time()
        if self._token and now < self._token_expire:
            return self._token
        dic = {'corpid': self.corpid, 'corpsecret': self.corpsecret}
        r = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken", json=dic)
        data = r.json()
        errcode = data["errcode"]
        if errcode != 0:
            self.server.add_warning(
                f"[Wechat_Push] Failed to get access_token. ErrCode:{errcode},ErrMsg:{data['errmsg']}"
                "\n\nIf you want to get rid of this warning, please restart MoonRaker.")
            logging.error(
                f"Failed to get access_token. ErrCode:{errcode},ErrMsg:{data['errmsg']}")
            return None
        self._token = data['access_token']
        self._token_expire = now + data.get('expires_in', 7200) - 200
        return self._token

    # 方法：上传图片到企业微信
    def _uploadImage(self, path):
        # 判断图片是否存在
        if not os.path.exists(path):
            logging.error("image does not exist")
            return

        # 获取Access token
        AsToken: str = self._getAsToken()
        if AsToken is None:
            return False

        file = {'attachment_file': (path, open(path, 'rb'), 'image/png', {})}

        # 上传图片到企业微信素材库
        r = requests.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={AsToken}&type=image", files=file)

        # 判断是否上传成功
        if r.json()['errcode'] != 0:
            logging.error(
                f"Media file upload failed. ErrCode:{r.json()['errcode']},ErrMsg:{r.json()['errmsg']}")
            return

        # 获取并返回素材ID
        media_id = r.json()['media_id']
        return media_id

    # 提取本地IP地址（获取本地IP地址失败，则将IP地址设置为"127.0.0.1"，即本地回环地址）
    @staticmethod
    def _is_lan_ip(ip: str) -> bool:
        try:
            p = list(map(int, ip.split('.')))
            return (
                p[0] == 10 or
                (p[0] == 172 and 16 <= p[1] <= 31) or
                (p[0] == 192 and p[1] == 168)
            )
        except Exception:
            return False

    def _extract_ip(self) -> str:
        import subprocess
        # 优先用 ip addr 枚举所有接口，取第一个 RFC-1918 私有 IP
        try:
            out = subprocess.check_output(
                ['ip', '-4', 'addr', 'show', 'scope', 'global'],
                timeout=2, stderr=subprocess.DEVNULL
            ).decode()
            for line in out.splitlines():
                line = line.strip()
                if line.startswith('inet '):
                    ip = line.split()[1].split('/')[0]
                    if self._is_lan_ip(ip):
                        return ip
        except Exception:
            pass
        # 回退：UDP 路由探测
        for target in ('8.8.8.8', '192.168.0.1', '10.0.0.1'):
            try:
                st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                st.connect((target, 80))
                ip = st.getsockname()[0]
                st.close()
                if self._is_lan_ip(ip):
                    return ip
            except Exception:
                pass
        return '127.0.0.1'

# 主方法：加载方法（调用WechatPush类的构造函数，并将config作为参数传递给构造函数，创建一个WechatPush对象。最后将对象返回。）
def load_component(config: ConfigHelper) -> WechatPush:
    return WechatPush(config)
