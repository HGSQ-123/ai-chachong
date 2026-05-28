/**
 * ============================================================
 * AI查重检测系统 - 检测页面交互脚本 v2
 * 双模式：普通版(免费) / Pro版(付费)
 * ============================================================
 */

let currentMode = 'text';       // text | file
let selectedFile = null;
let selectedPlan = 'pro';       // free | pro
let isDetecting = false;

// ==================== 检测计划切换 ====================
function selectDetectMode(plan) {
    selectedPlan = plan;
    document.getElementById('freeCard').classList.toggle('active', plan === 'free');
    document.getElementById('proCard').classList.toggle('active', plan === 'pro');
    document.getElementById('detectHint').innerHTML = plan === 'free'
        ? '🆓 <strong>普通版</strong>：AI生成率检测 + 基础报告。每日免费1次。'
        : '⭐ <strong>Pro版</strong>：AI检测 + 全网查重 + 详细报告 + PDF导出。¥0.49/千字。';
}

// ==================== 提交检测（文本） ====================
async function submitFreeDetection() {
    selectDetectMode('free');
    await doDetection(false);
}
async function submitProDetection() {
    selectDetectMode('pro');
    await doDetection(true);
}

async function doDetection(usePro) {
    if (isDetecting) return;
    const text = document.getElementById('textInput').value.trim();
    if (!text) { showToast('请先输入要检测的文本内容', 'warning'); return; }
    const wordCount = countWords(text);
    if (wordCount < 10) { showToast('文本过短（不足10字）', 'warning'); return; }
    if (wordCount > 50000) { showToast('单次最多50000字', 'warning'); return; }

    isDetecting = true;
    const label = usePro ? 'Pro检测中...' : '免费检测中...';
    showLoading(label, usePro ? 'AI分析 + 查重比对' : 'AI分析中');
    const btn = usePro ? document.getElementById('btnPro') : document.getElementById('btnFree');
    btn.disabled = true; btn.textContent = '⏳ ' + label;

    try {
        const result = await apiRequest('/detect/api/text', {
            method: 'POST',
            body: JSON.stringify({ text, mode: usePro ? 'both' : 'ai_only', use_pro: usePro }),
        }, 60000);

        if (result.success) {
            renderResult(result.report);
            showToast(usePro ? 'Pro检测完成！' : '免费检测完成！', 'success');
        } else if (result.need_upgrade) {
            showUpgradePrompt(result);
        } else if (result.need_pay) {
            showPayPrompt(result);
        } else {
            showToast(result.message || '检测失败', 'error');
        }
    } catch (e) {
        showToast('检测异常：' + e.message, 'error');
    } finally {
        isDetecting = false; hideLoading();
        btn.disabled = false;
        btn.textContent = usePro ? '⭐ Pro检测 · ¥0.49/千字' : '🆓 免费检测';
    }
}

// ==================== 旧的文本检测（保留兼容） ====================
async function submitTextDetection() {
    await doDetection(selectedPlan === 'pro');
}

// ==================== 模式切换（文本/文件） ====================
function switchDetectMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.detect-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(mode === 'text' ? 'tabText' : 'tabFile').classList.add('active');
    document.getElementById('textPanel').style.display = mode === 'text' ? 'block' : 'none';
    document.getElementById('filePanel').style.display = mode === 'file' ? 'block' : 'none';
    const rc = document.getElementById('resultContainer'); if (rc) rc.style.display = 'none';
}

// ==================== 字数统计 ====================
function countWords(text) {
    if (!text) return 0;
    let count = 0;
    count += (text.match(/[\u4e00-\u9fff]/g) || []).length;
    count += (text.match(/[a-zA-Z]+/g) || []).length;
    return count;
}
(function(){
    var ti = document.getElementById('textInput');
    if (ti) ti.addEventListener('input', function(){ document.getElementById('wordCount').textContent = '字数：' + countWords(this.value); });
})();

// ==================== 文件上传处理 ====================
function handleFileSelect(e) { var f = e.target.files[0]; if(f) processSelectedFile(f); }
function handleDragOver(e) { e.preventDefault(); document.getElementById('uploadArea').classList.add('drag-over'); }
function handleDragLeave(e) { e.preventDefault(); document.getElementById('uploadArea').classList.remove('drag-over'); }
function handleDrop(e) { e.preventDefault(); document.getElementById('uploadArea').classList.remove('drag-over'); var f = e.dataTransfer.files[0]; if(f) processSelectedFile(f); }
function processSelectedFile(file) {
    var allowed = ['docx','pdf','txt','doc']; var ext = file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) { showToast('不支持的文件格式', 'error'); return; }
    if (file.size > 20*1024*1024) { showToast('文件超过20MB', 'error'); return; }
    selectedFile = file;
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('fileInfo').style.display = 'inline-flex';
    document.getElementById('btnProFile').disabled = false;
}
function clearFile(e) { if(e) e.stopPropagation(); selectedFile = null; document.getElementById('fileInput').value = ''; document.getElementById('fileInfo').style.display = 'none'; document.getElementById('btnProFile').disabled = true; }
function formatFileSize(b) { return b<1024?b+' B':b<1048576?(b/1024).toFixed(1)+' KB':(b/1048576).toFixed(1)+' MB'; }

// ==================== 文件检测提交 ====================
async function submitFileFreeDetection() { selectDetectMode('free'); await submitFileDetection(false); }
async function submitFileProDetection() { selectDetectMode('pro'); await submitFileDetection(true); }
async function submitFileDetection(usePro) {
    if (!selectedFile) { showToast('请先选择文件', 'warning'); return; }

    var label = usePro ? 'Pro检测中...' : '免费检测中...';
    showLoading(label, usePro ? '文件解析 + AI分析 + 查重' : '文件解析 + AI分析');
    var btn = usePro ? document.getElementById('btnProFile') : document.getElementById('btnFreeFile');
    btn.disabled = true; btn.textContent = '⏳ ' + label;

    try {
        var fd = new FormData(); fd.append('file', selectedFile);
        fd.append('use_pro', usePro ? '1' : '0');
        var xhr = new XMLHttpRequest();
        var result = await new Promise(function(resolve, reject) {
            xhr.addEventListener('load', function() {
                if (xhr.status === 401) { window.location.href = '/auth/login'; reject(new Error('请先登录')); return; }
                try { resolve(JSON.parse(xhr.responseText)); } catch(e) { reject(new Error('解析失败')); }
            });
            xhr.addEventListener('error', function() { reject(new Error('网络异常')); });
            xhr.open('POST', '/detect/api/file');
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(fd);
        });
        if (result.success) { renderResult(result.report); showToast(usePro ? 'Pro检测完成！' : '免费检测完成！', 'success'); }
        else if (result.need_upgrade) { showUpgradePrompt(result); }
        else if (result.need_pay) { showPayPrompt(result); }
        else { showToast(result.message || '检测失败', 'error'); }
    } catch(e) { showToast('检测异常：' + e.message, 'error'); }
    finally { hideLoading(); btn.disabled = false; btn.textContent = usePro ? '⭐ Pro检测 · ¥0.49/千字' : '🆓 免费检测'; }
}

// ==================== 升级/付费提示 ====================
function showUpgradePrompt(data) {
    var c = document.getElementById('resultContainer'); if (!c) return; c.style.display = 'block';
    c.innerHTML = '<div class="prompt-card"><div style="font-size:56px">🎯</div><h3>今日免费次数已用完</h3><p style="color:#666">普通版每天' + (data.daily_free || '1') + '次免费检测</p><div style="margin-top:20px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap"><button class="btn-detect-pro" onclick="selectDetectMode(\'pro\');doDetection(true);">⭐ 立即使用Pro版 · ¥0.49/千字</button><a href="/pricing" class="btn btn-gold">💳 去充值</a></div></div>';
    c.scrollIntoView({ behavior: 'smooth' });
}

function showPayPrompt(data) {
    var c = document.getElementById('resultContainer'); if (!c) return;
    c.style.display = 'block';
    c.innerHTML = '<div class="prompt-card"><div style="font-size:56px">💰</div><h3>Pro额度不足</h3><p style="color:#666">本次检测超出 <strong style="color:#ef4444">' + (data.shortage || data.extra_words || 0) + '字</strong></p><p style="color:#666">需充值约 <strong style="font-size:24px;color:#d97706">¥' + (data.cost || data.extra_cost || 0) + '</strong></p><div style="margin-top:20px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap"><a href="/pricing" class="btn-detect-pro">💳 充值Pro额度</a><a href="/user/member" class="btn btn-gold">👑 开通会员</a></div></div>';
    c.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 加载动画 ====================
function showLoading(text, sub) {
    var ov = document.getElementById('loadingOverlay'); if (ov) { ov.style.display = 'flex'; }
    var lt = document.querySelector('.loading-text'); if (lt) lt.textContent = text || '正在检测中...';
    var ls = document.getElementById('loadingSubtext'); if (ls) ls.textContent = sub || '';
}
function hideLoading() { var ov = document.getElementById('loadingOverlay'); if (ov) ov.style.display = 'none'; }

// ==================== HTML转义 ====================
function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ==================== 结果渲染（精简版） ====================
function renderResult(report) {
    var c = document.getElementById('resultContainer'); if (!c) return;
    var score = report.originality_score;
    var gradeText, gradeColor;
    if (score >= 80) { gradeText = '🟢 优秀 · 原创度高'; gradeColor = '#059669'; }
    else if (score >= 60) { gradeText = '🟡 良好 · 建议优化'; gradeColor = '#d97706'; }
    else if (score >= 40) { gradeText = '🟠 一般 · 需深度修改'; gradeColor = '#ea580c'; }
    else { gradeText = '🔴 较低 · 需大幅修改'; gradeColor = '#dc2626'; }

    var aiColor = report.ai_score > 50 ? '#dc2626' : report.ai_score > 30 ? '#d97706' : '#059669';
    var plagColor = report.plagiarism_score > 50 ? '#dc2626' : report.plagiarism_score > 30 ? '#d97706' : '#059669';

    var aiSuggHtml = '';
    if (report.ai_suggestions && report.ai_suggestions.length > 0) {
        aiSuggHtml = '<div class="report-section"><h3>💡 AI检测建议</h3><ul class="suggestion-list">' +
            report.ai_suggestions.map(function(s){return '<li class="suggestion-item">'+s+'</li>';}).join('') +
            '</ul></div>';
    }
    var plagSuggHtml = '';
    if (report.plagiarism_suggestions && report.plagiarism_suggestions.length > 0) {
        plagSuggHtml = '<div class="report-section"><h3>💡 查重优化建议</h3><ul class="suggestion-list">' +
            report.plagiarism_suggestions.map(function(s){return '<li class="suggestion-item">'+s+'</li>';}).join('') +
            '</ul></div>';
    }

    c.innerHTML =
        '<div class="report-header" style="margin-top:30px;">' +
            '<div class="report-header-left">' +
                '<h2>📋 检测报告</h2>' +
                '<p class="report-meta">检测字数：' + (report.word_count||0) + '字 | ' +
                (report.detection_mode==='ai_only'?'仅AI检测':report.detection_mode==='plagiarism_only'?'仅查重':'AI+查重') +
                '</p>' +
            '</div>' +
            '<div class="report-header-right">' +
                (report.record_id?'<a href="/detect/report/'+report.record_id+'" class="btn btn-outline">📄 完整报告</a>':'') +
                '<button class="btn btn-primary" onclick="window.location.reload()">🔄 新建检测</button>' +
            '</div>' +
        '</div>' +
        '<div class="score-hero">' +
            '<div class="score-circle-large" style="--score:'+score+';">' +
                '<span class="score-number">'+score+'</span><span class="score-unit">分</span>' +
            '</div>' +
            '<div class="score-label">总体原创得分</div>' +
            '<div class="score-grade" style="color:'+gradeColor+';">'+gradeText+'</div>' +
        '</div>' +
        '<div class="score-breakdown">' +
            '<div class="score-item-card">' +
                '<div class="score-item-header"><span class="score-item-icon">🤖</span><h3>AI生成率</h3></div>' +
                '<div class="score-item-value" style="color:'+aiColor+';">'+(report.ai_score||0)+'%</div>' +
                '<p class="score-item-desc">AI撰写占比</p>' +
                '<div class="score-bar"><div class="score-bar-fill" style="width:'+(report.ai_score||0)+'%;background:'+aiColor+';"></div></div>' +
            '</div>' +
            '<div class="score-item-card">' +
                '<div class="score-item-header"><span class="score-item-icon">👤</span><h3>人工原创率</h3></div>' +
                '<div class="score-item-value text-green">'+(report.human_score||0)+'%</div>' +
                '<p class="score-item-desc">人工撰写占比</p>' +
                '<div class="score-bar"><div class="score-bar-fill" style="width:'+(report.human_score||0)+'%;background:#059669;"></div></div>' +
            '</div>' +
            '<div class="score-item-card">' +
                '<div class="score-item-header"><span class="score-item-icon">📊</span><h3>文本重复率</h3></div>' +
                '<div class="score-item-value" style="color:'+plagColor+';">'+(report.plagiarism_score||0)+'%</div>' +
                '<p class="score-item-desc">查重匹配率</p>' +
                '<div class="score-bar"><div class="score-bar-fill" style="width:'+(report.plagiarism_score||0)+'%;background:'+plagColor+';"></div></div>' +
            '</div>' +
        '</div>' +
        aiSuggHtml + plagSuggHtml +
        '<div class="disclaimer-inline" style="margin-top:24px;">⚠️ <strong>重要提示：</strong>检测结果仅供参考，学校定稿以官方查重系统为准。文稿检测后自动删除。</div>';

    c.style.display = 'block';
    c.scrollIntoView({ behavior: 'smooth' });
}
