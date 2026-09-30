from copy import deepcopy
import pickle
import pytest
from simulation.config import SimulationConfig
from simulation.engine import SimulationEngine
from simulation.economic_constrained_policy import EconomicConstrainedPolicy
from simulation.learning.experiments import collect


def engine():
    e = SimulationEngine(SimulationConfig(number_of_days=20,number_of_products=2,number_of_stores=2,random_seed=401),export_dataset=False)
    e.initialize()
    e.decision_policy = EconomicConstrainedPolicy()
    return e


def test_paired_reproducible_and_original_untouched():
    e = engine()
    before = pickle.dumps(e)
    a = collect(e,horizon=5,future_seeds=(1234,5678))
    assert pickle.dumps(e)==before
    assert a==collect(e,horizon=5,future_seeds=(1234,5678))
    for seed in (1234,5678):
        rows = [r for r in a['experiments'] if r['future_seed']==seed]
        assert len({r['demand_path_sha256'] for r in rows})==1
        assert next(r for r in rows if r['action']['action_type']=='DO_NOTHING')['labels']['value_delta_vs_wait']==0
    assert len({r['demand_path_sha256'] for r in a['experiments']})==2
    assert 'future_seed' not in a['observation']
    assert 'network_business_value' not in a['observation']


def test_delayed_consequences_and_action_coverage():
    e = engine()
    e.state.inventories[0].stock_level=0
    a = collect(e,horizon=10,future_seeds=(42,))
    rows=a['experiments']
    assert {'DO_NOTHING','ORDER_NORMAL','ORDER_EXPEDITE','TRANSFER_STOCK'} <= {r['action']['action_type'] for r in rows}
    assert len({r['labels']['network_business_value'] for r in rows})>1
    assert len({r['labels']['unmet_units'] for r in rows})>1
    assert len({r['action']['quantity'] for r in rows if r['action']['action_type']=='ORDER_NORMAL'})>1


@pytest.mark.parametrize('kwargs',[{'horizon':0},{'horizon':21},{'future_seeds':()},{'future_seeds':(1,1)}])
def test_invalid_experiment_rejected(kwargs):
    with pytest.raises(ValueError): collect(engine(),**kwargs)


def test_completed_day_rejected():
    e=engine();e.run_day()
    with pytest.raises(ValueError): collect(e,horizon=2)
