/**
 * ============================================================
 * AI查重+论文重复率检测系统 - 检测页面交互脚本
 * 功能：文本粘贴检测、文件上传检测、结果渲染
 * ============================================================
 */

// 当前检测模式（text / file）
let currentMode = 'text';
// 当前选中的文件
let selectedFile = null;

// ==================== 检测模式切换 ====================

/**
 * 切换检测模式（粘贴文本 / 上传文件）
 * @param {string} mode - 'text' 或 'file'
 */
function switchDetectMode(mode) {
    currentMode = mode;

    // 切换Tab高亮
    document.querySelectorAll('.detect-tab').forEach(t => t.classList.remove('active'));
    if (mode === 'text') {
        document.getElementById('tabText').classList.add('active');
        document.getElementById('textPanel').style.display = 'block';
        document.getElementById('filePanel').style.display = 'none';
    } else {
        document.getElementById('tabFile').classList.add('active');
        document.getElementById('textPanel').style.display = 'none';
        document.getElementById('filePanel').style.display = 'block';
    }

    // 隐藏之前的结果
    const resultContainer = document.getElementById('resultContainer');
    if (resultContainer) {
        resultContainer.style.display = 'none';
    }
}

// ==================== 文本字数统计 ====================

/**
 * 统计中英文字数
 * @param {string} text - 文本内容
 * @returns {number} 字数
 */
function countWords(text) {
    if (!text) return 0;
    let count = 0;
    // 中文字符
    count += (text.match(/[\u4e00-\u9fff]/g) || []).length;
    // 英文单词
    count += (text.match(/[a-zA-Z]+/g) || []).length;
    return count;
}

// 监听文本输入，实时更新字数
const textInput = document.getElementById('textInput');
if (textInput) {
    textInput.addEventListener('input', debounce(function () {
        const count = countWords(this.value);
        document.getElementById('wordCount').textContent = '字数：' + count;
    }, 200));
}

/**
 * 清空文本输入框
 */
function clearText() {
    const input = document.getElementById('textInput');
    if (input) {
        input.value = '';
        document.getElementById('wordCount').textContent = '字数：0';
    }
    const resultContainer = document.getElementById('resultContainer');
    if (resultContainer) {
        resultContainer.style.display = 'none';
    }
}

// ==================== 文件上传处理 ====================

/**
 * 处理文件选择
 * @param {Event} event - 文件选择事件
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    processSelectedFile(file);
}

/**
 * 处理拖拽事件
 */
function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    document.getElementById('uploadArea').classList.add('drag-over');
}

function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    document.getElementById('uploadArea').classList.remove('drag-over');
}

function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    document.getElementById('uploadArea').classList.remove('drag-over');

    const file = event.dataTransfer.files[0];
    if (file) {
        processSelectedFile(file);
    }
}

/**
 * 处理选中的文件
 * @param {File} file - 文件对象
 */
function processSelectedFile(file) {
    // 验证文件类型
    const allowedExts = ['docx', 'pdf', 'txt', 'doc'];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!allowedExts.includes(ext)) {
        showToast('不支持的文件格式，请上传 .docx / .pdf / .txt 文件', 'error');
        return;
    }

    // 验证文件大小（20MB）
    const maxSize = 20 * 1024 * 1024;
    if (file.size > maxSize) {
        showToast('文件大小超过20MB限制', 'error');
        return;
    }

    selectedFile = file;

    // 显示文件信息
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('fileInfo').style.display = 'inline-flex';
    document.getElementById('btnSubmitFile').disabled = false;
}

/**
 * 清除已选文件
 * @param {Event} event - 点击事件
 */
function clearFile(event) {
    if (event) event.stopPropagation();
    selectedFile = null;
    document.getElementById('fileInput').value = '';
    document.getElementById('fileInfo').style.display = 'none';
    document.getElementById('btnSubmitFile').disabled = true;
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的大小
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ==================== 提交检测 ====================

/**
 * 提交文本检测
 */
async function submitTextDetection() {
    const text = document.getElementById('textInput').value.trim();

    // 空文本检查
    if (!text) {
        showToast('请先输入要检测的文本内容', 'warning');
        return;
    }

    // 字数检查
    const wordCount = countWords(text);
    if (wordCount < 10) {
        showToast('文本过短（不足10字），无法进行有效检测', 'warning');
        return;
    }

    const maxWords = 50000;
    if (wordCount > maxWords) {
        showToast('单次检测最多支持' + maxWords + '字，当前' + wordCount + '字', 'warning');
        return;
    }

    // 获取检测模式
    const detectMode = document.getElementById('detectMode').value;

    // 显示加载动画
    showLoading('正在检测中，AI分析+查重比对进行中...');
    const btn = document.getElementById('btnSubmitText');
    btn.disabled = true;
    btn.textContent = '⏳ 检测中...';

    try {
        const result = await apiRequest('/detect/api/text', {
            method: 'POST',
            body: JSON.stringify({ text: text, mode: detectMode }),
        }, 60000); // 60秒超时

        if (result.success) {
            // 渲染结果
            renderResult(result.report);
            showToast('检测完成！', 'success');
        } else if (result.need_pay) {
            // 需要付费
            showPayPrompt(result);
        } else {
            showToast(result.message || '检测失败', 'error');
        }
    } catch (e) {
        showToast('检测请求异常：' + e.message, 'error');
    } finally {
        hideLoading();
        btn.disabled = false;
        btn.textContent = '🔍 开始检测';
    }
}

/**
 * 提交文件检测
 */
async function submitFileDetection() {
    if (!selectedFile) {
        showToast('请先选择要上传的文件', 'warning');
        return;
    }

    // 显示加载动画
    showLoading('正在上传并解析文件，请稍候...');
    const btn = document.getElementById('btnSubmitFile');
    btn.disabled = true;
    btn.textContent = '⏳ 检测中...';

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分钟超时

        const response = await fetch('/detect/api/file', {
            method: 'POST',
            body: formData,
            signal: controller.signal,
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });

        clearTimeout(timeoutId);

        if (response.status === 401) {
            window.location.href = '/auth/login';
            return;
        }

        const result = await response.json();

        if (result.success) {
            renderResult(result.report);
            showToast('文件检测完成！', 'success');
        } else if (result.need_pay) {
            showPayPrompt(result);
        } else {
            showToast(result.message || '文件检测失败', 'error');
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            showToast('文件检测超时，请检查网络后重试', 'error');
        } else {
            showToast('文件检测异常：' + error.message, 'error');
        }
    } finally {
        hideLoading();
        btn.disabled = false;
        btn.textContent = '🔍 上传并检测';
    }
}

// ==================== 付费提示 ====================

/**
 * 显示付费提示弹窗
 * @param {Object} data - 付费信息 { extra_words, extra_cost, quota_info }
 */
function showPayPrompt(data) {
    const container = document.getElementById('resultContainer');
    if (!container) return;

    container.style.display = 'block';
    container.innerHTML = `
        <div class="pay-prompt" style="text-align:center; padding:40px; background:white; border:1px solid var(--border); border-radius:16px;">
            <div style="font-size:48px; margin-bottom:16px;">💰</div>
            <h3 style="margin-bottom:12px;">额度不足</h3>
            <p style="color:var(--text-secondary); margin-bottom:8px;">
                本次检测共超出 <strong style="color:var(--danger);">${data.extra_words}字</strong>
            </p>
            <p style="color:var(--text-secondary); margin-bottom:24px;">
                需要付费 <strong style="font-size:24px; color:var(--primary);">¥${data.extra_cost}</strong>
            </p>
            ${data.quota_info ? `
            <div style="margin-bottom:20px; padding:12px; background:var(--bg-secondary); border-radius:8px; display:inline-block; text-align:left;">
                <p style="font-size:13px; color:var(--text-muted); margin:0;">
                    🎁 免费额度剩余：${data.quota_info.free_quota_remaining}字
                    ${data.quota_info.is_member ? ' | 👑 会员额度剩余：' + data.quota_info.member_quota_remaining + '字' : ''}
                </p>
            </div>` : ''}
            <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap;">
                <a href="/user/member" class="btn btn-gold">👑 开通会员（¥${data.extra_cost > 10 ? '29.9/月' : '更划算'}）</a>
                <button class="btn btn-outline" onclick="this.closest('.pay-prompt').parentElement.style.display='none'">暂不处理</button>
            </div>
        </div>
    `;

    // 滚动到结果区域
    container.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 结果渲染 ====================

/**
 * 渲染检测结果
 * @param {Object} report - 检测报告数据
 */
function renderResult(report) {
    const container = document.getElementById('resultContainer');
    if (!container) return;

    // 确定评分等级
    let gradeText = '';
    let gradeColor = '';
    const score = report.originality_score;
    if (score >= 80) {
        gradeText = '🟢 优秀 - 原创度较高';
        gradeColor = '#10b981';
    } else if (score >= 60) {
        gradeText = '🟡 良好 - 建议优化部分内容';
        gradeColor = '#f59e0b';
    } else if (score >= 40) {
        gradeText = '🟠 一般 - 建议深度修改';
        gradeColor = '#f97316';
    } else {
        gradeText = '🔴 较低 - 需要大幅修改';
        gradeColor = '#ef4444';
    }

    // AI得分颜色
    const aiColor = report.ai_score > 50 ? '#ef4444' : report.ai_score > 30 ? '#f59e0b' : '#10b981';
    const plagColor = report.plagiarism_score > 50 ? '#ef4444' : report.plagiarism_score > 30 ? '#f59e0b' : '#10b981';

    // 构建AI详情
    let aiDetailsHtml = '';
    if (report.ai_details && report.ai_details.length > 0) {
        aiDetailsHtml = '<div class="score-details">' +
            report.ai_details.map(d => `<div class="detail-row"><span>${d.label}</span><span>${d.value}</span></div>`).join('') +
            '</div>';
    }

    // 构建匹配片段
    let matchedHtml = '';
    if (report.matched_segments && report.matched_segments.length > 0) {
        matchedHtml = `
            <div class="report-section">
                <h3>🔴 重复/相似片段</h3>
                <p class="report-section-desc">以下片段与数据库存在相似匹配，建议进行改写或正确引用</p>
                ${report.matched_segments.map(seg => `
                    <div class="matched-segment">
                        <div class="matched-text">${escapeHtml(seg.text || '')}</div>
                        <div class="matched-meta">
                            <span class="matched-similarity">相似度：${seg.similarity || 0}%</span>
                            <span class="matched-source">📚 ${seg.source || ''}</span>
                            <span class="matched-position">📍 ${seg.position || ''}</span>
                        </div>
                    </div>
                `).join('')}
            </div>`;
    }

    // 构建来源
    let sourcesHtml = '';
    if (report.sources && report.sources.length > 0) {
        sourcesHtml = `
            <div class="report-section">
                <h3>📚 可能来源出处</h3>
                <ul class="source-list">
                    ${report.sources.map(s => `<li class="source-item">${s}</li>`).join('')}
                </ul>
            </div>`;
    }

    // 构建建议
    let aiSuggHtml = '';
    if (report.ai_suggestions && report.ai_suggestions.length > 0) {
        aiSuggHtml = `
            <div class="report-section">
                <h3>💡 AI检测建议</h3>
                <ul class="suggestion-list">
                    ${report.ai_suggestions.map(s => `<li class="suggestion-item">${s}</li>`).join('')}
                </ul>
            </div>`;
    }

    let plagSuggHtml = '';
    if (report.plagiarism_suggestions && report.plagiarism_suggestions.length > 0) {
        plagSuggHtml = `
            <div class="report-section">
                <h3>💡 查重优化建议</h3>
                <ul class="suggestion-list">
                    ${report.plagiarism_suggestions.map(s => `<li class="suggestion-item">${s}</li>`).join('')}
                </ul>
            </div>`;
    }

    // 拼接完整HTML
    container.innerHTML = `
        <!-- 报告头部 -->
        <div class="report-header" style="margin-top:30px;">
            <div class="report-header-left">
                <h2>📋 检测报告</h2>
                <p class="report-meta">
                    检测字数：${report.word_count || 0}字
                    ${report.file_name ? ' | 文件：' + report.file_name : ''}
                    | 模式：${report.detection_mode === 'ai_only' ? '仅AI检测' : report.detection_mode === 'plagiarism_only' ? '仅查重' : '双重检测'}
                </p>
            </div>
            <div class="report-header-right">
                ${report.record_id ? `<a href="/detect/report/${report.record_id}" class="btn btn-outline">📄 查看完整报告</a>` : ''}
                <button class="btn btn-primary" onclick="window.location.reload()">🔄 新建检测</button>
            </div>
        </div>

        <!-- 原创得分 -->
        <div class="score-hero">
            <div class="score-circle-large" style="--score: ${score};">
                <span class="score-number">${score}</span>
                <span class="score-unit">分</span>
            </div>
            <div class="score-label">总体原创得分</div>
            <div class="score-grade" style="color:${gradeColor};">${gradeText}</div>
        </div>

        <!-- 分项得分 -->
        <div class="score-breakdown">
            <div class="score-item-card">
                <div class="score-item-header">
                    <span class="score-item-icon">🤖</span>
                    <h3>AI生成率</h3>
                </div>
                <div class="score-item-value" style="color:${aiColor};">${report.ai_score || 0}%</div>
                <p class="score-item-desc">AI撰写占比</p>
                <div class="score-bar">
                    <div class="score-bar-fill" style="width:${report.ai_score || 0}%; background:${aiColor};"></div>
                </div>
                ${aiDetailsHtml}
            </div>

            <div class="score-item-card">
                <div class="score-item-header">
                    <span class="score-item-icon">👤</span>
                    <h3>人工原创率</h3>
                </div>
                <div class="score-item-value text-green">${report.human_score || 0}%</div>
                <p class="score-item-desc">人工撰写占比</p>
                <div class="score-bar">
                    <div class="score-bar-fill" style="width:${report.human_score || 0}%; background: #10b981;"></div>
                </div>
            </div>

            <div class="score-item-card">
                <div class="score-item-header">
                    <span class="score-item-icon">📊</span>
                    <h3>文本重复率</h3>
                </div>
                <div class="score-item-value" style="color:${plagColor};">${report.plagiarism_score || 0}%</div>
                <p class="score-item-desc">查重匹配率</p>
                <div class="score-bar">
                    <div class="score-bar-fill" style="width:${report.plagiarism_score || 0}%; background:${plagColor};"></div>
                </div>
            </div>
        </div>

        ${matchedHtml}
        ${sourcesHtml}
        ${aiSuggHtml}
        ${plagSuggHtml}

        <!-- AI降重入口 -->
        <div class="report-section">
            <div class="rewrite-cta">
                <div class="rewrite-cta-text">
                    <h3>✨ 需要降低重复率？</h3>
                    <p>使用AI智能降重改写工具，一键优化您的论文</p>
                </div>
                <a href="/tools" class="btn btn-primary-lg">🚀 AI降重改写 →</a>
            </div>
        </div>

        <!-- 免责声明 -->
        <div class="disclaimer-inline" style="margin-top:24px;">
            ⚠️ <strong>重要提示：</strong>本平台检测结果仅供参考，学校定稿请以官方查重系统为准。
            用户上传文稿检测完成后自动删除，我们不会永久保存您的文稿。
        </div>
    `;

    // 显示结果容器
    container.style.display = 'block';

    // 滚动到结果区域
    container.scrollIntoView({ behavior: 'smooth' });
}
