from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import CORS
from models import db, ProjectStage
from auth import get_employee_id

projectplan_bp = Blueprint('projectplan', __name__)
CORS(projectplan_bp)  # 为此蓝图启用 CORS
CORS(projectplan_bp, resources={r"/api/*": {"origins": "*"}})  # 根据需要调整路径


# 获取项目阶段
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
        'status': stage.status
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