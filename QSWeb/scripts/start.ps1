<#
.SYNOPSIS
    启动 QSWeb 前后端服务，日志输出到指定日志目录。

.DESCRIPTION
    启动后端 (uvicorn FastAPI) 和前端 (Vite dev server)，
    将各自的 stdout/stderr 重定向到日志文件。

.PARAMETER NoFrontend
    仅启动后端，不启动前端。

.PARAMETER NoBackend
    仅启动前端，不启动后端。

.PARAMETER BackendPort
    后端端口，默认 28000。

.PARAMETER FrontendPort
    前端端口，默认 23000。

.EXAMPLE
    .\start.ps1
    同时启动前后端服务。

.EXAMPLE
    .\start.ps1 -NoFrontend
    仅启动后端服务。

.EXAMPLE
    .\start.ps1 -BackendPort 8000
    启动后端在 8000 端口，前端在默认端口。
#>

param(
    [switch]$NoFrontend,
    [switch]$NoBackend,
    [int]$BackendPort = 28000,
    [int]$FrontendPort = 23000
)

$ErrorActionPreference = "Stop"

# ============================================================
# 用户配置区 — 根据本地环境修改以下路径
# ============================================================

# Python 解释器路径
# $PythonExe = "$env:USERPROFILE\Project\PythonEnv\QS\Scripts\python.exe"
$env:PYTHONPATH = "D:\HST\QSExt;D:\Project\QuantStudio;" + $env:PYTHONPATH
$PythonExe = "D:\PythonEnv\QS312\Scripts\python.exe"

# 日志输出目录
$LogDir = "$PSScriptRoot\..\logs"

# ============================================================
# 配置区结束
# ============================================================

# 将相对路径转为绝对路径
$LogDir = [System.IO.Path]::GetFullPath($LogDir)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Write-LogAndConsole {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "错误: 未找到 Python 解释器，请修改脚本顶部 `$PythonExe` 变量: $PythonExe" -ForegroundColor Red
    exit 1
}

# 启动进程的辅助函数
function Start-QSProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$LogFile,
        [string]$DependsOn = $null
    )

    Write-LogAndConsole "[$Name] 启动中..." "Cyan"
    Write-LogAndConsole "[$Name] 工作目录: $WorkingDirectory" "Gray"
    Write-LogAndConsole "[$Name] 日志文件: $LogFile" "Gray"

    $proc = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -PassThru `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError (Join-Path $LogDir "$Name-error-$Timestamp.log")

    Write-LogAndConsole "[$Name] PID: $($proc.Id)" "Green"

    return $proc
}

$Processes = @{}
$BackendDir = Join-Path $ProjectDir "backend"
$FrontendDir = Join-Path $ProjectDir "frontend"

# --- 启动后端 ---
if (-not $NoBackend) {
    $BackendLog = Join-Path $LogDir "backend-$Timestamp.log"
    $UvicornPath = Join-Path (Split-Path -Parent $PythonExe) "uvicorn.exe"

    if (-not (Test-Path $UvicornPath)) {
        Write-Host "警告: 未找到 uvicorn ($UvicornPath)，尝试通过 python -m uvicorn 启动" -ForegroundColor Yellow
        $Processes.Backend = Start-QSProcess -Name "backend" `
            -FilePath $PythonExe `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", $BackendPort, "--reload") `
            -WorkingDirectory $BackendDir `
            -LogFile $BackendLog
    } else {
        $Processes.Backend = Start-QSProcess -Name "backend" `
            -FilePath $UvicornPath `
            -ArgumentList @("app.main:app", "--host", "0.0.0.0", "--port", $BackendPort, "--reload") `
            -WorkingDirectory $BackendDir `
            -LogFile $BackendLog
    }
}

# --- 启动前端 ---
if (-not $NoFrontend) {
    $FrontendLog = Join-Path $LogDir "frontend-$Timestamp.log"

    # 查找 npm.cmd（Start-Process 无法直接执行 .ps1 脚本包装）
    $NpmPath = $null
    $NodeDir = Split-Path -Parent (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    if ($NodeDir) {
        $NpmCmdPath = Join-Path $NodeDir "npm.cmd"
        if (Test-Path $NpmCmdPath) {
            $NpmPath = $NpmCmdPath
        }
    }
    if (-not $NpmPath) {
        # 回退：通过 cmd /c 调用 npm
        $NpmPath = "npm"
    }

    # 修改 vite 端口（如果非默认端口）
    if ($FrontendPort -ne 23000) {
        $ViteConfig = Join-Path $FrontendDir "vite.config.ts"
        Write-Host "提示: 前端端口 $FrontendPort 非默认值，请确保 vite.config.ts 中 server.port 已配置" -ForegroundColor Yellow
    }

    $Processes.Frontend = Start-QSProcess -Name "frontend" `
        -FilePath $NpmPath `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory $FrontendDir `
        -LogFile $FrontendLog
}

Write-Host ""
Write-LogAndConsole "=== QSWeb 服务已启动 ===" "Green"
if ($Processes.Backend) {
    Write-LogAndConsole "  后端: http://localhost:$BackendPort (API 文档: http://localhost:$BackendPort/docs)" "White"
}
if ($Processes.Frontend) {
    Write-LogAndConsole "  前端: http://localhost:$FrontendPort" "White"
}
Write-LogAndConsole "  日志: $LogDir" "Gray"
Write-Host ""
Write-LogAndConsole "按 Ctrl+C 停止所有服务..." "Yellow"

# 注册退出清理
$Cleanup = {
    Write-Host ""
    Write-LogAndConsole "正在停止服务..." "Yellow"
    foreach ($key in $Processes.Keys) {
        $proc = $Processes[$key]
        if (-not $proc.HasExited) {
            Write-LogAndConsole "[$key] 停止 PID $($proc.Id)..." "Cyan"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-LogAndConsole "已停止所有服务" "Green"
}

# 使用 event-driven 方式监听 Ctrl+C
try {
    # 等待任意子进程退出，或用户中断
    $WaitHandles = @()
    foreach ($proc in $Processes.Values) {
        $WaitHandles += (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
    }
    $WaitHandles | ForEach-Object { $_.WaitForExit() } | Out-Null
} catch [System.Management.Automation.BreakException] {
    & $Cleanup
} finally {
    & $Cleanup
}
