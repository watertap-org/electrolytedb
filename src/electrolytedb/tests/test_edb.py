#################################################################################
# WaterTAP Copyright (c) 2020-2023, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National Laboratory,
# National Renewable Energy Laboratory, and National Energy Technology
# Laboratory (subject to receipt of any required approvals from the U.S. Dept.
# of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#################################################################################
"""
High-level tests for the Electrolyte Database (EDB)
"""
import json

import pytest

from electrolytedb import ElectrolyteDB
from electrolytedb import commands
from electrolytedb import validate


def test_connect(edb):
    assert isinstance(edb, ElectrolyteDB)


def test_load_bootstrap_no_validate(mock_edb):
    commands._load_bootstrap(mock_edb, do_validate=False)


@pytest.mark.unit
def test_load_bootstrap_data():
    for t in "component", "reaction":
        filename = t + ".json"
        path = commands.get_edb_data(filename)
        input_data = json.load(path.open("r", encoding="utf8"))
        for record in input_data:
            if t == "component":
                record = ElectrolyteDB._process_component(record)
            elif t == "reaction":
                record = ElectrolyteDB._process_reaction(record)
            validate.validate(record, obj_type=t)


def test_cloudatlas(cloud_edb):
    assert isinstance(cloud_edb, ElectrolyteDB)
