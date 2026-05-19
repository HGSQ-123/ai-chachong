/**
 * ============================================================
 * AI查重+论文重复率检测系统 - 全局脚本
 * 包含：Toast通知、页面通用交互、工具函数
 * ============================================================
 */

/**
 * 显示Toast通知
 * @param {string} message - 通知文本
 * @param {string} type - 类型: success/error/warning/info
 * @param {number} duration - 显示毫秒数（默认3000）
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // 自动移除
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, duration);
}

/**
 * 发送API请求的封装函数（带超时和错误处理）
 * @param {string} url - 请求地址
 * @param {Object} options - fetch选项
 * @param {number} timeoutMs - 超时毫秒数（默认30秒）
 * @returns {Promise<Object>} 响应数据
 */
async function apiRequest(url, options = {}, timeoutMs = 30000) {
    // 创建超时控制器
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                ...options.headers,
            },
        });

        clearTimeout(timeoutId);

        // 401未登录，自动跳转登录页
        if (response.status === 401) {
            const data = await response.json().catch(() => ({}));
            showToast(data.message || '请先登录', 'warning');
            if (data.redirect) {
                setTimeout(() => { window.location.href = data.redirect; }, 1500);
            }
            return { success: false, message: '请先登录' };
        }

        // 402需要付费
        if (response.status === 402) {
            const data = await response.json();
            return data; // 调用方自行处理付费提示
        }

        const data = await response.json();
        return data;

    } catch (error) {
        clearTimeout(timeoutId);

        if (error.name === 'AbortError') {
            showToast('请求超时，请检查网络后重试', 'error');
            return { success: false, message: '请求超时' };
        }

        showToast('网络异常，请检查网络连接后重试', 'error');
        return { success: false, message: `网络异常：${error.message}` };
    }
}

/**
 * 显示加载动画
 * @param {string} text - 加载提示文字
 */
function showLoading(text = '正在检测中，请稍候...') {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.querySelector('.loading-text').textContent = text;
        overlay.style.display = 'flex';
    }
}

/**
 * 隐藏加载动画
 */
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

/**
 * HTML转义（防XSS）
 * @param {string} text - 需要转义的文本
 * @returns {string} 转义后的安全文本
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 格式化数字（添加千位分隔符）
 * @param {number} num - 数字
 * @returns {string}
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * 防抖函数
 * @param {Function} fn - 需要防抖的函数
 * @param {number} delay - 延迟毫秒数
 * @returns {Function}
 */
function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// ==================== 页面加载完成后的初始化 ====================
document.addEventListener('DOMContentLoaded', function () {
    // 自动隐藏Flash消息（5秒后）
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.transition = 'opacity 0.3s';
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });

    // 公告栏关闭按钮
    const announcementBar = document.getElementById('announcementBar');
    if (announcementBar) {
        const closeBtn = announcementBar.querySelector('.announcement-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                announcementBar.style.display = 'none';
            });
        }
    }
});
