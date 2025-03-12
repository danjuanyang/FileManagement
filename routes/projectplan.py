# projectplan.py
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from models import db, ProjectStage, StageTask, EditTimeTracking, ProjectFile
from auth import get_employee_id
from utils.activity_tracking import track_activity

projectplan_bp = Blueprint('projectplan', __name__)
CORS(projectplan_bp)  # 为此蓝图启用 CORS
CORS(projectplan_bp, resources={r"/api/*": {"origins": "*"}})  # 根据需要调整路径


# 获取包含任务的项目阶段
@projectplan_bp.route('/stages/<int:project_id>', methods=['GET'])
@track_activity
def get_project_stages(project_id):
    stages = ProjectStage.query.filter_by(project_id=project_id).all()
    return jsonify([{
        'id': stage.id,
        'project_id': stage.project_id,
        'name': stage.name,
        'description': stage.description,
        'startDate': stage.start_date.isoformat(),
        'endDate': stage.end_date.isoformat(),
        'progress': stage.progress,
        'status': stage.status,
        'tasks': [{
            'id': task.id,
            'project_id': stage.project_id,
            'name': task.name,
            'description': task.description,
            'dueDate': task.due_date.isoformat(),
            'status': task.status,
            'progress': task.progress,
            'files': [{
                'id': f.id is not None,  # 检查文件是否有 ID
                # 如果没做索引，content为空，却有文件，那么前端就会判断错误没有文件，所以前端按照是否有 ID 来判断是否有文件
                'has_content': f.content is not None if hasattr(f, 'content') else False  # 检查文件是否有内容
            } for f in task.files]
        } for task in stage.tasks]
    } for stage in stages])


# 获取项目的所有文件
@projectplan_bp.route('/files/project/<int:project_id>', methods=['GET'])
@track_activity
def get_project_files(project_id):
    """获取项目的所有文件，不过滤阶段和任务"""
    try:
        # 获取与项目关联的所有文件
        files = ProjectFile.query.filter_by(project_id=project_id).all()

        return jsonify([{
            'id': file.id,
            'originalName': file.original_name,
            'fileSize': os.path.getsize(os.path.join(current_app.root_path, file.file_path)) if os.path.exists(
                os.path.join(current_app.root_path, file.file_path)) else 0,
            'fileType': file.file_type,
            'uploadTime': file.upload_date.isoformat(),
            'uploader': file.upload_user.username if hasattr(file, 'upload_user') and file.upload_user else "未知",
            'upload_user_id': file.upload_user_id,
            'isPublic': file.is_public,
            'stage_id': file.stage_id,
            'task_id': file.task_id,
            'project_id': file.project_id,
            'project_name': file.project.name if hasattr(file, 'project') and file.project else "未知项目"
        } for file in files])

    except Exception as e:
        print(f"获取项目文件时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 获取特定阶段的所有文件
@projectplan_bp.route('/files/stage/<int:stage_id>', methods=['GET'])
@track_activity
def get_stage_files(stage_id):
    """获取特定阶段的所有文件，不过滤任务"""
    try:
        # 只过滤阶段，不过滤任务
        files = ProjectFile.query.filter_by(stage_id=stage_id).all()

        # 获取阶段信息以便获取项目名称
        stage = ProjectStage.query.get(stage_id)
        project_name = ""
        if stage and hasattr(stage, 'project') and stage.project:
            project_name = stage.project.name

        return jsonify([{
            'id': file.id,
            'originalName': file.original_name,
            'fileSize': os.path.getsize(os.path.join(current_app.root_path, file.file_path)) if os.path.exists(
                os.path.join(current_app.root_path, file.file_path)) else 0,
            'fileType': file.file_type,
            'uploadTime': file.upload_date.isoformat(),
            'uploader': file.upload_user.username if hasattr(file, 'upload_user') and file.upload_user else "未知",
            'upload_user_id': file.upload_user_id,
            'isPublic': file.is_public,
            'stage_id': file.stage_id,
            'task_id': file.task_id,
            'project_id': stage.project_id if stage else None,
            'project_name': project_name
        } for file in files])

    except Exception as e:
        print(f"获取阶段文件时出错： {str(e)}")
        return jsonify({'error': str(e)}), 500


# 获取所有文件（系统级别）
@projectplan_bp.route('/files/all', methods=['GET'])
@track_activity
def get_all_files():
    """获取系统中的所有文件，用于全局文件视图"""
    try:
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        project_id = request.args.get('project_id', type=int)
        search = request.args.get('search', '')
        public_filter = request.args.get('public')

        # 构建查询
        query = ProjectFile.query

        # 应用过滤条件
        if project_id:
            query = query.filter(ProjectFile.project_id == project_id)

        if search:
            query = query.filter(ProjectFile.original_name.ilike(f'%{search}%'))

        if public_filter:
            is_public = public_filter.lower() == 'public'
            query = query.filter(ProjectFile.is_public == is_public)

        # 计算总数
        total = query.count()

        # 应用分页
        files = query.order_by(ProjectFile.upload_date.desc()).paginate(page=page, per_page=per_page).items

        # 构建响应
        result = {
            'files': [{
                'id': file.id,
                'originalName': file.original_name,
                'fileSize': os.path.getsize(os.path.join(current_app.root_path, file.file_path)) if os.path.exists(
                    os.path.join(current_app.root_path, file.file_path)) else 0,
                'fileType': file.file_type,
                'uploadTime': file.upload_date.isoformat(),
                'uploader': file.upload_user.username if hasattr(file, 'upload_user') and file.upload_user else "未知",
                'upload_user_id': file.upload_user_id,
                'isPublic': file.is_public,
                'stage_id': file.stage_id,
                'task_id': file.task_id,
                'project_id': file.project_id,
                'project_name': file.project.name if hasattr(file, 'project') and file.project else "未知项目"
            } for file in files],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page  # 总页数
        }

        return jsonify(result)

    except Exception as e:
        print(f"获取全部文件时出错： {str(e)}")
        return jsonify({'error': str(e), 'files': [], 'total': 0}), 500


# 创建项目阶段
@projectplan_bp.route('/stages', methods=['POST'])
@track_activity
def create_project_stage():
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)

    stage = ProjectStage(
        name=data['name'],
        description=data['description'],
        start_date=datetime.strptime(data['startDate'], '%Y-%m-%d'),
        end_date=datetime.strptime(data['endDate'], '%Y-%m-%d'),
        progress=data['progress'],
        status=data['status'],
        project_id=data['projectId']
    )

    db.session.add(stage)

    if tracking_id:
        tracking = EditTimeTracking.query.get(tracking_id)
        if tracking:
            tracking.end_time = datetime.now()
            tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
            tracking.stage_id = stage.id

    db.session.commit()
    return jsonify({'message': '阶段创建成功', '阶段ID': stage.id}), 201


# 更新项目阶段
@projectplan_bp.route('/stages/<int:id>', methods=['PUT'])
@track_activity
def update_project_stage(id):
    stage = ProjectStage.query.get_or_404(id)
    data = request.get_json()

    stage.name = data['name']
    stage.description = data['description']
    stage.start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
    stage.end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
    stage.progress = data['progress']
    stage.status = data['status']

    db.session.commit()
    return jsonify({'message': '阶段更新成功'}), 200


# 删除项目阶段
@projectplan_bp.route('/stages/<int:id>', methods=['DELETE'])
@track_activity
def delete_project_stage(id):
    stage = ProjectStage.query.get_or_404(id)
    db.session.delete(stage)
    db.session.commit()
    return jsonify({'message': '阶段删除成功'}), 200


# -------------------
# 为阶段创建任务
@projectplan_bp.route('/stages/<int:stage_id>/tasks', methods=['POST'])
@track_activity
def create_stage_task(stage_id):
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)

    task = StageTask(
        stage_id=stage_id,
        name=data['name'],
        description=data.get('description', ''),
        due_date=datetime.strptime(data['dueDate'], '%Y-%m-%d'),
        status=data.get('status', 'pending'),
        progress=data.get('progress', 0)
    )

    db.session.add(task)

    if tracking_id:
        tracking = EditTimeTracking.query.get(tracking_id)
        if tracking:
            tracking.end_time = datetime.now()
            tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
            tracking.task_id = task.id

    db.session.commit()
    update_stage_progress(stage_id)
    return jsonify({'message': '任务创建成功', 'id': task.id}), 201


# 更新任务
@projectplan_bp.route('/tasks/<int:task_id>', methods=['PUT'])
@track_activity
def update_task(task_id):
    task = StageTask.query.get_or_404(task_id)
    data = request.get_json()

    tracking_id = data.pop('trackingId', None)

    task.name = data.get('name', task.name)
    task.description = data.get('description', task.description)
    task.due_date = datetime.strptime(data['dueDate'], '%Y-%m-%d') if 'dueDate' in data else task.due_date
    task.status = data.get('status', task.status)
    task.progress = data.get('progress', task.progress)

    # 如果有追踪 ID，更新编辑时间记录
    if tracking_id:
        tracking = EditTimeTracking.query.get(tracking_id)
        if tracking:
            tracking.end_time = datetime.now()
            tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
            tracking.task_id = task.id

    db.session.commit()

    # 根据任务更新阶段进度
    update_stage_progress(task.stage_id)

    return jsonify({'message': '任务更新成功'}), 200


# 删除任务
@projectplan_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
@track_activity
def delete_task(task_id):
    task = StageTask.query.get_or_404(task_id)
    stage_id = task.stage_id

    db.session.delete(task)
    db.session.commit()

    # 根据剩余任务更新阶段进度
    update_stage_progress(stage_id)

    return jsonify({'message': '任务删除成功'}), 200


# 更新阶段进度和状态
def update_stage_progress(stage_id):
    stage = ProjectStage.query.get(stage_id)
    if not stage.tasks:
        return

    # 计算所有任务的平均进度
    total_progress = sum(task.progress for task in stage.tasks)
    stage.progress = total_progress // len(stage.tasks)

    # 根据任务更新阶段状态
    if all(task.status == 'completed' for task in stage.tasks):
        stage.status = 'completed'
    elif any(task.status == 'in_progress' for task in stage.tasks):
        stage.status = 'in_progress'

    db.session.commit()


# 导出项目计划，包含所有阶段和任务
@projectplan_bp.route('/projects/<int:project_id>/export', methods=['GET'])
@track_activity
def export_project_plan(project_id):
    stages = ProjectStage.query.filter_by(project_id=project_id).all()
    return jsonify([{
        'id': stage.id,
        'name': stage.name,
        'description': stage.description,
        'startDate': stage.start_date.isoformat(),
        'endDate': stage.end_date.isoformat(),
        'progress': stage.progress,
        'status': stage.status,
        'tasks': [{
            'id': task.id,
            'name': task.name,
            'description': task.description,
            'dueDate': task.due_date.isoformat(),
            'status': task.status,
            'progress': task.progress
        } for task in stage.tasks]
    } for stage in stages])


# 追踪编辑时间
@projectplan_bp.route('/tracking/start', methods=['POST'])
@track_activity
def start_edit_tracking():
    data = request.get_json()
    user_id = get_employee_id()

    tracking = EditTimeTracking(
        project_id=data['projectId'],
        user_id=user_id,
        edit_type=data['editType'],
        start_time=datetime.now(),
        end_time=datetime.now(),  # 将在编辑结束时更新
        duration=0,  # 将在编辑结束时计算
        stage_id=data.get('stageId'),
        task_id=data.get('taskId')
    )

    db.session.add(tracking)
    db.session.commit()

    return jsonify({'id': tracking.id}), 201


@projectplan_bp.route('/tracking/end/<int:tracking_id>', methods=['PUT'])
@track_activity
def end_edit_tracking(tracking_id):
    tracking = EditTimeTracking.query.get_or_404(tracking_id)
    tracking.end_time = datetime.now()
    tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())

    db.session.commit()
    return jsonify({'message': 'Tracking ended successfully'}), 200
