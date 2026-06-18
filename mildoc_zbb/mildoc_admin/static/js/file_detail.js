// 文件详情页面功能
class FileDetail {
    constructor() {
        this.filePath = this.getFilePathFromURL();
        this.init();
    }

    // 从 URL 获取文件路径
    getFilePathFromURL() {
        const pathParts = window.location.pathname.split('/');
        const encodedPath = pathParts.slice(2).join('/'); // 去掉 /file/ 前缀
        // 解码路径
        return decodeURIComponent(encodedPath);
    }

    init() {
        this.loadFileDetail();
        this.bindEvents();
    }

    // 绑定事件
    bindEvents() {
        document.getElementById('expand-all').addEventListener('click', () => {
            this.expandAllChunks();
        });

        document.getElementById('collapse-all').addEventListener('click', () => {
            this.collapseAllChunks();
        });

        document.getElementById('back-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.goBack();
        });

        document.getElementById('download-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.downloadFile();
        });

        document.getElementById('delete-btn').addEventListener('click', (e) => {
            e.preventDefault();
            this.showDeleteConfirmDialog();
        });
    }

    // 返回文件所在目录
    goBack() {
        // 计算父目录路径
        const pathParts = this.filePath.split('/');
        pathParts.pop(); // 移除文件名
        const parentPath = pathParts.join('/');
        
        // 构建返回 URL
        if (parentPath) {
            window.location.href = `/files?path=${encodeURIComponent(parentPath)}`;
        } else {
            window.location.href = '/files';
        }
    }

    // 下载文件
    downloadFile() {
        const downloadBtn = document.getElementById('download-btn');
        const originalText = downloadBtn.textContent;
        
        // 显示下载状态
        downloadBtn.textContent = '下载中...';
        downloadBtn.classList.add('downloading');
        
        // 构建下载URL
        const downloadUrl = `/api/file/${this.filePath.split('/').map(part => encodeURIComponent(part)).join('/')}/download`;
        
        // 创建隐藏的下载链接
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.style.display = 'none';
        document.body.appendChild(link);
        
        // 触发下载
        link.click();
        
        // 清理
        document.body.removeChild(link);
        
        // 恢复按钮状态
        setTimeout(() => {
            downloadBtn.textContent = originalText;
            downloadBtn.classList.remove('downloading');
        }, 1000);
    }

    // 显示删除确认对话框
    showDeleteConfirmDialog() {
        const fileName = decodeURIComponent(this.filePath.split('/').pop());
        
        const modalHtml = `
            <div id="delete-confirm-modal" class="modal-overlay" onclick="fileDetail.closeDeleteModal(event)">
                <div class="modal-content delete-modal">
                    <div class="modal-header">
                        <h3>确认删除文件</h3>
                        <button onclick="fileDetail.closeDeleteModal()" class="modal-close">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="delete-warning">
                            <div class="warning-icon">⚠️</div>
                            <div class="warning-text">
                                <p><strong>您确定要删除以下文件吗？</strong></p>
                                <p class="file-name-highlight">${this.escapeHtml(fileName)}</p>
                                <p class="warning-message">此操作将永久删除文件，无法恢复。如果文件已被索引，相关的向量数据也会一并删除。</p>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button onclick="fileDetail.closeDeleteModal()" class="btn btn-cancel">取消</button>
                        <button onclick="fileDetail.confirmDeleteFile()" class="btn btn-danger" id="confirm-delete-btn">确认删除</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // 关闭删除确认对话框
    closeDeleteModal(event) {
        if (!event || event.target.classList.contains('modal-overlay') || event.target.classList.contains('modal-close')) {
            const modal = document.getElementById('delete-confirm-modal');
            if (modal) {
                modal.remove();
            }
        }
    }

    // 确认删除文件
    confirmDeleteFile() {
        const confirmBtn = document.getElementById('confirm-delete-btn');
        const originalText = confirmBtn.textContent;
        
        // 显示删除中状态
        confirmBtn.textContent = '删除中...';
        confirmBtn.disabled = true;
        confirmBtn.classList.add('loading');
        
        // 构建删除URL
        const encodedPath = this.filePath.split('/').map(part => encodeURIComponent(part)).join('/');
        const deleteUrl = `/api/file/${encodedPath}/delete`;
        
        Utils.ajax(deleteUrl, 'DELETE')
            .then(data => {
                // 删除成功
                this.closeDeleteModal();
                this.showDeleteSuccessMessage(data.message);
                
                // 2秒后返回文件列表
                setTimeout(() => {
                    this.goBack();
                }, 2000);
            })
            .catch(error => {
                // 删除失败
                this.showDeleteErrorMessage(error.message);
                
                // 恢复按钮状态
                confirmBtn.textContent = originalText;
                confirmBtn.disabled = false;
                confirmBtn.classList.remove('loading');
            });
    }

    // 显示删除成功消息
    showDeleteSuccessMessage(message) {
        const messageHtml = `
            <div id="delete-success-message" class="delete-message success">
                <div class="message-icon">✅</div>
                <div class="message-text">
                    <strong>删除成功</strong><br>
                    ${message}<br>
                    <small>2秒后自动返回文件列表...</small>
                </div>
            </div>
        `;
        
        const fileInfoElement = document.getElementById('file-info');
        fileInfoElement.insertAdjacentHTML('beforebegin', messageHtml);
        
        // 3秒后自动移除消息
        setTimeout(() => {
            const msg = document.getElementById('delete-success-message');
            if (msg) msg.remove();
        }, 3000);
    }

    // 显示删除错误消息
    showDeleteErrorMessage(message) {
        const messageHtml = `
            <div id="delete-error-message" class="delete-message error">
                <div class="message-icon">❌</div>
                <div class="message-text">
                    <strong>删除失败</strong><br>
                    ${message}
                </div>
                <button onclick="document.getElementById('delete-error-message').remove()" class="message-close">&times;</button>
            </div>
        `;
        
        const fileInfoElement = document.getElementById('file-info');
        fileInfoElement.insertAdjacentHTML('beforebegin', messageHtml);
    }

    // 加载文件详情
    loadFileDetail() {
        const fileInfoElement = document.getElementById('file-info');
        Utils.showLoading(fileInfoElement);

        // 更新页面标题
        document.getElementById('file-title').textContent = `文件详情 - ${decodeURIComponent(this.filePath.split('/').pop())}`;

        const url = `/api/file/${this.filePath.split('/').map(part => encodeURIComponent(part)).join('/')}`;
        
        Utils.ajax(url)
            .then(data => {
                this.renderFileInfo(data);
                if (data.chunks && data.chunks.length > 0) {
                    this.renderChunks(data.chunks);
                }
            })
            .catch(error => {
                Utils.showError(fileInfoElement, error.message);
            });
    }

    // 渲染文件信息
    renderFileInfo(fileInfo) {
        const fileInfoElement = document.getElementById('file-info');
        
        const statusBadge = fileInfo.indexed 
            ? '<span class="status-badge status-indexed">已索引</span>'
            : '<span class="status-badge status-not-indexed">未索引</span>';

        let html = `
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">文件名</div>
                    <div class="info-value">${fileInfo.doc_name}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">文件路径</div>
                    <div class="info-value">${fileInfo.doc_path_name}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">文件大小</div>
                    <div class="info-value">${Utils.formatFileSize(fileInfo.file_size)}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">MD5值</div>
                    <div class="info-value">${fileInfo.file_md5}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">最后修改时间</div>
                    <div class="info-value">${fileInfo.last_modified}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">索引状态</div>
                    <div class="info-value">
                        ${statusBadge}
                    </div>
                </div>
        `;

        if (fileInfo.indexed) {
            html += `
                <div class="info-item">
                    <div class="info-label">文档类型</div>
                    <div class="info-value">${fileInfo.doc_type || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">索引MD5</div>
                    <div class="info-value">${fileInfo.indexed_md5 || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">文档长度</div>
                    <div class="info-value">${fileInfo.doc_length || 0} 字符</div>
                </div>
                <div class="info-item">
                    <div class="info-label">嵌入模型</div>
                    <div class="info-value">${fileInfo.embedding_model || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">分片数量</div>
                    <div class="info-value">${fileInfo.chunks ? fileInfo.chunks.length : 0} 个</div>
                </div>
            `;
        }

        html += '</div>';
        fileInfoElement.innerHTML = html;
    }

    // 渲染文件分片
    renderChunks(chunks) {
        const chunksElement = document.getElementById('file-chunks');
        const chunksContent = document.getElementById('chunks-content');
        
        if (chunks.length === 0) {
            chunksElement.style.display = 'none';
            return;
        }

        chunksElement.style.display = 'block';
        
        let html = '';
        chunks.forEach((chunk, index) => {
            const chunkId = `chunk-${index}`;
            html += `
                <div class="chunk-item">
                    <div class="chunk-header" onclick="fileDetail.toggleChunk('${chunkId}')">
                        <div class="chunk-title">分片 ${index + 1} (${chunk.length} 字符)</div>
                        <div class="chunk-toggle" id="${chunkId}-toggle">展开</div>
                    </div>
                    <div class="chunk-content collapsed" id="${chunkId}">${this.escapeHtml(chunk.content)}</div>
                </div>
            `;
        });

        chunksContent.innerHTML = html;
    }

    // 切换分片展开/折叠
    toggleChunk(chunkId) {
        const content = document.getElementById(chunkId);
        const toggle = document.getElementById(chunkId + '-toggle');
        
        if (content.classList.contains('collapsed')) {
            content.classList.remove('collapsed');
            toggle.textContent = '折叠';
        } else {
            content.classList.add('collapsed');
            toggle.textContent = '展开';
        }
    }

    // 展开所有分片
    expandAllChunks() {
        const chunks = document.querySelectorAll('.chunk-content');
        const toggles = document.querySelectorAll('.chunk-toggle');
        
        chunks.forEach(chunk => chunk.classList.remove('collapsed'));
        toggles.forEach(toggle => toggle.textContent = '折叠');
    }

    // 折叠所有分片
    collapseAllChunks() {
        const chunks = document.querySelectorAll('.chunk-content');
        const toggles = document.querySelectorAll('.chunk-toggle');
        
        chunks.forEach(chunk => chunk.classList.add('collapsed'));
        toggles.forEach(toggle => toggle.textContent = '展开');
    }


    // HTML 转义
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// 初始化文件详情页面
let fileDetail;
document.addEventListener('DOMContentLoaded', function() {
    fileDetail = new FileDetail();
}); 