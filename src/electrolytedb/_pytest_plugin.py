import contextlib
import json
import os
import signal
import shutil
import subprocess
import tempfile
from collections import abc
from numbers import Number
from pathlib import Path
from typing import Callable
from typing import Iterable
from typing import List
from typing import Optional
from typing import Union

import pytest
import pymongo

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
    def __init__(
        self, mongod_exe: str = "mongod", retry: Union[Number, Iterable[Number]] = 1
    ):
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
        else:
            # for CTRL_BREAK_EVENT to work properly, these flags must be specified
            self._proc_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        if isinstance(retry, Number):
            retry = [retry]
        self._retry = retry

    def client(self) -> ElectrolyteDB:
        assert ElectrolyteDB.can_connect()
        return ElectrolyteDB()

    def _log(self, msg):
        print(f"Mongod: {msg}", flush=True)

    def _wait_for_server_online(self, retry_intervals_s: list, **kwargs):

        total_time_waited_s = 0.0
        for wait_time_s in retry_intervals_s:
            c = client_to_test_connection = pymongo.MongoClient(
                **kwargs, serverSelectionTimeoutMS=(wait_time_s * 1000)
            )
            try:
                info = c.server_info()
            except pymongo.errors.ConnectionFailure:
                self._log(f"Could not connect to server in {wait_time_s} seconds")
                total_time_waited_s += wait_time_s
            else:
                self._log(f"Connected to server within {total_time_waited_s} seconds")
                return info

        n_attempts = len(retry_intervals_s)
        raise pymongo.errors.ConnectionFailure(
            f"Unable to connect to server after {n_attempts=} ({total_time_waited_s} total seconds waited)"
        )

    def _display_logs(self, logs: str = None):
        if not logs:
            self._log("No logs to display")
            return
        for line in logs.splitlines():
            line = line.strip()
            try:
                event_data = json.loads(line)
                to_print = json.dumps(event, indent=4)
            except Exception as e:
                to_print = line
            print(to_print)

    def setup(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        basedir = Path(self._tmpdir.name).resolve()
        data_dir = self._data_dir = basedir / "data"
        data_dir.mkdir(exist_ok=True, parents=True)
        log_path = self._log_path = basedir / "mongod.log"

        self._proc = subprocess.Popen(
            [
                self._mongod_exe,
                "--dbpath",
                self._data_dir,
                "--logpath",
                self._log_path,
            ],
            **self._proc_kwargs,
        )
        try:
            self._wait_for_server_online(retry_intervals_s=self._retry)
        except Exception as err:
            self._log(f"server setup failed: {err=}")
            self.teardown()
            self._log(f"{self._proc.returncode=}")
            self._display_logs(log_path.read_text())

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._mongod_exe} pid={self._proc.pid} returncode={self._proc.returncode})"

    def teardown(self, timeout=5):
        self._proc.send_signal(self._shutdown_signal)
        # out, err will be empty because we're not capturing them
        out, err = self._proc.communicate(timeout=timeout)
        self._display_logs(self._log_path.read_text())
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
            self._server = Mongod(retry=[1, 2, 5, 10, 30])
            self._make_client = self._server.client
        else:
            raise pytest.UsageError(
                f"Invalid EDB mode {mode!r}. Available: {self._modes}"
            )

    def pytest_sessionstart(self):
        self._server.setup()

    def pytest_sessionfinish(self):
        self._server.teardown()

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


edb = Plugin()
