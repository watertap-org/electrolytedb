import os

import pytest

from electrolytedb import ElectrolyteDB
from electrolytedb.commands import _load_bootstrap


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--edb-no-mock",
        help="Force the `edb` fixture to connect to a running MongoDB instance "
        "instead of falling back to mongomock",
        action="store_true",
        default=False,
        dest="edb_no_mock",
    )


class MockDB(ElectrolyteDB):
    def __init__(self, db="foo", **kwargs):
        from mongomock import MongoClient

        self._client = MongoClient()
        self._db = getattr(self._client, db)
        # note: don't call superclass!
        self._database_name = db
        self._server_url = "mock"
        self._mongoclient_connect_status = {"initial": "ok", "type": "mock"}


def _reset(edb: ElectrolyteDB):
    edb._client.drop_database(edb.database)


@pytest.fixture(scope="class")
def edb(pytestconfig: pytest.Config) -> ElectrolyteDB:
    """
    ElectrolyteDB instance with a non-mocked client, with mock client available as a fallback.
    """
    mock_allowed = not pytestconfig.option.edb_no_mock
    if ElectrolyteDB.can_connect():
        _edb = ElectrolyteDB()
    else:
        if not mock_allowed:
            pytest.fail(
                "EDB could not connect to a database instance, but mocking is not allowed"
            )
        _edb = MockDB()

    _load_bootstrap(_edb)
    yield _edb
    _reset(_edb)
    if not _edb.is_empty():
        pytest.fail("EDB instance should be empty, but it isn't")


@pytest.fixture(scope="class")
def mock_edb() -> MockDB:
    "ElectrolyteDB instance that always uses a mocked client."

    _edb = MockDB()
    yield _edb
    _reset(_edb)


@pytest.fixture(scope="module")
def cloud_edb() -> ElectrolyteDB:
    # this env var should be an encrypted secret in the repository
    passwd = os.environ.get("EDB_CLOUD_PASSWORD", "")
    if not passwd:
        pytest.skip("No password found for MongoDB cloud database")
    url_template = (
        "mongodb+srv://nawi:{passwd}@cluster0.utpac.mongodb.net/test?"
        "authSource=admin&replicaSet=atlas-nxwe6d-shard-0&"
        "readPreference=primary&ssl=true"
    )
    print(f"Connecting to MongoDB cloud server at url={url_template}")
    client = ElectrolyteDB(url=url_template.format(passwd=passwd))
