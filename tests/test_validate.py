###############################################################################
# WaterTAP Copyright (c) 2021, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National
# Laboratory, National Renewable Energy Laboratory, and National Energy
# Technology Laboratory (subject to receipt of any required approvals from
# the U.S. Dept. of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#
###############################################################################
"""
Tests for validate module
"""
import pytest
from ..validate import validate
from .data import component_data, reaction_data


@pytest.mark.unit
@pytest.mark.parametrize("comp", component_data)
def test_validate_component(comp):
    validate(comp, obj_type="component")


@pytest.mark.unit
@pytest.mark.parametrize("reaction", reaction_data)
def test_validate_reaction(reaction):
    validate(reaction, obj_type="reaction")
