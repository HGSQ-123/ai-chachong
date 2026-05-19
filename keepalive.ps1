# AI查重保活脚本 - Windows计划任务用
# 每10分钟ping一次health端点防止Render休眠
try {
    $r = Invoke-WebRequest -Uri "https://ai-chachong.onrender.com/health" -UseBasicParsing -TimeoutSec 30
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "$ts OK $($r.StatusCode) $($r.Content)"
} catch {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Output "$ts ERR $_"
}
