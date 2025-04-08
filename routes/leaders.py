# routes/leaders.py
import string
import random

from flask import Blueprint, request, jsonify
from flask_cors import CORS
from sqlalchemy import desc
from user_agents import parse

from models import db, Project, ProjectFile, User, StageTask, ProjectStage, EditTimeTracking, ReportClockinDetail, \
    ReportClockin, UserSession, TaskProgressUpdate, Subproject
from datetime import datetime

from routes.employees import token_required
from utils.activity_tracking import track_activity, log_user_activity
from utils.network_utils import get_real_ip

leader_bp = Blueprint('leader', __name__)
CORS(leader_bp)


@leader_bp.route('/projects', methods=['GET'])
@track_activity
def get_projects():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')

    query = Project.query
    if search:
        query = query.filter(Project.name.ilike(f'%{search}%'))

    projects = query.paginate(page=page, per_page=per_page)

    def format_date(date):
        return date.strftime('%Y-%m-%d') if date else None

    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'employee': p.employee.username if p.employee else None,
            'start_date': format_date(p.start_date),
            'deadline': format_date(p.deadline),
            # 'progress': p.progress,
            'progress': f"{p.progress:.2f}" if p.progress is not None else None,
            'status': p.status
        } for p in projects.items],
        'total': projects.total,
        'pages': projects.pages,
        'current_page': page
    })


# 创建项目
@leader_bp.route('/projects', methods=['POST'])
@track_activity
@token_required
def create_project(current_user):
    # 检查是否是管理员
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    data = request.get_json()

    # 验证员工是否存在
    if 'employee_id' in data:
        employee = User.query.get(data['employee_id'])
        if not employee:
            return jsonify({'error': '员工不存在'}), 400

    project = Project(
        name=data['name'],
        description=data['description'],
        employee_id=data['employee_id'],
        start_date=datetime.fromisoformat(data['start_date']),
        deadline=datetime.fromisoformat(data['deadline']),
        status='pending'
    )

    db.session.add(project)
    db.session.commit()

    return jsonify({
        'message': '项目创建成功',
        'project_id': project.id
    }), 201


# 更新项目
@leader_bp.route('/projects/<int:project_id>', methods=['PUT'])
@token_required
def update_project(current_user, project_id):  # 修改函数签名，接收 current_user 参数
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    # 更新处理程序保持不变
    update_handlers = {
        'name': lambda x: x,
        'description': lambda x: x,
        'status': lambda x: x,
        'progress': lambda x: x,
        'start_date': lambda x: datetime.fromisoformat(x),
        'deadline': lambda x: datetime.fromisoformat(x),
        'employee': lambda x: User.query.get(x) if x else None,
        'employee_id': lambda x: User.query.get(x) if x else None
    }

    try:
        for key, value in data.items():
            if key in update_handlers:
                if key == 'employee' or key == 'employee_id':
                    if value:
                        employee = User.query.get(value)
                        if employee is None:
                            return jsonify({'error': f'员工ID {value} 不存在'}), 400
                        project.employee = employee
                else:
                    processed_value = update_handlers[key](value)
                    setattr(project, key, processed_value)

        db.session.commit()
        return jsonify({
            'message': '项目更新成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'employee': project.employee.username if project.employee else None,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'deadline': project.deadline.isoformat() if project.deadline else None,
                'progress': project.progress,
                'status': project.status
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 查看项目文件
@leader_bp.route('/projects/<int:project_id>/files', methods=['GET'])
@track_activity
def get_project_files(project_id):
    files = ProjectFile.query.filter_by(project_id=project_id).all()
    return jsonify({
        'files': [{
            'id': f.id,
            'file_name': f.file_name,
            'file_type': f.file_type,
            'file_url': f.file_url,
            'file_size': f.file_size,
            'upload_user': f.upload_user.username,
            'upload_date': f.upload_date.isoformat()
        } for f in files]
    })


# 获取所有员工列表
@leader_bp.route('/employees', methods=['GET'])
@track_activity
def get_employees():
    employees = User.query.filter_by(role=2).all()
    return jsonify({
        'employees': [{
            'id': e.id,
            'username': e.username
        } for e in employees]
    })


# 查看单个项目所有信息，此处请求为project没有s
# 查看单个项目所有信息
@leader_bp.route('/project/<int:project_id>', methods=['GET'])
@track_activity
def get_project_details(project_id):
    try:
        # 检索项目
        project = Project.query.get_or_404(project_id)

        # 检索与项目相关的阶段
        stages = ProjectStage.query.filter_by(project_id=project_id).all()

        # 准备响应数据
        project_data = {
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'employee': project.employee.username if project.employee else None,
            'start_date': project.start_date.strftime('%Y-%m-%d') if project.start_date else None,
            'deadline': project.deadline.strftime('%Y-%m-%d') if project.deadline else None,
            'progress': f"{project.progress:.2f}" if project.progress is not None else None,
            'status': project.status,
            'stages': []
        }

        for stage in stages:
            # 检索与阶段相关的任务
            tasks = StageTask.query.filter_by(stage_id=stage.id).all()

            # 检索阶段的编辑时间跟踪
            stage_tracking = EditTimeTracking.query.filter_by(stage_id=stage.id, edit_type='stage').first()
            stage_edit_time = stage_tracking.duration if stage_tracking else None

            stage_data = {
                'id': stage.id,
                'name': stage.name,
                'tracking_edit_time': stage_edit_time,
                'tasks': []
            }
            for task in tasks:
                # 检索任务的编辑时间跟踪
                task_tracking = EditTimeTracking.query.filter_by(task_id=task.id, edit_type='task').first()
                task_edit_time = task_tracking.duration if task_tracking else None

                task_data = {
                    'id': task.id,
                    'name': task.name,
                    'description': task.description,
                    'employee': project.employee.username if project.employee else None,
                    'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                    'status': task.status,
                    'progress': f"{task.progress:.2f}" if task.progress is not None else None,
                    'created_at': task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else None,
                    'updated_at': task.updated_at.strftime('%Y-%m-%d %H:%M:%S') if task.updated_at else None,
                    'tracking_edit_time': task_edit_time
                }

                stage_data['tasks'].append(task_data)

            project_data['stages'].append(stage_data)

        return jsonify(project_data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@leader_bp.route('/report-clockin-data', methods=['GET'])
@track_activity
@token_required
def get_report_clockin_data(current_user):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    # 获取查询参数
    month = request.args.get('month')  # 格式：YYYY-MM

    try:
        if month:
            date = datetime.strptime(month, '%Y-%m')
            start_date = datetime(date.year, date.month, 1)
            if date.month == 12:
                end_date = datetime(date.year + 1, 1, 1)
            else:
                end_date = datetime(date.year, date.month + 1, 1)
        else:
            # 默认显示当月
            today = datetime.now()
            start_date = datetime(today.year, today.month, 1)
            if today.month == 12:
                end_date = datetime(today.year + 1, 1, 1)
            else:
                end_date = datetime(today.year, today.month + 1, 1)

        # 查询补卡记录
        reports = db.session.query(
            ReportClockin,
            User
        ).join(
            User,
            ReportClockin.employee_id == User.id
        ).filter(
            ReportClockin.report_date >= start_date,
            ReportClockin.report_date < end_date
        ).all()

        # 整理数据
        result = []
        for report, user in reports:
            # 获取补卡详情
            details = ReportClockinDetail.query.filter_by(report_id=report.id).all()

            result.append({
                'report_id': report.id,
                'employee_id': user.id,
                'employee_name': user.name if hasattr(user, 'name') else user.username,
                'report_date': report.report_date.strftime('%Y-%m-%d %H:%M:%S'),
                'dates': [{
                    'date': detail.clockin_date.strftime('%Y-%m-%d'),
                    'weekday': detail.weekday,
                    'remarks': detail.remarks
                } for detail in details]
            })
        return jsonify({
            'data': result,
            'total': len(result)
        })
    except ValueError:
        return jsonify({'error': '无效的日期格式'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@leader_bp.route('/projectlist', methods=['GET'])
@track_activity
@token_required
def get_project_list(current_user):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        # 检索所有项目
        projects = Project.query.all()

        # 准备响应数据
        project_list = []
        for project in projects:
            # 检索每个项目的子项目
            subprojects = Subproject.query.filter_by(project_id=project.id).all()
            subproject_list = []

            for subproject in subprojects:
                # 检索子项目的负责人信息
                employee = User.query.get(subproject.employee_id) if subproject.employee_id else None

                # 检索子项目的阶段
                stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()
                stage_list = []

                for stage in stages:
                    # 检索每个阶段的任务
                    tasks = StageTask.query.filter_by(stage_id=stage.id).all()
                    task_list = []

                    for task in tasks:
                        # 检索任务的进度更新
                        progress_updates = TaskProgressUpdate.query.filter_by(task_id=task.id).order_by(
                            TaskProgressUpdate.created_at.desc()).all()
                        update_list = [{
                            'id': update.id,
                            'progress': f"{update.progress:.2f}" if update.progress is not None else None,
                            'description': update.description,
                            'created_at': update.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                            'recorder_id': update.recorder_id,
                            'recorder_name': User.query.get(update.recorder_id).username if update.recorder_id else None
                        } for update in progress_updates]

                        task_list.append({
                            'id': task.id,
                            'name': task.name,
                            'description': task.description,
                            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                            'status': task.status,
                            'progress': f"{task.progress:.2f}" if task.progress is not None else None,
                            'progress_updates': update_list
                        })

                    stage_list.append({
                        'id': stage.id,
                        'name': stage.name,
                        'description': stage.description,
                        'start_date': stage.start_date.strftime('%Y-%m-%d') if stage.start_date else None,
                        'end_date': stage.end_date.strftime('%Y-%m-%d') if stage.end_date else None,
                        'progress': f"{stage.progress:.2f}" if stage.progress is not None else None,
                        'status': stage.status,
                        'tasks': task_list
                    })

                subproject_list.append({
                    'id': subproject.id,
                    'name': subproject.name,
                    'description': subproject.description,
                    'employee_id': subproject.employee_id,
                    'employee_name': employee.username if employee else None,
                    'start_date': subproject.start_date.strftime('%Y-%m-%d') if subproject.start_date else None,
                    'deadline': subproject.deadline.strftime('%Y-%m-%d') if subproject.deadline else None,
                    'progress': f"{subproject.progress:.2f}" if subproject.progress is not None else None,
                    'status': subproject.status,
                    'stages': stage_list
                })

            # 检索每个项目的阶段 (现在改为获取未分配到子项目的阶段，如果有的话)
            stages = ProjectStage.query.filter_by(project_id=project.id, subproject_id=None).all()
            stage_list = []
            for stage in stages:
                # 检索每个阶段的任务
                tasks = StageTask.query.filter_by(stage_id=stage.id).all()
                task_list = [{
                    'id': task.id,
                    'name': task.name,
                    'description': task.description,
                    'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else None,
                    'status': task.status,
                    'progress': f"{task.progress:.2f}" if task.progress is not None else None
                } for task in tasks]

                stage_list.append({
                    'id': stage.id,
                    'name': stage.name,
                    'description': stage.description,
                    'start_date': stage.start_date.strftime('%Y-%m-%d') if stage.start_date else None,
                    'end_date': stage.end_date.strftime('%Y-%m-%d') if stage.end_date else None,
                    'progress': f"{stage.progress:.2f}" if stage.progress is not None else None,
                    'status': stage.status,
                    'tasks': task_list
                })

            # 检索每个项目的文件
            files = ProjectFile.query.filter_by(project_id=project.id).all()
            file_list = [{
                'id': file.id,
                'file_name': file.file_name,
                'file_type': file.file_type,
                'file_path': file.file_path,
                'upload_user': file.upload_user.username if hasattr(file, 'upload_user') and file.upload_user else None,
                'upload_date': file.upload_date.strftime('%Y-%m-%d %H:%M:%S')
            } for file in files]

            project_list.append({
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'employee': project.employee.username if project.employee else None,
                'start_date': project.start_date.strftime('%Y-%m-%d') if project.start_date else None,
                'deadline': project.deadline.strftime('%Y-%m-%d') if project.deadline else None,
                'progress': f"{project.progress:.2f}" if project.progress is not None else None,
                'status': project.status,
                'subprojects': subproject_list,
                'stages': stage_list,
                'files': file_list
            })

        return jsonify({'projects': project_list})

    except Exception as e:
        return jsonify({'error': str(e)}), 500



# 用户管理
@leader_bp.route('/users', methods=['GET'])
@token_required
def get_users(current_user):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)
        search = request.args.get('search', '')
        role = request.args.get('role', type=int)

        query = User.query

        if search:
            query = query.filter(User.username.ilike(f'%{search}%'))

        if role:
            query = query.filter(User.role == role)
            # 如果当前用户是角色 1，则添加条件以筛选出角色 0 用户
        if current_user.role == 1:
            query = query.filter(User.role != 0)

        total = query.count()
        users = query.paginate(page=page, per_page=page_size)

        def parse_user_agent(user_agent_string):
            if not user_agent_string:
                return "未知设备"
            try:
                user_agent = parse(user_agent_string)
                # 获取设备信息
                if user_agent.is_mobile:
                    device = f"移动设备 ({user_agent.device.brand} {user_agent.device.model})"
                elif user_agent.is_tablet:
                    device = f"平板设备 ({user_agent.device.brand} {user_agent.device.model})"
                elif user_agent.is_pc:
                    device = f"电脑 ({user_agent.browser.family} on {user_agent.os.family})"
                else:
                    device = f"{user_agent.browser.family} on {user_agent.os.family}"
                return device
            except:
                return "未知设备"

        user_list = []
        for user in users.items:
            last_session = UserSession.query.filter_by(user_id=user.id).order_by(desc(UserSession.login_time)).first()

            projects = Project.query.filter_by(employee_id=user.id).all()
            project_list = [{
                'id': project.id,
                'name': project.name,
                'progress': f"{project.progress:.2f}" if project.progress is not None else None,
                'status': project.status,
                'deadline': project.deadline.isoformat() if project.deadline else None
            } for project in projects]

            # 更新获取IP的逻辑
            user_data = {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'lastLogin': {
                    'login_time': last_session.login_time.isoformat() if last_session else None,
                    'is_active': last_session.is_active if last_session else False,
                    'ip_address': get_real_ip() if last_session else None,
                    'device_info': parse_user_agent(last_session.user_agent) if last_session else "未知设备"
                } if last_session else None,
                'projects': project_list,
                'sessions': [{
                    'login_time': session.login_time.isoformat(),
                    'ip_address': get_real_ip(),
                    'device_info': parse_user_agent(session.user_agent)
                } for session in
                    UserSession.query.filter_by(user_id=user.id).order_by(desc(UserSession.login_time)).limit(5)]
            }
            user_list.append(user_data)

        return jsonify({
            'items': user_list,
            'total': total,
            'page': page,
            'pageSize': page_size
        })

    except Exception as e:
        print(f"获取用户时出错： {str(e)}")  # 添加日志
        return jsonify({'error': str(e)}), 500


# 新建用户
@leader_bp.route('/users', methods=['POST'])
@token_required
def create_user(current_user):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        data = request.get_json()

        # 验证必要字段
        if not all(k in data for k in ('username', 'password', 'role')):
            return jsonify({'error': '缺少必要字段'}), 400

        # 检查用户名是否已存在
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': '用户名已存在'}), 400

        # 创建新用户
        new_user = User()
        new_user.username = data['username']
        new_user.set_password(data['password'])
        new_user.role = data['role']

        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            'message': '用户创建成功',
            'user': {
                'id': new_user.id,
                'username': new_user.username,
                'role': new_user.role
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 更新用户
@leader_bp.route('/users/<int:user_id>', methods=['PUT'])
@token_required
def update_user(current_user, user_id):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        # 更新用户信息
        if 'username' in data and data['username'] != user.username:
            if User.query.filter_by(username=data['username']).first():
                return jsonify({'error': '用户名已存在'}), 400
            user.username = data['username']

        if 'password' in data and data['password']:
            user.set_password(data['password'])

        if 'role' in data:
            user.role = data['role']

        # 明确处理团队领导关系
        if 'team_leader_id' in data:
            # 如果传入null或None，则清除团队领导关系
            if data['team_leader_id'] is None:
                user.team_leader_id = None
                print(f"已解除用户 {user.username} 的团队领导关系")
            else:
                # 验证团队领导是否存在并具有正确的角色
                leader = User.query.get(data['team_leader_id'])
                if not leader:
                    return jsonify({'error': '指定的团队领导不存在'}), 400
                if leader.role != 2:  # 团队领导角色
                    return jsonify({'error': '指定的用户不是团队领导'}), 400
                user.team_leader_id = data['team_leader_id']
                print(f"已将用户 {user.username} 分配给团队领导 {leader.username}")

        db.session.commit()

        return jsonify({
            'message': '用户更新成功',
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'team_leader_id': user.team_leader_id
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 删除用户
@leader_bp.route('/users/<int:user_id>', methods=['DELETE'])
@token_required
def delete_user(current_user, user_id):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        user = User.query.get_or_404(user_id)

        # 检查是否删除自己
        if user.id == current_user.id:
            return jsonify({'error': '不能删除当前登录用户'}), 400

        # 开始事务
        with db.session.begin_nested():
            # 先处理可能的关联数据
            # 获取用户关联的项目
            projects = Project.query.filter_by(employee_id=user.id).all()
            if projects:
                for project in projects:
                    # 检查项目状态
                    if project.status == 'ongoing':
                        return jsonify({'error': f'用户有正在进行中的项目: {project.name}, 无法删除'}), 400
                    project.employee_id = None

            # 将上传文件的用户ID置为空
            ProjectFile.query.filter_by(upload_user_id=user.id).update({'upload_user_id': None})

            # 删除用户相关的编辑时间记录和补卡记录会通过 CASCADE 自动处理

            # 删除用户
            db.session.delete(user)

        # 提交事务
        db.session.commit()
        return jsonify({'message': '用户删除成功'})

    except Exception as e:
        db.session.rollback()
        print(f"删除用户错误: {str(e)}")  # 添加日志输出
        return jsonify({'error': f'删除用户失败: {str(e)}'}), 500


@leader_bp.route('/users/<int:user_id>/change-password', methods=['PUT'])
@token_required
def change_user_password(current_user, user_id):
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()

        # 验证必要字段
        if 'new_password' not in data:
            return jsonify({'error': '缺少必要字段'}), 400

        # 验证新密码
        new_password = data['new_password']
        if len(new_password) < 6:
            return jsonify({'error': '密码长度必须大于6位'}), 400

        # 验证新密码复杂度（至少包含数字和字母）
        if not any(c.isdigit() for c in new_password) or not any(c.isalpha() for c in new_password):
            return jsonify({'error': '密码必须包含数字和字母'}), 400

        # 更新密码
        user.set_password(new_password)

        # 记录活动
        log_user_activity(
            user_id=current_user.id,
            action_type='change_password',
            action_detail=f'管理员修改用户 {user.username} 的密码',
            resource_type='user',
            resource_id=user.id
        )

        db.session.commit()

        return jsonify({'message': '密码修改成功'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 管理员重置用户密码
@leader_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@token_required
def reset_user_password(current_user, user_id):
    global db
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    try:
        user = User.query.get_or_404(user_id)

        # 生成随机临时密码（12位字母数字组合）
        chars = string.ascii_letters + string.digits
        temp_password = ''
        # 确保至少包含一个字母和一个数字
        temp_password += random.choice(string.ascii_letters)  # 添加一个字母
        temp_password += random.choice(string.digits)  # 添加一个数字
        # 添加剩余的随机字符
        for _ in range(10):
            temp_password += random.choice(chars)

        # 将生成的字符打乱顺序
        temp_password_list = list(temp_password)
        random.shuffle(temp_password_list)
        temp_password = ''.join(temp_password_list)

        # 更新密码
        user.set_password(temp_password)

        # 记录活动
        log_user_activity(
            user_id=current_user.id,
            action_type='reset_password',
            action_detail=f'管理员重置用户 {user.username} 的密码',
            resource_type='user',
            resource_id=user.id
        )

        # 关闭用户当前所有活动会话
        from models import UserSession, db
        active_sessions = UserSession.query.filter_by(
            user_id=user.id,
            is_active=True
        ).all()

        for session in active_sessions:
            session.end_session()

        db.session.commit()

        return jsonify({
            'message': '密码重置成功',
            'username': user.username,
            'temp_password': temp_password,
            'note': '此临时密码仅显示一次，请立即保存并通知用户'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 添加新的端点以获取团队成员
@leader_bp.route('/team-members', methods=['GET'])
@track_activity
@token_required
def get_team_members(current_user):
    # 只有管理员、经理和团队负责人可以访问此内容
    if current_user.role not in [0, 1, 2]:
        return jsonify({'error': '权限不足'}), 403

    # 查询团队成员
    team_members = User.query.filter_by(role=3).all()

    return jsonify({
        'team_members': [{
            'id': tm.id,
            'username': tm.username,
            'name': tm.name if hasattr(tm, 'name') else tm.username,
            'role': tm.role,
        } for tm in team_members]
    })


@leader_bp.route('/my-projects', methods=['GET'])
@track_activity
@token_required
def get_my_projects(current_user):
    # 检查用户是否为团队领导
    if current_user.role != 2:  # 团队领导角色
        return jsonify({'error': '权限不足'}), 403

    # 将项目分配给此团队负责人
    projects = Project.query.filter_by(employee_id=current_user.id).all()

    return jsonify({
        'projects': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'start_date': p.start_date.strftime('%Y-%m-%d') if p.start_date else None,
            'deadline': p.deadline.strftime('%Y-%m-%d') if p.deadline else None,
            'progress': f"{p.progress:.2f}" if p.progress else None,
            'status': p.status,
            'subprojects': [{
                'id': sp.id,
                'name': sp.name,
                'description': sp.description,
                'employee_id': sp.employee_id,
                'employee_name': User.query.get(sp.employee_id).username if sp.employee_id else None,
                'progress': f"{sp.progress:.2f}" if sp.progress else None,
                'status': sp.status,
            } for sp in p.subprojects]
        } for p in projects]
    })


# -------------2025年3月27日22:36:34-------------------------------


# 获取特定团队领导的团队成员
@leader_bp.route('/team-leaders/<int:leader_id>/members', methods=['GET'])
@token_required
def get_leader_team_members(current_user, leader_id):
    # 检查权限：管理员、经理或团队负责人本人
    if current_user.role not in [0, 1] and current_user.id != leader_id:
        return jsonify({'error': '权限不足'}), 403

    # 验证领导者是否存在并具有正确的角色
    leader = User.query.get_or_404(leader_id)
    if leader.role != 2:  # 组长
        return jsonify({'error': '指定的用户不是组长'}), 400

    # 获取分配给此领导者的所有团队成员
    team_members = User.query.filter_by(team_leader_id=leader_id).all()

    return jsonify({
        'leader': {
            'id': leader.id,
            'username': leader.username
        },
        'team_members': [{
            'id': member.id,
            'username': member.username
        } for member in team_members]
    })


# 将团队成员分配给团队负责人
@leader_bp.route('/team-leaders/<int:leader_id>/members', methods=['PUT'])
@token_required
def assign_members_to_leader(current_user, leader_id):
    # 只有管理员和经理才能分配团队成员
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    data = request.get_json()
    member_ids = data.get('member_ids', [])

    # 验证领导者是否存在并具有正确的角色
    leader = User.query.get_or_404(leader_id)
    if leader.role != 2:
        return jsonify({'error': '指定的用户不是组长'}), 400

    try:
        # 获取当前已分配给该组长的所有组员
        current_members = User.query.filter_by(team_leader_id=leader_id).all()
        current_member_ids = [member.id for member in current_members]

        print(f"组长ID {leader_id} 当前组员: {current_member_ids}")
        print(f"请求分配的新组员: {member_ids}")

        # 找出需要移除的组员 (在当前列表但不在新列表中)
        to_remove = [mid for mid in current_member_ids if mid not in member_ids]
        # 找出需要添加的组员 (在新列表但不在当前列表中)
        to_add = [mid for mid in member_ids if mid not in current_member_ids]

        print(f"需要移除的组员: {to_remove}")
        print(f"需要添加的组员: {to_add}")

        # 清除不再属于该组长的组员
        if to_remove:
            User.query.filter(User.id.in_(to_remove)).update(
                {User.team_leader_id: None},
                synchronize_session=False
            )
            print(f"已解除 {len(to_remove)} 名组员与组长ID {leader_id} 的关联")

        # 添加新组员
        for member_id in to_add:
            member = User.query.get_or_404(member_id)

            # 检查用户是否为团队成员
            if member.role != 3:  # 团队成员角色
                return jsonify({'error': f'用户 {member.username} 不是组员角色'}), 400

            # 检查用户是否已分配给其他领导者
            if member.team_leader_id is not None and member.team_leader_id != leader_id:
                return jsonify({'error': f'用户 {member.username} 已经分配给其他组长'}), 400

            # 分配给此领导者
            member.team_leader_id = leader_id
            print(f"已将组员ID {member_id} 分配给组长ID {leader_id}")

        db.session.commit()
        return jsonify({
            'message': '组员分配成功',
            'added': len(to_add),
            'removed': len(to_remove)
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"分配组员失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 从团队负责人中删除团队成员
@leader_bp.route('/team-leaders/<int:leader_id>/members/<int:member_id>', methods=['DELETE'])
@token_required
def remove_member_from_leader(current_user, leader_id, member_id):
    # 只有管理员和经理才能移除团队成员
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    # 验证领导者是否存在并具有正确的角色
    leader = User.query.get_or_404(leader_id)
    if leader.role != 2:  # Team Leader role
        return jsonify({'error': '指定的用户不是组长'}), 400

    # 验证成员是否存在并分配给此领导
    member = User.query.get_or_404(member_id)
    if member.team_leader_id != leader_id:
        return jsonify({'error': '该组员不属于此组长'}), 400

    try:
        # 删除团队领导关联
        print(f"正在移除组员ID {member_id} 与组长ID {leader_id} 的关联")
        member.team_leader_id = None
        db.session.commit()

        # 验证关联是否确实被删除
        member = User.query.get(member_id)
        if member.team_leader_id is not None:
            print(f"警告: 组员ID {member_id} 的team_leader_id仍然是 {member.team_leader_id}")
            # 强制再次尝试删除
            User.query.filter_by(id=member_id).update({'team_leader_id': None})
            db.session.commit()
        else:
            print(f"成功: 组员ID {member_id} 的team_leader_id已成功设置为None")

        return jsonify({'message': '组员移除成功'}), 200

    except Exception as e:
        db.session.rollback()
        print(f"移除组员失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 让所有团队领导及其团队成员
@leader_bp.route('/team-leaders', methods=['GET'])
@token_required
def get_all_team_leaders(current_user):
    # 只有管理员和经理可以查看所有团队负责人
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403

    # 获取所有团队负责人
    team_leaders = User.query.filter_by(role=2).all()

    result = []
    for leader in team_leaders:
        # 获取此领导者的所有团队成员
        team_members = User.query.filter_by(team_leader_id=leader.id).all()

        leader_data = {
            'id': leader.id,
            'username': leader.username,
            'team_members': [{
                'id': member.id,
                'username': member.username
            } for member in team_members]
        }
        result.append(leader_data)

    return jsonify({'team_leaders': result})


# 管理员改密码
@leader_bp.route('/change-password', methods=['POST'])
@track_activity
@token_required
def change_password(current_user):
    # 只有管理员和经理才能更改密码
    if current_user.role not in [0, 1]:
        return jsonify({'error': '权限不足'}), 403
    else:
        try:
            data = request.get_json()

            # 验证必要字段
            if not all(k in data for k in ('old_password', 'new_password')):
                return jsonify({'error': '缺少必要字段'}), 400

            # 验证旧密码是否正确
            if not current_user.check_password(data['old_password']):
                return jsonify({'error': '旧密码不正确'}), 400

            # 验证新密码
            new_password = data['new_password']
            if len(new_password) < 6:
                return jsonify({'error': '密码长度必须大于6位'}), 400

            # 验证新密码复杂度（至少包含数字和字母）
            if not any(c.isdigit() for c in new_password) or not any(c.isalpha() for c in new_password):
                return jsonify({'error': '密码必须包含数字和字母'}), 400

            # 更新密码
            current_user.set_password(new_password)

            # 记录活动
            log_user_activity(
                user_id=current_user.id,
                action_type='change_password',
                action_detail=f'用户修改了密码',
                resource_type='leader',
                resource_id=current_user.id
            )

            db.session.commit()

            return jsonify({'message': '密码修改成功'})

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500