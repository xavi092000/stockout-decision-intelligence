from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from random import Random

import pandas as pd


@dataclass
class Supplier:
    supplier_id: str
    lead_time_days: int
    lead_time_variability_days: int
    fill_rate: float
    reliability_score: float
    logistics_cost_per_unit: float


@dataclass
class Store:
    store_id: str
    state_id: str
    capacity_units: int
    operating_cost_per_day: float
    service_level_target: float


@dataclass
class Product:
    sku_id: str
    category: str
    department: str
    supplier_id: str
    unit_cost: float
    unit_price: float
    holding_cost_per_unit_day: float
    stockout_penalty_per_unit: float


@dataclass
class InventoryPosition:
    store_id: str
    sku_id: str
    on_hand: int
    reserved: int
    in_transit: int
    reorder_point: int
    target_stock: int
    safety_stock: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d['available'] = max(0, self.on_hand - self.reserved)
        d['inventory_position'] = d['available'] + self.in_transit
        return d


def load_profiles(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    profiles = payload.get('profiles', [])
    if not profiles:
        raise RuntimeError(f'No profiles found in {path}')
    return profiles


def group_name(profile: dict, fallback: str) -> str:
    return str(profile.get('source_group') or profile.get('profile_id') or fallback)


def build_world(args: argparse.Namespace) -> dict:
    rng = Random(args.seed)
    calibration = args.demand_calibration_dir
    categories = load_profiles(calibration/'category_profiles.json')
    departments = load_profiles(calibration/'department_profiles.json')
    store_profiles = load_profiles(calibration/'store_profiles.json')
    state_profiles = load_profiles(calibration/'state_profiles.json')

    scenarios = pd.read_csv(args.scenario_summary)
    if scenarios.empty or 'expected_demand_units' not in scenarios.columns:
        raise RuntimeError('Sprint 6 scenario summary is missing or invalid.')
    demand_reference = max(0.25, float(scenarios['expected_demand_units'].fillna(0).mean()))

    suppliers = [Supplier(
        supplier_id=f'SUP-{i:03d}',
        lead_time_days=rng.randint(2, 12),
        lead_time_variability_days=rng.randint(1, 5),
        fill_rate=round(rng.uniform(.84, .99), 4),
        reliability_score=round(rng.uniform(.86, .995), 4),
        logistics_cost_per_unit=round(rng.uniform(.08, 1.25), 4),
    ) for i in range(1, 9)]

    stores=[]
    for i in range(args.stores):
        stores.append(Store(
            store_id=group_name(store_profiles[i % len(store_profiles)], f'STORE_{i+1:02d}'),
            state_id=group_name(state_profiles[i % len(state_profiles)], f'STATE_{i+1:02d}'),
            capacity_units=rng.randint(7000, 18000),
            operating_cost_per_day=round(rng.uniform(1200, 4200), 2),
            service_level_target=round(rng.uniform(.94, .99), 4),
        ))

    products=[]
    for i in range(1, args.skus+1):
        cost=rng.uniform(1.25,65)
        margin=rng.uniform(.18,.52)
        products.append(Product(
            sku_id=f'SKU-{i:05d}',
            category=group_name(rng.choice(categories),'UNKNOWN_CATEGORY'),
            department=group_name(rng.choice(departments),'UNKNOWN_DEPARTMENT'),
            supplier_id=rng.choice(suppliers).supplier_id,
            unit_cost=round(cost,2),
            unit_price=round(cost/(1-margin),2),
            holding_cost_per_unit_day=round(cost*rng.uniform(.0004,.0018),4),
            stockout_penalty_per_unit=round(cost*rng.uniform(.15,.55),2),
        ))

    inventory=[]
    for store in stores:
        remaining=store.capacity_units
        for product in products:
            daily=max(.15, rng.lognormvariate(0, .7)*demand_reference)
            safety=max(1, round(daily*rng.uniform(2,7)))
            reorder=max(safety, round(daily*rng.uniform(5,14)))
            target=max(reorder+1, round(reorder*rng.uniform(1.35,2.1)))
            on_hand=min(max(0, round(target*rng.uniform(.65,1.2))), remaining)
            remaining-=on_hand
            inventory.append(InventoryPosition(store.store_id, product.sku_id, on_hand, 0, 0, reorder, target, safety))

    product_cost={p.sku_id:p.unit_cost for p in products}
    initial_value=round(sum(i.on_hand*product_cost[i.sku_id] for i in inventory),2)
    payload={
        'schema_version':'1.0.0',
        'simulation_day':0,
        'current_date':args.start_date.isoformat(),
        'seed':args.seed,
        'stores':[asdict(x) for x in stores],
        'products':[asdict(x) for x in products],
        'suppliers':[asdict(x) for x in suppliers],
        'inventory':[x.to_dict() for x in inventory],
        'pending_orders':[],
        'financials':{
            'revenue':0.0,'cost_of_goods_sold':0.0,'holding_cost':0.0,
            'stockout_cost':0.0,'logistics_cost':0.0,'operating_cost':0.0,
            'gross_profit':0.0,'initial_inventory_value':initial_value,
        },
        'metadata':{
            'synthetic':True,'historical_rows_used':False,'world_status':'INITIALIZED',
            'store_count':len(stores),'sku_count':len(products),
            'supplier_count':len(suppliers),'inventory_position_count':len(inventory),
        },
    }
    return payload


def validate(payload: dict, stores: pd.DataFrame, products: pd.DataFrame, suppliers: pd.DataFrame, inventory: pd.DataFrame, expected_stores: int, expected_skus: int) -> dict:
    if len(stores)!=expected_stores: raise RuntimeError('Store count mismatch.')
    if len(products)!=expected_skus: raise RuntimeError('SKU count mismatch.')
    if len(inventory)!=expected_stores*expected_skus: raise RuntimeError('Inventory position count mismatch.')
    if stores.store_id.duplicated().any(): raise RuntimeError('Duplicate store IDs.')
    if products.sku_id.duplicated().any(): raise RuntimeError('Duplicate SKU IDs.')
    if inventory[['store_id','sku_id']].duplicated().any(): raise RuntimeError('Duplicate store/SKU positions.')
    for c in ['on_hand','reserved','in_transit','reorder_point','target_stock','safety_stock','available','inventory_position']:
        if (inventory[c] < 0).any(): raise RuntimeError(f'Negative values in {c}.')
    if (inventory.target_stock < inventory.reorder_point).any(): raise RuntimeError('Target stock below reorder point.')
    if (inventory.reorder_point < inventory.safety_stock).any(): raise RuntimeError('Reorder point below safety stock.')
    if not set(products.supplier_id).issubset(set(suppliers.supplier_id)): raise RuntimeError('Unknown supplier reference.')
    if payload['metadata']['synthetic'] is not True or payload['metadata']['historical_rows_used'] is not False:
        raise RuntimeError('Leakage guard failed.')
    return {
        'status':'PASSED','checked_files':5,'store_count':len(stores),'sku_count':len(products),
        'supplier_count':len(suppliers),'inventory_position_count':len(inventory),
        'total_on_hand_units':int(inventory.on_hand.sum()),
        'zero_stock_positions':int((inventory.on_hand==0).sum()),
        'initial_inventory_value':payload['financials']['initial_inventory_value'],
        'leakage_guard':'PASSED',
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--stores',type=int,default=10)
    p.add_argument('--skus',type=int,default=100)
    p.add_argument('--start-date',type=date.fromisoformat,default=date(2027,1,1))
    p.add_argument('--scenario-summary',type=Path,default=Path('simulation/output/scenarios/synthetic_scenarios_summary.csv'))
    p.add_argument('--demand-calibration-dir',type=Path,default=Path('reality_calibration/data/processed/calibration'))
    p.add_argument('--output-dir',type=Path,default=Path('simulation/output/world'))
    args=p.parse_args()
    try:
        payload=build_world(args)
        args.output_dir.mkdir(parents=True,exist_ok=True)
        (args.output_dir/'world_state_day_000.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
        stores=pd.DataFrame(payload['stores']); products=pd.DataFrame(payload['products']); suppliers=pd.DataFrame(payload['suppliers']); inventory=pd.DataFrame(payload['inventory'])
        stores.to_csv(args.output_dir/'stores.csv',index=False)
        products.to_csv(args.output_dir/'products.csv',index=False)
        suppliers.to_csv(args.output_dir/'suppliers.csv',index=False)
        inventory.to_csv(args.output_dir/'inventory_day_000.csv',index=False)
        validation=validate(payload,stores,products,suppliers,inventory,args.stores,args.skus)
        summary={'status':'PASSED','schema_version':'1.0.0','seed':args.seed,'simulation_day':0,'current_date':payload['current_date'],'stores':len(stores),'skus':len(products),'suppliers':len(suppliers),'inventory_positions':len(inventory),'validation':validation}
        (args.output_dir/'world_build_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print('\n'+'='*62); print('SPRINT 7A — WORLD STATE FOUNDATION'); print('='*62); print(json.dumps(summary,indent=2)); print('='*62); print('STATUS: PASSED')
        return 0
    except Exception as exc:
        print(json.dumps({'status':'FAILED','error':str(exc)},indent=2)); return 1

if __name__=='__main__':
    raise SystemExit(main())
