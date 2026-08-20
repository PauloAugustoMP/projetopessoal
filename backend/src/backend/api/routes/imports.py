from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile

from backend.api.dependencies import SessionDep, require_auth
from backend.api.errors import ApiError
from backend.api.schemas import ImportResultResponse, ReviewRowResponse
from backend.application.import_b3_statement import import_b3_statement
from backend.application.recalculation import recalculate_position
from backend.infrastructure.b3_import.statement_parser import (
    StatementFormatError,
    parse_statement,
)
from backend.infrastructure.persistence.database import get_session_factory

router = APIRouter(prefix="/import", tags=["import"], dependencies=[Depends(require_auth)])


@router.post("/b3-statement", response_model=ImportResultResponse, response_model_by_alias=True)
async def import_statement(
    file: UploadFile, session: SessionDep, background_tasks: BackgroundTasks
) -> ImportResultResponse:
    content = await file.read()
    filename = file.filename or "statement"
    try:
        statement = parse_statement(content, filename)
    except StatementFormatError as error:
        raise ApiError(400, "INVALID_STATEMENT_FILE", str(error)) from error

    result = import_b3_statement(session, statement, filename)

    for ticker in sorted(result.affected_tickers - result.inconsistent_tickers):
        background_tasks.add_task(recalculate_position, get_session_factory(), ticker)

    return ImportResultResponse(
        transactions_created=result.transactions_created,
        dividends_created=result.dividends_created,
        corporate_actions_created=result.corporate_actions_created,
        duplicates_skipped=result.duplicates_skipped,
        rows_for_manual_review=[
            ReviewRowResponse(**row) for row in result.rows_for_manual_review
        ],
    )
