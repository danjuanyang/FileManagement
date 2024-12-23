# utils/activity_tracking.py

from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

from config import app, db
from models import UserSession, UserActivityLog
import jwt
import re

from utils.network_utils import get_real_ip


# def create_user_session(user_id):
#     """
#     创建新的用户会话，并关闭该用户的所有旧会话
#     """
#     try:
#         # 关闭该用户的所有活动会话
#         active_sessions = UserSession.query.filter_by(
#             user_id=user_id,
#             is_active=True
#         ).all()
#
#         current_time = datetime.now()
#
#         for session in active_sessions:
#             session.is_active = False
#             session.logout_time = current_time
#             if session.login_time:
#                 session.session_duration = int((current_time - session.login_time).total_seconds())
#
#         # 创建新会话，只传入必要的参数
#         new_session = UserSession(
#             user_id=user_id,
#             ip_address=request.remote_addr if hasattr(request, 'remote_addr') else None,
#             user_agent=request.user_agent.string if hasattr(request, 'user_agent') else None
#         )
#
#         db.session.add(new_session)
#         db.session.commit()
#
#         return new_session.id
#
#     except Exception as e:
#         print(f"创建用户会话时出错： {str(e)}")
#         db.session.rollback()
#         raise


def create_user_session(user_id, ip_address=None):
    """
    创建新的用户会话，并关闭该用户的所有旧会话
    """
    try:
        # 关闭该用户的所有活动会话
        active_sessions = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).all()

        current_time = datetime.now()

        for session in active_sessions:
            session.is_active = False
            session.logout_time = current_time
            if session.login_time:
                session.session_duration = int((current_time - session.login_time).total_seconds())

        # 创建新会话
        new_session = UserSession(
            user_id=user_id,
            ip_address=ip_address,  # Use the passed ip_address
            user_agent=request.user_agent.string if hasattr(request, 'user_agent') else None
        )

        # 确保时间字段使用datetime对象
        new_session.login_time = datetime.now()
        new_session.last_activity_time = datetime.now()

        db.session.add(new_session)
        db.session.commit()

        return new_session.id

    except Exception as e:
        print(f"创建用户会话时出错： {str(e)}")
        db.session.rollback()
        raise






# 更新用户的最后活动时间
def update_user_activity(user_id):
    try:
        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if active_session:
            active_session.last_activity_time = datetime.now()  # 直接使用datetime对象
            db.session.commit()
    except Exception as e:
        print(f"Error updating user activity: {str(e)}")
        db.session.rollback()


def check_session_timeout(user_id):
    """
    检查用户会话是否超时（1小时无活动）
    """
    try:
        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if not active_session:
            return False

        last_activity = active_session.last_activity_time
        timeout_threshold = datetime.now() - timedelta(hours=1)

        if last_activity < timeout_threshold:
            current_time = datetime.now()
            active_session.is_active = False
            active_session.logout_time = current_time
            active_session.session_duration = int((current_time - active_session.login_time).total_seconds())
            db.session.commit()
            return False

        return True
    except Exception as e:
        print(f"检查会话超时时出错：{str(e)}")
        return False


def check_session_timeout(user_id):
    """
    检查用户会话是否超时（1小时无活动）
    返回 True 如果会话有效，False 如果会话已超时
    """
    try:
        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if not active_session:
            return False

        # 确保时间格式的一致性
        if isinstance(active_session.last_activity_time, datetime):
            last_activity = active_session.last_activity_time
        else:
            last_activity = datetime.strptime(active_session.last_activity_time, '%Y-%m-%d %H:%M:%S')

        timeout_threshold = datetime.now() - timedelta(hours=1)

        if last_activity < timeout_threshold:
            # 会话超时，更新会话状态
            current_time = datetime.now()
            active_session.is_active = False
            active_session.logout_time = current_time.strftime('%Y-%m-%d %H:%M:%S')

            # 计算会话持续时间
            login_time = (datetime.strptime(active_session.login_time, '%Y-%m-%d %H:%M:%S')
                          if isinstance(active_session.login_time, str)
                          else active_session.login_time)
            active_session.session_duration = int((current_time - login_time).total_seconds())

            db.session.commit()
            return False

        return True
    except Exception as e:
        print(f"Error checking session timeout: {str(e)}")
        return False


def extract_resource_info(endpoint, view_args):
    """
    从端点和URL参数中提取资源类型和ID
    """
    # 常见的资源类型映射
    resource_mappings = {
        'project': r'/projects?/(\d+)',
        'task': r'/tasks?/(\d+)',
        'file': r'/files?/(\d+)',
        'stage': r'/stages?/(\d+)',
        'user': r'/users?/(\d+)',
        'session': r'/sessions?/(\d+)'
    }

    path = request.path
    for resource_type, pattern in resource_mappings.items():
        match = re.search(pattern, path)
        if match:
            return resource_type, int(match.group(1))

    # 处理特殊情况
    if 'project_id' in view_args:
        return 'project', view_args['project_id']
    if 'task_id' in view_args:
        return 'task', view_args['task_id']
    if 'file_id' in view_args:
        return 'file', view_args['file_id']

    return None, None


# def log_user_activity(user_id, action_type, action_detail=None, resource_type=None,
#                       resource_id=None, status_code=None, request_method=None,
#                       endpoint=None, request_path=None):
#     """
#     记录用户活动
#     """
#     try:
#         # 如果没有提供状态码，尝试从 g 对象获取
#         if status_code is None and hasattr(g, 'response_status_code'):
#             status_code = g.response_status_code
#
#         # 如果没有提供请求方法和端点，从当前请求获取
#         if request_method is None:
#             request_method = request.method
#         if endpoint is None:
#             endpoint = request.endpoint
#         if request_path is None:
#             request_path = request.path
#
#         # 如果没有提供资源信息，尝试从URL提取
#         if resource_type is None and resource_id is None:
#             resource_type, resource_id = extract_resource_info(endpoint, request.view_args)
#
#         activity = UserActivityLog(
#             user_id=user_id,
#             action_type=action_type,
#             action_detail=action_detail,
#             ip_address=request.remote_addr,
#             resource_type=resource_type,
#             resource_id=resource_id,
#             status_code=status_code,
#             request_method=request_method,
#             endpoint=endpoint,
#             request_path=request_path
#         )
#
#         db.session.add(activity)
#         db.session.commit()
#     except Exception as e:
#         print(f"错误记录活动： {str(e)}")
#         db.session.rollback()


def log_user_activity(user_id, action_type, action_detail=None, resource_type=None,
                      resource_id=None, status_code=None, request_method=None,
                      endpoint=None, request_path=None):
    """
    记录用户活动
    """
    try:
        if status_code is None and hasattr(g, 'response_status_code'):
            status_code = g.response_status_code

        if request_method is None:
            request_method = request.method
        if endpoint is None:
            endpoint = request.endpoint
        if request_path is None:
            request_path = request.path

        if resource_type is None and resource_id is None:
            resource_type, resource_id = extract_resource_info(endpoint, request.view_args)

        # 创建活动记录时不传入 timestamp 参数，让模型的默认值处理
        activity = UserActivityLog(
            user_id=user_id,
            action_type=action_type,
            action_detail=action_detail,
            ip_address=request.remote_addr,
            resource_type=resource_type,
            resource_id=resource_id,
            status_code=status_code,
            request_method=request_method,
            endpoint=endpoint,
            request_path=request_path
        )

        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"错误记录活动： {str(e)}")
        db.session.rollback()


def track_activity(f):
    """
    用于跟踪用户活动的装饰器
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            # 获取并验证令牌
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                return jsonify({'message': '缺少认证令牌'}), 401

            token = auth_header.split()[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user_id = data['user_id']

            # 检查会话超时
            if not check_session_timeout(user_id):
                return jsonify({
                    'message': '会话已过期，请重新登录',
                    'code': 'SESSION_EXPIRED'
                }), 401

            # 更新最后活动时间
            update_user_activity(user_id)

            # 执行原始函数
            response = f(*args, **kwargs)

            # 获取状态码
            if isinstance(response, tuple):
                status_code = response[1]
                response_data = response[0]
            else:
                status_code = 200
                response_data = response

            # 存储状态码到 g 对象，供 log_user_activity 使用
            g.response_status_code = status_code

            # 获取资源信息
            resource_type, resource_id = extract_resource_info(request.endpoint, kwargs)

            # 构建操作详情
            action_detail = f'访问端点: {request.endpoint}, 方法: {request.method}, 路径: {request.path}'
            if isinstance(response_data, dict) and 'message' in response_data:
                action_detail += f', 结果: {response_data["message"]}'

            # 记录活动
            log_user_activity(
                user_id=user_id,
                action_type=f'{request.method.lower()}_{request.endpoint}',
                action_detail=action_detail,
                resource_type=resource_type,
                resource_id=resource_id,
                status_code=status_code,
                request_method=request.method,
                endpoint=request.endpoint,
                request_path=request.path
            )

            return response

        except jwt.ExpiredSignatureError:
            return jsonify({'message': '令牌已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '无效的令牌'}), 401
        except Exception as e:
            error_response = jsonify({'message': f'发生错误: {str(e)}'}), 500
            # 记录错误
            if 'user_id' in locals():
                log_user_activity(
                    user_id=user_id,
                    action_type='error',
                    action_detail=str(e),
                    status_code=500,
                    request_method=request.method,
                    endpoint=request.endpoint,
                    request_path=request.path
                )
            return error_response

    return decorated
