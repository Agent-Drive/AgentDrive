from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine
from agentdrive.config import settings
from agentdrive.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
sync_url = settings.database_url.replace("+asyncpg", "")

def run_migrations_online() -> None:
    connectable = create_engine(sync_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
