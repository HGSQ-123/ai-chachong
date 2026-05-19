"""
检测路由 - 文本检测、文件上传检测、结果查看
核心业务逻辑路由
"""

import os
import traceback
from flask import Blueprint, render_template, request, session, jsonify, send_file
from werkzeug.utils import secure_filename

from config import config
from utils.database import db
from utils.helpers import (
    count_chinese_words, text_hash, allowed_file,
    safe_filename, validate_text_content
)
from utils.decorators import login_required
from services.ai_detector import AIDetector
from services.plagiarism_checker import PlagiarismChecker
from services.file_parser import FileParser
from services.billing import BillingService

detect_bp = Blueprint("detect", __name__, url_prefix="/detect")


@detect_bp.route("/")
def detect_page():
    """检测页面（粘贴文本 & 上传文件）"""
    user = None
    quota_info = None
    if "user_id" in session:
        user = db.get_user_by_id(session["user_id"])
        if user:
            quota_info = BillingService.get_available_quota(user)
    return render_template("detect.html", user=user, quota_info=quota_info)


@detect_bp.route("/api/text", methods=["POST"])
def api_detect_text():
    """
    文本检测API（粘贴文本方式）
    接收JSON: {"text": "...", "mode": "both"}
    mode: both(同时检测) / ai_only(仅AI检测) / plagiarism_only(仅查重)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供检测内容"}), 400

        text = data.get("text", "").strip()
        mode = data.get("mode", "both")

        # 验证文本
        is_valid, error_msg = validate_text_content(text)
        if not is_valid:
            return jsonify({"success": False, "message": error_msg}), 400

        # 统计字数
        word_count = count_chinese_words(text)
        if word_count < 10:
            return jsonify({"success": False, "message": "文本过短（不足10字），无法进行有效检测"}), 400

        if word_count > config.MAX_DETECTION_WORDS:
            return jsonify({
                "success": False,
                "message": f"单次检测最多支持{config.MAX_DETECTION_WORDS}字，当前{word_count}字"
            }), 400

        # 计费检查
        user_id = session.get("user_id")
        billing_result = None

        if user_id:
            user = db.get_user_by_id(user_id)
            if user:
                # 计算需要扣除的额度
                deduct_result = BillingService.deduct_quota(user_id, word_count)
                if not deduct_result["success"]:
                    return jsonify({"success": False, "message": deduct_result.get("error", "额度扣除失败")}), 400

                billing_result = deduct_result

                # 如果有超出额度需要付费
                if deduct_result["extra_needed"] > 0:
                    return jsonify({
                        "success": False,
                        "need_pay": True,
                        "message": f"您的免费额度不足，超出{deduct_result['extra_needed']}字需要付费{deduct_result['extra_cost']}元",
                        "extra_words": deduct_result["extra_needed"],
                        "extra_cost": deduct_result["extra_cost"],
                        "quota_info": BillingService.get_available_quota(user),
                    }), 402  # 402 Payment Required

        # 执行检测
        ai_result = None
        plagiarism_result = None

        if mode in ("both", "ai_only"):
            ai_result = AIDetector.detect(text)

        if mode in ("both", "plagiarism_only"):
            plagiarism_result = PlagiarismChecker.check(text)

        # 计算综合得分
        ai_score = ai_result["ai_score"] if ai_result else 0
        plagiarism_score = plagiarism_result["plagiarism_score"] if plagiarism_result else 0
        # 原创得分：取AI得分和重复率中较高者，用100减去
        originality_score = round(100 - max(ai_score, plagiarism_score), 1)

        # 构建报告
        report = {
            "originality_score": originality_score,
            "ai_score": ai_score,
            "human_score": 100 - ai_score if ai_result else 0,
            "plagiarism_score": plagiarism_score,
            "word_count": word_count,
            "ai_details": ai_result.get("details", []) if ai_result else [],
            "ai_suggestions": ai_result.get("suggestions", []) if ai_result else [],
            "matched_segments": plagiarism_result.get("matched_segments", []) if plagiarism_result else [],
            "sources": plagiarism_result.get("sources", []) if plagiarism_result else [],
            "plagiarism_suggestions": plagiarism_result.get("suggestions", []) if plagiarism_result else [],
            "detection_mode": mode,
            "ai_method": ai_result.get("method", "simulation") if ai_result else "N/A",
            "plagiarism_method": plagiarism_result.get("method", "simulation") if plagiarism_result else "N/A",
        }

        # 保存检测记录（仅保存报告，不保存原文）
        if user_id:
            txt_hash = text_hash(text)
            record_id = db.create_detection_record(
                user_id=user_id,
                text_hash=txt_hash,
                word_count=word_count,
                ai_score=ai_score,
                plagiarism_score=plagiarism_score,
                report_data=report,
            )
            report["record_id"] = record_id

            # 记录计费日志
            if billing_result:
                if billing_result["free_used"] > 0:
                    db.create_billing_record(
                        user_id=user_id, amount=0,
                        word_count=billing_result["free_used"],
                        transaction_type="free_quota",
                        description=f"使用免费额度检测{billing_result['free_used']}字"
                    )
                if billing_result["member_used"] > 0:
                    db.create_billing_record(
                        user_id=user_id, amount=0,
                        word_count=billing_result["member_used"],
                        transaction_type="member",
                        description=f"使用会员额度检测{billing_result['member_used']}字"
                    )

        return jsonify({
            "success": True,
            "message": "检测完成",
            "report": report,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"检测服务异常：{str(e)}"}), 500


@detect_bp.route("/api/file", methods=["POST"])
def api_detect_file():
    """
    文件上传检测API
    支持Word(.docx)和PDF(.pdf)文件
    """
    try:
        # 检查是否有文件上传
        if "file" not in request.files:
            return jsonify({"success": False, "message": "请选择要上传的文件"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "message": "请选择要上传的文件"}), 400

        # 验证文件扩展名
        if not allowed_file(file.filename, config.ALLOWED_EXTENSIONS):
            return jsonify({
                "success": False,
                "message": f"不支持的文件格式，请上传 {', '.join(config.ALLOWED_EXTENSIONS)} 文件"
            }), 400

        # 保存文件到临时目录
        os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
        safe_name = safe_filename(file.filename)
        filepath = os.path.join(config.UPLOAD_FOLDER, safe_name)
        file.save(filepath)

        # 解析文件内容
        parse_result = FileParser.parse(filepath, file.filename)

        if not parse_result["success"]:
            # 清理临时文件
            try: os.remove(filepath)
            except OSError: pass
            return jsonify({
                "success": False,
                "message": parse_result["error"],
                "file_type": parse_result.get("file_type", "unknown"),
                "help": "扫描版PDF需先用WPS/Word转为文字版"
            }), 400

        text = parse_result["text"]
        word_count = parse_result["word_count"]

        # 字数检查
        if word_count < 10:
            try:
                os.remove(filepath)
            except OSError:
                pass
            return jsonify({"success": False, "message": "文档内容过短（不足10字），无法进行有效检测"}), 400

        if word_count > config.MAX_DETECTION_WORDS:
            try:
                os.remove(filepath)
            except OSError:
                pass
            return jsonify({
                "success": False,
                "message": f"单次检测最多支持{config.MAX_DETECTION_WORDS}字，当前文档{word_count}字"
            }), 400

        # 计费检查
        user_id = session.get("user_id")
        billing_result = None

        if user_id:
            user = db.get_user_by_id(user_id)
            if user:
                deduct_result = BillingService.deduct_quota(user_id, word_count)
                if not deduct_result["success"]:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                    return jsonify({"success": False, "message": deduct_result.get("error", "额度扣除失败")}), 400

                billing_result = deduct_result

                if deduct_result["extra_needed"] > 0:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                    return jsonify({
                        "success": False,
                        "need_pay": True,
                        "message": f"您的免费额度不足，超出{deduct_result['extra_needed']}字需要付费{deduct_result['extra_cost']}元",
                        "extra_words": deduct_result["extra_needed"],
                        "extra_cost": deduct_result["extra_cost"],
                        "quota_info": BillingService.get_available_quota(user),
                    }), 402

        # 执行双重检测
        ai_result = AIDetector.detect(text)
        plagiarism_result = PlagiarismChecker.check(text)

        ai_score = ai_result["ai_score"]
        plagiarism_score = plagiarism_result["plagiarism_score"]
        originality_score = round(100 - max(ai_score, plagiarism_score), 1)

        # 构建报告
        report = {
            "originality_score": originality_score,
            "ai_score": ai_score,
            "human_score": 100 - ai_score,
            "plagiarism_score": plagiarism_score,
            "word_count": word_count,
            "file_name": file.filename,
            "ai_details": ai_result.get("details", []),
            "ai_suggestions": ai_result.get("suggestions", []),
            "matched_segments": plagiarism_result.get("matched_segments", []),
            "sources": plagiarism_result.get("sources", []),
            "plagiarism_suggestions": plagiarism_result.get("suggestions", []),
            "detection_mode": "both",
            "ai_method": ai_result.get("method", "simulation"),
            "plagiarism_method": plagiarism_result.get("method", "simulation"),
        }

        # 保存记录
        if user_id:
            txt_hash = text_hash(text)
            record_id = db.create_detection_record(
                user_id=user_id,
                text_hash=txt_hash,
                word_count=word_count,
                ai_score=ai_score,
                plagiarism_score=plagiarism_score,
                report_data=report,
                file_name=file.filename,
            )
            report["record_id"] = record_id

            if billing_result:
                if billing_result["free_used"] > 0:
                    db.create_billing_record(
                        user_id=user_id, amount=0,
                        word_count=billing_result["free_used"],
                        transaction_type="free_quota",
                        description=f"文件检测使用免费额度{billing_result['free_used']}字"
                    )
                if billing_result["member_used"] > 0:
                    db.create_billing_record(
                        user_id=user_id, amount=0,
                        word_count=billing_result["member_used"],
                        transaction_type="member",
                        description=f"文件检测使用会员额度{billing_result['member_used']}字"
                    )

        # 清理临时文件（保护用户隐私）
        try:
            os.remove(filepath)
        except OSError:
            pass

        return jsonify({
            "success": True,
            "message": "文件检测完成",
            "report": report,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"文件检测异常：{str(e)}"}), 500


@detect_bp.route("/report/<int:record_id>")
@login_required
def report_page(record_id):
    """检测报告页面"""
    user_id = session["user_id"]
    record = db.get_detection_record(record_id, user_id)
    if not record:
        return render_template("404.html"), 404

    import json
    report_data = record.get("report_data")
    if isinstance(report_data, str):
        try:
            report_data = json.loads(report_data)
        except json.JSONDecodeError:
            report_data = {}

    user = db.get_user_by_id(user_id)

    return render_template(
        "report.html",
        record=record,
        report=report_data,
        user=user,
    )


@detect_bp.route("/api/report/<int:record_id>/download")
@login_required
def download_report(record_id):
    """
    下载检测报告（生成简易HTML报告文件）
    """
    user_id = session["user_id"]
    record = db.get_detection_record(record_id, user_id)
    if not record:
        return jsonify({"success": False, "message": "记录不存在"}), 404

    import json
    report_data = record.get("report_data")
    if isinstance(report_data, str):
        report_data = json.loads(report_data)

    user = db.get_user_by_id(user_id)

    # 生成HTML报告内容
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>检测报告 - {config.SITE_NAME}</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; color: #333; }}
        h1 {{ color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px; }}
        .score-box {{ background: linear-gradient(135deg, #eff6ff, #dbeafe); border-radius: 12px; padding: 20px; margin: 20px 0; text-align: center; }}
        .score-big {{ font-size: 48px; font-weight: bold; color: #2563eb; }}
        .section {{ margin: 20px 0; padding: 15px; background: #f8fafc; border-radius: 8px; }}
        .section h3 {{ margin-top: 0; color: #1e40af; }}
        .matched {{ background: #fee2e2; padding: 8px; border-radius: 4px; margin: 5px 0; border-left: 3px solid #ef4444; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 12px; text-align: center; }}
    </style>
</head>
<body>
    <h1>📋 {config.SITE_NAME} - 检测报告</h1>
    <p>检测时间：{record.get('created_at', '未知')} | 字数：{record.get('word_count', 0)}字</p>
    {"<p>文件：{}</p>".format(record.get('file_name')) if record.get('file_name') else ""}

    <div class="score-box">
        <p style="font-size:14px;color:#6b7280;">总体原创得分</p>
        <div class="score-big">{report_data.get('originality_score', 0)}<span style="font-size:24px;">/100</span></div>
    </div>

    <div class="section">
        <h3>🤖 AI生成率检测</h3>
        <p>AI撰写占比：<strong>{report_data.get('ai_score', 0)}%</strong></p>
        <p>人工原创占比：<strong>{report_data.get('human_score', 0)}%</strong></p>
        <p>检测方式：{report_data.get('ai_method', 'N/A')}</p>
    </div>

    <div class="section">
        <h3>📊 文本重复率查重</h3>
        <p>重复率：<strong>{report_data.get('plagiarism_score', 0)}%</strong></p>
        <h4>匹配片段：</h4>
        {"".join('<div class="matched">{} <br><small>来源：{}</small></div>'.format(s.get('text',''), s.get('source','')) for s in report_data.get('matched_segments', []))}
    </div>

    <div class="section">
        <h3>💡 优化建议</h3>
        <ul>
            {"".join('<li>{}</li>'.format(s) for s in report_data.get('ai_suggestions', []) + report_data.get('plagiarism_suggestions', []))}
        </ul>
    </div>

    <div class="footer">
        <p>本报告由{config.SITE_NAME}生成，结果仅供参考</p>
        <p>学校定稿以官方查重系统为准 | 报告生成时间：{record.get('created_at', '')}</p>
        <p>{config.SITE_DOMAIN}</p>
    </div>
</body>
</html>"""

    # 返回HTML文件
    from io import BytesIO
    buffer = BytesIO()
    buffer.write(html_content.encode("utf-8"))
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="text/html",
        as_attachment=True,
        download_name=f"检测报告_{record_id}_{record.get('created_at','')[:10]}.html",
    )
