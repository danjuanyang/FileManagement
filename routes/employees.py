# router/employees.py
import os
from datetime import datetime
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify
from flask_cors import CORS

from config import app
from models import db, Project, ProjectFile, ProjectUpdate, ProjectStage, User, ReportClockinDetail, ReportClockin, StageTask, TaskProgressUpdate
from auth import get_employee_id
from routes.filemanagement import allowed_file, MAX_FILE_SIZE, generate_unique_filename, create_upload_path

employee_bp = Blueprint('employee', __name__)
CORS(employee_bp)  # 为此蓝图启用 CORS


# 用于解码 JWT 令牌并返回员工 ID
def get_employee_id():
    token = request.headers.get('Authorization').split()[1]
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    return data['user_id']


# 工程查看和编辑路线
@employee_bp.route('/projects', methods=['GET'])
def get_assigned_projects():
    employee_id = get_employee_id()
    projects = Project.query.filter_by(employee_id=employee_id).all()

    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'start_date': p.start_date.strftime('%Y-%m-%d'),
        'deadline': p.deadline.strftime('%Y-%m-%d'),
        'progress': p.progress,
        'status': p.status,
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
                'progress': t.progress,
                'files': [{
                    'id': f.id is not None,  # 检查文件是否有 ID
                    # 如果没做索引，content为空，却有文件，那么前端就会判断错误没有文件，所以前端按照是否有 ID 来判断是否有文件
                    'has_content': f.content is not None  # 检查文件是否有内容
                } for f in t.files]
            } for t in s.tasks]
        } for s in p.stages]
    } for p in projects])



# 2024年11月1日09:05:36
@employee_bp.route('/projects/<int:project_id>', methods=['PUT'])
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

    db.session.commit()

    return jsonify({'message': '项目更新成功'})


# 进度跟踪
@employee_bp.route('/projects/<int:project_id>/progress', methods=['PUT'])
def update_progress(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    project.progress = data['progress']
    db.session.commit()
    return jsonify({'message': '已成功更新进度'})




# 获取项目进度以供显示
@employee_bp.route('/projects/<int:project_id>/timeline', methods=['GET'])
def get_project_timeline(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify({
        'start_date': project.start_date.strftime('%Y-%m-%d'),
        'deadline': project.deadline.strftime('%Y-%m-%d'),
        'progress': project.progress
    })


# 截止日期提醒
@employee_bp.route('/projects/reminders', methods=['GET'])
def get_reminders():
    employee_id = request.args.get('employee_id', type=int)
    projects = Project.query.filter_by(employee_id=employee_id).all()
    reminders = []

    for project in projects:
        if project.deadline and project.deadline.date() < datetime.now().date():
            reminders.append({
                'project_id': project.id,
                'message': f'Project {project.name} is past the deadline!'
            })
        elif project.deadline and (project.deadline - datetime.now()).days < 7:
            reminders.append({
                'project_id': project.id,
                'message': f'Project {project.name} is approaching the deadline!'
            })

    return jsonify(reminders)


# 获取项目更新
@employee_bp.route('/projects/<int:project_id>/updates', methods=['GET'])
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


# 更新项目进度
@employee_bp.route('/projects/<int:project_id>/progress', methods=['POST'])
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


# ---------------------------------





# 从登录信息获取用户信息
# Token 验证装饰器
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # 从请求头中获取 token
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'message': '无效的token格式'}), 401

        if not token:
            return jsonify({'message': 'token缺失'}), 401

        try:
            # 验证 token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user:
                return jsonify({'message': '用户不存在'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'token已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': '无效的token'}), 401

        return f(current_user, *args, **kwargs)

    return decorated


# 获取用户个人信息接口
@employee_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'role': current_user.role,
        'name': current_user.name if hasattr(current_user, 'name') else current_user.username,
    }), 200


# 后端接口 - 添加检查当月是否已填报的接口
@employee_bp.route('/check-monthly-report', methods=['GET'])
@token_required
def check_monthly_report(current_user):
    has_reported = ReportClockin.has_reported_this_month(current_user.id)
    return jsonify({
        'has_reported': has_reported,
        'month': datetime.now().strftime('%Y-%m'),
    })


# 修改提交接口，添加验证
# @employee_bp.route('/fill-card', methods=['POST'])
# @token_required
# def report_clock_in(current_user):
#     # 先检查是否已经提交过
#     if ReportClockin.has_reported_this_month(current_user.id):
#         return jsonify({
#             'error': '本月已提交过补卡申请，不能重复提交',
#         }), 400
#
#     data = request.get_json()
#     dates = data.get('dates', [])
#
#     if len(dates) > 3:
#         return jsonify({'error': '最多只能选择3天'}), 400
#
#     try:
#         # 创建补卡记录
#         report = ReportClockin(
#             employee_id=current_user.id,
#             report_date=datetime.now()
#         )
#         db.session.add(report)
#         db.session.flush()
#
#         # 添加补卡明细
#         reported_dates = []
#         for date_str in dates:
#             try:
#                 date_obj = datetime.strptime(date_str, '%Y-%m-%d')
#                 weekday = date_obj.strftime('%A')
#
#                 detail = ReportClockinDetail(
#                     report_id=report.id,
#                     clockin_date=date_obj.date(),
#                     weekday=weekday
#                 )
#                 db.session.add(detail)
#
#                 reported_dates.append({
#                     'date': date_str,
#                     'weekday': weekday
#                 })
#             except ValueError:
#                 db.session.rollback()
#                 return jsonify({'error': f'无效的日期格式: {date_str}'}), 400
#
#         db.session.commit()
#         return jsonify({
#             'message': '补卡提交成功',
#             'report_id': report.id,
#             'employee_id': current_user.id,
#             'employee_name': current_user.name if hasattr(current_user, 'name') else current_user.username,
#             'reported_dates': reported_dates
#         }), 200
#
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

@employee_bp.route('/fill-card', methods=['POST'])
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





# 获取补卡记录
# @employee_bp.route('/report-data', methods=['GET'])
# @token_required
# def get_report_data(current_user):
#     # 获取当前月份的开始和结束时间
#     today = datetime.now()
#     start_of_month = datetime(today.year, today.month, 1)
#     end_of_month = datetime(today.year, today.month + 1, 1) if today.month < 12 else datetime(today.year + 1, 1, 1)
#
#     # 查询本月的补卡记录
#     report = ReportClockin.query.filter(
#         ReportClockin.employee_id == current_user.id,
#         ReportClockin.report_date >= start_of_month,
#         ReportClockin.report_date < end_of_month
#     ).first()
#
#     if not report:
#         return jsonify({'error': '未找到补卡记录'}), 404
#
#     # 获取补卡明细
#     reported_dates = [{
#         'date': detail.clockin_date.strftime('%Y-%m-%d'),
#         'weekday': detail.weekday
#     } for detail in report.details]
#
#     return jsonify({
#         'report_date': report.report_date,
#         'employee_name': current_user.name if hasattr(current_user, 'name') else current_user.username,
#         'employee_id': current_user.id,
#         'reported_dates': reported_dates
#     })


@employee_bp.route('/report-data', methods=['GET'])
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

#2024年11月25日16:59:02

# 创建任务进度更新
@employee_bp.route('/tasks/<int:task_id>/progress-updates', methods=['POST'])
def add_task_progress_update(task_id):
    task = StageTask.query.get_or_404(task_id)
    data = request.get_json()

    if 'progress' not in data or 'description' not in data:
        return jsonify({'error': '缺少必要字段：progress 或 description'}), 400

    # 确保进度是向前推进的
    if data['progress'] < task.progress:
        return jsonify({'error': '任务进度不能回退'}), 400

    # 创建进度更新记录
    update = TaskProgressUpdate(
        task_id=task_id,
        progress=data['progress'],
        description=data['description']
    )

    # 更新任务的当前进度
    task.progress = data['progress']
    if task.progress == 100:
        task.status = 'completed'

    db.session.add(update)
    db.session.commit()

    return jsonify({'message': '任务进度更新成功'})

# 获取任务的进度更新记录
@employee_bp.route('/tasks/<int:task_id>/progress-updates', methods=['GET'])
def get_task_progress_updates(task_id):
    task = StageTask.query.get_or_404(task_id)
    updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.created_at.desc()).all()

    return jsonify([{
        'id': update.id,
        'progress': update.progress,
        'description': update.description,
        'created_at': update.created_at.isoformat()
    } for update in updates])