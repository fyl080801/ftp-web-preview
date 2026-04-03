#!/usr/bin/env python3
"""FTPS Web 文件预览应用"""

import os
import subprocess
import re
import logging
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
import tempfile
from pathlib import PurePosixPath
from functools import wraps

app = Flask(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FTPS 配置
FTP_HOST = os.environ.get('FTP_HOST', '192.168.68.246')
FTP_PORT = os.environ.get('FTP_PORT', '990')
FTP_USER = os.environ.get('FTP_USER', 'bblp')
FTP_PASS = os.environ.get('FTP_PASS', 'c97b754b')

# 安全配置
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
ALLOWED_EXTENSIONS = {'.3mf', '.gcode', '.bgcode', '.txt', '.stl'}
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

def secure_path(path):
    """安全路径处理，防止路径遍历攻击"""
    # 规范化路径
    path = path.lstrip('/')
    # 使用 PurePosixPath 解析
    try:
        clean_path = PurePosixPath('/' + path)
        # 检查是否包含危险的路径遍历
        if '..' in clean_path.parts:
            raise ValueError("Path traversal detected")
        return str(clean_path)
    except Exception as e:
        logger.warning(f"Invalid path attempt: {path} - {e}")
        raise ValueError(f"Invalid path: {path}")

def is_allowed_file(filename):
    """检查文件类型是否在白名单中"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def retry_on_failure(func):
    """重试装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except subprocess.TimeoutExpired as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} timed out for {func.__name__}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {func.__name__}: {e}")
                break
        return {'error': f'Operation failed after {MAX_RETRIES} retries: {str(last_error)}'}
    return wrapper

@retry_on_failure
def ftps_list(path='/'):
    """使用 curl 获取 FTPS 隐式 TLS 文件列表 (端口 990)"""
    try:
        # 安全路径处理
        safe_path = secure_path(path)
        
        logger.info(f"Listing directory: {safe_path}")
        
        # 构建完整 URL
        url = f'ftps://{FTP_USER}:{FTP_PASS}@{FTP_HOST}:{FTP_PORT}{safe_path}'
        
        cmd = [
            'curl', '--ssl-reqd', '-k', '-s',
            url,
            '--max-time', '30'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f'FTP error code {result.returncode}'
            logger.error(f"FTP list error: {error_msg}")
            return {'error': f'FTP error: {error_msg}', 'url': url}
        
        files = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            # 解析 LIST 格式: -rwxr-xr-x 1 103 107 52569 Mar 30 07:04 filename
            match = re.match(r'^(\S+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line)
            if match:
                perms, links, owner, group, size, month, day, time_or_year, name = match.groups()
                
                # 解析日期
                try:
                    year = datetime.now().year
                    if ':' in time_or_year:
                        date_str = f"{year}-{month}-{day}"
                    else:
                        date_str = f"{time_or_year}-{month}-{day}"
                except:
                    date_str = f"{month}-{day}"
                
                is_dir = perms.startswith('d')
                size_int = int(size)
                
                files.append({
                    'name': name,
                    'size': size_int,
                    'size_formatted': format_size(size_int),
                    'is_dir': is_dir,
                    'permissions': perms,
                    'owner': owner,
                    'group': group,
                    'modified': f"{month} {day} {time_or_year}",
                    'is_3mf': name.lower().endswith('.3mf')
                })
        
        logger.info(f"Listed {len(files)} items in {safe_path}")
        return {'files': files, 'path': safe_path}
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        logger.exception(f"Unexpected error in ftps_list: {e}")
        return {'error': f'Unexpected error: {str(e)}'}

@retry_on_failure
def ftps_download(remote_path):
    """下载 FTPS 文件到临时目录（隐式 TLS）"""
    try:
        # 安全路径处理
        safe_path = secure_path(remote_path)
        
        logger.info(f"Downloading file: {safe_path}")
        
        fd, local_path = tempfile.mkstemp(suffix=os.path.basename(safe_path))
        os.close(fd)
        
        url = f'ftps://{FTP_USER}:{FTP_PASS}@{FTP_HOST}:{FTP_PORT}{safe_path}'
        
        cmd = [
            'curl', '--ssl-reqd', '-k', '-o', local_path,
            url,
            '--max-time', '300'
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=310)
        
        if result.returncode == 0:
            # 检查文件大小
            file_size = os.path.getsize(local_path)
            if file_size > MAX_FILE_SIZE:
                os.remove(local_path)
                logger.warning(f"File too large: {file_size} bytes")
                return {'error': f'File exceeds maximum size limit ({MAX_FILE_SIZE // (1024*1024)}MB)'}
            
            logger.info(f"Downloaded {safe_path} ({file_size} bytes)")
            return local_path
        return None
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        logger.exception(f"Download error: {e}")
        return None

def ftps_upload(local_file, remote_path):
    """上传文件到 FTPS (隐式 TLS，端口 990)"""
    try:
        # 安全路径处理
        safe_path = secure_path(remote_path)
        
        # 检查文件大小
        file_size = os.path.getsize(local_file)
        if file_size > MAX_FILE_SIZE:
            return {'error': f'File exceeds maximum size limit ({MAX_FILE_SIZE // (1024*1024)}MB)'}
        
        filename = os.path.basename(safe_path)
        
        # 检查文件类型白名单
        if not is_allowed_file(filename):
            allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
            return {'error': f'File type not allowed. Allowed types: {allowed}'}
        
        logger.info(f"Uploading file: {safe_path} ({file_size} bytes)")
        
        # 使用 curl -T 上传
        url = f'ftps://{FTP_USER}:{FTP_PASS}@{FTP_HOST}:{FTP_PORT}{safe_path}'
        
        cmd = [
            'curl', '--ssl-reqd', '-k', '-T', local_file,
            url,
            '--max-time', '600'  # 上传可能需要更长时间
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=610)
        
        if result.returncode == 0:
            logger.info(f"Upload successful: {safe_path}")
            return {'success': True, 'path': safe_path, 'size': file_size}
        else:
            error_msg = result.stderr.strip() or f'Upload failed with code {result.returncode}'
            logger.error(f"Upload error: {error_msg}")
            return {'error': error_msg}
            
    except subprocess.TimeoutExpired:
        logger.error(f"Upload timeout for {remote_path}")
        return {'error': 'Upload timed out'}
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        logger.exception(f"Upload error: {e}")
        return {'error': str(e)}

@app.route('/')
def index():
    """主页"""
    logger.info("Index page accessed")
    return render_template('index.html', ftp_host=FTP_HOST, ftp_port=FTP_PORT)

@app.route('/api/list')
def api_list():
    """API: 获取文件列表"""
    path = request.args.get('path', '/')
    logger.info(f"API list request for path: {path}")
    
    result = ftps_list(path)
    
    if 'error' in result:
        logger.error(f"List error: {result['error']}")
        return jsonify(result), 500
    
    return jsonify(result)

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """API: 上传文件"""
    logger.info("Upload request received")
    
    # 检查是否有文件
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = file.filename
    
    # 检查文件类型白名单
    if not is_allowed_file(filename):
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return jsonify({'error': f'File type not allowed. Allowed types: {allowed}'}), 400
    
    # 获取目标路径
    remote_dir = request.form.get('path', '/')
    
    # 安全路径处理
    try:
        safe_dir = secure_path(remote_dir)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # 构建远程文件路径
    remote_path = f"{safe_dir.rstrip('/')}/{filename}"
    
    # 检查 Content-Length 防止超大文件
    content_length = request.content_length
    if content_length and content_length > MAX_FILE_SIZE:
        return jsonify({'error': f'File exceeds maximum size limit ({MAX_FILE_SIZE // (1024*1024)}MB)'}), 400
    
    # 保存到临时文件
    try:
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        file.save(temp_path)
        
        # 再次检查文件大小
        file_size = os.path.getsize(temp_path)
        if file_size > MAX_FILE_SIZE:
            os.remove(temp_path)
            return jsonify({'error': f'File exceeds maximum size limit ({MAX_FILE_SIZE // (1024*1024)}MB)'}), 400
        
        # 执行上传
        result = ftps_upload(temp_path, remote_path)
        
        # 清理临时文件
        try:
            os.remove(temp_path)
        except:
            pass
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception(f"Upload processing error: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/download')
def api_download():
    """API: 下载文件"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'No path specified'}), 400
    
    logger.info(f"Download request for: {path}")
    
    result = ftps_download(path)
    
    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500
    
    if result:
        filename = os.path.basename(path)
        return send_file(result, as_attachment=True, download_name=filename)
    
    return jsonify({'error': 'Download failed'}), 500

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
