import subprocess
import os


def test_migration_on_clean_db():
    test_db = "./test_migration.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db}"

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    if os.path.exists(test_db):
        os.remove(test_db)
