import contextlib
import os
import signal
import shutil
import subprocess
import tempfile
from collections import abc
from pathlib import Path
from typing import Callable
from typing import List
from typing import Optional

import pytest

from electrolytedb import ElectrolyteDB
from electrolytedb.commands import _load_bootstrap


class MockDB(ElectrolyteDB):
    def __init__(self, db="foo", **kwargs):
        from mongomock import MongoClient

        self._client = MongoClient()
        self._db = getattr(self._client, db)
        # note: don't call superclass!
        self._database_name = db
        self._server_url = "mock"
        self._mongoclient_connect_status = {"initial": "ok", "type": "mock"}


class DBHandler:
    def setup(self):
        pass

    def teardown(self):
        pass


class NoServer(DBHandler):
    def __str__(self) -> str:
        return "<no server>"


class Mongod(DBHandler):
    def __init__(self, mongod_exe: str = "mongod"):
        self._mongod_exe = shutil.which(mongod_exe)
        assert self._mongod_exe is not None
        self._proc = None
        self._tmpdir = None
        self._data_dir = None
        self._proc_kwargs = {}
        self._proc_output = None
        try:
            # this is specific to Windows
            self._shutdown_signal = signal.CTRL_BREAK_EVENT
        except AttributeError:
            self._shutdown_signal = signal.SIGINT
            # on non-Windows, mongod is fast so we don't need to show its stdout
            self._proc_kwargs["stdout"] = subprocess.PIPE
        else:
            # for CTRL_BREAK_EVENT to work properly, these flags must be specified
            self._proc_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    def client(self) -> ElectrolyteDB:
        assert ElectrolyteDB.can_connect()
        return ElectrolyteDB()

    def setup(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmpdir.name).resolve()

        self._proc = subprocess.Popen(
            [
                self._mongod_exe,
                "--dbpath",
                self._data_dir,
            ],
            text=True,
            **self._proc_kwargs,
        )

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._mongod_exe} pid={self._proc.pid} returncode={self._proc.returncode})"

    def teardown(self, timeout=5):
        self._proc.send_signal(self._shutdown_signal)
        # err will be empty because we're not capturing it
        self._proc_output, err = self._proc.communicate(timeout=timeout)
        self._tmpdir.cleanup()


class Plugin:
    def __init__(self):
        self._modes = ("mongod", "mock")
        self._server = None
        self._make_client = None
        self._mode = None

    def pytest_addoption(self, parser: pytest.Parser):
        parser.addoption(
            "--edb",
            help="Choose how to run ElectrolyteDB tests",
            action="store",
            choices=self._modes,
            default="mock",
            dest="edb",
        )

    def pytest_configure(self, config: pytest.Config):
        mode = self._mode = config.option.edb
        if mode == "mock":
            self._server = NoServer()
            self._make_client = MockDB
        elif mode == "mongod":
            self._server = Mongod()
            self._make_client = self._server.client
        else:
            raise pytest.UsageError(
                f"Invalid EDB mode {mode!r}. Available: {self._modes}"
            )

        self._server.setup()

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_header(self) -> List[str]:
        return [
            "edb:",
            f"\tmode={self._mode}",
            f"\tserver={self._server}",
        ]

    def reset(self, instance: ElectrolyteDB):
        instance._client.drop_database(instance.database)

    def ensure_empty(self, instance):
        if not instance.is_empty():
            pytest.fail(f"EDB instance {instance} should be empty, but it isn't")

    @pytest.fixture(scope="class")
    def edb(self) -> ElectrolyteDB:
        instance = self._make_client()

        yield instance
        self.reset(instance)
        self.ensure_empty(instance)

    @pytest.fixture(scope="class")
    def mock_edb(self) -> MockDB:
        instance = MockDB()

        yield instance
        self.reset(instance)
        self.ensure_empty(instance)

    @pytest.fixture(scope="module")
    def cloud_edb(self) -> ElectrolyteDB:
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
        yield client

    def pytest_sessionfinish(self):
        self._server.teardown()


edb = Plugin()
