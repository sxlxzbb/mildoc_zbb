// 文件浏览器功能
class FileBrowser {
    constructor() {
        this.currentPath = new URLSearchParams(window.location.search).get('path') || '';
        this.uploadingFiles = new Map(); // 存储正在上传的文件
        this.init();
    }

    init() {
        this.loadFiles();
        this.updateBreadcrumb();
        this.bindEvents();
    }

    // 绑定事件
    bindEvents() {
        // 上传按钮事件
        document.getElementById('upload-btn').addEventListener('click', () => {
            this.showUploadDialog();
        });

        // 文件选择事件
        document.getElementById('file-input').addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });

        // 创建目录按钮事件
        document.getElementById('create-dir-btn').addEventListener('click', () => {
            this.showCreateDirectoryDialog();
        });

        // 删除目录按钮事件
        document.getElementById('delete-dir-btn').addEventListener('click', () => {
            this.showDeleteDirectoryDialog();
        });
    }

    // 加载文件列表
    loadFiles() {
        const contentElement = document.getElementById('file-list-content');
        Utils.showLoading(contentElement);

        const url = `/api/files?path=${encodeURIComponent(this.currentPath)}`;
        
        Utils.ajax(url)
            .then(data => {
                this.renderFiles(data.files);
            })
            .catch(error => {
                Utils.showError(contentElement, error.message);
            });
    }

    // 渲染文件列表
    renderFiles(files) {
        const contentElement = document.getElementById('file-list-content');
        
        // 检查是否显示删除目录按钮
        this.updateDeleteDirectoryButton(files);
        
        if (files.length === 0) {
            contentElement.innerHTML = '<div class="loading">此目录为空</div>';
            return;
        }

        let html = '';
        
        // 如果不在根目录，显示返回上级目录
        if (this.currentPath) {
            const parentPath = this.currentPath.substring(0, this.currentPath.lastIndexOf('/'));
            html += `
                <div class="file-item" onclick="fileBrowser.navigateToPath('${parentPath}')">
                    <div class="file-item-name">
                        <span class="file-icon folder">📁</span>
                        <span>..</span>
                    </div>
                    <div class="file-item-size">-</div>
                    <div class="file-item-modified">-</div>
                </div>
            `;
        }

        files.forEach(file => {
            const icon = file.type === 'folder' ? '📁' : '📄';
            const size = file.type === 'folder' ? '-' : Utils.formatFileSize(file.size);
            const onclick = file.type === 'folder' 
                ? `fileBrowser.navigateToPath('${file.path}')` 
                : `fileBrowser.viewFile('${file.path}')`;

            html += `
                <div class="file-item" onclick="${onclick}">
                    <div class="file-item-name">
                        <span class="file-icon ${file.type}">${icon}</span>
                        <span>${file.name}</span>
                    </div>
                    <div class="file-item-size">${size}</div>
                    <div class="file-item-modified">${file.modified}</div>
                </div>
            `;
        });

        contentElement.innerHTML = html;
    }

    // 导航到指定路径
    navigateToPath(path) {
        const url = new URL(window.location);
        if (path) {
            url.searchParams.set('path', path);
        } else {
            url.searchParams.delete('path');
        }
        window.location.href = url.toString();
    }

    // 查看文件详情
    viewFile(filePath) {
        // 对路径进行正确的编码
        const encodedPath = filePath.split('/').map(part => encodeURIComponent(part)).join('/');
        window.location.href = `/file/${encodedPath}`;
    }

    // 更新面包屑导航
    updateBreadcrumb() {
        const breadcrumbPath = document.getElementById('breadcrumb-path');
        
        if (!this.currentPath) {
            breadcrumbPath.innerHTML = '';
            return;
        }

        const parts = this.currentPath.split('/').filter(part => part);
        let html = '';
        let currentPath = '';

        parts.forEach((part, index) => {
            currentPath += (currentPath ? '/' : '') + part;
            
            if (index === parts.length - 1) {
                html += ` / <span class="breadcrumb-item">${part}</span>`;
            } else {
                html += ` / <span class="breadcrumb-item">
                    <a href="?path=${encodeURIComponent(currentPath)}" class="breadcrumb-link">${part}</a>
                </span>`;
            }
        });

        breadcrumbPath.innerHTML = html;
    }

    // 显示上传对话框
    showUploadDialog() {
        document.getElementById('file-input').click();
    }

    // 处理文件选择
    handleFileSelect(event) {
        const files = Array.from(event.target.files);
        if (files.length === 0) return;

        // 重置文件选择器
        event.target.value = '';

        // 开始上传文件
        this.uploadFiles(files);
    }

    // 上传文件
    async uploadFiles(files) {
        const formData = new FormData();
        
        // 添加当前路径
        formData.append('path', this.currentPath);
        
        // 添加所有文件
        files.forEach(file => {
            formData.append('files', file);
        });

        // 在列表中显示上传中的文件
        this.showUploadingFiles(files);

        try {
            // 发送上传请求
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            
            // 处理上传结果
            this.handleUploadResult(result);

        } catch (error) {
            console.error('上传失败:', error);
            this.handleUploadError(error.message);
        }
    }

    // 在列表中显示上传中的文件
    showUploadingFiles(files) {
        const contentElement = document.getElementById('file-list-content');
        
        files.forEach(file => {
            const fileId = 'upload-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
            this.uploadingFiles.set(fileId, file);

            const uploadItem = document.createElement('div');
            uploadItem.className = 'file-item uploading';
            uploadItem.id = fileId;
            uploadItem.innerHTML = `
                <div class="file-item-name">
                    <span class="file-icon file">📄</span>
                    <span>${file.name}</span>
                    <span class="upload-status">上传中...</span>
                </div>
                <div class="file-item-size">${Utils.formatFileSize(file.size)}</div>
                <div class="file-item-modified">
                    <div class="upload-progress">
                        <div class="progress-bar">
                            <div class="progress-fill"></div>
                        </div>
                    </div>
                </div>
            `;

            // 添加到列表顶部（在返回上级目录项之后）
            const firstFileItem = contentElement.querySelector('.file-item:not(.uploading)');
            if (firstFileItem && firstFileItem.textContent.includes('..')) {
                firstFileItem.insertAdjacentElement('afterend', uploadItem);
            } else {
                contentElement.insertBefore(uploadItem, contentElement.firstChild);
            }

            // 模拟进度条动画
            setTimeout(() => {
                const progressFill = uploadItem.querySelector('.progress-fill');
                if (progressFill) {
                    progressFill.style.width = '90%';
                }
            }, 100);
        });
    }

    // 处理上传结果
    handleUploadResult(result) {
        // 移除上传中的文件项
        this.uploadingFiles.forEach((file, fileId) => {
            const uploadItem = document.getElementById(fileId);
            if (uploadItem) {
                uploadItem.remove();
            }
        });
        this.uploadingFiles.clear();

        // 显示上传结果
        this.showUploadResultDialog(result);
    }

    // 处理上传错误
    handleUploadError(errorMessage) {
        // 移除上传中的文件项并显示错误
        this.uploadingFiles.forEach((file, fileId) => {
            const uploadItem = document.getElementById(fileId);
            if (uploadItem) {
                const statusElement = uploadItem.querySelector('.upload-status');
                const progressElement = uploadItem.querySelector('.upload-progress');
                
                if (statusElement) statusElement.textContent = '上传失败';
                if (progressElement) progressElement.innerHTML = '<span class="error-text">❌</span>';
                
                uploadItem.classList.add('upload-error');
                
                // 3秒后移除
                setTimeout(() => {
                    uploadItem.remove();
                }, 3000);
            }
        });
        this.uploadingFiles.clear();

        // 显示错误消息
        this.showUploadResultDialog({
            success: false,
            uploaded_count: 0,
            failed_count: this.uploadingFiles.size,
            message: errorMessage,
            uploaded_files: [],
            failed_files: []
        });
    }

    // 显示上传结果对话框
    showUploadResultDialog(result) {
        const modalHtml = `
            <div id="upload-result-modal" class="modal-overlay">
                <div class="modal-content upload-result-modal">
                    <div class="modal-header">
                        <h3>上传结果</h3>
                    </div>
                    <div class="modal-body">
                        <div class="upload-result ${result.success ? 'success' : 'error'}">
                            <div class="result-icon">${result.success ? '✅' : '❌'}</div>
                            <div class="result-message">
                                <p><strong>${result.message}</strong></p>
                                ${result.uploaded_count > 0 ? `<p>成功上传: ${result.uploaded_count} 个文件</p>` : ''}
                                ${result.failed_count > 0 ? `<p>上传失败: ${result.failed_count} 个文件</p>` : ''}
                            </div>
                        </div>
                        
                        ${result.failed_files && result.failed_files.length > 0 ? `
                            <div class="failed-files">
                                <h4>失败文件详情:</h4>
                                <ul>
                                    ${result.failed_files.map(file => 
                                        `<li><strong>${file.filename}:</strong> ${file.error}</li>`
                                    ).join('')}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                    <div class="modal-footer">
                        <button onclick="fileBrowser.closeUploadResultDialog()" class="btn btn-primary">确认</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // 关闭上传结果对话框
    closeUploadResultDialog() {
        const modal = document.getElementById('upload-result-modal');
        if (modal) {
            modal.remove();
        }
        
        // 刷新文件列表
        this.loadFiles();
    }

    // 更新删除目录按钮的显示状态
    updateDeleteDirectoryButton(files) {
        const deleteBtn = document.getElementById('delete-dir-btn');
        
        // 只有在非根目录且目录为空时才显示删除按钮
        if (this.currentPath && files.length === 0) {
            deleteBtn.style.display = 'inline-block';
        } else {
            deleteBtn.style.display = 'none';
        }
    }

    // 显示创建目录对话框
    showCreateDirectoryDialog() {
        const modalHtml = `
            <div id="create-dir-modal" class="modal-overlay">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>创建目录</h3>
                        <button onclick="fileBrowser.closeCreateDirectoryDialog()" class="modal-close">×</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label class="form-label">目录名称:</label>
                            <input type="text" id="dir-name-input" class="form-input" placeholder="请输入目录名称" maxlength="255">
                            <small style="color: #666; margin-top: 5px; display: block;">
                                目录名称不能包含以下字符: / \\ : * ? " < > |
                            </small>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button onclick="fileBrowser.closeCreateDirectoryDialog()" class="btn btn-cancel">取消</button>
                        <button onclick="fileBrowser.createDirectory()" class="btn btn-primary" id="create-dir-confirm">创建</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 聚焦到输入框
        setTimeout(() => {
            const input = document.getElementById('dir-name-input');
            if (input) {
                input.focus();
                // 回车键确认
                input.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        this.createDirectory();
                    }
                });
            }
        }, 100);
    }

    // 关闭创建目录对话框
    closeCreateDirectoryDialog() {
        const modal = document.getElementById('create-dir-modal');
        if (modal) {
            modal.remove();
        }
    }

    // 创建目录
    async createDirectory() {
        const input = document.getElementById('dir-name-input');
        const confirmBtn = document.getElementById('create-dir-confirm');
        
        if (!input) return;
        
        const dirName = input.value.trim();
        
        // 验证目录名称
        if (!dirName) {
            alert('请输入目录名称');
            input.focus();
            return;
        }
        
        // 检查非法字符
        const invalidChars = /[\/\\:*?"<>|]/;
        if (invalidChars.test(dirName)) {
            alert('目录名称不能包含以下字符: / \\ : * ? " < > |');
            input.focus();
            return;
        }
        
        // 禁用按钮，防止重复提交
        confirmBtn.disabled = true;
        confirmBtn.textContent = '创建中...';
        
        try {
            const response = await fetch('/api/create-directory', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    path: this.currentPath,
                    name: dirName
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // 成功创建
                this.closeCreateDirectoryDialog();
                this.loadFiles(); // 刷新文件列表
                
                // 显示成功消息
                this.showMessage('目录创建成功', 'success');
            } else {
                // 创建失败
                alert(result.error || '创建目录失败');
                confirmBtn.disabled = false;
                confirmBtn.textContent = '创建';
                input.focus();
            }
        } catch (error) {
            console.error('创建目录失败:', error);
            alert('创建目录失败: ' + error.message);
            confirmBtn.disabled = false;
            confirmBtn.textContent = '创建';
        }
    }

    // 显示删除目录对话框
    showDeleteDirectoryDialog() {
        const currentDirName = this.currentPath.split('/').pop() || this.currentPath;
        
        const modalHtml = `
            <div id="delete-dir-modal" class="modal-overlay">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>删除目录</h3>
                        <button onclick="fileBrowser.closeDeleteDirectoryDialog()" class="modal-close">×</button>
                    </div>
                    <div class="modal-body">
                        <div class="delete-warning">
                            <div class="warning-icon">⚠️</div>
                            <div class="warning-text">
                                <p>您确定要删除目录 "<span class="file-name-highlight">${currentDirName}</span>" 吗？</p>
                                <p><strong>此操作不可撤销！</strong></p>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button onclick="fileBrowser.closeDeleteDirectoryDialog()" class="btn btn-cancel">取消</button>
                        <button onclick="fileBrowser.deleteDirectory()" class="btn btn-danger" id="delete-dir-confirm">删除</button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // 关闭删除目录对话框
    closeDeleteDirectoryDialog() {
        const modal = document.getElementById('delete-dir-modal');
        if (modal) {
            modal.remove();
        }
    }

    // 删除目录
    async deleteDirectory() {
        const confirmBtn = document.getElementById('delete-dir-confirm');
        
        // 禁用按钮，防止重复提交
        confirmBtn.disabled = true;
        confirmBtn.textContent = '删除中...';
        
        try {
            const response = await fetch('/api/delete-directory', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    path: this.currentPath
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // 成功删除
                this.closeDeleteDirectoryDialog();
                
                // 导航到父目录
                const parentPath = this.currentPath.substring(0, this.currentPath.lastIndexOf('/'));
                this.navigateToPath(parentPath);
                
                // 显示成功消息
                this.showMessage('目录删除成功', 'success');
            } else {
                // 删除失败
                alert(result.error || '删除目录失败');
                confirmBtn.disabled = false;
                confirmBtn.textContent = '删除';
            }
        } catch (error) {
            console.error('删除目录失败:', error);
            alert('删除目录失败: ' + error.message);
            confirmBtn.disabled = false;
            confirmBtn.textContent = '删除';
        }
    }

    // 显示消息提示
    showMessage(text, type = 'info') {
        const messageHtml = `
            <div class="delete-message ${type}">
                <div class="message-icon">${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</div>
                <div class="message-text">${text}</div>
                <button onclick="this.parentElement.remove()" class="message-close">×</button>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', messageHtml);
        
        // 3秒后自动消失
        setTimeout(() => {
            const message = document.querySelector('.delete-message');
            if (message) {
                message.remove();
            }
        }, 3000);
    }
}

// 初始化文件浏览器
let fileBrowser;
document.addEventListener('DOMContentLoaded', function() {
    fileBrowser = new FileBrowser();
}); 