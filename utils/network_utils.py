# utils/network_utils.py

from flask import request

def get_real_ip():
    """
    获取真实的客户端IP地址
    按优先级依次检查各种头部信息
    """
    headers_to_check = [
        'X-Forwarded-For',  # 代理服务器转发的IP链
        'X-Real-IP',  # Nginx代理添加的真实IP
        'CF-Connecting-IP',  # Cloudflare的真实IP
        'True-Client-IP',  # 一些CDN使用的真实IP
    ]

    for header in headers_to_check:
        ip = request.headers.get(header)
        if ip:
            # 如果是X-Forwarded-For，可能包含多个IP，取第一个
            if header == 'X-Forwarded-For':
                ip = ip.split(',')[0].strip()
            if ip and ip != '127.0.0.1':
                return ip

    # 如果都没有，则返回remote_addr
    return request.remote_addr