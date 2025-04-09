# routes/admin.py
import os

from flask import Blueprint, request, jsonify, current_app
from models import User, UserSession, UserActivityLog, Project, ProjectFile
from utils.activity_tracking import track_activity, log_user_activity
import jwt
import datetime
from config import app, db

admin_bp = Blueprint('admin', __name__)


def check_admin_auth():
    """验证管理员权限的辅助函数"""
    token = request.headers.get('Authorization').split()[1]
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    if data.get('role') != 0:
        raise Exception('权限不足')
    return data


# 活动日志接口
@admin_bp.route('/activity-logs', methods=['GET'])
@track_activity
def get_activity_logs():
    try:
        check_admin_auth()

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


@admin_bp.route('/sessions', methods=['GET'])
@track_activity
def get_sessions():
    try:
        check_admin_auth()

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        is_active = request.args.get('is_active', type=bool)

        query = UserSession.query

        if user_id:
            query = query.filter_by(user_id=user_id)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        if start_date:
            query = query.filter(UserSession.login_time >= start_date)
        if end_date:
            query = query.filter(UserSession.login_time <= end_date)

        sessions = query.order_by(UserSession.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        sessions_data = []
        for session in sessions.items:
            user = session.user
            current_time = datetime.datetime.now()
            session_data = {
                'id': session.id,
                'user_id': session.user_id,
                'username': user.username if user else None,
                'login_time': session.login_time,
                'logout_time': session.logout_time,
                'is_active': session.is_active,
                'last_activity_time': session.last_activity_time,
                'session_duration': session.session_duration,
                'status': '活跃' if session.is_active else '已结束',
                'current_duration': (
                    session.session_duration if session.session_duration
                    else int((current_time - session.login_time).total_seconds())
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
            'summary': {
                'total_sessions': sessions.total,
                'active_sessions': sum(1 for s in sessions_data if s['is_active']),
                'average_duration': sum(s['session_duration'] or 0 for s in sessions_data) / len(
                    sessions_data) if sessions_data else 0
            }
        })

    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/alerts', methods=['GET'])
@track_activity
def get_system_alerts():
    try:
        check_admin_auth()

        alerts = []
        current_time = datetime.datetime.now()

        # 检查逾期项目
        overdue_projects = Project.query.filter(
            Project.deadline < current_time,
            Project.status != 'completed'
        ).all()

        if overdue_projects:
            alerts.append({
                'type': '项目逾期',
                'content': f'有 {len(overdue_projects)} 个项目已逾期',
                'time': current_time.strftime('%Y-%m-%d %H:%M:%S')
            })

        # 检查长时间未活动的会话
        inactive_sessions = UserSession.query.filter_by(is_active=True).all()
        inactive_count = 0
        for session in inactive_sessions:
            if (current_time - session.last_activity_time).total_seconds() > 3600:
                inactive_count += 1

        if inactive_count > 0:
            alerts.append({
                'type': '系统告警',
                'content': f'有 {inactive_count} 个会话超过1小时未活动',
                'time': current_time.strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify({
            'alerts': alerts,
            'total': len(alerts),
            'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/handle-overdue', methods=['POST'])
@track_activity
def handle_overdue_alert():
    try:
        check_admin_auth()

        overdue_projects = Project.query.filter(
            Project.deadline < datetime.datetime.now(),
            Project.status != 'completed'
        ).all()

        for project in overdue_projects:
            project.status = 'overdue'

        db.session.commit()
        return jsonify({'message': '已处理逾期项目告警'}), 200

    except Exception as e:
        return jsonify({'message': str(e)}), 500


# 获取用户活动日志
@admin_bp.route('/dashboard-stats', methods=['GET'])
@track_activity
def get_dashboard_stats():
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 0:
            return jsonify({'message': '权限不足'}), 403

        # 获取基础统计数据
        total_users = User.query.count()
        active_users = UserSession.query.filter_by(is_active=True).count()
        today = datetime.datetime.now().date()
        today_activities = UserActivityLog.query.filter(
            db.func.date(UserActivityLog.timestamp) == today
        ).count()

        # 获取项目统计
        projects = Project.query.all()
        project_stats = {
            'total': len(projects),
            'pending': len([p for p in projects if p.status == 'pending']),
            'ongoing': len([p for p in projects if p.status == 'ongoing']),
            'completed': len([p for p in projects if p.status == 'completed']),
            'overdue': len([p for p in projects if p.status == 'overdue'])
        }

        # 获取最近活动趋势
        activity_trends = db.session.query(
            db.func.date(UserActivityLog.timestamp).label('date'),
            db.func.count(UserActivityLog.id).label('count')
        ).group_by(
            db.func.date(UserActivityLog.timestamp)
        ).order_by(
            db.func.date(UserActivityLog.timestamp).desc()
        ).limit(30).all()

        return jsonify({
            'user_stats': {
                'total_users': total_users,
                'active_users': active_users,
                'today_activities': today_activities
            },
            'project_stats': project_stats,
            'activity_trends': [
                {'date': str(date), 'count': count}
                for date, count in activity_trends
            ]
        })

    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/logout', methods=['POST'])
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


# 销毁会话
@admin_bp.route('/sessions/<int:session_id>/terminate', methods=['POST'])
@track_activity
def terminate_session(session_id):
    """终止指定的会话"""
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 0:
            return jsonify({'message': '权限不足'}), 403

        # 查找并终止会话
        session = UserSession.query.get(session_id)
        if not session:
            return jsonify({'message': '会话不存在'}), 404

        if session.is_active:
            session.end_session()
            db.session.commit()
            return jsonify({'message': '会话已终止'}), 200
        else:
            return jsonify({'message': '会话已结束'}), 400

    except jwt.ExpiredSignatureError:
        return jsonify({'message': '令牌已过期'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'message': '无效的令牌'}), 401
    except Exception as e:
        return jsonify({'message': f'终止会话时发生错误: {str(e)}'}), 500


# 检查用户统计信息
@admin_bp.route('/user-stats', methods=['GET'])
@track_activity
def get_user_stats():
    """获取用户统计信息"""
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 0:
            return jsonify({'message': '权限不足'}), 403

        user_id = request.args.get('user_id', type=int)

        # 基础查询
        base_query = UserActivityLog.query
        if user_id:
            base_query = base_query.filter_by(user_id=user_id)

        # 获取今天的日期
        today = datetime.datetime.now().strftime('%Y-%m-%d')

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


# 清理过期会话
@admin_bp.route('/clear-expired-sessions', methods=['POST'])
@track_activity
def clear_expired_sessions():
    """清理过期会话"""
    try:
        # 验证管理员权限
        token = request.headers.get('Authorization').split()[1]
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        if data.get('role') != 0:
            return jsonify({'message': '权限不足'}), 403

        # 获取所有活动会话
        active_sessions = UserSession.query.filter_by(is_active=True).all()
        cleared_count = 0

        for session in active_sessions:
            # last_activity = datetime.datetime.strptime(session.last_activity_time, '%Y-%m-%d %H:%M:%S')
            last_activity = session.last_activity_time
            if (datetime.datetime.now() - last_activity) > datetime.timedelta(hours=1):
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
@admin_bp.route('/activity-summary', methods=['GET'])
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
        today = datetime.datetime.now().strftime('%Y-%m-%d')
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


# 管理员文件删除接口 - 可以删除任何文件及关联数据
@admin_bp.route('/files/<int:file_id>', methods=['DELETE'])
@track_activity
def admin_delete_file(file_id):
    try:
        # 验证管理员权限
        admin_data = check_admin_auth()
        admin_id = admin_data.get('user_id')

        # 获取文件记录
        file = ProjectFile.query.get_or_404(file_id)

        # 记录被删除的文件信息，用于日志
        file_info = {
            'id': file.id,
            'name': file.original_name,
            'project': file.project.name if file.project else "Unknown",
            'subproject': file.subproject.name if file.subproject else "Unknown",
            'stage': file.stage.name if file.stage else "Unknown",
            'task': file.task.name if file.task else "Unknown",
            'uploader': file.upload_user.username if file.upload_user else "Unknown",
        }

        # 获取物理文件路径
        file_path = os.path.join(app.root_path, file.file_path)

        # 先删除文件内容记录（如果存在）
        if file.content:
            db.session.delete(file.content)

        # 删除文件数据库记录
        db.session.delete(file)
        db.session.commit()

        # 删除物理文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)

                # 尝试删除空文件夹
                directory = os.path.dirname(file_path)
                if os.path.exists(directory) and not os.listdir(directory):
                    os.rmdir(directory)
            except OSError as e:
                # 记录错误但继续执行，因为数据库记录已删除
                print(f"删除物理文件时出错： {e}")
                # 记录日志
                log_user_activity(
                    user_id=admin_id,
                    action_type='admin_delete_file_error',
                    action_detail=f"管理员删除文件 {file_info['name']} (ID: {file_id}) 的物理文件时出错: {str(e)}",
                    resource_type='file',
                    resource_id=file_id
                )

        # 记录操作日志
        log_user_activity(
            user_id=admin_id,
            action_type='admin_delete_file',
            action_detail=f"管理员删除了文件 {file_info['name']} (ID: {file_id})，项目: {file_info['project']}，" \
                          f"子项目: {file_info['subproject']}，阶段: {file_info['stage']}，" \
                          f"任务: {file_info['task']}，上传者: {file_info['uploader']}",
            resource_type='file',
            resource_id=file_id
        )

        return jsonify({
            'message': '文件删除成功',
            'file_id': file_id,
            'file_info': file_info
        })

    except Exception as e:
        db.session.rollback()
        print(f"管理员删除文件错误: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 批量删除文件接口
@admin_bp.route('/files/batch-delete', methods=['POST'])
@track_activity
def admin_batch_delete_files():
    try:
        # 验证管理员权限
        admin_data = check_admin_auth()
        admin_id = admin_data.get('user_id')

        # 获取请求中的文件ID列表
        data = request.get_json()
        file_ids = data.get('file_ids', [])

        if not file_ids:
            return jsonify({'error': '未提供文件ID列表'}), 400

        deleted_files = []
        error_files = []

        for file_id in file_ids:
            try:
                # 获取文件记录
                file = ProjectFile.query.get(file_id)
                if not file:
                    error_files.append({'id': file_id, 'error': '文件不存在'})
                    continue

                # 记录被删除的文件信息
                file_info = {
                    'id': file.id,
                    'name': file.original_name,
                    'project': file.project.name if file.project else "Unknown",
                    'subproject': file.subproject.name if file.subproject else "Unknown",
                    'stage': file.stage.name if file.stage else "Unknown",
                    'task': file.task.name if file.task else "Unknown"
                }

                # 获取物理文件路径
                file_path = os.path.join(app.root_path, file.file_path)

                # 先删除文件内容记录（如果存在）
                if file.content:
                    db.session.delete(file.content)

                # 删除文件数据库记录
                db.session.delete(file)

                # 删除物理文件
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        # 记录错误但继续执行
                        pass

                deleted_files.append(file_info)

            except Exception as e:
                error_files.append({'id': file_id, 'error': str(e)})
                # 回滚当前文件的删除操作
                db.session.rollback()

        # 提交所有成功的删除
        if deleted_files:
            db.session.commit()

            # 记录操作日志
            log_user_activity(
                user_id=admin_id,
                action_type='admin_batch_delete_files',
                action_detail=f"管理员批量删除了 {len(deleted_files)} 个文件",
                resource_type='file'
            )

        return jsonify({
            'message': f'批量删除完成: {len(deleted_files)} 个文件删除成功, {len(error_files)} 个文件删除失败',
            'deleted_files': deleted_files,
            'error_files': error_files
        })

    except Exception as e:
        db.session.rollback()
        print(f"管理员批量删除文件错误: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 根据筛选条件批量删除文件
@admin_bp.route('/files/delete-by-filter', methods=['POST'])
@track_activity
def admin_delete_files_by_filter():
    try:
        # 验证管理员权限
        admin_data = check_admin_auth()
        admin_id = admin_data.get('user_id')

        # 获取请求中的筛选条件
        data = request.get_json()
        project_id = data.get('project_id')
        subproject_id = data.get('subproject_id')
        stage_id = data.get('stage_id')
        task_id = data.get('task_id')
        upload_user_id = data.get('upload_user_id')
        date_before = data.get('date_before')  # 格式: "YYYY-MM-DD"
        date_after = data.get('date_after')  # 格式: "YYYY-MM-DD"
        file_type = data.get('file_type')  # 文件类型

        # 构建查询
        query = ProjectFile.query

        if project_id:
            query = query.filter(ProjectFile.project_id == project_id)
        if subproject_id:
            query = query.filter(ProjectFile.subproject_id == subproject_id)
        if stage_id:
            query = query.filter(ProjectFile.stage_id == stage_id)
        if task_id:
            query = query.filter(ProjectFile.task_id == task_id)
        if upload_user_id:
            query = query.filter(ProjectFile.upload_user_id == upload_user_id)
        if date_before:
            query = query.filter(ProjectFile.upload_date <= datetime.strptime(date_before, "%Y-%m-%d"))
        if date_after:
            query = query.filter(ProjectFile.upload_date >= datetime.strptime(date_after, "%Y-%m-%d"))
        if file_type:
            query = query.filter(ProjectFile.file_type.like(f"%{file_type}%"))

        # 获取符合条件的文件数量
        matching_count = query.count()

        # 安全检查：如果匹配的文件太多，需要确认
        if matching_count > 100 and not data.get('confirmed'):
            return jsonify({
                'status': 'confirm_required',
                'message': f'该操作将删除 {matching_count} 个文件，请确认',
                'matching_count': matching_count
            }), 200

        # 获取所有匹配的文件
        matching_files = query.all()

        deleted_count = 0
        error_count = 0

        # 删除所有匹配的文件
        for file in matching_files:
            try:
                # 获取物理文件路径
                file_path = os.path.join(app.root_path, file.file_path)

                # 先删除文件内容记录（如果存在）
                if file.content:
                    db.session.delete(file.content)

                # 删除文件数据库记录
                db.session.delete(file)

                # 删除物理文件
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        # 记录错误但继续执行
                        pass

                deleted_count += 1

            except Exception as e:
                error_count += 1
                print(f"删除文件 {file.id} 时出错: {str(e)}")
                # 单个文件删除失败不影响其他文件
                db.session.rollback()

        # 提交所有成功的删除
        if deleted_count > 0:
            db.session.commit()

            # 记录操作日志
            filter_description = ', '.join(f"{k}:{v}" for k, v in data.items() if k != 'confirmed' and v)
            log_user_activity(
                user_id=admin_id,
                action_type='admin_delete_files_by_filter',
                action_detail=f"管理员通过筛选条件({filter_description})批量删除了 {deleted_count} 个文件",
                resource_type='file'
            )

        return jsonify({
            'message': f'批量删除完成: {deleted_count} 个文件删除成功, {error_count} 个文件删除失败',
            'deleted_count': deleted_count,
            'error_count': error_count,
            'total_matched': matching_count
        })

    except Exception as e:
        db.session.rollback()
        print(f"管理员按条件删除文件错误: {str(e)}")
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/files', methods=['GET'])
@track_activity
def get_admin_files():
    try:
        # 验证管理员授权
        check_admin_auth()

        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 获取筛选器参数
        project_id = request.args.get('project_id', type=int)
        upload_user_id = request.args.get('upload_user_id', type=int)
        visibility = request.args.get('visibility')

        # 构建查询
        query = ProjectFile.query.options(
            db.joinedload(ProjectFile.project),
            db.joinedload(ProjectFile.subproject),
            db.joinedload(ProjectFile.stage),
            db.joinedload(ProjectFile.task),
            db.joinedload(ProjectFile.upload_user)
        )

        # 应用筛选器
        if project_id:
            query = query.filter(ProjectFile.project_id == project_id)
        if upload_user_id:
            query = query.filter(ProjectFile.upload_user_id == upload_user_id)
        if visibility == 'public':
            query = query.filter(ProjectFile.is_public == True)
        elif visibility == 'private':
            query = query.filter(ProjectFile.is_public == False)

        # 执行分页查询
        paginated_files = query.order_by(ProjectFile.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # 准备响应数据
        files_data = []
        for file in paginated_files.items:
            try:
                file_path = os.path.join(current_app.root_path, file.file_path)
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

                files_data.append({
                    'id': file.id,
                    'fileName': file.file_name,
                    'originalName': file.original_name,
                    'fileSize': file_size,
                    'fileType': file.file_type,
                    'uploadTime': file.upload_date.isoformat(),
                    'uploader': file.upload_user.username if file.upload_user else "Unknown",
                    'upload_user_id': file.upload_user_id,
                    'projectName': file.project.name if file.project else None,
                    'project_id': file.project_id,
                    'subprojectName': file.subproject.name if file.subproject else None,
                    'subproject_id': file.subproject_id,
                    'stageName': file.stage.name if file.stage else None,
                    'stage_id': file.stage_id,
                    'taskName': file.task.name if file.task else None,
                    'task_id': file.task_id,
                    'is_public': file.is_public
                })
            except Exception as e:
                print(f"Error processing file {file.id}: {str(e)}")
                continue

        return jsonify({
            'files': files_data,
            'total': paginated_files.total,
            'pages': paginated_files.pages,
            'current_page': page
        })

    except Exception as e:
        return jsonify({'message': str(e)}), 500
