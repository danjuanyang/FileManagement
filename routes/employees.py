# router/employees.py
import os
from datetime import datetime
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify
from flask_cors import CORS

from config import app
from models import db, Project, Subproject, ProjectFile, ProjectUpdate, ProjectStage, User, ReportClockinDetail, \
    ReportClockin, \
    StageTask, TaskProgressUpdate, EditTimeTracking
from auth import get_employee_id
from routes.filemanagement import allowed_file, MAX_FILE_SIZE, generate_unique_filename, create_upload_path
from utils.activity_tracking import track_activity, log_user_activity

employee_bp = Blueprint('employee', __name__)
CORS(employee_bp)  # 为此蓝图启用 CORS


# 用于解码 JWT 令牌并返回员工 ID
def get_employee_id():
    token = request.headers.get('Authorization').split()[1]
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    return data['user_id']


# 项目概览统计接口
@employee_bp.route('/projets/dashboard', methods=['GET'])
@track_activity
def get_projects_dashboard(current_user):
    employee_id = current_user.id

    # 获取分配给该员工的所有项目
    projects = Project.query.filter_by(employee_id=employee_id).all()

    # 计算统计数据
    total_projects = len(projects)
    completed_projects = sum(1 for p in projects if p.status == 'completed')
    in_progress_projects = sum(1 for p in projects if p.status == 'in_progress')
    pending_projects = sum(1 for p in projects if p.status == 'pending')

    # 统计子项目数据
    total_subprojects = 0
    completed_subprojects = 0
    in_progress_subprojects = 0
    pending_subprojects = 0

    for project in projects:
        total_subprojects += len(project.subprojects)
        completed_subprojects += sum(1 for sp in project.subprojects if sp.status == 'completed')
        in_progress_subprojects += sum(1 for sp in project.subprojects if sp.status == 'in_progress')
        pending_subprojects += sum(1 for sp in project.subprojects if sp.status == 'pending')

    # 计算即将到期和已逾期的项目
    today = datetime.now().date()
    upcoming_deadlines = []
    overdue_projects = []

    for project in projects:
        if project.status != 'completed':
            if project.deadline.date() < today:
                overdue_projects.append({
                    'id': project.id,
                    'name': project.name,
                    'deadline': project.deadline.strftime('%Y-%m-%d'),
                    'days_overdue': (today - project.deadline.date()).days,
                    'type': 'project'
                })
            elif (project.deadline.date() - today).days <= 7:
                upcoming_deadlines.append({
                    'id': project.id,
                    'name': project.name,
                    'deadline': project.deadline.strftime('%Y-%m-%d'),
                    'days_remaining': (project.deadline.date() - today).days,
                    'type': 'project'
                })

        # 检查子项目截止日期
        for subproject in project.subprojects:
            if subproject.status != 'completed':
                if subproject.deadline.date() < today:
                    overdue_projects.append({
                        'id': subproject.id,
                        'project_id': project.id,
                        'name': subproject.name,
                        'deadline': subproject.deadline.strftime('%Y-%m-%d'),
                        'days_overdue': (today - subproject.deadline.date()).days,
                        'type': 'subproject'
                    })
                elif (subproject.deadline.date() - today).days <= 7:
                    upcoming_deadlines.append({
                        'id': subproject.id,
                        'project_id': project.id,
                        'name': subproject.name,
                        'deadline': subproject.deadline.strftime('%Y-%m-%d'),
                        'days_remaining': (subproject.deadline.date() - today).days,
                        'type': 'subproject'
                    })

    return jsonify({
        'projects': {
            'total': total_projects,
            'completed': completed_projects,
            'in_progress': in_progress_projects,
            'pending': pending_projects
        },
        'subprojects': {
            'total': total_subprojects,
            'completed': completed_subprojects,
            'in_progress': in_progress_subprojects,
            'pending': pending_subprojects
        },
        'deadlines': {
            'upcoming': upcoming_deadlines,
            'overdue': overdue_projects
        }
    })


# 工程查看和编辑路线 - 更新以包含子项目
@employee_bp.route('/projects', methods=['GET'])
@track_activity
def get_assigned_projects():
    employee_id = get_employee_id()
    projects = Project.query.filter_by(employee_id=employee_id).all()

    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'start_date': p.start_date.strftime('%Y-%m-%d'),
        'deadline': p.deadline.strftime('%Y-%m-%d'),
        'progress': f"{p.progress:.2f}" if p.progress else None,
        'status': p.status,
        'subprojects': [{
            'id': sp.id,
            'name': sp.name,
            'description': sp.description,
            'start_date': sp.start_date.strftime('%Y-%m-%d'),
            'deadline': sp.deadline.strftime('%Y-%m-%d'),
            'progress': f"{sp.progress:.2f}" if sp.progress else None,
            'status': sp.status,
            'stages': [{
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'start_date': s.start_date.strftime('%Y-%m-%d'),
                'end_date': s.end_date.strftime('%Y-%m-%d'),
                'progress': f"{s.progress:.2f}" if s.progress else None,
                'status': s.status,
                'tasks': [{
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'due_date': t.due_date.strftime('%Y-%m-%d'),
                    'status': t.status,
                    'progress': f"{t.progress:.2f}" if t.progress else None,
                    'files': [{
                        'id': f.id is not None,  # 检查文件是否有 ID
                        # 如果没做索引，content为空，却有文件，那么前端就会判断错误没有文件，所以前端按照是否有 ID 来判断是否有文件
                        'has_content': f.content is not None  # 检查文件是否有内容
                    } for f in t.files]
                } for t in s.tasks]
            } for s in sp.stages]
        } for sp in p.subprojects]
    } for p in projects])


# 获取特定项目的详细信息，包括子项目层次结构
@employee_bp.route('/projects/<int:project_id>', methods=['GET'])
@track_activity
def get_project_details(project_id):
    project = Project.query.get_or_404(project_id)

    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'start_date': project.start_date.strftime('%Y-%m-%d'),
        'deadline': project.deadline.strftime('%Y-%m-%d'),
        'progress': f"{project.progress:.2f}" if project.progress else None,
        'status': project.status,
        'employee_id': project.employee_id,
        'subprojects': [{
            'id': sp.id,
            'name': sp.name,
            'description': sp.description,
            'start_date': sp.start_date.strftime('%Y-%m-%d'),
            'deadline': sp.deadline.strftime('%Y-%m-%d'),
            'progress': f"{sp.progress:.2f}" if sp.progress else None,
            'status': sp.status,
            'stages': [{
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'start_date': s.start_date.strftime('%Y-%m-%d'),
                'end_date': s.end_date.strftime('%Y-%m-%d'),
                'progress': f"{s.progress:.2f}" if s.progress else None,
                'status': s.status,
                'tasks': [{
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'due_date': t.due_date.strftime('%Y-%m-%d'),
                    'status': t.status,
                    'progress': f"{t.progress:.2f}" if t.progress else None,
                } for t in s.tasks]
            } for s in sp.stages]
        } for sp in project.subprojects]
    })


@employee_bp.route('/projects/<int:project_id>', methods=['PUT'])
@track_activity
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    # 更新项目信息
    if 'start_date' in data:
        project.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    if 'deadline' in data:
        project.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
    if 'status' in data:
        # 只有当新状态不是 'completed' 时才允许更新状态
        # 这样可以防止通过这个接口将已完成的项目重新设为进行中
        if data['status'] != 'completed' or project.status != 'completed':
            project.status = data['status']
    if 'name' in data:
        project.name = data['name']
    if 'description' in data:
        project.description = data['description']

    db.session.commit()

    return jsonify({'message': '项目更新成功'})


# 子项目相关接口
@employee_bp.route('/subprojects/<int:subproject_id>', methods=['GET'])
@track_activity
def get_subproject_details(subproject_id):
    subproject = Subproject.query.get_or_404(subproject_id)

    return jsonify({
        'id': subproject.id,
        'name': subproject.name,
        'description': subproject.description,
        'project_id': subproject.project_id,
        'start_date': subproject.start_date.strftime('%Y-%m-%d'),
        'deadline': subproject.deadline.strftime('%Y-%m-%d'),
        'progress': f"{subproject.progress:.2f}" if subproject.progress else None,
        'status': subproject.status,
        'stages': [{
            'id': s.id,
            'name': s.name,
            'description': s.description,
            'start_date': s.start_date.strftime('%Y-%m-%d'),
            'end_date': s.end_date.strftime('%Y-%m-%d'),
            'progress': f"{s.progress:.2f}" if s.progress else None,
            'status': s.status,
            'tasks': [{
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'due_date': t.due_date.strftime('%Y-%m-%d'),
                'status': t.status,
                'progress': f"{t.progress:.2f}" if t.progress else None,
            } for t in s.tasks]
        } for s in subproject.stages]
    })


@employee_bp.route('/subprojects/<int:subproject_id>', methods=['PUT'])
@track_activity
def update_subproject(subproject_id):
    subproject = Subproject.query.get_or_404(subproject_id)
    data = request.get_json()

    # 更新子项目信息
    if 'name' in data:
        subproject.name = data['name']
    if 'description' in data:
        subproject.description = data['description']
    if 'start_date' in data:
        subproject.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
    if 'deadline' in data:
        subproject.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
    if 'status' in data:
        subproject.status = data['status']
    if 'progress' in data:
        subproject.progress = data['progress']

    db.session.commit()

    return jsonify({'message': '子项目更新成功'})


# 进度跟踪 - 更新为支持子项目层次结构
@employee_bp.route('/projects/<int:project_id>/progress', methods=['PUT'])
@track_activity
def update_progress(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    project.progress = data['progress']

    # 更新进度时创建进度更新记录
    new_update = ProjectUpdate(
        project_id=project_id,
        progress=data['progress'],
        description=data.get('description', '项目进度更新'),
        created_at=datetime.now(),
        type='progress'
    )
    db.session.add(new_update)

    db.session.commit()
    return jsonify({'message': '已成功更新进度'})


@employee_bp.route('/subprojects/<int:subproject_id>/progress', methods=['PUT'])
@track_activity
def update_subproject_progress(current_user, subproject_id):
    subproject = Subproject.query.get_or_404(subproject_id)

    # 权限检查 - 组员只能更新分配给自己的子项目
    if current_user.role == 3 and subproject.employee_id != current_user.id:
        return jsonify({'error': '您没有权限更新此子项目的进度'}), 403

    # 组长只能更新自己项目下的子项目
    elif current_user.role == 2:
        project = Project.query.get(subproject.project_id)
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限更新此项目的子项目进度'}), 403

    data = request.get_json()
    subproject.progress = data['progress']

    # 可能需要更新子项目状态
    if data.get('status'):
        subproject.status = data['status']

    # 更新父项目的进度
    # 父项目的进度基于所有子项目的平均进度
    project = Project.query.get(subproject.project_id)
    if project and project.subprojects:
        total_progress = sum(sp.progress for sp in project.subprojects)
        project.progress = total_progress / len(project.subprojects)

    db.session.commit()
    return jsonify({'message': '已成功更新子项目进度'})


# 获取项目进度以供显示 - 更新为支持子项目
@employee_bp.route('/projects/<int:project_id>/timeline', methods=['GET'])
@track_activity
def get_project_timeline(project_id):
    project = Project.query.get_or_404(project_id)

    # 获取项目所有子项目的时间线信息
    subprojects_timelines = [{
        'id': sp.id,
        'name': sp.name,
        'start_date': sp.start_date.strftime('%Y-%m-%d'),
        'deadline': sp.deadline.strftime('%Y-%m-%d'),
        'progress': f"{sp.progress:.2f}" if sp.progress else None,
        'status': sp.status,
        'stages': [{
            'id': s.id,
            'name': s.name,
            'start_date': s.start_date.strftime('%Y-%m-%d'),
            'end_date': s.end_date.strftime('%Y-%m-%d'),
            'progress': f"{s.progress:.2f}" if s.progress else None,
            'status': s.status
        } for s in sp.stages]
    } for sp in project.subprojects]

    return jsonify({
        'project': {
            'id': project.id,
            'name': project.name,
            'start_date': project.start_date.strftime('%Y-%m-%d'),
            'deadline': project.deadline.strftime('%Y-%m-%d'),
            'progress': f"{project.progress:.2f}" if project.progress else None,
            'status': project.status
        },
        'subprojects': subprojects_timelines
    })


# 截止日期提醒 - 更新以包括子项目
@employee_bp.route('/projects/reminders', methods=['GET'])
@track_activity
def get_reminders():
    employee_id = request.args.get('employee_id', type=int)
    projects = Project.query.filter_by(employee_id=employee_id).all()
    reminders = []

    today = datetime.now().date()

    # 项目级别的提醒
    for project in projects:
        if project.deadline and project.deadline.date() < today:
            reminders.append({
                'project_id': project.id,
                'project_name': project.name,
                'type': 'project',
                'message': f'项目 {project.name} 已经超过截止日期！',
                'days_overdue': (today - project.deadline.date()).days
            })
        elif project.deadline and (project.deadline.date() - today).days < 7:
            reminders.append({
                'project_id': project.id,
                'project_name': project.name,
                'type': 'project',
                'message': f'项目 {project.name} 即将到期！',
                'days_remaining': (project.deadline.date() - today).days
            })

        # 子项目级别的提醒
        for subproject in project.subprojects:
            if subproject.deadline and subproject.deadline.date() < today:
                reminders.append({
                    'project_id': project.id,
                    'project_name': project.name,
                    'subproject_id': subproject.id,
                    'subproject_name': subproject.name,
                    'type': 'subproject',
                    'message': f'子项目 {subproject.name} 已经超过截止日期！',
                    'days_overdue': (today - subproject.deadline.date()).days
                })
            elif subproject.deadline and (subproject.deadline.date() - today).days < 7:
                reminders.append({
                    'project_id': project.id,
                    'project_name': project.name,
                    'subproject_id': subproject.id,
                    'subproject_name': subproject.name,
                    'type': 'subproject',
                    'message': f'子项目 {subproject.name} 即将到期！',
                    'days_remaining': (subproject.deadline.date() - today).days
                })

    return jsonify(reminders)


# 获取项目更新 - 保持不变
@employee_bp.route('/projects/<int:project_id>/updates', methods=['GET'])
@track_activity
def get_project_updates(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        updates = ProjectUpdate.query.filter_by(project_id=project_id) \
            .order_by(ProjectUpdate.created_at.desc()).all()

        return jsonify({
            'updates': [{
                'id': update.id,
                'progress': update.progress,
                'description': update.description,
                'created_at': update.created_at.isoformat(),
                'type': update.type
            } for update in updates]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 更新项目进度 - 更新为支持子项目
@employee_bp.route('/projects/<int:project_id>/progress', methods=['POST'])
@track_activity
def update_project_progress(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()

    if 'progress' not in data or 'description' not in data:
        return jsonify({'error': '无效的负载'}), 400

    new_update = ProjectUpdate(
        project_id=project_id,
        progress=data['progress'],
        description=data['description'],
        created_at=datetime.now(),
        type='progress'
    )

    project.progress = data['progress']

    db.session.add(new_update)
    db.session.commit()

    return jsonify({
        'message': '已成功更新进度',
        # 返回所有更新
        'update_id': new_update.id
    })


# Token 验证装饰器 - 保持不变
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'message': '无效的token格式'}), 401

        if not token:
            return jsonify({'message': 'token缺失'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.filter_by(id=data['user_id']).first()

            if not current_user:
                return jsonify({'message': '用户不存在'}), 401

            # 检查函数参数中是否已经有 current_user
            if 'current_user' in kwargs:
                return f(*args, **kwargs)
            else:
                # 保持原有的参数传递方式
                return f(current_user, *args, **kwargs)

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'token已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '无效的token'}), 401

    return decorated


# 获取用户个人信息接口 - 保持不变
@employee_bp.route('/profile', methods=['GET'])
@track_activity
@token_required
def get_profile(current_user):
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'role': current_user.role,
        'name': current_user.name if hasattr(current_user, 'name') else current_user.username,
    }), 200


# 后端接口 - 添加检查当月是否已填报的接口 - 保持不变
@employee_bp.route('/check-monthly-report', methods=['GET'])
@track_activity
@token_required
def check_monthly_report(current_user):
    has_reported = ReportClockin.has_reported_this_month(current_user.id)
    return jsonify({
        'has_reported': has_reported,
        'month': datetime.now().strftime('%Y-%m'),
    })


# 修改提交接口，添加验证 - 保持不变
@employee_bp.route('/fill-card', methods=['POST'])
@track_activity
@token_required
def report_clock_in(current_user):
    # 先检查是否已经提交过
    if ReportClockin.has_reported_this_month(current_user.id):
        return jsonify({
            'error': '本月已提交过补卡申请，不能重复提交',
        }), 400

    data = request.get_json()
    dates_data = data.get('dates', [])

    if len(dates_data) > 3:
        return jsonify({'error': '最多只能选择3天'}), 400

    try:
        # 创建补卡记录
        report = ReportClockin(
            employee_id=current_user.id,
            report_date=datetime.now()
        )
        db.session.add(report)
        db.session.flush()

        # 添加补卡明细
        reported_dates = []
        for date_item in dates_data:
            try:
                date_str = date_item['date']
                remarks = date_item['remarks']
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                weekday = date_obj.strftime('%A')

                detail = ReportClockinDetail(
                    report_id=report.id,
                    clockin_date=date_obj.date(),
                    weekday=weekday,
                    remarks=remarks
                )
                db.session.add(detail)

                reported_dates.append({
                    'date': date_str,
                    'weekday': weekday,
                    'remarks': remarks
                })
            except ValueError:
                db.session.rollback()
                return jsonify({'error': f'无效的日期格式: {date_str}'}), 400

        db.session.commit()
        return jsonify({
            'message': '补卡提交成功',
            'report_id': report.id,
            'employee_id': current_user.id,
            'employee_name': current_user.name if hasattr(current_user, 'name') else current_user.username,
            'reported_dates': reported_dates
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 获取补卡记录 - 保持不变
@employee_bp.route('/report-data', methods=['GET'])
@track_activity
@token_required
def get_report_data(current_user):
    # 获取当前月份的开始和结束时间
    today = datetime.now()
    start_of_month = datetime(today.year, today.month, 1)
    end_of_month = datetime(today.year, today.month + 1, 1) if today.month < 12 else datetime(today.year + 1, 1, 1)

    # 查询本月的补卡记录
    report = ReportClockin.query.filter(
        ReportClockin.employee_id == current_user.id,
        ReportClockin.report_date >= start_of_month,
        ReportClockin.report_date < end_of_month
    ).first()

    if not report:
        return jsonify({'error': '未找到补卡记录'}), 404

    # 获取补卡明细（现在包含备注信息）
    reported_dates = [{
        'date': detail.clockin_date.strftime('%Y-%m-%d'),
        'weekday': detail.weekday,
        'remarks': detail.remarks
    } for detail in report.details]

    return jsonify({
        'report_date': report.report_date,
        'employee_name': current_user.name if hasattr(current_user, 'name') else current_user.username,
        'employee_id': current_user.id,
        'reported_dates': reported_dates
    })


# 创建任务进度更新 - 更新以添加更多关联字段
# 创建任务进度更新 - 更新以添加记录人ID
@employee_bp.route('/tasks/<int:task_id>/progress-updates', methods=['POST'])
@track_activity
def add_task_progress_update(task_id):
    task = StageTask.query.get_or_404(task_id)
    data = request.get_json()

    # 获取当前用户ID
    current_user_id = get_employee_id()

    if 'progress' not in data or 'description' not in data:
        return jsonify({'error': '缺少必要字段：progress 或 description'}), 400

    # 确保进度是向前推进的
    if data['progress'] < task.progress:
        return jsonify({'error': '任务进度不能回退'}), 400

    # 创建进度更新记录，添加记录人ID
    update = TaskProgressUpdate(
        task_id=task_id,
        progress=data['progress'],
        description=data['description'],
        recorder_id=current_user_id  # 添加记录人ID
    )

    # 更新任务的当前进度
    task.progress = data['progress']
    if task.progress == 100:
        task.status = 'completed'

    db.session.add(update)
    db.session.commit()

    # 更新关联的阶段进度
    # 计算阶段的进度
    stage = ProjectStage.query.get(task.stage_id)
    if stage and stage.tasks:
        total_progress = sum(t.progress for t in stage.tasks)
        stage.progress = total_progress / len(stage.tasks)

        # 如果所有任务已完成，则阶段也标记为已完成
        if all(t.status == 'completed' for t in stage.tasks):
            stage.status = 'completed'
        elif any(t.status == 'in_progress' for t in stage.tasks):
            stage.status = 'in_progress'

        db.session.commit()

        # 更新子项目进度
        if stage.subproject_id:
            subproject = Subproject.query.get(stage.subproject_id)
            if subproject and subproject.stages:
                total_progress = sum(s.progress for s in subproject.stages)
                subproject.progress = total_progress / len(subproject.stages)

                # 更新子项目状态
                if all(s.status == 'completed' for s in subproject.stages):
                    subproject.status = 'completed'
                elif any(s.status == 'in_progress' for s in subproject.stages):
                    subproject.status = 'in_progress'

                db.session.commit()

                # 更新父项目进度
                project = Project.query.get(subproject.project_id)
                if project and project.subprojects:
                    total_progress = sum(sp.progress for sp in project.subprojects)
                    project.progress = total_progress / len(project.subprojects)
                    db.session.commit()

    return jsonify({'message': '任务进度更新成功'})


# 获取特定子项目下的所有任务
@employee_bp.route('/subprojects/<int:subproject_id>/tasks', methods=['GET'])
@track_activity
def get_subproject_tasks(subproject_id):
    # 通过子项目ID获取所有关联的阶段
    stages = ProjectStage.query.filter_by(subproject_id=subproject_id).all()

    # 收集所有阶段的任务
    all_tasks = []
    for stage in stages:
        tasks = StageTask.query.filter_by(stage_id=stage.id).all()
        for task in tasks:
            all_tasks.append({
                'id': task.id,
                'name': task.name,
                'description': task.description,
                'due_date': task.due_date.strftime('%Y-%m-%d'),
                'status': task.status,
                'progress': task.progress,
                'stage_id': stage.id,
                'stage_name': stage.name
            })

    return jsonify(all_tasks)


# 获取任务的进度更新记录 - 保持不变
# 获取任务的进度更新记录 - 包含记录人信息
@employee_bp.route('/tasks/<int:task_id>/progress-updates', methods=['GET'])
@track_activity
def get_task_progress_updates(task_id):
    task = StageTask.query.get_or_404(task_id)
    updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.created_at.desc()).all()

    result = []
    for update in updates:
        update_data = {
            'id': update.id,
            'progress': update.progress,
            'description': update.description,
            'created_at': update.created_at.isoformat(),
            'recorder_id': update.recorder_id
        }

        # 如果有记录人，添加记录人的用户名
        if update.recorder_id:
            recorder = User.query.get(update.recorder_id)
            if recorder:
                update_data['recorder_name'] = recorder.username

        result.append(update_data)

    return jsonify(result)


# 检测任务编辑时间 - 保持不变
@employee_bp.route('/tasks/<int:task_id>/edit-time', methods=['GET'])
@track_activity
@token_required  # 确保使用身份验证装饰器
def get_task_edit_time(current_user, task_id):
    try:
        # 首先验证任务是否存在
        task = StageTask.query.get_or_404(task_id)

        # 获取此任务的所有编辑时间记录
        edit_records = EditTimeTracking.query.filter_by(
            task_id=task_id,
            edit_type='task'
        ).all()

        # 计算总持续时间
        total_duration = sum(record.duration for record in edit_records)

        # 获取详细的编辑历史记录
        edit_history = [{
            'start_time': record.start_time.isoformat(),
            'end_time': record.end_time.isoformat(),
            'duration': record.duration,
            'user_id': record.user_id
        } for record in edit_records]

        return jsonify({
            'task_id': task_id,
            'duration': total_duration,
            'edit_history': edit_history,
            'edit_count': len(edit_records)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 获取阶段编辑时间 - 保持不变
@employee_bp.route('/stages/<int:stage_id>/edit-time', methods=['GET'])
@track_activity
@token_required
def get_stage_edit_time(current_user, stage_id):
    try:
        # 获取此阶段的所有编辑时间记录
        edit_records = EditTimeTracking.query.filter_by(
            stage_id=stage_id,
            edit_type='stage'
        ).all()

        total_duration = sum(record.duration for record in edit_records)

        edit_history = [{
            'start_time': record.start_time.isoformat(),
            'end_time': record.end_time.isoformat(),
            'duration': record.duration,
            'user_id': record.user_id
        } for record in edit_records]

        return jsonify({
            'stage_id': stage_id,
            'duration': total_duration,
            'edit_history': edit_history,
            'edit_count': len(edit_records)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 获取子项目编辑时间
@employee_bp.route('/subprojects/<int:subproject_id>/edit-time', methods=['GET'])
@track_activity
@token_required
def get_subproject_edit_time(current_user, subproject_id):
    try:
        # 获取此子项目的所有编辑时间记录
        edit_records = EditTimeTracking.query.filter_by(
            subproject_id=subproject_id,
            edit_type='subproject'
        ).all()

        total_duration = sum(record.duration for record in edit_records)

        edit_history = [{
            'start_time': record.start_time.isoformat(),
            'end_time': record.end_time.isoformat(),
            'duration': record.duration,
            'user_id': record.user_id
        } for record in edit_records]

        return jsonify({
            'subproject_id': subproject_id,
            'duration': total_duration,
            'edit_history': edit_history,
            'edit_count': len(edit_records)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 获取项目总编辑时间 - 更新以包含子项目
@employee_bp.route('/projects/<int:project_id>/total-edit-time', methods=['GET'])
@track_activity
@token_required
def get_project_total_edit_time(current_user, project_id):
    try:
        # 获取此项目的所有编辑时间记录
        edit_records = EditTimeTracking.query.filter_by(
            project_id=project_id
        ).all()

        # 计算不同类型的总计
        task_duration = sum(record.duration for record in edit_records if record.edit_type == 'task')
        stage_duration = sum(record.duration for record in edit_records if record.edit_type == 'stage')
        subproject_duration = sum(record.duration for record in edit_records if record.edit_type == 'subproject')
        total_duration = task_duration + stage_duration + subproject_duration

        # 获取每个用户的统计数据
        user_stats = {}
        for record in edit_records:
            if record.user_id not in user_stats:
                user_stats[record.user_id] = 0
            user_stats[record.user_id] += record.duration

        return jsonify({
            'project_id': project_id,
            'total_duration': total_duration,
            'task_duration': task_duration,
            'stage_duration': stage_duration,
            'subproject_duration': subproject_duration,
            'user_stats': user_stats,
            'edit_count': len(edit_records)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 用于计算编辑时间统计信息 - 保持不变
def calculate_edit_stats(records):
    if not records:
        return {
            'total_duration': 0,
            'average_duration': 0,
            'edit_count': 0,
            'last_edit': None
        }

    total_duration = sum(record.duration for record in records)
    edit_count = len(records)
    average_duration = total_duration / edit_count
    last_edit = max(record.end_time for record in records)

    return {
        'total_duration': total_duration,
        'average_duration': round(average_duration, 2),
        'edit_count': edit_count,
        'last_edit': last_edit.isoformat()
    }


# 搜索与过滤功能
@employee_bp.route('/search', methods=['GET'])
@track_activity
@token_required
def search_resources(current_user):
    query = request.args.get('q', '')
    resource_type = request.args.get('type', 'all')
    status = request.args.get('status', '')

    results = {
        'projects': [],
        'subprojects': [],
        'stages': [],
        'tasks': [],
        'files': []
    }

    # 搜索项目
    if resource_type in ['all', 'projects']:
        projects_query = Project.query

        if query:
            projects_query = projects_query.filter(Project.name.like(f'%{query}%') |
                                                   Project.description.like(f'%{query}%'))

        if status:
            projects_query = projects_query.filter(Project.status == status)

        # 只返回当前员工负责的项目
        projects_query = projects_query.filter(Project.employee_id == current_user.id)

        projects = projects_query.all()
        results['projects'] = [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'status': p.status,
            'progress': p.progress,
            'deadline': p.deadline.strftime('%Y-%m-%d'),
            'type': 'project'
        } for p in projects]

    # 搜索子项目
    if resource_type in ['all', 'subprojects']:
        # 获取当前用户负责的所有项目
        user_projects = Project.query.filter_by(employee_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]

        subprojects_query = Subproject.query.filter(Subproject.project_id.in_(project_ids))

        if query:
            subprojects_query = subprojects_query.filter(Subproject.name.like(f'%{query}%') |
                                                         Subproject.description.like(f'%{query}%'))

        if status:
            subprojects_query = subprojects_query.filter(Subproject.status == status)

        subprojects = subprojects_query.all()
        results['subprojects'] = [{
            'id': sp.id,
            'name': sp.name,
            'description': sp.description,
            'status': sp.status,
            'progress': sp.progress,
            'deadline': sp.deadline.strftime('%Y-%m-%d'),
            'project_id': sp.project_id,
            'type': 'subproject'
        } for sp in subprojects]

    # 只在查询不为空时搜索任务和阶段，以避免返回太多结果
    if query and resource_type in ['all', 'tasks', 'stages']:
        # 获取用户负责的项目相关的所有子项目ID
        user_projects = Project.query.filter_by(employee_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]

        # 获取这些项目下所有子项目的ID
        subprojects = Subproject.query.filter(Subproject.project_id.in_(project_ids)).all()
        subproject_ids = [sp.id for sp in subprojects]

        # 获取这些子项目下的所有阶段
        if resource_type in ['all', 'stages']:
            stages_query = ProjectStage.query.filter(ProjectStage.subproject_id.in_(subproject_ids))

            if query:
                stages_query = stages_query.filter(ProjectStage.name.like(f'%{query}%') |
                                                   ProjectStage.description.like(f'%{query}%'))

            if status:
                stages_query = stages_query.filter(ProjectStage.status == status)

            stages = stages_query.all()
            results['stages'] = [{
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'status': s.status,
                'progress': s.progress,
                'subproject_id': s.subproject_id,
                'project_id': s.project_id,
                'type': 'stage'
            } for s in stages]

        # 搜索任务
        if resource_type in ['all', 'tasks']:
            # 获取所有相关阶段的ID
            stages = ProjectStage.query.filter(ProjectStage.subproject_id.in_(subproject_ids)).all()
            stage_ids = [s.id for s in stages]

            tasks_query = StageTask.query.filter(StageTask.stage_id.in_(stage_ids))

            if query:
                tasks_query = tasks_query.filter(StageTask.name.like(f'%{query}%') |
                                                 StageTask.description.like(f'%{query}%'))

            if status:
                tasks_query = tasks_query.filter(StageTask.status == status)

            tasks = tasks_query.all()
            results['tasks'] = [{
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'status': t.status,
                'progress': t.progress,
                'due_date': t.due_date.strftime('%Y-%m-%d'),
                'stage_id': t.stage_id,
                'type': 'task'
            } for t in tasks]

    # 搜索文件
    if resource_type in ['all', 'files'] and query:
        # 获取用户负责的项目的ID
        user_projects = Project.query.filter_by(employee_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]

        files_query = ProjectFile.query.filter(ProjectFile.project_id.in_(project_ids))

        files_query = files_query.filter(ProjectFile.original_name.like(f'%{query}%'))

        files = files_query.all()
        results['files'] = [{
            'id': f.id,
            'name': f.original_name,
            'file_type': f.file_type,
            'upload_date': f.upload_date.strftime('%Y-%m-%d'),
            'project_id': f.project_id,
            'subproject_id': f.subproject_id,
            'stage_id': f.stage_id,
            'task_id': f.task_id,
            'type': 'file'
        } for f in files]

    return jsonify(results)


# 修改密码 - 保持不变
@employee_bp.route('/change-password', methods=['POST'])
@track_activity
@token_required
def change_user_password(current_user):
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
            resource_type='user',
            resource_id=current_user.id
        )

        db.session.commit()

        return jsonify({'message': '密码修改成功'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -----------------------------------权限--------------------------------------

@employee_bp.route('/my-subprojects', methods=['GET'])
@track_activity
@token_required
def get_my_subprojects(current_user):
    # 仅团队成员可以访问此端点
    if current_user.role != 3:
        return jsonify({'error': '权限不足'}), 403

    try:
        # 获取分配给此团队成员的子项目
        subprojects = Subproject.query.filter_by(employee_id=current_user.id).all()

        # 检查此组员是否还属于某个组长团队
        if current_user.team_leader_id is None:
            # 如果组员不再属于任何组长，需要解除其与所有子项目的关联
            for subproject in subprojects:
                print(f"解除组员ID {current_user.id} 与子项目ID {subproject.id} 的关联")
                subproject.employee_id = None

            # 提交更改到数据库
            db.session.commit()

            # 清空子项目列表，因为现在应该没有分配的子项目了
            subprojects = []

            print(f"组员ID {current_user.id} 已不再属于任何组长，已解除所有子项目关联")
            return jsonify([])

        # 即使没有分配的子项目，也返回空数组而不是错误
        if not subprojects:
            return jsonify([])

        return jsonify([{
            'id': sp.id,
            'name': sp.name,
            'description': sp.description,
            'project_id': sp.project_id,
            'project_name': sp.project.name if sp.project else "未知项目",
            'start_date': sp.start_date.strftime('%Y-%m-%d'),
            'deadline': sp.deadline.strftime('%Y-%m-%d'),
            'progress': sp.progress,
            'status': sp.status,
            'employee_id': sp.employee_id,
            'stages': [{
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'start_date': s.start_date.strftime('%Y-%m-%d'),
                'end_date': s.end_date.strftime('%Y-%m-%d'),
                'progress': s.progress,
                'status': s.status,
                'tasks': [{
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'due_date': t.due_date.strftime('%Y-%m-%d'),
                    'status': t.status,
                    'progress': t.progress
                } for t in s.tasks]
            } for s in sp.stages]
        } for sp in subprojects])
    except Exception as e:
        print(f"获取组员子项目时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 确保是组员角色
@employee_bp.route('/assigned-projects/dashboard', methods=['GET'])
@track_activity
@token_required
def get_assigned_projects_dashboard(current_user):
    # 确保是组员角色
    if current_user.role != 3:
        return jsonify({'error': '此端点仅供组员访问'}), 403

    try:
        # 检查此组员是否还属于某个组长团队
        if current_user.team_leader_id is None:
            # 如果组员不再属于任何组长，需要解除其与所有子项目的关联
            assigned_subprojects = Subproject.query.filter_by(employee_id=current_user.id).all()
            for subproject in assigned_subprojects:
                print(f"解除组员ID {current_user.id} 与子项目ID {subproject.id} 的关联")
                subproject.employee_id = None

            # 提交更改到数据库
            db.session.commit()

            print(f"组员ID {current_user.id} 已不再属于任何组长，已解除所有子项目关联")
            return jsonify({
                'has_assignments': False,
                'message': '您当前没有被分配任何子项目'
            })

        # 获取分配给此组员的所有子项目
        assigned_subprojects = Subproject.query.filter_by(employee_id=current_user.id).all()

        # 如果没有分配的子项目，返回空响应
        if not assigned_subprojects:
            return jsonify({
                'has_assignments': False,
                'message': '您当前没有被分配任何子项目'
            })

        # 准备返回的数据
        result = {
            'has_assignments': True,
            'subprojects': []
        }

        for subproject in assigned_subprojects:
            # 获取父项目信息
            project = Project.query.get(subproject.project_id)
            project_name = project.name if project else "未知项目"

            # 获取子项目的阶段
            stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()

            # 构建子项目数据
            subproject_data = {
                'id': subproject.id,
                'name': subproject.name,
                'description': subproject.description,
                'project_id': subproject.project_id,
                'project_name': project_name,
                'startDate': subproject.start_date.strftime('%Y-%m-%d'),
                'deadline': subproject.deadline.strftime('%Y-%m-%d'),
                'progress': subproject.progress,
                'status': subproject.status,
                'stages_count': len(stages)
            }

            result['subprojects'].append(subproject_data)

        return jsonify(result)

    except Exception as e:
        print(f"获取组员分配的项目数据时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/assigned-projects', methods=['GET'])
@track_activity
@token_required
def get_assigned_projects_data(current_user):
    # 确保是组员角色
    if current_user.role != 3:
        return jsonify({'error': '此端点仅供组员访问'}), 403

    try:
        # 检查此组员是否还属于某个组长团队
        if current_user.team_leader_id is None:
            # 如果组员不再属于任何组长，需要解除其与所有子项目的关联
            assigned_subprojects = Subproject.query.filter_by(employee_id=current_user.id).all()
            for subproject in assigned_subprojects:
                print(f"解除组员ID {current_user.id} 与子项目ID {subproject.id} 的关联")
                subproject.employee_id = None

            # 提交更改到数据库
            db.session.commit()

            print(f"组员ID {current_user.id} 已不再属于任何组长，已解除所有子项目关联")
            return jsonify({
                'has_assignments': False,
                'subprojects': []
            })

        # 获取分配给此组员的所有子项目
        assigned_subprojects = Subproject.query.filter_by(employee_id=current_user.id).all()

        if not assigned_subprojects:
            return jsonify({
                'has_assignments': False,
                'subprojects': []
            })

        # 构建完整的数据结构
        result = {
            'has_assignments': True,
            'subprojects': []
        }

        for subproject in assigned_subprojects:
            # 获取所有阶段
            stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()

            # 构建阶段数据，包括任务
            stages_data = []
            for stage in stages:
                # 获取任务
                tasks = StageTask.query.filter_by(stage_id=stage.id).all()

                # 构建任务数据
                tasks_data = []
                for task in tasks:
                    # 获取文件信息
                    files = ProjectFile.query.filter_by(task_id=task.id).all()

                    tasks_data.append({
                        'id': task.id,
                        'name': task.name,
                        'description': task.description,
                        'dueDate': task.due_date.isoformat(),
                        'status': task.status,
                        'progress': task.progress,
                        'files': [{
                            'id': f.id,
                            'original_name': f.original_name,
                            'file_type': f.file_type,
                            'upload_date': f.upload_date.isoformat()
                        } for f in files]
                    })

                stages_data.append({
                    'id': stage.id,
                    'name': stage.name,
                    'description': stage.description,
                    'startDate': stage.start_date.isoformat(),
                    'endDate': stage.end_date.isoformat(),
                    'progress': stage.progress,
                    'status': stage.status,
                    'tasks': tasks_data
                })

            # 获取项目信息
            project = Project.query.get(subproject.project_id)

            result['subprojects'].append({
                'id': subproject.id,
                'name': subproject.name,
                'description': subproject.description,
                'startDate': subproject.start_date.isoformat(),
                'deadline': subproject.deadline.isoformat(),
                'progress': subproject.progress,
                'status': subproject.status,
                'project_id': subproject.project_id,
                'project_name': project.name if project else "未知项目",
                'stages': stages_data
            })

        return jsonify(result)

    except Exception as e:
        print(f"获取组员分配的项目数据时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500
