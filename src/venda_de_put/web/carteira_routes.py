from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from venda_de_put.carteira.auth import (
    SESSION_SECONDS,
    AuthError,
    AuthService,
    SessionBundle,
    UserPrincipal,
)
from venda_de_put.carteira.db import Database
from venda_de_put.carteira.market import build_market_view
from venda_de_put.carteira.performance import compute_operation, compute_personal_summary
from venda_de_put.carteira.repository import CarteiraRepository, RepositoryConflict
from venda_de_put.carteira.schemas import (
    AccountBody,
    AccountOut,
    AuthSessionOut,
    CashFlowBody,
    CashFlowOut,
    CustodyEntryBody,
    CustodyEntryOut,
    LoginBody,
    MeOut,
    OperationPerformanceOut,
    OptionOperationBody,
    PersonalSummaryOut,
    PortfolioEntryBody,
    PortfolioEntryOut,
    RegisterBody,
)
from venda_de_put.models import Snapshot
from venda_de_put.tz import TZ
from venda_de_put.web.http_security import cookie_path, cookie_secure


def _tokens_match(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return secrets.compare_digest(left, right)


def _set_session_cookies(
    request: Request, response: Response, bundle: SessionBundle
) -> None:
    path = cookie_path(request)
    secure = cookie_secure(request)
    response.set_cookie(
        "carteira_session",
        bundle.token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=SESSION_SECONDS,
        path=path,
    )
    response.set_cookie(
        "carteira_csrf",
        bundle.csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        max_age=SESSION_SECONDS,
        path=path,
    )


def _clear_session_cookies(request: Request, response: Response) -> None:
    path = cookie_path(request)
    secure = cookie_secure(request)
    response.delete_cookie(
        "carteira_session",
        httponly=True,
        samesite="lax",
        secure=secure,
        path=path,
    )
    response.delete_cookie(
        "carteira_csrf",
        httponly=False,
        samesite="lax",
        secure=secure,
        path=path,
    )


def _map_auth_error(error: AuthError, *, login: bool) -> HTTPException:
    message = str(error)
    if "já existe" in message:
        return HTTPException(409, message)
    if login or "usuário ou senha inválidos" in message:
        return HTTPException(401, "usuário ou senha inválidos")
    return HTTPException(422, message)


def _map_domain_error(error: Exception) -> HTTPException:
    if isinstance(error, RepositoryConflict):
        return HTTPException(409, str(error))
    if isinstance(error, ValueError):
        return HTTPException(422, str(error))
    raise error


def create_carteira_router(
    db: Database,
    snapshot_provider: Callable[[], Snapshot | None],
) -> APIRouter:
    router = APIRouter(prefix="/api/carteira")
    auth = AuthService(db)
    repo = CarteiraRepository(db)

    def require_personal_user(request: Request) -> UserPrincipal:
        token = request.cookies.get("carteira_session")
        if not token:
            raise HTTPException(401, "não autorizado")
        principal = auth.resolve_session(token)
        if principal is None:
            raise HTTPException(401, "não autorizado")
        return principal

    def require_csrf(request: Request) -> UserPrincipal:
        principal = require_personal_user(request)
        header_token = request.headers.get("x-csrf-token")
        cookie_token = request.cookies.get("carteira_csrf")
        if header_token is None or cookie_token is None:
            raise HTTPException(403, "csrf inválido")
        if not _tokens_match(header_token, cookie_token):
            raise HTTPException(403, "csrf inválido")
        session_token = request.cookies.get("carteira_session") or ""
        if not auth.verify_csrf(session_token, header_token):
            raise HTTPException(403, "csrf inválido")
        return principal

    def _today():
        return datetime.now(TZ).date()

    def _market():
        return build_market_view(snapshot_provider())

    def _operation_out(operation) -> OperationPerformanceOut:
        return OperationPerformanceOut.from_domain(
            compute_operation(operation, _market(), _today())
        )

    @router.post("/auth/register", status_code=201, response_model=AuthSessionOut)
    def register(body: RegisterBody, request: Request, response: Response):
        try:
            bundle = auth.register(body.username, body.password)
        except AuthError as error:
            raise _map_auth_error(error, login=False) from error
        _set_session_cookies(request, response, bundle)
        return AuthSessionOut(
            username=bundle.user.username,
            csrf_token=bundle.csrf_token,
        )

    @router.post("/auth/login", response_model=AuthSessionOut)
    def login(body: LoginBody, request: Request, response: Response):
        try:
            bundle = auth.login(body.username, body.password)
        except AuthError as error:
            raise _map_auth_error(error, login=True) from error
        _set_session_cookies(request, response, bundle)
        return AuthSessionOut(
            username=bundle.user.username,
            csrf_token=bundle.csrf_token,
        )

    @router.post("/auth/logout")
    def logout(
        request: Request,
        response: Response,
        _principal: UserPrincipal = Depends(require_csrf),
    ):
        token = request.cookies.get("carteira_session")
        if token:
            auth.logout(token)
        _clear_session_cookies(request, response)
        return {"authenticated": False}

    @router.get("/me", response_model=MeOut)
    def me(request: Request):
        token = request.cookies.get("carteira_session")
        if not token:
            return MeOut(authenticated=False, username=None)
        principal = auth.resolve_session(token)
        if principal is None:
            return MeOut(authenticated=False, username=None)
        return MeOut(authenticated=True, username=principal.username)

    @router.get("/account", response_model=AccountOut)
    def get_account(principal: UserPrincipal = Depends(require_personal_user)):
        return AccountOut(cash_cents=repo.get_cash(principal.user_id))

    @router.put("/account", response_model=AccountOut)
    def put_account(
        body: AccountBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        cash = repo.set_cash(principal.user_id, body.cash_cents)
        return AccountOut(cash_cents=cash)

    @router.get("/summary", response_model=PersonalSummaryOut)
    def summary(
        year: int | None = Query(default=None, ge=2000, le=2100),
        principal: UserPrincipal = Depends(require_personal_user),
    ):
        today = _today()
        selected_year = today.year if year is None else year
        inputs = repo.load_inputs(principal.user_id)
        return PersonalSummaryOut.from_domain(
            compute_personal_summary(inputs, _market(), today, selected_year)
        )

    @router.get("/portfolio", response_model=list[PortfolioEntryOut])
    def list_portfolio(principal: UserPrincipal = Depends(require_personal_user)):
        return [
            PortfolioEntryOut.from_domain(item)
            for item in repo.list_portfolio_entries(principal.user_id)
        ]

    @router.post("/portfolio", status_code=201, response_model=PortfolioEntryOut)
    def create_portfolio(
        body: PortfolioEntryBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            created = repo.create_portfolio_entry(
                principal.user_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        return PortfolioEntryOut.from_domain(created)

    @router.get("/portfolio/{entry_id}", response_model=PortfolioEntryOut)
    def get_portfolio(
        entry_id: int,
        principal: UserPrincipal = Depends(require_personal_user),
    ):
        entry = repo.get_portfolio_entry(principal.user_id, entry_id)
        if entry is None:
            raise HTTPException(404, "lançamento não encontrado")
        return PortfolioEntryOut.from_domain(entry)

    @router.put("/portfolio/{entry_id}", response_model=PortfolioEntryOut)
    def update_portfolio(
        entry_id: int,
        body: PortfolioEntryBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            updated = repo.update_portfolio_entry(
                principal.user_id, entry_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        if updated is None:
            raise HTTPException(404, "lançamento não encontrado")
        return PortfolioEntryOut.from_domain(updated)

    @router.delete("/portfolio/{entry_id}", status_code=204)
    def delete_portfolio(
        entry_id: int,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        if not repo.delete_portfolio_entry(principal.user_id, entry_id):
            raise HTTPException(404, "lançamento não encontrado")
        return Response(status_code=204)

    @router.get("/operations", response_model=list[OperationPerformanceOut])
    def list_operations(principal: UserPrincipal = Depends(require_personal_user)):
        return [
            _operation_out(item)
            for item in repo.list_option_operations(principal.user_id)
        ]

    @router.post(
        "/operations", status_code=201, response_model=OperationPerformanceOut
    )
    def create_operation(
        body: OptionOperationBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            created = repo.create_option_operation(
                principal.user_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        return _operation_out(created)

    @router.get("/operations/{operation_id}", response_model=OperationPerformanceOut)
    def get_operation(
        operation_id: int,
        principal: UserPrincipal = Depends(require_personal_user),
    ):
        operation = repo.get_option_operation(principal.user_id, operation_id)
        if operation is None:
            raise HTTPException(404, "operação não encontrada")
        return _operation_out(operation)

    @router.put("/operations/{operation_id}", response_model=OperationPerformanceOut)
    def update_operation(
        operation_id: int,
        body: OptionOperationBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            updated = repo.update_option_operation(
                principal.user_id, operation_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        if updated is None:
            raise HTTPException(404, "operação não encontrada")
        return _operation_out(updated)

    @router.delete("/operations/{operation_id}", status_code=204)
    def delete_operation(
        operation_id: int,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        if not repo.delete_option_operation(principal.user_id, operation_id):
            raise HTTPException(404, "operação não encontrada")
        return Response(status_code=204)

    @router.get("/custody", response_model=list[CustodyEntryOut])
    def list_custody(principal: UserPrincipal = Depends(require_personal_user)):
        return [
            CustodyEntryOut.from_domain(item)
            for item in repo.list_custody_entries(principal.user_id)
        ]

    @router.post("/custody", status_code=201, response_model=CustodyEntryOut)
    def create_custody(
        body: CustodyEntryBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            created = repo.create_custody_entry(principal.user_id, body.to_domain())
        except ValueError as error:
            raise _map_domain_error(error) from error
        return CustodyEntryOut.from_domain(created)

    @router.get("/custody/{entry_id}", response_model=CustodyEntryOut)
    def get_custody(
        entry_id: int,
        principal: UserPrincipal = Depends(require_personal_user),
    ):
        entry = repo.get_custody_entry(principal.user_id, entry_id)
        if entry is None:
            raise HTTPException(404, "custódia não encontrada")
        return CustodyEntryOut.from_domain(entry)

    @router.put("/custody/{entry_id}", response_model=CustodyEntryOut)
    def update_custody(
        entry_id: int,
        body: CustodyEntryBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            updated = repo.update_custody_entry(
                principal.user_id, entry_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        if updated is None:
            raise HTTPException(404, "custódia não encontrada")
        return CustodyEntryOut.from_domain(updated)

    @router.delete("/custody/{entry_id}", status_code=204)
    def delete_custody(
        entry_id: int,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        if not repo.delete_custody_entry(principal.user_id, entry_id):
            raise HTTPException(404, "custódia não encontrada")
        return Response(status_code=204)

    @router.get("/cash-flows", response_model=list[CashFlowOut])
    def list_cash_flows(principal: UserPrincipal = Depends(require_personal_user)):
        return [
            CashFlowOut.from_domain(item)
            for item in repo.list_cash_flows(principal.user_id)
        ]

    @router.post("/cash-flows", status_code=201, response_model=CashFlowOut)
    def create_cash_flow(
        body: CashFlowBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            created = repo.create_cash_flow(principal.user_id, body.to_domain())
        except ValueError as error:
            raise _map_domain_error(error) from error
        return CashFlowOut.from_domain(created)

    @router.get("/cash-flows/{flow_id}", response_model=CashFlowOut)
    def get_cash_flow(
        flow_id: int,
        principal: UserPrincipal = Depends(require_personal_user),
    ):
        flow = repo.get_cash_flow(principal.user_id, flow_id)
        if flow is None:
            raise HTTPException(404, "fluxo não encontrado")
        return CashFlowOut.from_domain(flow)

    @router.put("/cash-flows/{flow_id}", response_model=CashFlowOut)
    def update_cash_flow(
        flow_id: int,
        body: CashFlowBody,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        try:
            updated = repo.update_cash_flow(
                principal.user_id, flow_id, body.to_domain()
            )
        except ValueError as error:
            raise _map_domain_error(error) from error
        if updated is None:
            raise HTTPException(404, "fluxo não encontrado")
        return CashFlowOut.from_domain(updated)

    @router.delete("/cash-flows/{flow_id}", status_code=204)
    def delete_cash_flow(
        flow_id: int,
        principal: UserPrincipal = Depends(require_csrf),
    ):
        if not repo.delete_cash_flow(principal.user_id, flow_id):
            raise HTTPException(404, "fluxo não encontrado")
        return Response(status_code=204)

    return router
