# projectplan.py
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from models import db, Subproject, ProjectStage, StageTask, EditTimeTracking, ProjectFile
from auth import get_employee_id
from utils.activity_tracking import track_activity

projectplan_bp = Blueprint('projectplan', __name__)
CORS(projectplan_bp)
CORS(projectplan_bp, resources={r"/api/*": {"origins": "*"}})


# ------------------ 子项目端点------------------

# 获取项目的所有子项目
@projectplan_bp.route('/subprojects/<int:project_id>', methods=['GET'])
@track_activity
def get_project_subprojects(project_id):
    subprojects = Subproject.query.filter_by(project_id=project_id).all()
    return jsonify([{
        'id': subproject.id,
        'project_id': subproject.project_id,
        'name': subproject.name,
        'description': subproject.description,
        'startDate': subproject.start_date.isoformat(),
        'deadline': subproject.deadline.isoformat(),
        'progress': subproject.progress,
        'status': subproject.status,
        'stagesCount': len(subproject.stages) if hasattr(subproject, 'stages') else 0
    } for subproject in subprojects])


# 创建新的子项目
@projectplan_bp.route('/subprojects', methods=['POST'])
@track_activity
def create_subproject():
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)

    subproject = Subproject(
        name=data['name'],
        description=data.get('description', ''),
        project_id=data['projectId'],
        start_date=datetime.strptime(data['startDate'], '%Y-%m-%d') if 'startDate' in data else datetime.now(),
        deadline=datetime.strptime(data['deadline'], '%Y-%m-%d'),
        progress=data.get('progress', 0.0),
        status=data.get('status', 'pending')
    )

    db.session.add(subproject)

    if tracking_id:
        tracking = EditTimeTracking.query.get(tracking_id)
        if tracking:
            tracking.end_time = datetime.now()
            tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
            tracking.subproject_id = subproject.id

    db.session.commit()
    return jsonify({'message': '小项目创建成功', 'id': subproject.id}), 201


# 更新子项目
@projectplan_bp.route('/subprojects/<int:id>', methods=['PUT'])
@track_activity
def update_subproject(id):
    subproject = Subproject.query.get_or_404(id)
    data = request.get_json()

    subproject.name = data.get('name', subproject.name)
    subproject.description = data.get('description', subproject.description)
    if 'startDate' in data:
        subproject.start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
    if 'deadline' in data:
        subproject.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
    subproject.progress = data.get('progress', subproject.progress)
    subproject.status = data.get('status', subproject.status)

    db.session.commit()
    return jsonify({'message': '子项目更新成功'}), 200


# 删除子项目
@projectplan_bp.route('/subprojects/<int:id>', methods=['DELETE'])
@track_activity
def delete_subproject(id):
    subproject = Subproject.query.get_or_404(id)
    db.session.delete(subproject)
    db.session.commit()
    return jsonify({'message': '子项目删除成功'}), 200


# ------------------ 更新的阶段终端节点 ------------------

# 获取子项目的阶段
@projectplan_bp.route('/stages/subproject/<int:subproject_id>', methods=['GET'])
@track_activity
def get_subproject_stages(subproject_id):
    stages = ProjectStage.query.filter_by(subproject_id=subproject_id).all()
    return jsonify([{
        'id': stage.id,
        'project_id': stage.project_id,
        'subproject_id': stage.subproject_id,
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
            'progress': task.progress,
            'files': [{
                'id': f.id is not None,
                'has_content': f.content is not None if hasattr(f, 'content') else False
            } for f in task.files]
        } for task in stage.tasks]
    } for stage in stages])


# 保留旧端点以实现向后兼容性
@projectplan_bp.route('/stages/<int:project_id>', methods=['GET'])
@track_activity
def get_project_stages(project_id):
    # 现在，这将返回给定项目的所有子项目中的所有阶段
    stages = ProjectStage.query.filter_by(project_id=project_id).all()
    return jsonify([{
        'id': stage.id,
        'project_id': stage.project_id,
        'subproject_id': stage.subproject_id,
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
                'id': f.id is not None,
                'has_content': f.content is not None if hasattr(f, 'content') else False
            } for f in task.files]
        } for task in stage.tasks]
    } for stage in stages])


# 创建新的阶段
@projectplan_bp.route('/stages', methods=['POST'])
@track_activity
def create_project_stage():
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)

    # 从子项目中获取project_id（如果未提供）
    project_id = data.get('projectId')
    subproject_id = data['subprojectId']

    if not project_id:
        subproject = Subproject.query.get(subproject_id)
        if subproject:
            project_id = subproject.project_id
        else:
            return jsonify({'error': '找不到小项目或项目ID不存在'}), 404

    try:
        stage = ProjectStage(
            name=data['name'],
            description=data['description'],
            start_date=datetime.strptime(data['startDate'], '%Y-%m-%d'),
            end_date=datetime.strptime(data['endDate'], '%Y-%m-%d'),
            progress=data['progress'],
            status=data['status'],
            project_id=project_id,
            subproject_id=subproject_id
        )

        db.session.add(stage)

        if tracking_id:
            tracking = EditTimeTracking.query.get(tracking_id)
            if tracking:
                tracking.end_time = datetime.now()
                tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
                tracking.stage_id = stage.id

        db.session.commit()

        # 更新子项目进度
        update_subproject_progress(subproject_id)

        return jsonify({'message': '阶段创建成功', 'id': stage.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ------------------ 文件终端节点 ------------------

# 获取子项目的文件
@projectplan_bp.route('/files/subproject/<int:subproject_id>', methods=['GET'])
@track_activity
def get_subproject_files(subproject_id):
    try:
        files = ProjectFile.query.filter_by(subproject_id=subproject_id).all()

        subproject = Subproject.query.get(subproject_id)
        project_name = ""
        if subproject and hasattr(subproject, 'project') and subproject.project:
            project_name = subproject.project.name

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

            'projectName': file.project.name,
            'project_id': file.project_id,
            'project_name': file.project.name if hasattr(file, 'project') and file.project else None,
            'task_id': file.task_id,
            'subproject_id': file.subproject_id,
            'subprojectName': file.subproject.name,
            'stageName': file.stage.name,
            'taskName': file.task.name,
        } for file in files])

    except Exception as e:
        print(f"获取小项目文件时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 更新现有项目文件端点以包含子项目信息
@projectplan_bp.route('/files/project/<int:project_id>', methods=['GET'])
@track_activity
def get_project_files(project_id):
    try:
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

            'subproject_name': file.subproject.name if hasattr(file, 'subproject') and file.subproject else "未知子项目",

            'projectName': file.project.name,
            'project_id': file.project_id,
            'project_name': file.project.name if hasattr(file, 'project') and file.project else None,
            'task_id': file.task_id,
            'subproject_id': file.subproject_id,
            'subprojectName': file.subproject.name,
            'stageName': file.stage.name,
            'taskName': file.task.name,
        } for file in files])

    except Exception as e:
        print(f"获取项目文件时出错: {str(e)}")
        return jsonify({'error': str(e)}), 500


# 更新 Get all files 端点
@projectplan_bp.route('/files/all', methods=['GET'])
@track_activity
def get_all_files():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        project_id = request.args.get('project_id', type=int)
        subproject_id = request.args.get('subproject_id', type=int)
        search = request.args.get('search', '')
        public_filter = request.args.get('public')

        query = ProjectFile.query

        if project_id:
            query = query.filter(ProjectFile.project_id == project_id)

        if subproject_id:
            query = query.filter(ProjectFile.subproject_id == subproject_id)

        if search:
            query = query.filter(ProjectFile.original_name.ilike(f'%{search}%'))

        if public_filter:
            is_public = public_filter.lower() == 'public'
            query = query.filter(ProjectFile.is_public == is_public)

        total = query.count()
        files = query.order_by(ProjectFile.upload_date.desc()).paginate(page=page, per_page=per_page).items

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
                'subproject_id': file.subproject_id,
                'project_id': file.project_id,
                'project_name': file.project.name if hasattr(file, 'project') and file.project else "未知项目",
                'subproject_name': file.subproject.name if hasattr(file, 'subproject') and file.subproject else "未知小项目"
            } for file in files],
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        }

        return jsonify(result)

    except Exception as e:
        print(f"获取全部文件时出错： {str(e)}")
        return jsonify({'error': str(e), 'files': [], 'total': 0}), 500


# 创建任务
@projectplan_bp.route('/tasks', methods=['POST'])
@track_activity
def create_task():
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)

    try:
        task = StageTask(
            stage_id=data['stageId'],
            name=data['name'],
            description=data.get('description', ''),
            due_date=datetime.strptime(data['dueDate'], '%Y-%m-%d'),
            status=data.get('status', 'pending'),
            progress=data.get('progress', 0)
        )

        db.session.add(task)
        db.session.flush()  # Flush 获取任务 ID 而不提交

        # 如果提供了跟踪 ID，则更新跟踪
        if tracking_id:
            tracking = EditTimeTracking.query.get(tracking_id)
            if tracking:
                tracking.end_time = datetime.now()
                tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
                tracking.task_id = task.id
                tracking.edit_type = 'task'

        db.session.commit()

        # 创建任务后更新阶段进度
        update_stage_progress(task.stage_id)

        return jsonify({
            'message': '任务创建成功',
            'id': task.id,
            'tracking_duration': tracking.duration if tracking_id and tracking else None
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 更新任务
@projectplan_bp.route('/tasks/<int:id>', methods=['PUT'])
@track_activity
def update_task(id):
    task = StageTask.query.get_or_404(id)
    data = request.get_json()

    if 'name' in data:
        task.name = data['name']
    if 'description' in data:
        task.description = data['description']
    if 'dueDate' in data:
        task.due_date = datetime.strptime(data['dueDate'], '%Y-%m-%d')
    if 'status' in data:
        task.status = data['status']
    if 'progress' in data:
        task.progress = data['progress']

    db.session.commit()

    # 更新阶段进度
    update_stage_progress(task.stage_id)

    return jsonify({'message': '任务更新成功'}), 200


# 删除任务
@projectplan_bp.route('/tasks/<int:id>', methods=['DELETE'])
@track_activity
def delete_task(id):
    task = StageTask.query.get_or_404(id)
    stage_id = task.stage_id

    db.session.delete(task)
    db.session.commit()

    # 删除任务后更新阶段进度
    update_stage_progress(stage_id)

    return jsonify({'message': '任务删除成功'}), 200


# ------------------ 跟踪终端节点 ------------------

# 更新编辑跟踪起始端点
# @projectplan_bp.route('/tracking/start', methods=['POST'])
# @track_activity
# def start_edit_tracking():
#     data = request.get_json()
#     user_id = get_employee_id()
#
#     tracking = EditTimeTracking(
#         project_id=data['projectId'],
#         subproject_id=data.get('subprojectId'),
#         user_id=user_id,
#         edit_type=data['editType'],
#         start_time=datetime.now(),
#         end_time=datetime.now(),
#         duration=0,
#         stage_id=data.get('stageId'),
#         task_id=data.get('taskId')
#     )
#
#     db.session.add(tracking)
#     db.session.commit()
#
#     return jsonify({'id': tracking.id}), 201

# 2025年3月17日16:38:08
@projectplan_bp.route('/tracking/start', methods=['POST'])
@track_activity
def start_edit_tracking():
    data = request.get_json()

    try:
        user_id = get_employee_id()
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401

        tracking = EditTimeTracking(
            project_id=data.get('projectId'),
            subproject_id=data.get('subprojectId'),
            user_id=user_id,
            edit_type=data.get('editType', 'task'),  # 如果未指定，则默认为 task
            start_time=datetime.now(),
            end_time=datetime.now(),  # 稍后将在跟踪结束时更新
            duration=0,  # 将在跟踪结束时计算
            stage_id=data.get('stageId'),
            task_id=data.get('taskId')
        )

        db.session.add(tracking)
        db.session.commit()

        return jsonify({'id': tracking.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# 更新编辑跟踪结束端点
@projectplan_bp.route('/tracking/end', methods=['POST'])
@track_activity
def end_edit_tracking():
    data = request.get_json()

    try:
        tracking_id = data.get('trackingId')
        if not tracking_id:
            return jsonify({'error': '缺少追踪ID'}), 400

        tracking = EditTimeTracking.query.get_or_404(tracking_id)

        # 更新结束时间并计算持续时间
        tracking.end_time = datetime.now()
        tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())

        # 更新相关 ID（如果提供）
        if 'projectId' in data and data['projectId']:
            tracking.project_id = data['projectId']
        if 'subprojectId' in data and data['subprojectId']:
            tracking.subproject_id = data['subprojectId']
        if 'stageId' in data and data['stageId']:
            tracking.stage_id = data['stageId']
        if 'taskId' in data and data['taskId']:
            tracking.task_id = data['taskId']

        db.session.commit()

        return jsonify({
            'id': tracking.id,
            'duration': tracking.duration,
            'message': '追踪结束时间更新成功'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ------------------ 导出端点------------------

# 更新导出项目计划端点以包含子项目
@projectplan_bp.route('/projects/<int:project_id>/export', methods=['GET'])
@track_activity
def export_project_plan(project_id):
    subprojects = Subproject.query.filter_by(project_id=project_id).all()

    result = []
    for subproject in subprojects:
        stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()
        subproject_data = {
            'id': subproject.id,
            'name': subproject.name,
            'description': subproject.description,
            'startDate': subproject.start_date.isoformat(),
            'deadline': subproject.deadline.isoformat(),
            'progress': subproject.progress,
            'status': subproject.status,
            'subproject':[{
                'id': subproject.id,
                'name': subproject.name,
                'description': subproject.description,
                'startDate': subproject.start_date.isoformat(),
                'deadline': subproject.deadline.isoformat(),
                'progress': subproject.progress,
                'status': subproject.status,

                'stages': [{
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
                } for stage in subproject.stages]
            }for subproject in subprojects],

        }
        result.append(subproject_data)

    return jsonify(result)


# ------------------ 帮助程序函数------------------

# 更新阶段进度
def update_stage_progress(stage_id):
    stage = ProjectStage.query.get(stage_id)
    if not stage or not stage.tasks:
        return

    total_progress = sum(task.progress for task in stage.tasks)
    stage.progress = total_progress // len(stage.tasks)

    if all(task.status == 'completed' for task in stage.tasks):
        stage.status = 'completed'
    elif any(task.status == 'in_progress' for task in stage.tasks):
        stage.status = 'in_progress'

    db.session.commit()

    # 更新子项目进度
    update_subproject_progress(stage.subproject_id)


# 更新阶段数据
@projectplan_bp.route('/stages/<int:id>', methods=['PUT'])
@track_activity
def update_stage(id):
    stage = ProjectStage.query.get_or_404(id)
    data = request.get_json()

    if 'name' in data:
        stage.name = data['name']
    if 'description' in data:
        stage.description = data['description']
    if 'startDate' in data:
        stage.start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
    if 'endDate' in data:
        stage.end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
    if 'progress' in data:
        stage.progress = data['progress']
    if 'status' in data:
        stage.status = data['status']

    db.session.commit()

    # 如果状态变为完成，可能需要更新子项目状态
    if stage.status == 'completed':
        update_subproject_progress(stage.subproject_id)

    return jsonify({'message': '阶段更新成功'}), 200


# 新功能，可根据阶段更新子项目进度
def update_subproject_progress(subproject_id):
    subproject = Subproject.query.get(subproject_id)
    if not subproject or not subproject.stages:
        return

    total_progress = sum(stage.progress for stage in subproject.stages)
    subproject.progress = total_progress / len(subproject.stages)

    if all(stage.status == 'completed' for stage in subproject.stages):
        subproject.status = 'completed'
    elif any(stage.status == 'in_progress' for stage in subproject.stages):
        subproject.status = 'in_progress'

    db.session.commit()
