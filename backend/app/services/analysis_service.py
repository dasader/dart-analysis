import json

from sqlalchemy.orm import Session

from app.models import Analysis, PromptTemplate
from app.services.gemini_client import generate, MODEL_NAME
from app.services.report_service import extract_text_from_report

VALID_TYPES = {"subsidiary", "rnd", "national_tech"}


async def run_analysis(db: Session, analysis_id: int) -> None:
    """analysis_id에 해당하는 분석을 실행. 큐 워커에서 호출."""
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        return

    analysis.status = "running"
    db.commit()

    try:
        template = db.query(PromptTemplate).filter_by(
            analysis_type=analysis.analysis_type
        ).first()
        if not template:
            raise ValueError(f"프롬프트 템플릿이 없습니다: {analysis.analysis_type}")

        report = analysis.report
        report_text = extract_text_from_report(report.file_path)
        if not report_text:
            raise ValueError("보고서 텍스트를 추출할 수 없습니다.")

        max_chars = 2_000_000
        if len(report_text) > max_chars:
            report_text = report_text[:max_chars]

        user_prompt = template.user_prompt_template.format(
            corp_name=report.company.corp_name,
            fiscal_year=report.fiscal_year,
            report_text=report_text,
        )

        result_text = await generate(template.system_prompt, user_prompt)

        analysis.result_summary = result_text
        analysis.result_json = json.dumps({"raw_response": result_text}, ensure_ascii=False)
        analysis.model_name = MODEL_NAME
        analysis.status = "completed"
        db.commit()

    except Exception as e:
        analysis.status = "failed"
        analysis.error_message = str(e)
        db.commit()
