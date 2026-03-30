#!/usr/bin/env python3
"""FTPS Web 文件预览应用"""

import os
import subprocess
import re
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
import tempfile

app = Flask(__name__)

# FTPS 配置
FTP_HOST = os.environ.get('FTP_HOST', '192.168.68.246')
FTP_PORT = os.environ.get('FTP_PORT', '990')
FTP_USER = os.environ.get('FTP_USER', 'bblp')
FTP_PASS = os.environ.get('FTP_PASS', 'c97b754b')

def ftps_list(path='/'):
    """使用 curl 获取 FTPS 隐式 TLS 文件列表 (端口 990)"""
    try:
        # 确保路径以 / 开头
        if not path.startswith('/'):
            path = '/' + path
        
        # 构建完整 URL
        url = f'ftps://{FTP_USER}:{FTP_PASS}@{FTP_HOST}:{FTP_PORT}{path}'
        
        cmd = [
            'curl', '--ssl-reqd', '-k', '-s',
            url,
            '--max-time', '30'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        
        if result.returncode != 0:
            return {'error': f'FTP error: {result.stderr}', 'url': url}
        
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
                
                files.append({
                    'name': name,
                    'size': int(size),
                    'size_formatted': format_size(int(size)),
                    'is_dir': is_dir,
                    'permissions': perms,
                    'owner': owner,
                    'group': group,
                    'modified': f"{month} {day} {time_or_year}",
                    'is_3mf': name.lower().endswith('.3mf')
                })
        
        return {'files': files, 'path': path}
    except Exception as e:
        return {'error': str(e)}

def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def ftps_download(remote_path):
    """下载 FTPS 文件到临时目录（隐式 TLS）"""
    try:
        fd, local_path = tempfile.mkstemp(suffix=os.path.basename(remote_path))
        os.close(fd)
        
        # 确保路径以 / 开头
        if not remote_path.startswith('/'):
            remote_path = '/' + remote_path
        
        url = f'ftps://{FTP_USER}:{FTP_PASS}@{FTP_HOST}:{FTP_PORT}{remote_path}'
        
        cmd = [
            'curl', '--ssl-reqd', '-k', '-o', local_path,
            url,
            '--max-time', '300'
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=310)
        
        if result.returncode == 0:
            return local_path
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/list')
def api_list():
    """API: 获取文件列表"""
    path = request.args.get('path', '/')
    result = ftps_list(path)
    return jsonify(result)

@app.route('/api/download')
def api_download():
    """API: 下载文件"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': 'No path specified'}), 400
    
    local_path = ftps_download(path)
    if local_path:
        return send_file(local_path, as_attachment=True, download_name=os.path.basename(path))
    return jsonify({'error': 'Download failed'}), 500

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
