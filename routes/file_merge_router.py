# file_merge_routes.py
import os
import time
from flask import Blueprint, jsonify, send_file, Response, stream_with_context, current_app, request
from flask_cors import CORS

from auth import get_employee_id
from routes.file_merger import merge_project_files_to_pdf
from utils.activity_tracking import track_activity
from models import User, Project

# 创建蓝图
merge_bp = Blueprint('file_merge', __name__)
CORS(merge_bp)

# 全局变量，用于存储合并进度
merge_progress = {}


@merge_bp.route('/project/<int:project_id>/merge-pdf/progress')
def merge_progress_stream(project_id):
    """提供合并进度的SSE流"""

    def generate():
        # 初始进度设为5%，表示开始处理
        yield f"data: {{'progress': 5}}\n\n"

        counter = 0
        while True:
            progress = merge_progress.get(project_id, 5)

            # 如果进度未更新，微增一些进度值让用户看到进展
            if counter % 3 == 0 and progress < 90:
                progress += 1
                merge_progress[project_id] = progress

            yield f"data: {{'progress': {progress}}}\n\n"

            if progress >= 100:
                break

            counter += 1
            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )


@merge_bp.route('/project/<int:project_id>/merge-pdf', methods=['POST'])
@track_activity
def merge_project_pdf(project_id):
    """将项目文件合并为PDF"""
    try:
        # 获取当前用户信息
        employee_id = get_employee_id()
        user = User.query.get(employee_id)
        if not user:
            return jsonify({'error': '未找到用户'}), 404

        # 验证项目存在
        project = Project.query.get_or_404(project_id)
        if not project:
            return jsonify({'error': '项目不存在'}), 404

        # 初始化进度
        merge_progress[project_id] = 10

        # 执行合并操作
        current_app.logger.info(f"开始合并项目 {project.name} 的PDF文件")

        output_path, error = merge_project_files_to_pdf(project_id)

        # 更新进度到95%，表示合并完成，准备下载
        merge_progress[project_id] = 95

        # 处理错误
        if error:
            current_app.logger.error(f"PDF合并失败: {error}")
            return jsonify({'error': error}), 400

        if not output_path or not os.path.exists(output_path):
            current_app.logger.error("合并失败：无法生成PDF文件")
            return jsonify({'error': '合并失败：无法生成PDF文件'}), 500

        # 更新进度为100%，表示所有操作完成
        merge_progress[project_id] = 100

        current_app.logger.info(f"项目 {project.name} 的PDF文件合并成功")

        # 返回合并后的文件
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=f"{project.name}_merged.pdf",
            mimetype='application/pdf'
        )

        # 在响应结束后清理临时文件
        @response.call_on_close
        def cleanup():
            try:
                if output_path and os.path.exists(output_path):
                    os.unlink(output_path)
                    current_app.logger.info(f"临时文件 {output_path} 已清理")
            except Exception as e:
                current_app.logger.error(f"清理临时文件失败: {str(e)}")

        return response

    except Exception as e:
        current_app.logger.error(f"PDF合并失败: {str(e)}")
        return jsonify({'error': f"发生错误: {str(e)}"}), 500
    finally:
        # 无论成功还是失败，都清理进度记录
        if project_id in merge_progress:
            del merge_progress[project_id]