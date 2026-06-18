#!/bin/bash

# =============================================================================
# Solis_wechatpush 交互式安装脚本
# 功能：
#   1. 安装 Moonraker 组件 (wechat_push.py) 软链接
#   2. 验证字体文件 (fonts/FreeMono.ttf)
#   3. 配置 moonraker.conf 添加 [wechat_push] 及更新管理器
#   4. 重启 Moonraker 服务
# 使用 -u 参数卸载所有安装项
# =============================================================================

set -e

# ----------------------------- 全局变量 ----------------------------------
SCRIPT_VERSION="1.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_USER="${SUDO_USER:-$(id -un)}"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" 2>/dev/null | cut -d: -f6 || echo "$HOME")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 默认路径（可交互修改）
MOONRAKER_HOME="${INSTALL_HOME}/moonraker"
KLIPPER_CONFIG_HOME="${INSTALL_HOME}/printer_data/config"
MOONRAKER_CONFIG="${KLIPPER_CONFIG_HOME}/moonraker.conf"

# 源文件位置
SRC_PYTHON="${SCRIPT_DIR}/wechat_push.py"
SRC_FONT="${SCRIPT_DIR}/fonts/FreeMono.ttf"
SRC_SAMPLE_CFG="${SCRIPT_DIR}/sample.cfg"

# 目标位置
DEST_COMPONENT="${MOONRAKER_HOME}/moonraker/components/wechat_push.py"

# 服务名称
MOONRAKER_SERVICE="moonraker"

# ----------------------------- 辅助函数 ----------------------------------
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_info()   { echo -e "${BLUE}ℹ ${1}${NC}"; }
print_success(){ echo -e "${GREEN}✓ ${1}${NC}"; }
print_warning(){ echo -e "${YELLOW}⚠ ${1}${NC}"; }
print_error()  { echo -e "${RED}✗ ${1}${NC}"; }

prompt_yes_no() {
    local prompt="$1"
    local response
    while true; do
        read -p "$(echo -e ${BLUE}${prompt}${NC} [y/N]: )" response
        case "$response" in
            [yY][eE][sS]|[yY]) return 0 ;;
            [nN][oO]|[nN]|"")   return 1 ;;
            *) echo "请回答 y 或 n" ;;
        esac
    done
}

prompt_input() {
    local prompt="$1"
    local default="$2"
    local response
    read -p "$(echo -e ${BLUE}${prompt}${NC} [${default}]: )" response
    echo "${response:-$default}"
}

backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local timestamp=$(date +"%Y%m%d_%H%M%S")
        local backup="${file}.backup_${timestamp}"
        cp "$file" "$backup"
        print_success "已备份: $file → $backup"
        return 0
    fi
    return 1
}

add_line_to_file_if_missing() {
    local file="$1"
    local line="$2"
    if ! grep -qF "$line" "$file" 2>/dev/null; then
        echo "$line" >> "$file"
        print_success "已添加行至 $file"
    else
        print_info "行已存在于 $file"
    fi
}

# ----------------------------- 安装步骤 ----------------------------------
install_component() {
    print_header "1. 安装 Moonraker 组件"

    # 检查源文件
    if [ ! -f "$SRC_PYTHON" ]; then
        print_error "未找到 wechat_push.py: $SRC_PYTHON"
        exit 1
    fi

    # 检查目标目录是否存在
    local comp_dir="$(dirname "$DEST_COMPONENT")"
    if [ ! -d "$comp_dir" ]; then
        print_error "Moonraker components 目录不存在: $comp_dir"
        print_info "请确认 Moonraker 已正确安装"
        exit 1
    fi

    # 创建软链接（如果已存在则先移除）
    if [ -L "$DEST_COMPONENT" ] || [ -f "$DEST_COMPONENT" ]; then
        print_warning "wechat_push.py 已存在，将替换"
        rm -f "$DEST_COMPONENT"
    fi

    ln -sf "$SRC_PYTHON" "$DEST_COMPONENT"
    print_success "软链接已创建: $DEST_COMPONENT → $SRC_PYTHON"
}

verify_font() {
    print_header "2. 验证字体文件"

    if [ ! -f "$SRC_FONT" ]; then
        print_warning "未找到字体文件: $SRC_FONT"
        print_info "请确保 fonts/FreeMono.ttf 存在，否则推送的图片将无法显示文字"
        return 1
    else
        print_success "字体文件已就绪: $SRC_FONT"
    fi
}

verify_font_path() {
    print_header "3. 验证字体路径"

    if [ ! -f "$DEST_COMPONENT" ]; then
        print_error "组件文件不存在: $DEST_COMPONENT"
        return 1
    fi

    # 检查 Python 代码中是否使用了 _FONT_PATH 变量
    if grep -qF "_FONT_PATH" "$DEST_COMPONENT" 2>/dev/null || grep -qF "_FONT_PATH" "$SRC_PYTHON" 2>/dev/null; then
        print_success "字体路径使用动态解析 (_FONT_PATH)，无需修复"
    else
        print_warning "未检测到 _FONT_PATH，请确保字体路径指向 fonts/FreeMono.ttf"
    fi
}

configure_moonraker() {
    print_header "4. 配置 moonraker.conf"

    if [ ! -f "$MOONRAKER_CONFIG" ]; then
        print_error "未找到 moonraker.conf: $MOONRAKER_CONFIG"
        print_info "请先确认 Klipper 配置目录路径"
        return 1
    fi

    # 检查是否已存在 [wechat_push] 配置
    if grep -qi '^[[:space:]]*\[wechat_push\]' "$MOONRAKER_CONFIG" 2>/dev/null; then
        print_success "[wechat_push] 配置已存在"
    else
        # 添加配置节
        echo -e "\n#####################################################################" >> "$MOONRAKER_CONFIG"
        echo -e "# Wechat_push           企业微信推送" >> "$MOONRAKER_CONFIG"
        echo -e "#####################################################################" >> "$MOONRAKER_CONFIG"
        echo -e "[wechat_push]" >> "$MOONRAKER_CONFIG"
        echo -e "corp_secret:                                          # 企业微信应用私钥" >> "$MOONRAKER_CONFIG"
        echo -e "corp_id:                                              # 企业ID" >> "$MOONRAKER_CONFIG"
        echo -e "agent_id:                                             # 企业微信应用ID" >> "$MOONRAKER_CONFIG"
        echo -e "to_user: @all                                         # 接收消息的人，@all默认所有人" >> "$MOONRAKER_CONFIG"
        echo -e "#domain:                                              # 域名（可选）" >> "$MOONRAKER_CONFIG"
        echo -e "#camera: /webcam?action=snapshot                      # 摄像头地址（可选）" >> "$MOONRAKER_CONFIG"
        print_success "已添加 [wechat_push] 配置到 moonraker.conf"
        print_warning "请编辑 moonraker.conf 填写 corp_secret、corp_id、agent_id 等参数"
    fi
}

add_update_manager() {
    print_header "5. 添加更新管理器"

    if [ ! -f "$MOONRAKER_CONFIG" ]; then
        print_error "未找到 moonraker.conf"
        return 1
    fi

    local updater_section="[update_manager Solis_wechatpush]
type: git_repo
primary_branch: main
path: ${SCRIPT_DIR}
origin: https://github.com/Solismuchengxue/Solis_wechatpush.git
managed_services: moonraker"

    if grep -qF "[update_manager Solis_wechatpush]" "$MOONRAKER_CONFIG" 2>/dev/null; then
        print_success "更新管理器 [update_manager Solis_wechatpush] 已存在"
    else
        echo -e "\n$updater_section" >> "$MOONRAKER_CONFIG"
        print_success "已添加更新管理器 [update_manager Solis_wechatpush]"
    fi
}

set_instance_name() {
    print_header "6. 设置打印机名称（可选）"

    if ! prompt_yes_no "是否设置打印机名称（显示在微信推送标题中）？"; then
        print_info "跳过，可在后期通过 Fluidd 设置或使用 API 设置"
        return
    fi

    local default_name="${HOSTNAME:-klipper}"
    local instance_name
    instance_name=$(prompt_input "请输入打印机名称" "$default_name")

    if [ -z "$instance_name" ]; then
        print_warning "名称不能为空，跳过设置"
        return
    fi

    print_info "正在设置打印机名称: $instance_name"

    # 通过 Moonraker API 设置实例名称
    local api_url="http://localhost:7125/server/database/item"
    local payload="{\"namespace\": \"fluidd\", \"key\": \"uiSettings.general.instanceName\", \"value\": \"$instance_name\"}"

    if curl -s -X POST "$api_url" -H "Content-Type: application/json" -d "$payload" > /dev/null 2>&1; then
        print_success "打印机名称已设置为: $instance_name"
    else
        print_warning "API 设置失败，请确保 Moonraker 正在运行"
        print_info "安装完成后可手动设置："
        echo "  curl -X POST http://localhost:7125/server/database/item \\"
        echo "    -H \"Content-Type: application/json\" \\"
        echo "    -d '{\"namespace\": \"fluidd\", \"key\": \"uiSettings.general.instanceName\", \"value\": \"$instance_name\"}'"
    fi
}

restart_services() {
    print_header "7. 重启服务"
    if prompt_yes_no "是否立即重启 Moonraker 服务？"; then
        sudo systemctl restart $MOONRAKER_SERVICE && print_success "Moonraker 已重启" || print_error "Moonraker 重启失败，请手动执行: sudo systemctl restart moonraker"
    else
        print_warning "请稍后手动重启 Moonraker 服务:"
        echo "  sudo systemctl restart moonraker"
    fi
}

# ----------------------------- 卸载流程 ----------------------------------
uninstall_all() {
    print_header "卸载 Solis_wechatpush"

    # 移除组件文件
    if [ -f "$DEST_COMPONENT" ]; then
        print_info "正在移除 Moonraker 组件..."
        rm -f "$DEST_COMPONENT"
        print_success "已移除: $DEST_COMPONENT"
    else
        print_info "组件文件不存在，跳过"
    fi

    # 提示手动移除配置
    print_info "请在 Fluidd / Mainsail 的配置文件编辑器中删除以下两个配置段："
    echo ""
    echo "  - [wechat_push]"
    echo "  - [update_manager Solis_wechatpush]"
    echo ""

    if prompt_yes_no "是否立即重启 Moonraker 服务？"; then
        sudo systemctl restart $MOONRAKER_SERVICE && print_success "Moonraker 已重启"
    fi

    print_success "卸载流程已完成"
}

# ----------------------------- 主流程 ----------------------------------
show_help() {
    cat << EOF
用法: $0 [选项]

选项:
  -u          卸载 Solis_wechatpush
  -h          显示此帮助信息
  -v          显示版本信息

不带选项运行时将启动交互式安装向导。
EOF
}

show_version() {
    echo "Solis_wechatpush 安装脚本 v${SCRIPT_VERSION}"
}

# 解析命令行参数
UNINSTALL=0
while getopts "uhv" opt; do
    case $opt in
        u) UNINSTALL=1 ;;
        h) show_help; exit 0 ;;
        v) show_version; exit 0 ;;
        *) show_help; exit 1 ;;
    esac
done

# 检查是否以 root 运行
if [ "$EUID" -eq 0 ] && [ "$(uname -m)" != "mips" ]; then
    print_error "请勿以 root 用户运行此脚本。"
    exit 1
fi

# 执行相应操作
if [ "$UNINSTALL" -eq 1 ]; then
    uninstall_all
    exit 0
fi

# 交互式安装
print_header "Solis_wechatpush 交互式安装向导 v${SCRIPT_VERSION}"
echo "本项目用于将 Klipper 打印机状态实时推送到企业微信。"
echo ""

# 确认或修改默认路径
print_info "检测到以下默认路径，如有不符请修改："
MOONRAKER_HOME=$(prompt_input "Moonraker 安装目录" "$MOONRAKER_HOME")
KLIPPER_CONFIG_HOME=$(prompt_input "Klipper 配置目录" "$KLIPPER_CONFIG_HOME")
MOONRAKER_CONFIG="${KLIPPER_CONFIG_HOME}/moonraker.conf"
DEST_COMPONENT="${MOONRAKER_HOME}/moonraker/components/wechat_push.py"

# 验证关键路径
if [ ! -d "$MOONRAKER_HOME/moonraker/components" ]; then
    print_error "Moonraker components 目录不存在: $MOONRAKER_HOME/moonraker/components"
    exit 1
fi

# 执行安装步骤
install_component
verify_font
verify_font_path
configure_moonraker
add_update_manager
set_instance_name
restart_services

print_header "安装成功完成！"
cat << EOF

Solis_wechatpush 已成功安装。

- Moonraker 组件:  $DEST_COMPONENT → $SRC_PYTHON (软链接)
- 字体文件:        $SRC_FONT (项目内 fonts/ 目录)
- 配置文件:        $MOONRAKER_CONFIG (包含 [wechat_push] 及 [update_manager Solis_wechatpush])

重要：请在 Fluidd / Mainsail 的配置文件编辑器中打开 moonraker.conf，
填写以下企业微信参数：

  - corp_secret:  企业微信应用私钥
  - corp_id:      企业ID
  - agent_id:     企业微信应用ID
  - to_user:      接收消息成员，@all 为所有人

配置完成后重启 Moonraker 即可生效：
  sudo systemctl restart moonraker

可选：在 printer.cfg 中加入以下宏，即可从 Klipper 控制台发送测试推送：

  [gcode_macro SEND_WECHAT_TEST]
  gcode:
      {action_call_remote_method("send_wechat_test")}

如需卸载，请运行: $0 -u

EOF
