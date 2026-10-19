"""Safe public errors, without database, credential or request payload details."""


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, *, details=None):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(message)


def not_found():
    return DomainError('not_found', 'Запись не найдена.', 404)


def conflict(message='Данные изменились. Обновите экран и повторите действие.', *, details=None):
    return DomainError('version_conflict', message, 409, details=details)
