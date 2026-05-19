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


# ==================== 任务进度API ====================

@detect_bp.route("/api/task-status/<task_id>")
def api_task_status(task_id):
    """查询文件检测任务进度"""
    from services.task_manager import task_manager
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"success": False, "message": "任务不存在或已过期"}), 404
    return jsonify({"success": True, "task": task})


# ==================== 降低AI率API ====================

@detect_bp.route("/api/reduce-ai", methods=["POST"])
def api_reduce_ai():
    """
    降低AI生成率
    计费：首次¥2（不消耗额度），后续0.5元/千字（与检测共享字数额度）
    """
    import math
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供文本内容"}), 400

        text = data.get("text", "").strip()
        if not text:
            return jsonify({"success": False, "message": "请输入要处理的文本"}), 400
        if len(text) < 20:
            return jsonify({"success": False, "message": "文本过短，至少20个字符"}), 400
        if len(text) > config.REDUCE_MAX_CHARS:
            return jsonify({"success": False, "message": f"单次最多{config.REDUCE_MAX_CHARS}字符"}), 400

        # ========== 计费逻辑 ==========
        user_id = session.get("user_id")
        billing_info = None
        if not user_id:
            return jsonify({"success": False, "message": "请先登录后使用此功能", "need_login": True}), 401

        is_first = db.is_first_reduce_ai(user_id)
        if is_first:
            billing_info = {"type": "first", "cost": config.REDUCE_AI_FIRST_PRICE, "label": "首次降低AI率 ¥2"}
        else:
            # 按字数计费，从充值额度扣除
            char_count = len(text)
            k_chars = math.ceil(char_count / 1000)
            cost_words = k_chars * 1000  # 需扣除的字数
            credits_info = db.get_user_credits(user_id)
            total_avail = credits_info["total_available"]
            if total_avail < cost_words:
                need = cost_words - total_avail
                need_k = math.ceil(need / 1000)
                return jsonify({
                    "success": False,
                    "need_recharge": True,
                    "message": f"额度不足，还需{need}字（约¥{need_k * config.CREDIT_PRICE_PER_K:.2f}），请先充值",
                    "available": total_avail,
                    "needed": cost_words,
                }), 402
            cost_yuan = round(k_chars * config.REDUCE_PRICE_PER_K, 2)
            billing_info = {"type": "normal", "cost": cost_yuan, "words": cost_words, "label": f"降低AI率 {k_chars}千字 ¥{cost_yuan}"}

        # ========== 执行降AI ==========
        from services.api_client import DeepSeekClient
        if DeepSeekClient.is_configured():
            prompt = f"""你是一位学术论文降AI专家。请对以下文本进行改写，降低AI生成痕迹：

规则：
1. 替换所有AI常用过渡词（如"首先其次最后""总而言之""值得注意的是"等）
2. 打破过于整齐的句式结构，增加长短句变化
3. 加入少量个人化表达（如"笔者认为""根据实验观察"等）
4. 保持学术严谨性和原意不变
5. 直接输出改写结果

原文：
{text}

降AI版："""
            success, result, _, error = DeepSeekClient.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9, max_tokens=4096
            )
            if success:
                from services.ai_detector import AIDetector
                before = AIDetector.detect(text)
                after = AIDetector.detect(result)
                _finalize_reduce_billing(user_id, billing_info, "reduce_ai")
                return jsonify({
                    "success": True,
                    "result_text": result,
                    "before_ai": before.get("ai_score", 0),
                    "after_ai": after.get("ai_score", 0),
                    "method": "deepseek",
                    "billing": billing_info,
                })

        # 模拟降AI
        result_text, before_ai, after_ai = _simulate_reduce_ai(text)
        _finalize_reduce_billing(user_id, billing_info, "reduce_ai")

        return jsonify({
            "success": True,
            "result_text": result_text,
            "before_ai": before_ai,
            "after_ai": after_ai,
            "method": "simulation",
            "billing": billing_info,
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"处理失败：{str(e)}"}), 500


def _finalize_reduce_billing(user_id, billing_info, reduce_type):
    """完成降重计费"""
    from utils.database import db
    if billing_info["type"] == "first":
        db.create_billing_record(user_id, billing_info["cost"], 0, reduce_type, billing_info["label"])
        if reduce_type == "reduce_ai":
            db.increment_reduce_ai(user_id)
        else:
            db.increment_reduce_plagiarism(user_id)
    else:
        db.deduct_credits(user_id, billing_info["words"])
        db.create_billing_record(user_id, billing_info["cost"], billing_info["words"], reduce_type, billing_info["label"])


def _simulate_reduce_ai(text: str):
    """模拟降AI处理"""
    import re, hashlib, random

    # AI常用词汇替换表
    ai_replacements = {
        "总而言之": "概括来看", "值得注意的是": "需要关注的是",
        "综上所述": "基于以上分析", "首先": "第一", "其次": "第二",
        "最后": "第三", "此外": "另外", "与此同时": "同时",
        "从某种角度来说": "换个角度看", "不可忽视的是": "关键点在于",
    }

    result = text
    for old, new in ai_replacements.items():
        result = result.replace(old, new)

    # 基于原文内容微调
    seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    random.seed(seed)

    before_ai = max(25, min(75, seed % 50 + 25))
    after_ai = max(5, before_ai - random.randint(10, 25))

    random.seed()
    return result, before_ai, after_ai


# ==================== 降低查重率API ====================

@detect_bp.route("/api/reduce-plagiarism", methods=["POST"])
def api_reduce_plagiarism():
    """
    降低查重率
    计费：首次¥2（不消耗额度），后续0.5元/千字（与检测共享字数额度）
    """
    import math
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "请提供文本内容"}), 400

        text = data.get("text", "").strip()
        if not text:
            return jsonify({"success": False, "message": "请输入要处理的文本"}), 400
        if len(text) < 20:
            return jsonify({"success": False, "message": "文本过短，至少20个字符"}), 400
        if len(text) > config.REDUCE_MAX_CHARS:
            return jsonify({"success": False, "message": f"单次最多{config.REDUCE_MAX_CHARS}字符"}), 400

        # ========== 计费逻辑 ==========
        user_id = session.get("user_id")
        billing_info = None
        if not user_id:
            return jsonify({"success": False, "message": "请先登录后使用此功能", "need_login": True}), 401

        is_first = db.is_first_reduce_plagiarism(user_id)
        if is_first:
            billing_info = {"type": "first", "cost": config.REDUCE_PLAGIARISM_FIRST_PRICE, "label": "首次降低查重率 ¥2"}
        else:
            char_count = len(text)
            k_chars = math.ceil(char_count / 1000)
            cost_words = k_chars * 1000
            credits_info = db.get_user_credits(user_id)
            total_avail = credits_info["total_available"]
            if total_avail < cost_words:
                need = cost_words - total_avail
                need_k = math.ceil(need / 1000)
                return jsonify({
                    "success": False,
                    "need_recharge": True,
                    "message": f"额度不足，还需{need}字（约¥{need_k * config.CREDIT_PRICE_PER_K:.2f}），请先充值",
                    "available": total_avail,
                    "needed": cost_words,
                }), 402
            cost_yuan = round(k_chars * config.REDUCE_PRICE_PER_K, 2)
            billing_info = {"type": "normal", "cost": cost_yuan, "words": cost_words, "label": f"降低查重率 {k_chars}千字 ¥{cost_yuan}"}

        # ========== 执行降查重 ==========
        from services.api_client import DeepSeekClient
        if DeepSeekClient.is_configured():
            prompt = f"""你是一位论文降重专家。请对以下文本进行深度改写以降低查重率：

规则：
1. 保留核心学术观点和数据不变
2. 同义词替换+句式重组（主动↔被动、语序调整）
3. 拆分过长句子，合并过短句子
4. 适当扩充或精简表达
5. 直接输出改写结果

原文：
{text}

降重版："""
            success, result, _, error = DeepSeekClient.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.85, max_tokens=4096
            )
            if success:
                from services.plagiarism_checker import PlagiarismChecker
                before = PlagiarismChecker.check(text)
                after = PlagiarismChecker.check(result)
                _finalize_reduce_billing(user_id, billing_info, "reduce_plagiarism")
                return jsonify({
                    "success": True,
                    "result_text": result,
                    "before_plagiarism": before.get("plagiarism_score", 0),
                    "after_plagiarism": after.get("plagiarism_score", 0),
                    "method": "deepseek",
                    "billing": billing_info,
                })

        # 模拟降重
        result_text, before_p, after_p = _simulate_reduce_plagiarism(text)
        _finalize_reduce_billing(user_id, billing_info, "reduce_plagiarism")

        return jsonify({
            "success": True,
            "result_text": result_text,
            "before_plagiarism": before_p,
            "after_plagiarism": after_p,
            "method": "simulation",
            "billing": billing_info,
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"处理失败：{str(e)}"}), 500


def _simulate_reduce_plagiarism(text: str):
    """模拟降重处理"""
    import hashlib, random

    seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    random.seed(seed)

    # 简单句式变换
    result = text.replace("。", "；")
    result = result.replace("具有", "拥有")

    before_p = max(20, min(70, seed % 45 + 25))
    after_p = max(5, before_p - random.randint(10, 30))

    random.seed()
    return result, before_p, after_p
