from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from project_manager_api.db import models as _models  # noqa: E402, F401
