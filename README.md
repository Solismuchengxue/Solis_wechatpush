# Solis WeChatPush

> 一个将 Klipper 3D 打印机状态实时推送到企业微信的 Moonraker 插件

<p align="center">
  <img src="klipper-logo.png" alt="Solis WeChatPush" width="200"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Moonraker-组件-blue?style=flat-square"/>
  <img src="https://img.shields.io/badge/license-GPLv3-green?style=flat-square"/>
  <img src="https://img.shields.io/badge/python-3.8+-orange?style=flat-square"/>
</p>

## 📋 功能

- **实时推送** — 将打印机状态实时推送到企业微信
- **状态全面覆盖** — 支持以下状态推送：

| 打印机状态 | 推送内容 |
|-----------|---------|
| 🟢 开始打印 | 文件名 + 开始时间 + 进度 |
| 🔵 打印完成 | 文件名 + 完成时间 + 用时 + 缩略图 |
| 🟡 打印暂停 | 文件名 + 暂停时间 + 进度 |
| 🔴 打印错误 | 文件名 + 出错时间 + 错误信息 |
| 🔴 取消打印 | 文件名 + 取消时间 |
| 🔴 设备停机 | 停机时间 + 原因 |

- **图片支持** — 自动截取摄像头快照、生成状态图片或使用 G-Code 缩略图一并推送
- **域名/IP 显示** — 推送消息中包含打印机访问地址，方便远程控制
- **深色模式** — 卡片采用白底设计，微信夜间模式也能清晰显示
- **更新管理器** — 支持通过 Moonraker 的 update_manager 自动更新

## 📦 项目结构

```
Solis_wechatpush/
├── wechat_push.py         # 🌟 Moonraker 组件（核心推送逻辑）
├── install.sh             # 🔧 交互式安装/卸载脚本
├── sample.cfg             # 📝 Moonraker 配置示例
├── klipper-logo.png       # 🎨 项目 Logo
├── fonts/
│   └── FreeMono.ttf       # 🔤 图片生成字体文件
├── doc/
│   └── 企业微信可信域名个人配置方法.pdf  # 📖 企业微信配置教程
```

## ⚙️ 工作原理

```
Klippy ──▶ Moonraker ──▶ wechat_push 组件 ──▶ 企业微信 API ──▶ 微信消息
                │                                    │
                ├── 监听 print_stats 状态变化          └── 上传图片素材
                ├── 监听 webhooks 停机事件
                └── 获取摄像头快照 / 生成状态图
```

## 🔧 安装

### 前置条件

- Klipper / Moonraker 已安装并正常运行
- Python 依赖：`requests`, `Pillow`（通常 Moonraker 环境已包含）
- 拥有一个企业微信账号（免费注册）

### 方法一：使用安装脚本（推荐）

```bash
cd ~ && git clone https://github.com/Solismuchengxue/Solis_wechatpush.git
cd ~/Solis_wechatpush
chmod +x install.sh
./install.sh
```

脚本会交互式引导完成以下操作：
1. 创建 `wechat_push.py` 的软链接到 Moonraker 组件目录
2. 验证 `fonts/FreeMono.ttf` 字体文件是否存在
3. 在 `moonraker.conf` 中添加 `[wechat_push]` 配置段
4. 添加 `[update_manager Solis_wechatpush]` 更新管理器
5. 可选：设置打印机名称（显示在推送标题中）
6. 重启 Moonraker 服务

> **卸载：** `./install.sh -u`

### 方法二：手动安装

```bash
# 1. 创建软链接
ln -sf ~/Solis_wechatpush/wechat_push.py ~/moonraker/moonraker/components/wechat_push.py

# 2. 重启 Moonraker
sudo systemctl restart moonraker
```

## 📝 配置

在 `moonraker.conf` 中添加以下配置：

```cfg
[wechat_push]
corp_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 企业微信应用私钥（必填）
corp_id: wwxxxxxxxxxxxxxxxx                 # 企业ID（必填）
agent_id: 1000001                           # 企业微信应用ID（必填）
to_user: @all                               # 接收消息成员，@all为所有人
#domain: klipper.example.com                # 域名（可选，用于消息中的链接）
#camera: /webcam?action=snapshot            # 摄像头地址（可选，推送时附带快照）
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `corp_secret` | ✅ | 企业微信应用 Secret，在应用详情页获取 |
| `corp_id` | ✅ | 企业微信的企业 ID，在后台"我的企业"中查看 |
| `agent_id` | ✅ | 企业微信应用的 AgentId |
| `to_user` | ❌ | 接收消息的成员 ID，`@all` 表示全部成员，多人用 `\|` 分隔 |
| `domain` | ❌ | 域名地址，配置后消息中的链接将使用域名而非 IP |
| `camera` | ❌ | 摄像头快照地址，如 `/webcam?action=snapshot` |

> ⚠️ **注意：** 企业微信需要配置**可信域名**才能正常调用 API。如果未配置，可能会出现 `ErrCode: 60020` 错误。
>
> 配置入口：企业微信网页后台 → 应用管理 → 应用 → **设置可信域名**
>
> 详细配置方法请参考 `doc/` 目录下的 PDF 文档。

## 🔑 获取企业微信参数

### 1. 注册企业微信

如果还没有企业微信账号，请先注册：[https://work.weixin.qq.com/](https://work.weixin.qq.com/)

### 2. 获取 CorpID

扫码进入企业微信后台 → **我的企业** → **企业信息** → 复制**企业 ID**

### 3. 创建应用

企业微信后台 → **应用管理** → **自建** → **创建应用**

### 4. 获取 AgentId 和 CorpSecret

在刚创建的应用详情页中：
- **AgentId** — 直接复制
- **Secret** — 点击"查看"后需在企业微信客户端中查看

### 5. 配置可信 IP（重要）

企业微信 API 需要配置可信 IP 地址才能正常调用：
1. 进入企业微信后台 → **应用管理** → 选择应用 → **设置可信域名**
2. 添加打印机上位机的公网 IP 或使用代理

## 🔄 更新管理器

安装脚本会自动在 `moonraker.conf` 中添加以下配置，实现通过 Moonraker 的 UI 界面（Fluidd / Mainsail）直接更新：

```cfg
[update_manager Solis_wechatpush]
type: git_repo
primary_branch: main
path: ~/Solis_wechatpush
origin: https://github.com/Solismuchengxue/Solis_wechatpush.git
managed_services: moonraker
```

## 🗑️ 卸载

```bash
cd ~/Solis_wechatpush
./install.sh -u
```

脚本会自动移除组件软链接，并提示手动清理 `moonraker.conf` 中的配置段。

## 🙏 致谢

- 本项目基于 [kluoyun/push_wechat](https://github.com/kluoyun/push_wechat) 修改与完善，感谢原作者的开源贡献
- 参考 [Moonraker 组件开发文档](https://moonraker.readthedocs.io/) 实现插件架构

## 📄 许可

本项目基于 **GNU GPLv3** 许可证发布。

Copyright (C) 2022 Cao Zheng &lt;smile.caozheng@outlook.com&gt;
