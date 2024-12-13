# projectplan.py
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from models import db, ProjectStage, StageTask, EditTimeTracking
from auth import get_employee_id

projectplan_bp = Blueprint('projectplan', __name__)
CORS(projectplan_bp)  # 为此蓝图启用 CORS
CORS(projectplan_bp, resources={r"/api/*": {"origins": "*"}})  # 根据需要调整路径


# 获取包含任务的项目阶段
@projectplan_bp.route('/stages/<int:project_id>', methods=['GET'])
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
                'has_content': f.content is not None  # 检查文件是否有内容
            } for f in task.files]
        } for task in stage.tasks]
    } for stage in stages])


# 创建项目阶段
@projectplan_bp.route('/stages', methods=['POST'])
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
    return jsonify({'message': '阶段创建成功', 'stageId': stage.id}), 201


# 更新项目阶段
@projectplan_bp.route('/stages/<int:id>', methods=['PUT'])
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
def delete_project_stage(id):
    stage = ProjectStage.query.get_or_404(id)
    db.session.delete(stage)
    db.session.commit()
    return jsonify({'message': '阶段删除成功'}), 200


# -------------------
# 为阶段创建任务
@projectplan_bp.route('/stages/<int:stage_id>/tasks', methods=['POST'])
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
def update_task(task_id):
    task = StageTask.query.get_or_404(task_id)
    data = request.get_json()

    tracking_id = data.pop('trackingId', None)

    task.name = data.get('name', task.name)
    task.description = data.get('description', task.description)
    task.due_date = datetime.strptime(data['dueDate'], '%Y-%m-%d') if 'dueDate' in data else task.due_date
    task.status = data.get('status', task.status)
    task.progress = data.get('progress', task.progress)

    # 2024年12月12日11:50:37
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
def end_edit_tracking(tracking_id):
    tracking = EditTimeTracking.query.get_or_404(tracking_id)
    tracking.end_time = datetime.now()
    tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())

    db.session.commit()
    return jsonify({'message': 'Tracking ended successfully'}), 200



