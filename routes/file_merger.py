# file_merger.py
import os
import re
import shutil
import tempfile
import io
import uuid

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from reportlab.pdfgen import canvas as reportlab_canvas  # 为避免冲突而重命名
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

from flask import current_app,url_for
from pdf2image import convert_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError
)

from models import Project, ProjectFile, ProjectStage, StageTask, Subproject

# --- Font Setup ---
FONT_NAME = 'SimSun'
# 临时预览图片相对于 static 文件夹的路径
TEMP_PREVIEW_IMAGE_SUBDIR = 'temp_preview_images'


def setup_fonts():
    """设置 ReportLab 的 SimSun 字体."""
    try:
        # 尝试查找相对于应用程序根目录的字体
        font_path_app_root = os.path.join(current_app.root_path, 'fonts', 'simsun.ttf')
        # 尝试查找相对于脚本目录结构的字体
        font_path_script_relative = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts',
                                                 'simsun.ttf')
        # 尝试在系统位置查找字体（Windows 示例）
        font_path_system = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts',
                                        'simsun.ttc')  # .ttc通常包含 Simsun

        font_path = None
        if os.path.exists(font_path_app_root):
            font_path = font_path_app_root
        elif os.path.exists(font_path_script_relative):
            font_path = font_path_script_relative
        elif os.path.exists(font_path_system):
            font_path = font_path_system  # 如果找到，请使用系统字体
        else:
            current_app.logger.error(
                f"在选中的位置找不到字体 simsun.ttf/.ttc: {font_path_app_root}, {font_path_script_relative}, {font_path_system}")
            return False

        if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            current_app.logger.info(f"注册字体： {FONT_NAME} from {font_path}")
            pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))  # 使用找到的路径
            registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME, italic=FONT_NAME, boldItalic=FONT_NAME)
        return True
    except Exception as e:
        current_app.logger.error(f"字体设置失败：{str(e)}", exc_info=True)
        return False


# ---PDF 生成实用程序 ---

def create_dynamic_title_page(title_text, output_path, subtitle_text=None, font_size=24):
    """创建具有动态主标题和可选副标题的标题页。"""
    if not setup_fonts():
        current_app.logger.warning("创建标题页期间字体设置失败。可能会使用默认字体.")

    c = reportlab_canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    default_font = "Helvetica"  # 回退字体

    # 确定要使用的字体
    font_to_use = FONT_NAME if FONT_NAME in pdfmetrics.getRegisteredFontNames() else default_font

    try:
        c.setFont(font_to_use, font_size)
        title_width = c.stringWidth(title_text, font_to_use, font_size)
        x_title = (width - title_width) / 2
        y_title = height / 2 + (font_size if subtitle_text else 0)
        c.drawString(x_title, y_title, title_text)

        if subtitle_text:
            subtitle_font_size = font_size - 6
            c.setFont(font_to_use, subtitle_font_size)
            subtitle_width = c.stringWidth(subtitle_text, font_to_use, subtitle_font_size)
            x_subtitle = (width - subtitle_width) / 2
            y_subtitle = y_title - font_size - 10  # 根据需要调整间距
            c.drawString(x_subtitle, y_subtitle, subtitle_text)

    except Exception as e:
        current_app.logger.error(f"在标题页上绘制文本时出错 (使用字体{font_to_use}): {e}", exc_info=True)
        # 如果主数据库失败，则尝试回退绘制
        if font_to_use != default_font:
            try:
                c.setFont(default_font, font_size)
                title_width = c.stringWidth(title_text, default_font, font_size)
                x_title = (width - title_width) / 2
                y_title = height / 2 + (font_size if subtitle_text else 0)
                c.drawString(x_title, y_title, title_text)
                if subtitle_text:
                    subtitle_font_size = font_size - 6
                    c.setFont(default_font, subtitle_font_size)
                    subtitle_width = c.stringWidth(subtitle_text, default_font, subtitle_font_size)
                    x_subtitle = (width - subtitle_width) / 2
                    y_subtitle = y_title - font_size - 10
                    c.drawString(x_subtitle, y_subtitle, subtitle_text)
                current_app.logger.warning("由于错误，退回到 Helvetica 的标题页.")
            except Exception as fallback_e:
                current_app.logger.error(f"回退绘制失败： {fallback_e}", exc_info=True)

    c.showPage()
    c.save()
    return output_path


def create_toc_pdf_page(toc_items, output_path, max_level=4):
    """创建目录 PDF 页面。"""
    if not setup_fonts():
        current_app.logger.warning("创建 TOC 页面期间字体设置失败。可能会使用默认字体.")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    default_font_name = "Helvetica" if FONT_NAME not in pdfmetrics.getRegisteredFontNames() else FONT_NAME
    current_app.logger.info(f"使用字体 '{default_font_name}' for TOC.")

    title_style = ParagraphStyle('TocTitle', parent=styles['h1'], fontName=default_font_name, fontSize=18, alignment=1,
                                 spaceAfter=20)
    story.append(Paragraph("目 录", title_style))

    level_styles = {
        1: ParagraphStyle('TocLevel1', parent=styles['Normal'], fontName=default_font_name, fontSize=14, leading=18,
                          spaceBefore=6, leftIndent=0 * cm),
        2: ParagraphStyle('TocLevel2', parent=styles['Normal'], fontName=default_font_name, fontSize=12, leading=16,
                          spaceBefore=4, leftIndent=1 * cm),
        3: ParagraphStyle('TocLevel3', parent=styles['Normal'], fontName=default_font_name, fontSize=10, leading=14,
                          spaceBefore=2, leftIndent=2 * cm),
        4: ParagraphStyle('TocLevel4', parent=styles['Normal'], fontName=default_font_name, fontSize=10, leading=14,
                          spaceBefore=2, leftIndent=3 * cm, textColor=colors.grey),
    }

    for item in toc_items:
        level = item.get('level', 1)
        text = item.get('text', 'Untitled')
        if level > max_level:
            continue
        # 确保文本为字符串
        safe_text = str(text) if text is not None else 'Untitled'
        try:
            para = Paragraph(safe_text, level_styles.get(level, level_styles[4]))
            story.append(para)
            if item.get('files'):
                for file_name_in_toc in item['files']:
                    safe_file_name = str(file_name_in_toc) if file_name_in_toc is not None else 'Untitled File'
                    file_para = Paragraph(safe_file_name, level_styles[4])  # 对任务下的文件使用级别 4 样式
                    story.append(file_para)
        except Exception as e:
            current_app.logger.error(f"为 TOC 项目创建段落时出错：{safe_text} (Level {level}). Error: {e}",
                                     exc_info=True)
            # （可选）附加一个占位符段落，指示错误
            error_para = Paragraph(f"[处理项目时出错： {safe_text[:30]}...]", styles['Normal'])
            story.append(error_para)

    try:
        doc.build(story)
    except Exception as e:
        current_app.logger.error(f"无法构建 TOC PDF 文档： {e}", exc_info=True)
        # 处理构建失败，可能返回 None 或 raise
        return None  # 表示失败
    return output_path


def add_page_numbers_to_pdf(input_pdf_path, output_pdf_path):
    """将页码（第 X 页，共第 Y 页）添加到 PDF 的每一页。"""
    if not setup_fonts():
        current_app.logger.warning("页码的字体设置失败。可能会使用默认字体.")

    reader = PdfReader(input_pdf_path)
    writer = PdfWriter()
    num_pages = len(reader.pages)

    default_font_name = "Helvetica" if FONT_NAME not in pdfmetrics.getRegisteredFontNames() else FONT_NAME
    current_app.logger.info(f"对页码使用字体'{default_font_name}' ")

    for i, page in enumerate(reader.pages):
        packet = io.BytesIO()
        # 使用 Reader 中的页面尺寸
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        can = reportlab_canvas.Canvas(packet, pagesize=(page_width, page_height))

        try:
            page_number_text = f"第 {i + 1} 页 / 共 {num_pages} 页"
            font_size = 9
            can.setFont(default_font_name, font_size)  # 使用确定的字体
            text_width = can.stringWidth(page_number_text, default_font_name, font_size)
            x_pos = (page_width - text_width) / 2
            y_pos = 1 * cm  # 位置从下开始
            can.drawString(x_pos, y_pos, page_number_text)
        except Exception as e:
            current_app.logger.error(f"在页面上绘制页码时出错 {i + 1}: {e}", exc_info=True)
            # 如果主数据库失败（例如字体问题），则尝试回退
            if default_font_name != "Helvetica":
                try:
                    can.setFont("Helvetica", font_size)
                    text_width = can.stringWidth(page_number_text, "Helvetica", font_size)
                    x_pos = (page_width - text_width) / 2
                    can.drawString(x_pos, y_pos, page_number_text)
                    current_app.logger.warning(f"回退到 Helvetica 获取 pag 上的页码e {i + 1}.")
                except Exception as fallback_e:
                    current_app.logger.error(f"页面的回退页码绘制失败 {i + 1}: {fallback_e}",
                                             exc_info=True)

        can.save()
        packet.seek(0)
        watermark_pdf = PdfReader(packet)
        # 合并前确保水印页面存在
        if watermark_pdf.pages:
            page.merge_page(watermark_pdf.pages[0])
        else:
            current_app.logger.warning(f"页面水印 PDF {i + 1} 为空.")
        writer.add_page(page)

    try:
        with open(output_pdf_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        current_app.logger.error(f"无法编写包含页码的最终 PDF: {e}", exc_info=True)
        return None  # Indicate failure
    return output_pdf_path


def extract_prefix_number(filename):
    """提取前缀编号以对文件进行排序."""
    if not filename: return float('inf')  # 处理 None 或空文件名
    match = re.match(r'^(\d+)', str(filename))  # 确保 filename 为 string
    return int(match.group(1)) if match else float('inf')


def sort_files_by_prefix(files):
    """按对象的original_name的前缀编号对 ProjectFile 对象进行排序."""
    return sorted(files, key=lambda x: extract_prefix_number(x.original_name))


def generate_toc_items_structure(project_id, selected_file_ids=None, max_level=4):
    """为目录生成结构化的项目列表."""
    project = Project.query.get(project_id)
    if not project:
        current_app.logger.warning(f"generate_toc_items_structure：ID 为 的项目 {project_id} 未找到.")
        return []

    toc_items = []
    current_app.logger.debug(
        f"为项目生成 TOC 结构: {project.name} (ID: {project.id}), 最高层级：{max_level}")

    if max_level >= 1:
        toc_items.append({'level': 1, 'text': project.name, 'id': f"project_{project.id}"})
        current_app.logger.debug(f"  Added Level 1: {project.name}")

    # 确保排序一致
    subprojects = Subproject.query.filter_by(project_id=project.id).order_by(Subproject.name).all()
    current_app.logger.debug(f"  Found {len(subprojects)} subprojects.")

    for subproject in subprojects:
        subproject_text = f"{project.name} - {subproject.name}"  # 示例格式
        if max_level >= 2:
            toc_items.append({'level': 2, 'text': subproject_text, 'id': f"subproject_{subproject.id}"})
            current_app.logger.debug(f"    Added Level 2: {subproject_text}")

        stages = ProjectStage.query.filter_by(subproject_id=subproject.id).order_by(ProjectStage.name).all()
        current_app.logger.debug(f"    Subproject '{subproject.name}' has {len(stages)} stages.")

        for stage in stages:
            stage_text = f"{subproject.name} - {stage.name}"  # 示例格式
            if max_level >= 3:
                toc_items.append({'level': 3, 'text': stage_text, 'id': f"stage_{stage.id}"})
                current_app.logger.debug(f"      Added Level 3: {stage_text}")

            tasks = StageTask.query.filter_by(stage_id=stage.id).order_by(StageTask.name).all()
            current_app.logger.debug(f"      Stage '{stage.name}' has {len(tasks)} tasks.")

            for task in tasks:
                task_text = f"{stage.name} - {task.name}"  # 示例格式
                # 查询与此任务关联的文件
                query = ProjectFile.query.filter_by(task_id=task.id,
                                                    project_id=project.id)  # 如果文件可以直接属于项目project_id请确保存在过滤器

                # 按所选文件 ID 过滤（如果提供）
                if selected_file_ids:
                    current_app.logger.debug(
                        f"        Filtering task '{task.name}' files by selected IDs: {selected_file_ids}")
                    query = query.filter(ProjectFile.id.in_(selected_file_ids))

                # 筛选专门用于 TOC 文件列表的 PDF 文件
                task_files_query = query.filter(ProjectFile.file_name.ilike('%.pdf'))
                task_files = sort_files_by_prefix(task_files_query.all())  # Execute query

                current_app.logger.debug(
                    f"       任务 '{task.name}' has {len(task_files)}过滤后的相关 PDF 文件.")

                if task_files and max_level >= 4:
                    file_names_for_toc = [f.original_name for f in task_files]
                    toc_items.append(
                        {'level': 4, 'text': task_text, 'id': f"task_{task.id}", 'files': file_names_for_toc})
                    current_app.logger.debug(f"        Added Level 4: {task_text} with files: {file_names_for_toc}")
                elif not task_files and max_level >= 4:
                    current_app.logger.debug(
                        f"        Task '{task.name}'没有 PDF 文件与级别 4 TOC 条目的条件匹配。")

    current_app.logger.debug(f"完成生成 TOC 结构。总项目： {len(toc_items)}")
    return toc_items


def get_pdf_file_paths_for_merging(project_id, selected_file_ids=None):
    """
    收集要合并的 PDF 文件的路径，同时考虑选择和顺序。
    优化了路径解析逻辑，以处理绝对路径和相对路径。
    """
    current_app.logger.info(f"开始为项目 {project_id} 获取 PDF 文件路径。选择的 ID: {selected_file_ids}")
    files_to_merge_info = []
    project = Project.query.get(project_id)
    if not project:
        current_app.logger.error(f"在 get_pdf_file_paths_for_merging 中未找到项目 {project_id}。")
        return []

    # 定义上传文件的基础目录 (根据你的实际配置修改)
    upload_base_directory = os.path.join(current_app.root_path, 'uploads')  # 存储在 应用根目录/uploads/ 下
    current_app.logger.debug(f"使用的上传基础目录: {upload_base_directory}")

    # 保持结构顺序: Subproject -> Stage -> Task -> Files (已排序)
    subprojects = Subproject.query.filter_by(project_id=project.id).order_by(Subproject.name).all()
    current_app.logger.debug(f"  正在遍历 {len(subprojects)} 个子项目...")

    for subproject in subprojects:
        current_app.logger.debug(f"    处理子项目: {subproject.name}")
        stages = ProjectStage.query.filter_by(subproject_id=subproject.id).order_by(ProjectStage.name).all()
        for stage in stages:
            current_app.logger.debug(f"      处理阶段: {stage.name}")
            tasks = StageTask.query.filter_by(stage_id=stage.id).order_by(StageTask.name).all()
            for task in tasks:
                current_app.logger.debug(f"        处理任务: {task.name}")
                query = ProjectFile.query.filter_by(task_id=task.id)

                if selected_file_ids is not None:
                    query = query.filter(ProjectFile.id.in_(selected_file_ids))
                    current_app.logger.debug(f"          应用 selected_file_ids 过滤器: {selected_file_ids}")

                query = query.filter(ProjectFile.file_name.ilike('%.pdf'))
                pdf_files_for_task = sort_files_by_prefix(query.all())
                current_app.logger.debug(f"          过滤和排序后，找到 {len(pdf_files_for_task)} 个此任务的 PDF 文件。")

                for pf_obj in pdf_files_for_task:
                    stored_path = pf_obj.file_path

                    if not stored_path:
                        current_app.logger.warning(f"文件 ID={pf_obj.id} 的 stored_path 为空, 跳过。")
                        continue

                    if os.path.isabs(stored_path):
                        full_path = stored_path
                        current_app.logger.debug(f"将存储的路径视为绝对路径: '{full_path}'")
                    else:
                        full_path = os.path.join(upload_base_directory, stored_path)
                        current_app.logger.debug(
                            f"            将相对路径与上传基础目录 '{upload_base_directory}' 拼接: '{full_path}'")

                    current_app.logger.debug(
                        f"检查文件: ID={pf_obj.id}, Name='{pf_obj.original_name}', Stored Path='{stored_path}', Resolved Path='{full_path}'")

                    if os.path.exists(full_path):
                        if os.path.isfile(full_path):
                            files_to_merge_info.append(
                                {'id': pf_obj.id, 'path': full_path, 'original_name': pf_obj.original_name}
                            )
                            current_app.logger.debug(f"已添加文件到合并列表: {full_path}")
                        else:
                            current_app.logger.warning(f"路径存在但不是文件, 跳过: {full_path}")
                    else:
                        current_app.logger.warning(f"在解析的路径未找到文件, 跳过: {full_path}")

    current_app.logger.info(f"总共找到 {len(files_to_merge_info)} 个要合并的 PDF 文件。")
    return files_to_merge_info


# --- 主要合并逻辑 ---

def _generate_base_merged_pdf(project_id, merge_config, selected_file_ids=None):
    """用于生成初始合并 PDF（封面、目录、内容）的内部函数。
    返回：基本合并 PDF 的路径、错误消息和临时目录路径。
    """
    current_app.logger.info(
        f"为项目启动 _generate_base_merged_pdf {project_id}. Selected IDs: {selected_file_ids}")
    project = Project.query.get(project_id)
    if not project:
        current_app.logger.error(f"Project {project_id} 在 _generate_base_merged_pdf 中未找到.")
        return None, "项目不存在 (Project does not exist)", None

    pdf_temp_dir = tempfile.mkdtemp(prefix=f"merge_pdf_{project.id}_")
    current_app.logger.info(f"Created temporary PDF directory: {pdf_temp_dir}")

    try:
        merger = PdfMerger()

        # 1. 准备封面
        cover_options = merge_config.get('coverPage', {})
        cover_title = cover_options.get('name', project.name)
        cover_subtitle = cover_options.get('subtitle', None)
        cover_page_pdf_path = os.path.join(pdf_temp_dir, "00_cover_page.pdf")
        current_app.logger.info(f"Creating cover page: Title='{cover_title}', Subtitle='{cover_subtitle}'")
        create_dynamic_title_page(cover_title, cover_page_pdf_path, subtitle_text=cover_subtitle)
        if os.path.exists(cover_page_pdf_path):
            merger.append(cover_page_pdf_path)
            current_app.logger.info("附加封面.")
        else:
            current_app.logger.warning("未创建封面 PDF.")

        # 2. 准备目录
        toc_options = merge_config.get('toc', {})
        if toc_options.get('include', True):
            max_toc_level = toc_options.get('maxLevel', 3)
            current_app.logger.info(f"生成 TOC 项结构 (最高级别: {max_toc_level})...")
            toc_items_data = generate_toc_items_structure(project_id, selected_file_ids, max_toc_level)

            if toc_items_data:
                toc_pdf_path = os.path.join(pdf_temp_dir, "01_toc_page.pdf")
                current_app.logger.info(f"创建 TOC 页面 {len(toc_items_data)} items...")
                created_toc_path = create_toc_pdf_page(toc_items_data, toc_pdf_path, max_level=max_toc_level)
                if created_toc_path and os.path.exists(created_toc_path):
                    merger.append(created_toc_path)
                    current_app.logger.info("附加的 TOC 页面.")
                else:
                    current_app.logger.warning("TOC 页面 PDF 未创建或失败。")
            else:
                current_app.logger.info("未生成 TOC 项，跳过 TOC 页.")
        else:
            current_app.logger.info("在配置中禁用了 TOC 包含.")

        # 3. Get Content Files
        current_app.logger.info("正在获取用于合并的内容文件路径...")
        content_file_infos = get_pdf_file_paths_for_merging(project_id, selected_file_ids)
        if not content_file_infos:
            current_app.logger.warning(f"未找到或未为项目选择内容 PDF 文件 {project_id}.")
        else:
            current_app.logger.info(f"Found {len(content_file_infos)} 要附加的内容文件.")

        # 4. 追加内容文件
        for i, file_info in enumerate(content_file_infos):
            file_path = file_info['path']
            original_name = file_info['original_name']
            current_app.logger.info(
                f"  Appending content file {i + 1}/{len(content_file_infos)}: '{original_name}' from path '{file_path}'")
            try:
                # 更正的行：将 import_bookmarks 替换为 import_outline
                merger.append(file_path, outline_item=original_name, import_outline=False)
            except Exception as append_error:
                current_app.logger.error(f"附加文件时出错 '{original_name}' ({file_path}): {append_error}",
                                         exc_info=True)
                raise append_error

        # 5. 编写基本合并的 PDF
        base_merged_pdf_path = os.path.join(pdf_temp_dir, f"{project.name}_base_merged.pdf")
        current_app.logger.info(f"将 PDF 合并到: {base_merged_pdf_path}")
        merger.write(base_merged_pdf_path)
        merger.close()
        current_app.logger.info("基础合并 PDF 已编写并关闭.")

        try:
            reader_check = PdfReader(base_merged_pdf_path)
            num_pages_check = len(reader_check.pages)
            current_app.logger.info(
                f"验证：基础合并 PDF'{base_merged_pdf_path}' has {num_pages_check} pages.")
        except Exception as read_error:
            current_app.logger.error(f"无法读取基本合并的 PDF 以进行页数验证: {read_error}")

        return base_merged_pdf_path, None, pdf_temp_dir

    except Exception as e:
        current_app.logger.error(f"合并基础 PDF 期间出错：{str(e)}", exc_info=True)
        if 'merger' in locals() and merger is not None:  # 类型：忽略
            try:
                merger.close()
                current_app.logger.info("在异常处理期间关闭合并.")
            except Exception as close_err:
                current_app.logger.error(f"在异常处理期间关闭合并程序时出错: {close_err}")
        if os.path.exists(pdf_temp_dir):
            shutil.rmtree(pdf_temp_dir)
            current_app.logger.info(f"由于错误，清理了临时 PDF 目录 {pdf_temp_dir} ")
        return None, str(e), None


def generate_paged_preview_data(project_id, merge_config, selected_file_ids=None):
    """
    为合并的 PDF 的每个页面生成图像预览。
    返回： preview_session_id、页面图像信息列表（索引、url）、错误消息image_temp_dir_for_cleanup。
    """
    current_app.logger.info(
        f"开始为项目生成分页预览{project_id}. Selected IDs: {selected_file_ids}")
    base_merged_pdf_path, error, pdf_temp_dir = _generate_base_merged_pdf(project_id, merge_config, selected_file_ids)

    if error:
        current_app.logger.error(f"无法生成基本合并的 PDF： {error}")
        return None, None, error, None

    if not base_merged_pdf_path or not os.path.exists(base_merged_pdf_path):
        current_app.logger.error("基本合并的 PDF 路径丢失或生成后文件不存在.")
        if pdf_temp_dir and os.path.exists(pdf_temp_dir): shutil.rmtree(pdf_temp_dir)
        return None, None, "无法创建基本 PDF 文件。", None

    preview_session_id = str(uuid.uuid4())
    current_app.logger.info(f"生成的预览会话 ID: {preview_session_id}")

    main_temp_image_dir = os.path.join(current_app.static_folder, TEMP_PREVIEW_IMAGE_SUBDIR)
    os.makedirs(main_temp_image_dir, exist_ok=True)

    session_image_dir_abs = os.path.join(main_temp_image_dir, preview_session_id)

    if os.path.exists(session_image_dir_abs):
        shutil.rmtree(session_image_dir_abs)
    os.makedirs(session_image_dir_abs, exist_ok=True)
    current_app.logger.info(f"已创建临时镜像目录： {session_image_dir_abs}")

    pages_data = []
    try:
        try:
            reader_check = PdfReader(base_merged_pdf_path)
            num_pages_to_convert = len(reader_check.pages)
            current_app.logger.info(
                f"尝试转换 PDF '{base_merged_pdf_path}' with {num_pages_to_convert} 页面转换为图像。")
        except Exception as read_error:
            current_app.logger.error(f"转换前无法读取基本合并的 PDF： {read_error}")
            num_pages_to_convert = "Unknown"  # 类型：忽略

        images = convert_from_path(base_merged_pdf_path, dpi=100, fmt='jpeg')
        current_app.logger.info(f"已成功将 PDF 转换为 {len(images)}PIL 图像。")

        if num_pages_to_convert != "未知" and int(num_pages_to_convert) != len(images):  # 类型：忽略
            current_app.logger.warning(
                f"Mismatch: Expected {num_pages_to_convert} pages, but converted {len(images)} images.")

        for i, image in enumerate(images):
            image_filename = f"page_{i}.jpeg"
            image_path_abs = os.path.join(session_image_dir_abs, image_filename)
            current_app.logger.debug(f"  为页面保存图像 {i} to {image_path_abs}")
            image.save(image_path_abs, "JPEG")

            image_url = url_for('file_merge_refactored.serve_temp_preview_image',
                                session_id=preview_session_id,
                                image_filename=image_filename,
                                _external=False)
            current_app.logger.debug(f"  为页面生成的 URL{i}: {image_url}")

            pages_data.append({
                "page_index": i,
                "image_url": image_url
            })

        current_app.logger.info(f"完成生成{len(pages_data)} 页面预览数据。")

        if pdf_temp_dir and os.path.exists(pdf_temp_dir):
            shutil.rmtree(pdf_temp_dir)
            current_app.logger.info(f"清理了临时 PDF 目录：{pdf_temp_dir}")

        return preview_session_id, pages_data, None, session_image_dir_abs

    except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError) as pdf_err:
        current_app.logger.error(
            f"PDF 到图像转换错误：{str(pdf_err)} -检查 Poppler 安装和 PDF 有效性.",
            exc_info=True)
        error_msg = f"无法转换PDF页面为图片: {str(pdf_err)}。请确保Poppler已正确安装并配置在服务器。(Could not convert PDF pages to images. Ensure Poppler is correctly installed and configured on the server.)"
        if pdf_temp_dir and os.path.exists(pdf_temp_dir): shutil.rmtree(pdf_temp_dir)
        if os.path.exists(session_image_dir_abs): shutil.rmtree(session_image_dir_abs)
        return None, None, error_msg, None
    except Exception as e:
        current_app.logger.error(f"generate_paged_preview_data 中出现意外错误： {str(e)}", exc_info=True)
        if pdf_temp_dir and os.path.exists(pdf_temp_dir): shutil.rmtree(pdf_temp_dir)
        if os.path.exists(session_image_dir_abs): shutil.rmtree(session_image_dir_abs)
        return None, None, str(e), None


def build_final_pdf(project_id, merge_config, selected_file_ids=None, pages_to_delete_indices=None):
    """
    构建最终合并的 PDF（可能删除了页面）并添加页码。
    返回：最终 PDF 的路径、错误消息和用于清理的临时目录路径。
    """
    current_app.logger.info(
        f"Starting final PDF build for project {project_id}. Selected IDs: {selected_file_ids}. Pages to delete: {pages_to_delete_indices}")
    project = Project.query.get(project_id)
    if not project:
        current_app.logger.error(f"Project {project_id} not found in build_final_pdf.")
        return None, "项目不存在 (Project does not exist)", None

    base_merged_pdf_path, error, base_pdf_temp_dir = _generate_base_merged_pdf(project_id, merge_config,
                                                                               selected_file_ids)

    if error:
        current_app.logger.error(f"无法为最终构建生成基本合并的 PDF：{error}")
        return None, error, None

    if not base_merged_pdf_path or not os.path.exists(base_merged_pdf_path):
        current_app.logger.error(
            "基本合并的 PDF 路径缺失或在生成最终构建后文件不存在。")
        if base_pdf_temp_dir and os.path.exists(base_pdf_temp_dir): shutil.rmtree(base_pdf_temp_dir)
        return None, "Failed to create the base PDF file for finalization.", None

    final_pdf_processing_temp_dir = tempfile.mkdtemp(prefix=f"final_pdf_{project.id}_")
    current_app.logger.info(f"已创建最终处理临时目录： {final_pdf_processing_temp_dir}")

    try:
        pdf_path_before_numbering = os.path.join(final_pdf_processing_temp_dir, f"{project.name}_deleted_pages.pdf")

        if pages_to_delete_indices is not None and pages_to_delete_indices:
            current_app.logger.info(f"删除带有索引的页面： {pages_to_delete_indices}")
            reader = PdfReader(base_merged_pdf_path)
            writer = PdfWriter()
            original_page_count = len(reader.pages)
            deleted_count = 0
            for i, page in enumerate(reader.pages):
                if i not in pages_to_delete_indices:
                    writer.add_page(page)
                else:
                    deleted_count += 1
            current_app.logger.info(
                f"Original pages: {original_page_count}, Pages deleted: {deleted_count}, Pages remaining: {len(writer.pages)}")
            with open(pdf_path_before_numbering, "wb") as f_out:
                writer.write(f_out)
            current_app.logger.info(f"已删除页面的 PDF 存储到：{pdf_path_before_numbering}")
        else:
            current_app.logger.info("没有要删除的页面。复制基础合并的 PDF.")
            shutil.copy(base_merged_pdf_path, pdf_path_before_numbering)

        if base_pdf_temp_dir and os.path.exists(base_pdf_temp_dir):
            shutil.rmtree(base_pdf_temp_dir)
            current_app.logger.info(f"清理了基本 PDF 临时目录： {base_pdf_temp_dir}")
            base_pdf_temp_dir = None

        final_output_filename = f"{project.name}_final_merged.pdf"
        final_output_path_with_pagenumbers = os.path.join(final_pdf_processing_temp_dir, final_output_filename)
        current_app.logger.info(
            f"添加页码 '{pdf_path_before_numbering}' -> '{final_output_path_with_pagenumbers}'")

        numbered_pdf_path = add_page_numbers_to_pdf(pdf_path_before_numbering, final_output_path_with_pagenumbers)

        if not numbered_pdf_path or not os.path.exists(numbered_pdf_path):
            current_app.logger.error("添加页码失败或缺少最终编号的 PDF。")
            raise RuntimeError("页码排序失败。")

        current_app.logger.info(f"已创建页码的最终 PDF： {numbered_pdf_path}")
        return numbered_pdf_path, None, final_pdf_processing_temp_dir

    except Exception as e:
        current_app.logger.error(f"生成最终 PDF 期间出错： {str(e)}", exc_info=True)
        if base_pdf_temp_dir and os.path.exists(base_pdf_temp_dir):
            shutil.rmtree(base_pdf_temp_dir)
            current_app.logger.info(f"在错误处理期间清理了基本 PDF 临时目录 {base_pdf_temp_dir} ")
        if os.path.exists(final_pdf_processing_temp_dir):
            shutil.rmtree(final_pdf_processing_temp_dir)
            current_app.logger.info(
                f"在错误处理期间清理了最终处理临时目录{final_pdf_processing_temp_dir}.")
        return None, str(e), None
