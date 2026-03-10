#!/bin/bash

set -euo pipefail

BOLD='\033[1m'
SUCCESS='\033[38;2;0;180;120m'
INFO='\033[38;2;100;120;150m'
WARN='\033[38;2;220;160;0m'
NC='\033[0m'

ui_success() { echo -e "${SUCCESS}OK${NC} $*"; }
ui_info()    { echo -e "${INFO}..${NC} $*"; }
ui_warn()    { echo -e "${WARN}!!${NC} $*"; }
ui_bold()    { echo -e "${BOLD}$*${NC}"; }

is_ja=false
if [[ "${LANG:-}" == ja* ]]; then
    is_ja=true
fi

get_installed_version() {
    if command -v gperm >/dev/null 2>&1; then
        gperm --version 2>/dev/null | head -n1 | tr -d '[:space:]'
    else
        echo "not installed"
    fi
}

get_target_version() {
    local target="unknown"
    if command -v curl >/dev/null 2>&1; then
        target="$(curl -fsSL https://pypi.org/pypi/global-permission/json 2>/dev/null \
            | grep -o '"version":"[^"]*"' \
            | head -n1 \
            | cut -d'"' -f4 || true)"
    fi
    if [[ -z "${target}" ]]; then
        target="unknown"
    fi
    echo "${target}"
}

if $is_ja; then
    MSG_TITLE="gperm installer"
    MSG_NO_UV="'uv' が見つかりません。"
    MSG_NO_UV_HINT="  -> https://github.com/astral-sh/uv からインストールしてください。"
    MSG_INSTALLING="global-permission を PyPI からインストール中..."
    MSG_CURR_VER="  現在のバージョン: %s"
    MSG_TARGET_VER="  インストール対象:   %s"
    MSG_AFTER_VER="  インストール後:     %s"
    MSG_INSTALLED="gperm のインストール完了"
    MSG_INIT="初期設定を確認中..."
    MSG_INIT_DONE="初期設定を用意しました"
    MSG_INIT_SKIP="初期設定は既に存在するため、スキップしました"
    MSG_DOCTOR="doctor を実行中..."
    MSG_DONE="インストール完了"
    MSG_NEXT1="  設定確認:           gperm config show"
    MSG_NEXT2="  状態確認:           gperm doctor"
    MSG_NEXT3="  同期確認:           gperm check"
    MSG_NEXT4="  一括同期:           gperm sync"
else
    MSG_TITLE="gperm installer"
    MSG_NO_UV="'uv' not found."
    MSG_NO_UV_HINT="  -> Install it from https://github.com/astral-sh/uv"
    MSG_INSTALLING="Installing global-permission from PyPI..."
    MSG_CURR_VER="  Current version:     %s"
    MSG_TARGET_VER="  Target version:      %s"
    MSG_AFTER_VER="  Installed version:   %s"
    MSG_INSTALLED="gperm installed successfully"
    MSG_INIT="Checking starter config..."
    MSG_INIT_DONE="Starter config created"
    MSG_INIT_SKIP="Starter config already exists; skipped"
    MSG_DOCTOR="Running doctor..."
    MSG_DONE="Installation complete"
    MSG_NEXT1="  Inspect config:       gperm config show"
    MSG_NEXT2="  Run diagnostics:      gperm doctor"
    MSG_NEXT3="  Check drift:          gperm check"
    MSG_NEXT4="  Sync settings:        gperm sync"
fi

echo ""
ui_bold "$MSG_TITLE"
echo "========================================"
echo ""

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: $MSG_NO_UV"
    echo "$MSG_NO_UV_HINT"
    exit 1
fi

CURRENT_VERSION="$(get_installed_version)"
TARGET_VERSION="$(get_target_version)"
ui_info "$MSG_INSTALLING"
ui_info "$(printf "$MSG_CURR_VER" "$CURRENT_VERSION")"
ui_info "$(printf "$MSG_TARGET_VER" "$TARGET_VERSION")"
uv tool install global-permission --reinstall --force -q
ui_success "$MSG_INSTALLED"
INSTALLED_VERSION="$(get_installed_version)"
ui_success "$(printf "$MSG_AFTER_VER" "$INSTALLED_VERSION")"
echo ""

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
GPERM_CONFIG_PATH="$CONFIG_HOME/gperm/config.toml"

ui_info "$MSG_INIT"
if [[ -f "$GPERM_CONFIG_PATH" ]]; then
    ui_warn "$MSG_INIT_SKIP"
else
    gperm config init --if-missing
    ui_success "$MSG_INIT_DONE"
fi
echo ""

ui_info "$MSG_DOCTOR"
gperm doctor || true
echo ""

ui_success "$MSG_DONE"
echo ""
echo "$MSG_NEXT1"
echo "$MSG_NEXT2"
echo "$MSG_NEXT3"
echo "$MSG_NEXT4"
echo ""
