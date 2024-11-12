# projectplan.py
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from models import db, ProjectStage, StageTask
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


# 创建项目阶段
@projectplan_bp.route('/stages', methods=['POST'])
def create_project_stage():
    data = request.get_json()
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
    db.session.commit()
    return jsonify({'message': '阶段创建成功'}), 201


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
    task = StageTask(
        stage_id=stage_id,
        name=data['name'],
        description=data.get('description', ''),
        due_date=datetime.strptime(data['dueDate'], '%Y-%m-%d'),
        status=data.get('status', 'pending'),
        progress=data.get('progress', 0)
    )
    db.session.add(task)
    db.session.commit()

    # 根据任务更新阶段进度
    update_stage_progress(stage_id)

    return jsonify({'message': '任务创建成功', 'id': task.id}), 201


# 更新任务
@projectplan_bp.route('/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    task = StageTask.query.get_or_404(task_id)
    data = request.get_json()

    task.name = data.get('name', task.name)
    task.description = data.get('description', task.description)
    task.due_date = datetime.strptime(data['dueDate'], '%Y-%m-%d') if 'dueDate' in data else task.due_date
    task.status = data.get('status', task.status)
    task.progress = data.get('progress', task.progress)

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

