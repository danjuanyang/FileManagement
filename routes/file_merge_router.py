# file_merge_router.py
import os
import time
import shutil
import tempfile
import uuid
from urllib.parse import quote
from flask import (
    Blueprint, jsonify, send_file, Response,
    stream_with_context, current_app, request,
    send_from_directory  # 添加了用于在需要时提供静态文件的功能
)
from flask_cors import CORS

from models import User, Project, ProjectFile  # type: ignore

from .file_merger import (
    generate_paged_preview_data,
    build_final_pdf,
    TEMP_PREVIEW_IMAGE_SUBDIR  # Import the constant
)

merge_bp = Blueprint('file_merge_refactored', __name__, url_prefix='/api/filles')
CORS(merge_bp)
# 合并会话的内存存储（考虑将 Redis/DB 用于生产）
merge_sessions = {}


# --- Helper 函数在应用程序上下文中调用函数 ---
def call_with_app_context(app, func, *args, **kwargs):
    """
在应用程序上下文中执行函数的帮助程序。
    这对于通过 response.call_on_close 调用的函数非常有用。
    """
    with app.app_context():
        func(*args, **kwargs)


# --- 会话管理助手 ---
def get_session_progress(session_id):
    return merge_sessions.get(session_id, {}).get('progress', 0)


def update_session_progress(session_id, progress, status_message=None, completed=False, error=None):
    if session_id in merge_sessions:
        merge_sessions[session_id]['progress'] = progress
        if status_message: merge_sessions[session_id]['status_message'] = status_message
        merge_sessions[session_id]['completed'] = completed
        if error: merge_sessions[session_id]['error'] = error
        if completed or error:
            merge_sessions[session_id]['status'] = 'error' if error else 'completed'
    else:
        # 如果 current_app 可能不可用，请使用直接 Logger（尽管此函数通常在上下文中调用）
        app = current_app._get_current_object() if current_app else None
        if app:
            app.logger.warning(f"尝试更新不存在的会话 ID 的进度 {session_id}.")
        else:
            print(f"警告：尝试更新不存在的会话 ID 的进度{session_id} (无应用程序上下文).")


def create_merge_session(custom_session_id=None):
    session_id = custom_session_id if custom_session_id else str(uuid.uuid4())
    merge_sessions[session_id] = {
        'progress': 0,
        'status_message': 'Initializing...',
        'status': 'running',  # '正在运行'， '已完成'， '错误'
        'completed': False,
        'error': None,
        'start_time': time.time(),
        'pdf_temp_dir': None,  # 对于 PDF 生成临时文件
        'image_temp_dir': None  # 用于预览图像临时文件
    }
    return session_id


def cleanup_session(session_id):
    """
    清理与合并会话关联的临时目录。
    此函数现在设计为在应用程序上下文中调用
    由 call_with_app_context 帮助程序。
    """
    # current_app应该在这里可用，因为call_with_app_context建立了它。
    app_logger = current_app.logger

    if session_id in merge_sessions:
        session_data = merge_sessions.pop(session_id)  # 删除和获取数据

        pdf_temp_dir_to_clean = session_data.get('pdf_temp_dir')
        if pdf_temp_dir_to_clean and os.path.exists(pdf_temp_dir_to_clean):
            try:
                shutil.rmtree(pdf_temp_dir_to_clean)
                app_logger.info(
                    f"临时 PDF 目录 {pdf_temp_dir_to_clean} 已清理会话{session_id}.")
            except Exception as e:
                app_logger.error(f"无法清理临时 PDF 目录 {pdf_temp_dir_to_clean}: {e}")

        image_temp_dir_to_clean = session_data.get('image_temp_dir')
        if image_temp_dir_to_clean and os.path.exists(image_temp_dir_to_clean):
            try:
                shutil.rmtree(image_temp_dir_to_clean)  # 这是特定于会话的 image 文件夹
                app_logger.info(
                    f"临时镜像目录 {image_temp_dir_to_clean} 已清理会话{session_id}.")
            except Exception as e:
                app_logger.error(f"清理临时镜像目录失败 {image_temp_dir_to_clean}: {e}")

        app_logger.info(f"Session {session_id} data cleaned up.")
    else:
        app_logger.warning(f"尝试清理不存在的会话 ID {session_id}.")


# --- Routes ---

@merge_bp.route('/generate-paged-preview', methods=['POST'])
def generate_paged_preview_route():
    """
    生成合并的 PDF，然后将其页面转换为图像以供预览。
    返回包含会话 ID 和图像 URL 列表的 JSON。
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的请求数据 (Invalid request data)'}), 400

    project_id_str = data.get('project_id')
    selected_file_ids = data.get('selected_files')  # List of file IDs
    cover_options = data.get('cover_options', {})
    toc_options = data.get('toc_options', {})

    if not project_id_str:
        return jsonify({'error': '缺少项目ID (Missing project_id)'}), 400

    try:
        project_id = int(project_id_str)
    except ValueError:
        return jsonify({'error': '无效的项目ID格式 (Invalid project ID format)'}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': '项目未找到 (Project not found)'}), 404

    if selected_file_ids is not None and not isinstance(selected_file_ids, list):
        return jsonify(
            {'error': 'selected_files 参数格式错误，应为列表 (Invalid selected_files format, should be a list)'}), 400

    merge_config = {'coverPage': cover_options, 'toc': toc_options}

    try:
        preview_session_id, pages_image_info, error_msg, image_temp_dir = generate_paged_preview_data(
            project_id=project.id,
            merge_config=merge_config,
            selected_file_ids=selected_file_ids
        )

        if error_msg:
            current_app.logger.error(f"Error generating paged preview for project {project.id}: {error_msg}")
            return jsonify({'error': f"生成分页预览失败 (Failed to generate paged preview): {error_msg}"}), 500

        if not preview_session_id or pages_image_info is None:
            return jsonify({'error': '生成分页预览时发生未知错误 (Unknown error during paged preview generation)'}), 500

        create_merge_session(custom_session_id=preview_session_id)
        if preview_session_id in merge_sessions:
            merge_sessions[preview_session_id]['image_temp_dir'] = image_temp_dir
            merge_sessions[preview_session_id]['status_message'] = '分页预览已生成 (Paged preview generated)'
            merge_sessions[preview_session_id]['progress'] = 100
            merge_sessions[preview_session_id]['completed'] = True

        return jsonify({
            'preview_session_id': preview_session_id,
            'pages': pages_image_info
        }), 200

    except Exception as e:
        current_app.logger.error(f"Unexpected error in generate_paged_preview_route: {str(e)}", exc_info=True)
        return jsonify({'error': f"服务器内部错误 (Internal server error): {str(e)}"}), 500


@merge_bp.route('/temp_preview_image/<session_id>/<image_filename>', methods=['GET'])
def serve_temp_preview_image(session_id, image_filename):
    """为给定会话提供临时预览图像."""
    main_temp_image_dir_abs = os.path.join(current_app.static_folder, TEMP_PREVIEW_IMAGE_SUBDIR)
    session_image_dir_abs = os.path.join(main_temp_image_dir_abs, session_id)

    if ".." in image_filename or image_filename.startswith("/"):
        return jsonify({'error': '无效的文件名 (Invalid filename)'}), 400

    try:
        return send_from_directory(session_image_dir_abs, image_filename)
    except FileNotFoundError:
        return jsonify({'error': '图片未找到 (Image not found)'}), 404
    except Exception as e:
        current_app.logger.error(f"Error serving temp image {session_id}/{image_filename}: {e}")
        return jsonify({'error': '无法提供图片 (Could not serve image)'}), 500


@merge_bp.route('/finalize-merge', methods=['POST'])
def finalize_merge_route():
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的请求数据 (Invalid request data)'}), 400

    project_id_str = data.get('project_id')
    preview_session_id = data.get('preview_session_id')
    selected_file_ids = data.get('selected_files')
    cover_options = data.get('cover_options', {})
    toc_options = data.get('toc_options', {})
    pages_to_delete_indices = data.get('pages_to_delete_indices', [])

    if not project_id_str or not preview_session_id:
        return jsonify({'error': '缺少项目ID或预览会话ID (Missing project_id or preview_session_id)'}), 400

    try:
        project_id = int(project_id_str)
    except ValueError:
        return jsonify({'error': '无效的项目ID格式 (Invalid project ID format)'}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({'error': '项目未找到 (Project not found)'}), 404

    if not isinstance(pages_to_delete_indices, list):
        return jsonify({'error': 'pages_to_delete_indices 参数格式错误 （pages_to_delete_indices格式无效）'}), 400

    if preview_session_id not in merge_sessions:
        current_app.logger.warning(
            f"Finalize merge called with unknown preview_session_id: {preview_session_id}. Creating a new session entry.")
        create_merge_session(custom_session_id=preview_session_id)

    session_id_for_finalize = preview_session_id
    update_session_progress(session_id_for_finalize, 5, "开始最终合并 (Starting final merge)...")

    merge_config = {'coverPage': cover_options, 'toc': toc_options}
    # 当 app 上下文处于活动状态时获取实际的 app 实例
    # 这将传递给 call_with_app_context 帮助程序
    actual_app = current_app._get_current_object()

    try:
        final_pdf_path, error_msg, pdf_temp_dir = build_final_pdf(
            project_id=project.id,
            merge_config=merge_config,
            selected_file_ids=selected_file_ids,
            pages_to_delete_indices=pages_to_delete_indices
        )

        if error_msg:
            current_app.logger.error(f"Error finalizing merge for project {project.id}: {error_msg}")
            update_session_progress(session_id_for_finalize, 100, error_msg, completed=True, error=error_msg)
            return jsonify({'error': f"最终合并PDF失败 (Failed to finalize PDF): {error_msg}"}), 500

        if not final_pdf_path:
            update_session_progress(session_id_for_finalize, 100, "最终合并PDF失败 (Failed to finalize PDF)",
                                    completed=True, error="Unknown error, final_pdf_path is None")
            return jsonify({'error': '最终合并PDF失败 (Failed to finalize PDF)'}), 500

        update_session_progress(session_id_for_finalize, 90, "准备发送最终文件 (Preparing to send final file)...")

        if session_id_for_finalize in merge_sessions:
            merge_sessions[session_id_for_finalize]['pdf_temp_dir'] = pdf_temp_dir
        else:
            current_app.logger.error(f"Session {session_id_for_finalize} vanished before storing pdf_temp_dir.")

        def generate_file_stream_final():
            try:
                with open(final_pdf_path, "rb") as f:
                    yield from f
            finally:
                pass  # 清理由 response.call_on_close 处理

        base_filename_final = f"{project.name}_final_merged.pdf"
        encoded_filename_final = quote(base_filename_final)

        response = Response(stream_with_context(generate_file_stream_final()), mimetype='application/pdf')
        response.headers["Content-Disposition"] = (
            f"attachment; filename=\"{base_filename_final.encode('latin-1', 'replace').decode('latin-1')}\"; "
            f"filename*=UTF-8''{encoded_filename_final}"
        )

        update_session_progress(session_id_for_finalize, 100, "最终合并成功 (Final merge successful)", completed=True)

        response.call_on_close(
            lambda: call_with_app_context(actual_app, cleanup_session, session_id_for_finalize)
        )

        return response

    except Exception as e:
        current_app.logger.error(f"finalize_merge_route 中出现意外错误: {str(e)}", exc_info=True)
        update_session_progress(session_id_for_finalize, 100, f"服务器内部错误 (Internal server error): {str(e)}",
                                completed=True, error=str(e))
        # 如果在设置 response.call_on_close 之前出现意外错误，也可以在此处调用 cleanup
        call_with_app_context(actual_app, cleanup_session, session_id_for_finalize)
        return jsonify(
            {'error': f"最终合并PDF时发生未预期的错误 (Unexpected error during final PDF merge): {str(e)}"}), 500


@merge_bp.route('/progress/<session_id>')
def merge_progress_sse(session_id):
    if session_id not in merge_sessions:
        def empty_stream():
            yield f"data: {{ \"progress\": 100, \"status_message\": \"会话未找到或已过期 (Session not found or expired).\", \"completed\": true, \"error\": \"会话无效 (Invalid session)\" }}\n\n"

        return Response(stream_with_context(empty_stream()), mimetype='text/event-stream')

    # 如果需要，获取用于在 SSE 流中进行日志记录的实际应用实例，
    # 但如果流的生存期很长，则此处的直接日志记录也可能会遇到上下文问题。
    # 对于 SSE，如果主应用程序将更新推送到 SSE 从中读取的队列，通常会更好。
    # 或 SSE 本身会定期检查由主应用程序更新的状态。
    # 但是，对于这种特定结构，我们假设 current_app 在直播开始时可用。
    # actual_app_for_sse = current_app._get_current_object（） # 如果从这里记录，则可以使用

    def generate_progress_stream():
        last_progress = -1
        last_status_message = ""
        last_error = None
        start_time = time.time()
        timeout_seconds = 300  # 如果没有活动，则 SSE 流超时 5 分钟

        # 如果可能，最好获取一次 app 对象，或者处理它的缺失。
        app_for_sse_logging = current_app._get_current_object() if current_app else None

        while True:
            session_data = merge_sessions.get(session_id)
            if not session_data:
                yield f"data: {{ \"progress\": 100, \"status_message\": \"会话已结束或未找到 (Session ended or not found).\", \"completed\": true, \"error\": \"会话已结束 (Session ended)\" }}\n\n"
                break

            if time.time() - start_time > timeout_seconds and session_data.get(
                    'status') == 'running' and session_data.get('progress', 0) < 100:
                if app_for_sse_logging:
                    app_for_sse_logging.logger.warning(f"SSE stream for session {session_id} timed out.")
                else:
                    print(f"警告：会话的 SSE 流 {session_id} 超时（无 Logger 的应用程序上下文）.")

                yield f"data: {{ \"progress\": {session_data.get('progress', 0)}, \"status_message\": \"操作超时 (Operation timed out).\", \"completed\": true, \"error\": \"超时 (Timeout)\" }}\n\n"
                # 如果 SSE 超时，它也应该触发该会话的清理。
                if app_for_sse_logging:
                    call_with_app_context(app_for_sse_logging, cleanup_session, session_id)
                else:  # 如果 app_for_sse_logging 为 None，则回退（理想情况下不应在请求中发生）
                    print(f"错误：无法清理会话 {session_id}由于缺少应用程序上下文而导致 SSE 超时.")
                break

            progress = session_data.get('progress', 0)
            status_message = session_data.get('status_message', '')
            current_error = session_data.get('error')
            completed = session_data.get('completed', False)

            if progress != last_progress or status_message != last_status_message or (
                    current_error and current_error != last_error):
                event_data = {
                    "progress": progress, "status_message": status_message, "completed": completed
                }
                if current_error: event_data["error"] = current_error

                # jsonify 需要一个 app context。如果此流运行时间较长，则上下文可能是一个问题。
                # 更安全的方法是手动构造 JSON 字符串或确保上下文。
                try:
                    json_data_string = jsonify(event_data).get_data(as_text=True)
                    yield f"data: {json_data_string}\n\n"
                except RuntimeError:  # 可能断章取义
                    if app_for_sse_logging:
                        app_for_sse_logging.logger.error(
                            "由于缺少应用程序上下文，jsonify 在 SSE 流中失败。可能需要手动构建 JSON.")
                    else:
                        print("错误：由于缺少应用程序上下文，SSE 流中的 jsonify 失败。")
                    # 回退到手动 JSON 构造或发送更简单的错误消息
                    yield f"data: {{ \"progress\": {progress}, \"status_message\": \"Error fetching details.\", \"completed\": {str(completed).lower()} }}\n\n"

                last_progress = progress
                last_status_message = status_message
                if current_error: last_error = current_error

            if completed:
                if not current_error and progress < 100:
                    final_event_data = {"progress": 100,
                                        "status_message": status_message or "处理完成 (Processing complete)",
                                        "completed": True}
                    try:
                        yield f"data: {jsonify(final_event_data).get_data(as_text=True)}\n\n"
                    except RuntimeError:
                        yield f"data: {{ \"progress\": 100, \"status_message\": \"Processing complete (error formatting details).\", \"completed\": true }}\n\n"
                break

            if current_error:
                break

            time.sleep(0.5)

    return Response(stream_with_context(generate_progress_stream()), mimetype='text/event-stream')
