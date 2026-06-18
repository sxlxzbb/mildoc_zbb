// 通用工具函数
const Utils = {
    // 格式化文件大小
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // 显示加载状态
    showLoading: function(element) {
        element.innerHTML = '<div class="loading">加载中...</div>';
    },

    // 显示错误信息
    showError: function(element, message) {
        element.innerHTML = `<div class="error">错误: ${message}</div>`;
    },

    // 发送 AJAX 请求
    ajax: function(url, methodOrOptions = {}) {
        let options = {};
        
        // 如果第二个参数是字符串，视为 HTTP method
        if (typeof methodOrOptions === 'string') {
            options = { method: methodOrOptions };
        } else {
            options = methodOrOptions;
        }
        
        return fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        }).then(response => {
            if (!response.ok) {
                // 对于404错误，尝试解析JSON响应以获取更详细的错误信息
                if (response.status === 404) {
                    return response.json().then(data => {
                        throw new Error(data.error || `文件不存在 (${response.status})`);
                    }).catch(() => {
                        throw new Error(`文件不存在 (${response.status})`);
                    });
                }
                
                // 尝试解析错误响应
                return response.json().then(data => {
                    throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
                }).catch(() => {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                });
            }
            return response.json();
        });
    }
};

// 初始化页面
document.addEventListener('DOMContentLoaded', function() {
    // 自动隐藏闪现消息
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            message.style.opacity = '0';
            setTimeout(function() {
                message.remove();
            }, 300);
        }, 5000);
    });
}); 