# projectplan.py
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_cors import CORS
from models import db, Subproject, ProjectStage, StageTask, EditTimeTracking, ProjectFile, Project, User
from auth import get_employee_id
from routes.employees import token_required
from utils.activity_tracking import track_activity

projectplan_bp = Blueprint('projectplan', __name__)
CORS(projectplan_bp)
CORS(projectplan_bp, resources={r"/api/*": {"origins": "*"}})


# ------------------ 子项目端点------------------

# 获取项目的所有子项目
@projectplan_bp.route('/subprojects/<int:project_id>', methods=['GET'])
@track_activity
@token_required
def get_project_subprojects(current_user, project_id):
    # 检查项目是否存在
    project = Project.query.get_or_404(project_id)

    # 权限检查
    if current_user.role in [0, 1]:  # 管理员或经理可以看所有
        subprojects = Subproject.query.filter_by(project_id=project_id).all()
    elif current_user.role == 2:  # 组长只能看自己的项目
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限查看此项目的子项目'}), 403
        subprojects = Subproject.query.filter_by(project_id=project_id).all()
    else:  # 组员只能看分配给自己的
        subprojects = Subproject.query.filter_by(
            project_id=project_id,
            employee_id=current_user.id
        ).all()

    return jsonify([{
        'id': subproject.id,
        'project_id': subproject.project_id,
        'name': subproject.name,
        'description': subproject.description,
        'startDate': subproject.start_date.isoformat(),
        'deadline': subproject.deadline.isoformat(),
        'progress': subproject.progress,
        'status': subproject.status,
        'employee_id': subproject.employee_id,
        'stagesCount': len(subproject.stages) if hasattr(subproject, 'stages') else 0
    } for subproject in subprojects])


# 创建新的子项目
# 加权限
@projectplan_bp.route('/subprojects', methods=['POST'])
@track_activity
@token_required
def create_subproject(current_user):
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)
    project_id = data['projectId']

    # 检查此用户是否已分配给项目
    project = Project.query.get_or_404(project_id)

    # 只有管理员、经理或分配的团队负责人才能创建子项目
    if current_user.role > 2 or (current_user.role == 2 and project.employee_id != current_user.id):
        return jsonify({'error': '权限不足'}), 403

    # 创建子项目
    subproject = Subproject(
        name=data['name'],
        description=data.get('description', ''),
        project_id=project_id,
        # 如果团队领导创建了它，他们可以预先分配它
        employee_id=data.get('employee_id'),
        start_date=datetime.strptime(data['startDate'], '%Y-%m-%d') if 'startDate' in data else datetime.now(),
        deadline=datetime.strptime(data['deadline'], '%Y-%m-%d'),
        progress=data.get('progress', 0.0),
        status=data.get('status', 'pending')
    )

    db.session.add(subproject)

    # 将父项目状态更新为 “in_progress”
    if project:
        project.status = "in_progress"

    if tracking_id:
        tracking = EditTimeTracking.query.get(tracking_id)
        if tracking:
            tracking.end_time = datetime.now()
            tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
            tracking.subproject_id = subproject.id

    db.session.commit()
    return jsonify({'message': '子项目创建成功', 'id': subproject.id}), 201


# 2025年3月27日10:39:55
# 加权限的更新子项目
@projectplan_bp.route('/subprojects/<int:id>', methods=['PUT'])
@track_activity
@token_required
def update_subproject(current_user, id):
    try:
        subproject = Subproject.query.get_or_404(id)

        data = request.get_json()
        # 添加具有验证的字段
        subproject.name = data.get('name', subproject.name)
        subproject.description = data.get('description', subproject.description)
        # 使用验证更新字段
        if 'name' in data:
            subproject.name = data['name']
        if 'startDate' in data:
            subproject.start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
        if 'deadline' in data:
            subproject.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
        if 'employee_id' in data:
            subproject.employee_id = data['employee_id']
        subproject.progress = data.get('progress', subproject.progress)
        subproject.status = data.get('status', subproject.status)

        db.session.commit()
        return jsonify({'message': '子项目更新成功'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


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
@token_required
def get_subproject_stages(current_user, subproject_id):
    # 获取子项目信息
    subproject = Subproject.query.get_or_404(subproject_id)

    # 权限检查 - 组员只能查看分配给自己的子项目
    if current_user.role == 3:  # 组员
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限查看此子项目的阶段'}), 403
    # 组长只能查看自己项目下的子项目
    elif current_user.role == 2:  # 组长
        project = Project.query.get(subproject.project_id)
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限查看此项目的子项目阶段'}), 403

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
@token_required
def get_project_stages(current_user, project_id):
    # 权限检查 - 管理员可以查看所有项目的阶段
    if current_user.role not in [0, 1]:  # 不是管理员或经理
        # 组长只能查看自己的项目
        if current_user.role == 2:  # 组长
            project = Project.query.get_or_404(project_id)
            if project.employee_id != current_user.id:
                return jsonify({'error': '您没有权限查看此项目的阶段'}), 403

        # 组员只能查看分配给自己的子项目
        elif current_user.role == 3:  # 组员
            # 获取项目下所有子项目
            subprojects = Subproject.query.filter_by(project_id=project_id).all()
            # 检查是否有分配给该组员的子项目
            if not any(sp.employee_id == current_user.id for sp in subprojects):
                return jsonify({'error': '您没有权限查看此项目的阶段'}), 403

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


# 加权限的创建阶段
# @projectplan_bp.route('/stages', methods=['POST'])
# @track_activity
# @token_required
# def create_project_stage(current_user):
#     data = request.get_json()
#     tracking_id = data.pop('trackingId', None)
#     subproject_id = data['subprojectId']
#
#     # 验证访问权限
#     subproject = Subproject.query.get_or_404(subproject_id)
#
#     # 不同角色的权限检查
#     if current_user.role > 2:  # 组员
#         # 组员只能为分配给自己的子项目创建阶段
#         if subproject.employee_id != current_user.id:
#             return jsonify({'error': '您没有权限为此子项目创建阶段'}), 403
#     elif current_user.role == 2:  # 组长
#         # 组长只能为自己负责的项目下的子项目创建阶段
#         project = Project.query.get(subproject.project_id)
#         if project.employee_id != current_user.id:
#             return jsonify({'error': '您没有权限为此项目的子项目创建阶段'}), 403
#
#     # 从子项目中获取project_id（如果未提供）
#     project_id = data.get('projectId')
#
#     if not project_id:
#         if subproject:
#             project_id = subproject.project_id
#         else:
#             return jsonify({'error': '找不到子项目或项目ID不存在'}), 404
#
#     try:
#         stage = ProjectStage(
#             name=data['name'],
#             description=data['description'],
#             start_date=datetime.strptime(data['startDate'], '%Y-%m-%d'),
#             end_date=datetime.strptime(data['endDate'], '%Y-%m-%d'),
#             progress=data['progress'],
#             status=data['status'],
#             project_id=project_id,
#             subproject_id=subproject_id
#         )
#
#         db.session.add(stage)
#
#         if tracking_id:
#             tracking = EditTimeTracking.query.get(tracking_id)
#             if tracking:
#                 tracking.end_time = datetime.now()
#                 tracking.duration = int((tracking.end_time - tracking.start_time).total_seconds())
#                 tracking.stage_id = stage.id
#
#         db.session.commit()
#
#         # 更新子项目进度
#         update_subproject_progress(subproject_id)
#
#         return jsonify({'message': '阶段创建成功', 'id': stage.id}), 201
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

# 修改创建阶段端点
@projectplan_bp.route('/stages', methods=['POST'])
@track_activity
@token_required
def create_project_stage(current_user):
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)
    subproject_id = data['subprojectId']

    # 验证访问权限
    subproject = Subproject.query.get_or_404(subproject_id)

    # 不同角色的权限检查
    if current_user.role > 2:  # 组员
        # 组员只能为分配给自己的子项目创建阶段
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限为此子项目创建阶段'}), 403
    elif current_user.role == 2:  # 组长
        # 组长只能为自己负责的项目下的子项目创建阶段
        project = Project.query.get(subproject.project_id)
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限为此项目的子项目创建阶段'}), 403

    # 从子项目中获取project_id（如果未提供）
    project_id = data.get('projectId')

    if not project_id:
        if subproject:
            project_id = subproject.project_id
        else:
            return jsonify({'error': '找不到子项目或项目ID不存在'}), 404

    try:
        # 重要：无论子项目当前状态如何，添加新阶段时都将其更新为"in_progress"
        if subproject.status == 'completed':
            subproject.status = 'in_progress'
            db.session.flush()  # 将更改刷新到数据库，但不提交

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
@token_required
def get_subproject_files(current_user, subproject_id):
    try:
        # 获取子项目信息
        subproject = Subproject.query.get_or_404(subproject_id)

        # 权限检查
        if current_user.role > 2:  # 组员
            # 组员只能查看分配给自己的子项目的文件
            if subproject.employee_id != current_user.id:
                return jsonify({'error': '您没有权限查看此子项目的文件'}), 403
        elif current_user.role == 2:  # 组长
            # 组长只能查看自己负责的项目下的子项目文件
            project = Project.query.get(subproject.project_id)
            if project.employee_id != current_user.id:
                return jsonify({'error': '您没有权限查看此子项目的文件'}), 403

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
        print(f"获取子项目文件时出错: {str(e)}")
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

            'subproject_name': file.subproject.name if hasattr(file,
                                                               'subproject') and file.subproject else "未知子项目",

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
                'subproject_name': file.subproject.name if hasattr(file, 'subproject') and file.subproject else "未知子项目"
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
@token_required
def create_task(current_user):
    data = request.get_json()
    tracking_id = data.pop('trackingId', None)
    stage_id = data['stageId']

    # 获取阶段信息用于权限检查
    stage = ProjectStage.query.get_or_404(stage_id)
    if not stage:
        return jsonify({'error': '未找到指定的阶段'}), 404

    # 获取子项目和项目信息
    subproject = Subproject.query.get(stage.subproject_id)
    if not subproject:
        return jsonify({'error': '未找到关联的子项目'}), 404

    project = Project.query.get(stage.project_id)
    if not project:
        return jsonify({'error': '未找到关联的项目'}), 404

    # 权限检查
    if current_user.role > 2:  # 组员
        # 组员只能为分配给自己的子项目创建任务
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限为此阶段创建任务'}), 403
    elif current_user.role == 2:  # 组长
        # 组长只能为自己负责的项目下的阶段创建任务
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限为此阶段创建任务'}), 403

    try:
        task = StageTask(
            stage_id=stage_id,
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
@token_required
def update_task(current_user, id):
    task = StageTask.query.get_or_404(id)

    # 获取任务所属的阶段、子项目和项目
    stage = ProjectStage.query.get(task.stage_id)
    if not stage:
        return jsonify({'error': '未找到任务所属的阶段'}), 404

    subproject = Subproject.query.get(stage.subproject_id)
    if not subproject:
        return jsonify({'error': '未找到关联的子项目'}), 404

    project = Project.query.get(stage.project_id)
    if not project:
        return jsonify({'error': '未找到关联的项目'}), 404

    # 权限检查
    if current_user.role > 2:  # 组员
        # 组员只能更新分配给自己的子项目的任务
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限更新此任务'}), 403
    elif current_user.role == 2:  # 组长
        # 组长只能更新自己负责的项目下的任务
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限更新此任务'}), 403

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
@token_required
def delete_task(current_user, id):
    task = StageTask.query.get_or_404(id)
    stage_id = task.stage_id

    # Get task's stage, subproject, and project
    stage = ProjectStage.query.get(task.stage_id)
    if not stage:
        return jsonify({'error': '未找到任务所属的阶段'}), 404

    subproject = Subproject.query.get(stage.subproject_id)
    if not subproject:
        return jsonify({'error': '未找到关联的子项目'}), 404

    project = Project.query.get(stage.project_id)
    if not project:
        return jsonify({'error': '未找到关联的项目'}), 404

    # 权限检查
    if current_user.role > 2:  # Team member
        # Team members can only delete tasks from subprojects assigned to them
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限删除此任务'}), 403
        elif task.status == 'completed':
            return jsonify({'error': '您没有权限删除已完成的任务'}), 403
        else:
            # Team member has permission to delete the task
            db.session.delete(task)
            db.session.commit()

            # Update stage progress after task deletion
            update_stage_progress(stage_id)

            return jsonify({'message': '任务删除成功'}), 200
    elif current_user.role == 2:  # Team leader
        # 团队主管可以删除其项目中的任何任务
        db.session.delete(task)
        db.session.commit()

        # 删除任务后更新阶段进度
        update_stage_progress(stage_id)

        return jsonify({'message': '任务删除成功'}), 200
    else:  # 管理员或其他角色
        # 管理员可以删除任何任务
        db.session.delete(task)
        db.session.commit()

        # 删除任务后更新阶段进度
        update_stage_progress(stage_id)

        return jsonify({'message': '任务删除成功'}), 200


# ------------------ 跟踪终端节点 ------------------

# 更新编辑跟踪起始端点
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
# 正确的导出项目计划端点实现
@projectplan_bp.route('/projects/<int:project_id>/export', methods=['GET'])
@track_activity
def export_project_plan(project_id):
    # 检查项目是否存在
    project = Project.query.get_or_404(project_id)

    # 获取所有相关的子项目
    subprojects = Subproject.query.filter_by(project_id=project_id).all()

    # 构建结果
    result = []
    for subproject in subprojects:
        # 获取子项目的所有阶段
        stages = ProjectStage.query.filter_by(subproject_id=subproject.id).all()

        # 构建子项目数据
        subproject_data = {
            'id': subproject.id,
            'name': subproject.name,
            'description': subproject.description,
            'startDate': subproject.start_date.isoformat(),
            'deadline': subproject.deadline.isoformat(),
            'progress': subproject.progress,
            'status': subproject.status,
            'stages': []  # 将包含该子项目的所有阶段
        }

        # 添加每个阶段及其任务
        for stage in stages:
            stage_data = {
                'id': stage.id,
                'name': stage.name,
                'description': stage.description,
                'startDate': stage.start_date.isoformat(),
                'endDate': stage.end_date.isoformat(),
                'progress': stage.progress,
                'status': stage.status,
                'tasks': []  # 将包含该阶段的所有任务
            }

            # 添加该阶段的所有任务
            for task in stage.tasks:
                task_data = {
                    'id': task.id,
                    'name': task.name,
                    'description': task.description,
                    'dueDate': task.due_date.isoformat(),
                    'status': task.status,
                    'progress': task.progress
                }
                stage_data['tasks'].append(task_data)

            # 将阶段添加到子项目中
            subproject_data['stages'].append(stage_data)

        # 将子项目添加到结果中
        result.append(subproject_data)

    return jsonify(result)


# ------------------ 帮助程序函数------------------

# 更新阶段数据
@projectplan_bp.route('/stages/<int:id>', methods=['PUT'])
@track_activity
@token_required
def update_stage_progress(current_user, id):
    stage = ProjectStage.query.get_or_404(id)

    # 获取子项目和项目信息用于权限检查
    subproject = Subproject.query.get(stage.subproject_id)
    if not subproject:
        return jsonify({'error': '未找到关联的子项目'}), 404

    project = Project.query.get(stage.project_id)
    if not project:
        return jsonify({'error': '未找到关联的项目'}), 404

    # 权限检查
    if current_user.role > 2:  # 组员
        # 组员只能更新分配给自己的子项目的阶段
        if subproject.employee_id != current_user.id:
            return jsonify({'error': '您没有权限更新此阶段'}), 403
    elif current_user.role == 2:  # 组长
        # 组长只能更新自己负责的项目下的阶段
        if project.employee_id != current_user.id:
            return jsonify({'error': '您没有权限更新此阶段'}), 403

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
# def update_subproject_progress(subproject_id):
#     subproject = Subproject.query.get(subproject_id)
#     if not subproject or not subproject.stages:
#         return
#
#     total_progress = sum(stage.progress for stage in subproject.stages)
#     subproject.progress = total_progress / len(subproject.stages)
#
#     if all(stage.status == 'completed' for stage in subproject.stages):
#         subproject.status = 'completed'
#     elif any(stage.status == 'in_progress' for stage in subproject.stages):
#         subproject.status = 'in_progress'
#
#     # 更新父项目状态
#     project = Project.query.get(subproject.project_id)
#     if project and project.subprojects:
#         # 计算项目总进度
#         total_progress = sum(sp.progress for sp in project.subprojects)
#         project.progress = total_progress / len(project.subprojects)
#
#         # 更新项目状态
#         if all(sp.status == 'completed' for sp in project.subprojects):
#             project.status = 'completed'
#         elif any(sp.status == 'in_progress' for sp in project.subprojects) or any(
#                 sp.progress < 100 for sp in project.subprojects):
#             project.status = 'in_progress'
#
#     db.session.commit()

# 修改 update_subproject_progress 函数，不自动将状态设置为 completed
def update_subproject_progress(subproject_id):
    subproject = Subproject.query.get(subproject_id)
    if not subproject or not subproject.stages:
        return

    total_progress = sum(stage.progress for stage in subproject.stages)
    subproject.progress = total_progress / len(subproject.stages)

    # 只有当状态为 pending 且有进行中的阶段时，才将状态更新为 in_progress
    # 不再自动设置为 completed，让用户手动控制完成状态
    if subproject.status == 'pending' and any(stage.status == 'in_progress' for stage in subproject.stages):
        subproject.status = 'in_progress'

    # 更新父项目状态
    project = Project.query.get(subproject.project_id)
    if project and project.subprojects:
        # 计算项目总进度
        total_progress = sum(sp.progress for sp in project.subprojects)
        project.progress = total_progress / len(project.subprojects)

        # 更新项目状态
        if all(sp.status == 'completed' for sp in project.subprojects):
            project.status = 'completed'
        elif any(sp.status == 'in_progress' for sp in project.subprojects) or any(
                sp.progress < 100 for sp in project.subprojects):
            project.status = 'in_progress'

    db.session.commit()
# -------------------------------权限--------------------------------------

# 组长分配
@projectplan_bp.route('/subprojects/<int:id>/assign', methods=['PUT'])
@track_activity
@token_required
def assign_subproject(current_user, id):
    # 检查用户是否是团队领导
    if current_user.role != 2:  # Team Leader role
        return jsonify({'error': '权限不足'}), 403

    subproject = Subproject.query.get_or_404(id)

    # 检查团队领导是否负责父项目
    project = Project.query.get(subproject.project_id)
    if project.employee_id != current_user.id:
        return jsonify({'error': '您不是此项目的组长，无法分配子项目'}), 403

    data = request.get_json()

    if 'employee_id' not in data:
        return jsonify({'error': '缺少员工ID'}), 400

    # 验证员工存在且是团队成员
    employee = User.query.get(data['employee_id'])
    if not employee:
        return jsonify({'error': '员工不存在'}), 400
    if employee.role != 3:  # Team Member role
        return jsonify({'error': '只能将子项目分配给组员'}), 400

    # 更新子项目的员工ID
    subproject.employee_id = data['employee_id']

    db.session.commit()
    return jsonify({
        'message': '子项目分配成功',
        'subproject': {
            'id': subproject.id,
            'name': subproject.name,
            'employee_id': subproject.employee_id
        }
    }), 200


@projectplan_bp.route('/team-members', methods=['GET'])
@track_activity
@token_required
def get_team_members(current_user):
    # 只有超管，管理员和团队领导才能访问此内容
    if current_user.role not in [0, 1, 2]:
        return jsonify({'error': '权限不足'}), 403

    # 从请求参数中获取团队领导 ID
    leader_id = request.args.get('leader_id', type=int)

    # 如果是团队负责人，则仅返回分配给他们的成员
    if current_user.role == 2:
        # 如果提供了 leader_id 并且与当前用户匹配，则使用它
        if leader_id and leader_id == current_user.id:
            # 使用 team_leader_id 关系的直接查询
            team_members = User.query.filter_by(team_leader_id=leader_id, role=3).all()
        else:
            # If no leader_id or doesn't match, use current user's ID
            team_members = User.query.filter_by(team_leader_id=current_user.id, role=3).all()
    else:
        # 对于管理员和经理，如果提供了 leader_id，请按此进行筛选
        if leader_id:
            team_members = User.query.filter_by(team_leader_id=leader_id, role=3).all()
        else:
            # 否则返回所有团队成员
            team_members = User.query.filter_by(role=3).all()

    return jsonify({
        'team_members': [{
            'id': tm.id,
            'username': tm.username,
            'name': tm.name if hasattr(tm, 'name') else tm.username,
            'role': tm.role,
        } for tm in team_members]
    })


# 添加一个任务进度更新函数，与路由函数分开
def update_stage_progress(stage_id):
    """根据任务进度更新阶段进度"""
    stage = ProjectStage.query.get(stage_id)
    if not stage:
        return False

    tasks = StageTask.query.filter_by(stage_id=stage_id).all()

    # 如果没有任务，阶段进度设为0
    if not tasks:
        stage.progress = 0
        db.session.commit()
        return True

    # 计算平均进度
    total_progress = sum(task.progress for task in tasks)
    stage.progress = total_progress / len(tasks)

    # 更新阶段状态
    if all(task.status == 'completed' for task in tasks) and tasks:
        stage.status = 'completed'
    elif any(task.status == 'in_progress' for task in tasks):
        stage.status = 'in_progress'
    elif all(task.status == 'pending' for task in tasks):
        stage.status = 'pending'

    db.session.commit()

    # 更新子项目进度
    update_subproject_progress(stage.subproject_id)

    return True