import yaml
from gmee.datagatherer import DataGathererRegistry

def test_registry_loads_default_config(tmp_path):
    reg = DataGathererRegistry.load("configs/datagatherers.yaml")
    assert len(reg.gatherers) >= 1
