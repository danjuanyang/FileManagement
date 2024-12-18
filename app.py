# app.py
import os
import sys
import tempfile
import time

from sqlalchemy import text
# from sqlalchemy import Flask_SQLAlchemy, text
from config import app, db
from flask import request, jsonify, redirect, url_for
import jwt
import datetime
from models import User, Project, UserSession, UserActivityLog
from routes.filemanagement import files_bp
from routes.leaders import leader_bp
from routes.employees import employee_bp
from routes.projectplan import projectplan_bp
from utils.activity_tracking import create_user_session, log_user_activity, track_activity

app.register_blueprint(leader_bp, url_prefix='/api/leader')
app.register_blueprint(employee_bp, url_prefix='/api/employee')

app.register_blueprint(projectplan_bp, url_prefix='/api/projectplan')

app.register_blueprint(files_bp, url_prefix='/api/files')


# 用户登录接口
# @app.route('/api/login', methods=['POST'])
# def login():
#     data = request.get_json()
#     username = data.get('username')
#     password = data.get('password')
#
#
#     user = User.query.filter_by(username=username).first()
#
#     if user and user.check_password(password):
#         token = jwt.encode({
#             'user_id': user.id,
#             'username': user.username,
#             'role': user.role,
#             'exp': datetime.datetime.now() + datetime.timedelta(minutes=1)
#         }, app.config['SECRET_KEY'], algorithm='HS256')
#
#         return jsonify({
#             'token': token,
#             'role': user.role,
#             'username': user.username,
#             'user_id': user.id,
#             # 当前时间,返回时分秒
#             'now': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
#             # 过期时间
#             'exp': datetime.datetime.now() + datetime.timedelta(minutes=1)
#
#         }), 200
#     return jsonify({'message': '用户名或密码无效'}), 401


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        # 创建会话并记录活动
        session_id = create_user_session(user.id)
        log_user_activity(
            user_id=user.id,
            action_type='login',
            action_detail=f'用户登录，IP: {request.remote_addr}'
        )

        # 创建JWT令牌，1小时有效期
        token = jwt.encode({
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'exp': datetime.datetime.now() + datetime.timedelta(minutes=1)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'token': token,
            'role': user.role,
            'username': user.username,
            'user_id': user.id,
            'session_id': session_id,
            'login_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    return jsonify({'message': '用户名或密码无效'}), 401


# 用户注销接口
@app.route('/api/logout', methods=['POST'])
@track_activity
def logout():
    try:
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = data['user_id']

        # 关闭活动会话
        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if active_session:
            active_session.end_session()

        # 记录登出活动
        log_user_activity(
            user_id=user_id,
            action_type='logout',
            action_detail='用户正常登出'
        )

        db.session.commit()
        return jsonify({'message': '成功登出'}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 401


# 添加用于查看活动日志的管理端点
@app.route('/api/admin/activity-logs', methods=['GET'])
@track_activity
def get_activity_logs():
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 1:  # 假设角色1是管理员
            return jsonify({'message': '权限不足'}), 403

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        user_id = request.args.get('user_id', type=int)

        query = UserActivityLog.query
        if user_id:
            query = query.filter_by(user_id=user_id)

        logs = query.order_by(UserActivityLog.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify({
            'logs': [{
                'id': log.id,
                'user_id': log.user_id,
                'username': log.user.username,
                'action_type': log.action_type,
                'action_detail': log.action_detail,
                'ip_address': log.ip_address,
                'timestamp': log.timestamp,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id
            } for log in logs.items],
            'total': logs.total,
            'pages': logs.pages,
            'current_page': page
        })

    except Exception as e:
        return jsonify({'message': str(e)}), 500


# 添加用于查看会话历史的管理端点
@app.route('/api/admin/sessions', methods=['GET'])
@track_activity
def get_sessions():
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 1:
            return jsonify({'message': '权限不足'}), 403

        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        is_active = request.args.get('is_active', type=bool)

        # 构建基础查询
        query = UserSession.query

        # 应用过滤条件
        if user_id:
            query = query.filter_by(user_id=user_id)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        if start_date:
            query = query.filter(UserSession.login_time >= start_date)
        if end_date:
            query = query.filter(UserSession.login_time <= end_date)

        # 按ID降序排序并分页
        sessions = query.order_by(UserSession.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # 准备响应数据
        sessions_data = []
        for session in sessions.items:
            user = session.user  # 假设在UserSession模型中定义了relationship
            session_data = {
                'id': session.id,
                'user_id': session.user_id,
                'username': user.username if user else None,
                'login_time': session.login_time,
                'logout_time': session.logout_time,
                'is_active': session.is_active,
                'last_activity_time': session.last_activity_time,
                'session_duration': session.session_duration,
                # 计算会话状态
                'status': '活跃' if session.is_active else '已结束',
                # 如果session_duration为None且会话活跃，计算当前持续时间
                'current_duration': (
                    session.session_duration if session.session_duration
                    else int(
                        (datetime.now() - datetime.strptime(session.login_time, '%Y-%m-%d %H:%M:%S')).total_seconds())
                    if session.is_active else None
                )
            }
            sessions_data.append(session_data)

        return jsonify({
            'sessions': sessions_data,
            'total': sessions.total,
            'pages': sessions.pages,
            'current_page': page,
            'per_page': per_page,
            # 添加汇总信息
            'summary': {
                'total_sessions': sessions.total,
                'active_sessions': sum(1 for s in sessions_data if s['is_active']),
                'average_duration': sum(s['session_duration'] or 0 for s in sessions_data) / len(
                    sessions_data) if sessions_data else 0
            }
        })

    except jwt.ExpiredSignatureError:
        return jsonify({'message': '令牌已过期'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'message': '无效的令牌'}), 401
    except Exception as e:
        return jsonify({'message': f'获取会话记录时发生错误: {str(e)}'}), 500



# 检查当前会话状态
def check_session_status():
    """检查当前会话状态"""
    try:
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = data['user_id']

        active_session = UserSession.query.filter_by(
            user_id=user_id,
            is_active=True
        ).first()

        if not active_session:
            return jsonify({
                'active': False,
                'message': '没有活动的会话'
            }), 200

        last_activity = datetime.strptime(active_session.last_activity_time, '%Y-%m-%d %H:%M:%S')
        current_time = datetime.now()
        time_diff = current_time - last_activity

        return jsonify({
            'active': True,
            'session_id': active_session.id,
            'login_time': active_session.login_time,
            'last_activity': active_session.last_activity_time,
            'inactive_minutes': int(time_diff.total_seconds() / 60),
            'remaining_minutes': int(60 - (time_diff.total_seconds() / 60))  # 剩余分钟数直到超时
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 401

# 检查用户统计信息
@app.route('/api/admin/user-stats', methods=['GET'])
@track_activity
def get_user_stats():
    """获取用户统计信息"""
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 1:
            return jsonify({'message': '权限不足'}), 403

        user_id = request.args.get('user_id', type=int)

        # 基础查询
        base_query = UserActivityLog.query
        if user_id:
            base_query = base_query.filter_by(user_id=user_id)

        # 获取今天的日期
        today = datetime.now().strftime('%Y-%m-%d')

        # 获取各种统计数据
        stats = {
            'total_activities': base_query.count(),
            'today_activities': base_query.filter(
                UserActivityLog.timestamp.like(f'{today}%')
            ).count(),
            'login_count': base_query.filter_by(
                action_type='login'
            ).count(),
            'total_sessions': UserSession.query.filter_by(
                user_id=user_id
            ).count() if user_id else UserSession.query.count()
        }

        # 获取活动用户数
        active_users = db.session.query(UserSession.user_id).filter_by(
            is_active=True
        ).distinct().count()

        stats['active_users'] = active_users

        return jsonify(stats), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/api/admin/clear-expired-sessions', methods=['POST'])
@track_activity
def clear_expired_sessions():
    """清理过期会话"""
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 1:
            return jsonify({'message': '权限不足'}), 403

        # 获取所有活动会话
        active_sessions = UserSession.query.filter_by(is_active=True).all()
        cleared_count = 0

        for session in active_sessions:
            last_activity = datetime.strptime(session.last_activity_time, '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - last_activity) > datetime.timedelta(hours=1):
                session.end_session()
                cleared_count += 1

        db.session.commit()

        return jsonify({
            'message': f'已清理 {cleared_count} 个过期会话',
            'cleared_count': cleared_count
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500

#  获取当前用户的活动摘要
@app.route('/api/user/activity-summary', methods=['GET'])
@track_activity
def get_user_activity_summary():

    try:
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = data['user_id']

        # 获取用户的最后一个会话
        last_session = UserSession.query.filter_by(
            user_id=user_id
        ).order_by(UserSession.id.desc()).first()

        # 获取今天的活动数量
        today = datetime.now().strftime('%Y-%m-%d')
        today_activities = UserActivityLog.query.filter_by(
            user_id=user_id
        ).filter(
            UserActivityLog.timestamp.like(f'{today}%')
        ).count()

        # 获取用户的总活动统计
        activity_stats = db.session.query(
            UserActivityLog.action_type,
            db.func.count(UserActivityLog.id)
        ).filter_by(
            user_id=user_id
        ).group_by(
            UserActivityLog.action_type
        ).all()

        return jsonify({
            'last_session': {
                'login_time': last_session.login_time if last_session else None,
                'is_active': last_session.is_active if last_session else False,
                'duration': last_session.session_duration if last_session else None
            },
            'today_activities': today_activities,
            'activity_breakdown': dict(activity_stats)
        }), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500


# 注册路由
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 2)

    if User.query.filter_by(username=username).first():
        return jsonify({'message': '用户名已存在'}), 400

    new_user = User(username=username, role=role)
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '用户注册成功'}), 201


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # 确保外键约束开启
        db.session.execute(text('PRAGMA foreign_keys=ON'))

        print("创建用户会话和活动日志表...")
        try:
            UserSession.__table__.create(db.engine)
            print("成功创建用户会话表")
        except Exception as e:
            print(f"用户会话表已存在或创建失败: {str(e)}")

        try:
            UserActivityLog.__table__.create(db.engine)
            print("成功创建用户活动日志表")
        except Exception as e:
            print(f"用户活动日志表已存在或创建失败: {str(e)}")

        print("永不宕机！程序开启时间：", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
        print(f"数据库在: {app.config['SQLALCHEMY_DATABASE_URI']}")
        # print("环境变量:", os.environ)
        print("Python路径:", sys.executable)
        print("临时文件夹:", tempfile.gettempdir())

        # 启用外键约束
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        # 尝试直接创建FTS5表（不加载扩展）
        try:
            create_fts_table_sql = text("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS file_contents_fts 
                        USING fts5(
                            content,
                            tokenize=porter
                        )
                    """)
            db.session.execute(create_fts_table_sql)
            db.session.commit()
            print("成功创建FTS5表")
        except Exception as e:
            # 如果FTS5失败，尝试使用FTS4
            try:
                create_fts4_table_sql = text("""
                            CREATE VIRTUAL TABLE IF NOT EXISTS file_contents_fts 
                            USING fts4(
                                content,
                                tokenize=simple
                            )
                        """)
                db.session.execute(create_fts4_table_sql)
                db.session.commit()
                print("成功创建FTS4表（FTS5不可用，已降级使用FTS4）")
            except Exception as e2:
                print(f"警告: 全文搜索表创建失败 - {str(e2)}")
                print("将使用基础的LIKE查询作为备选方案")

    app.run(host='0.0.0.0', port=6543, debug=False)
