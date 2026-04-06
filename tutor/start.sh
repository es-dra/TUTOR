#!/bin/bash

# TUTOR 生产环境启动脚本
# 用于管理TUTOR服务的启动、停止、重启等操作

set -e

# 配置变量
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$APP_DIR/config/config.yaml"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/tutor.pid"

# 环境变量
export PYTHONPATH="$APP_DIR"
export TUTOR_HOME="$APP_DIR/data"
export DATA_PATH="$APP_DIR/data/tutor_runs.db"

# 确保目录存在
mkdir -p "$LOG_DIR"
mkdir -p "$APP_DIR/data"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查配置文件
check_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo_error "配置文件不存在: $CONFIG_FILE"
        echo_info "请从模板创建配置文件: cp config/config.production.yaml $CONFIG_FILE"
        exit 1
    fi
    echo_info "配置文件检查通过: $CONFIG_FILE"
}

# 检查依赖
check_dependencies() {
    echo_info "检查依赖..."
    if ! command -v python3 &> /dev/null; then
        echo_error "Python 3 未安装"
        exit 1
    fi
    if ! command -v uvicorn &> /dev/null; then
        echo_error "uvicorn 未安装"
        echo_info "请运行: pip install uvicorn[standard]"
        exit 1
    fi
    echo_info "依赖检查通过"
}

# 启动服务
start_service() {
    check_config
    check_dependencies
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo_warn "服务已经在运行 (PID: $PID)"
            return 0
        else
            echo_warn "发现旧的PID文件，但服务未运行，删除旧文件"
            rm -f "$PID_FILE"
        fi
    fi
    
    echo_info "启动 TUTOR 服务..."
    
    # 启动 uvicorn 服务
    uvicorn tutor.api.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 4 \
        --timeout-keep-alive 30 \
        --log-level warn \
        --access-logfile "$LOG_DIR/access.log" \
        --error-logfile "$LOG_DIR/error.log" \
        --pid "$PID_FILE" \
        --daemon
    
    # 等待服务启动
    sleep 3
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo_info "服务启动成功 (PID: $PID)"
            return 0
        else
            echo_error "服务启动失败"
            return 1
        fi
    else
        echo_error "服务启动失败，未生成PID文件"
        return 1
    fi
}

# 停止服务
stop_service() {
    if [ ! -f "$PID_FILE" ]; then
        echo_warn "服务未运行"
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo_info "停止服务 (PID: $PID)..."
        kill "$PID"
        
        # 等待服务停止
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo_warn "服务停止超时，强制终止"
            kill -9 "$PID"
        fi
        
        rm -f "$PID_FILE"
        echo_info "服务已停止"
    else
        echo_warn "服务未运行，但存在PID文件，删除旧文件"
        rm -f "$PID_FILE"
    fi
}

# 重启服务
restart_service() {
    stop_service
    start_service
}

# 查看服务状态
status_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo_info "服务正在运行 (PID: $PID)"
            return 0
        else
            echo_warn "服务未运行，但存在PID文件"
            return 1
        fi
    else
        echo_warn "服务未运行"
        return 1
    fi
}

# 查看日志
show_logs() {
    if [ -f "$LOG_DIR/error.log" ]; then
        echo_info "显示错误日志..."
        tail -n 50 "$LOG_DIR/error.log"
    else
        echo_warn "错误日志文件不存在"
    fi
}

# 健康检查
health_check() {
    echo_info "检查服务健康状态..."
    if status_service; then
        if command -v curl &> /dev/null; then
            RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/live)
            if [ "$RESPONSE" -eq 200 ]; then
                echo_info "服务健康检查通过"
                return 0
            else
                echo_error "服务健康检查失败，HTTP状态码: $RESPONSE"
                return 1
            fi
        else
            echo_warn "curl 未安装，无法进行健康检查"
            return 0
        fi
    else
        echo_error "服务未运行"
        return 1
    fi
}

# 主函数
main() {
    case "$1" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            status_service
            ;;
        logs)
            show_logs
            ;;
        health)
            health_check
            ;;
        *)
            echo "使用方法: $0 {start|stop|restart|status|logs|health}"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
