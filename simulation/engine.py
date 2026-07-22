from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from simulation.action import ActionType, InventoryAction
from simulation.arrival_engine import ArrivalEngine
from simulation.clock import SimulationClock
from simulation.config import SimulationConfig
from simulation.dataset_builder import LeakageSafeDatasetBuilder
from simulation.decision_policy import (
    DecisionResult,
    RuleBasedDecisionPolicy,
)
from simulation.demand_engine import (
    DemandEngine,
    DemandForecast,
    RealizedDemand,
)
from simulation.economics import (
    CumulativeEconomicOutcome,
    DailyEconomicOutcome,
    EconomicConfig,
    EconomicEngine,
)
from simulation.pending_operation import (
    PendingOperation,
    PendingOperationType,
)
from simulation.reward_engine import (
    DecisionRewardEngine,
    validate_reward_total,
)
from simulation.scenario import DayScenario
from simulation.scenario_generator import ScenarioGenerator
from simulation.scenario_profile import (
    ScenarioProfile,
    ScenarioProfileLoader,
)
from simulation.scenario_rules import ScenarioValidator
from simulation.simulator import SimulationWorld
from simulation.state import SimulationState
from simulation.state_transition import (
    DailyTransitionOutcome,
    StateTransitionEngine,
)


@dataclass
class SimulationEngine:
    config: SimulationConfig
    start_date: date = date(2026, 1, 1)
    scenario_profile_path: Path = Path(
        "simulation/configs/scenario_profile.json"
    )
    dataset_output_directory: Path = Path(
        "data/training"
    )
    export_dataset: bool = True
    economic_config: EconomicConfig | None = None

    world: SimulationWorld = field(init=False)
    clock: SimulationClock = field(init=False)
    state: SimulationState | None = field(
        init=False,
        default=None,
    )

    profile: ScenarioProfile = field(init=False)
    scenario_generator: ScenarioGenerator = field(init=False)
    demand_engine: DemandEngine = field(init=False)
    arrival_engine: ArrivalEngine = field(init=False)
    transition_engine: StateTransitionEngine = field(init=False)
    decision_policy: RuleBasedDecisionPolicy = field(init=False)
    economic_engine: EconomicEngine = field(init=False)
    reward_engine: DecisionRewardEngine = field(init=False)
    dataset_builder: LeakageSafeDatasetBuilder = field(init=False)

    completed_days: int = field(init=False, default=0)
    operation_sequence: int = field(init=False, default=0)

    cumulative_demand: int = field(init=False, default=0)
    cumulative_fulfilled_demand: int = field(init=False, default=0)
    cumulative_unmet_demand: int = field(init=False, default=0)
    cumulative_stockouts: int = field(init=False, default=0)
    cumulative_units_received: int = field(init=False, default=0)

    cumulative_economics: CumulativeEconomicOutcome = field(
        init=False,
        default_factory=CumulativeEconomicOutcome,
    )

    cumulative_action_counts: Counter[str] = field(
        init=False,
        default_factory=Counter,
    )

    last_action_counts: Counter[str] = field(
        init=False,
        default_factory=Counter,
    )

    last_scenario: DayScenario | None = field(
        init=False,
        default=None,
    )

    last_outcome: DailyTransitionOutcome | None = field(
        init=False,
        default=None,
    )

    last_economic_outcome: DailyEconomicOutcome | None = field(
        init=False,
        default=None,
    )

    last_decisions: list[DecisionResult] = field(
        init=False,
        default_factory=list,
    )

    last_dataset_path: Path | None = field(
        init=False,
        default=None,
    )

    def __post_init__(self) -> None:
        self.world = SimulationWorld(config=self.config)

        self.clock = SimulationClock(
            start_date=self.start_date,
            total_days=self.config.number_of_days,
        )

        self.profile = ScenarioProfileLoader().load(
            self.scenario_profile_path
        )

        self.scenario_generator = ScenarioGenerator(
            profile=self.profile,
            validator=ScenarioValidator(),
            random_seed=self.config.random_seed,
        )

        self.demand_engine = DemandEngine(
            profile=self.profile,
            random_seed=self.config.random_seed,
        )

        self.arrival_engine = ArrivalEngine()
        self.transition_engine = StateTransitionEngine()
        self.decision_policy = RuleBasedDecisionPolicy()
        self.economic_engine = EconomicEngine(
            config=self.economic_config,
        )
        self.reward_engine = DecisionRewardEngine(
            config=self.economic_engine.config,
        )

        self.dataset_builder = LeakageSafeDatasetBuilder(
            simulation_id=self.config.simulation_name,
            episode_seed=self.config.random_seed,
        )

    def initialize(self) -> None:
        """
        Initialize one persistent simulation episode.

        Inventories and pending operations survive from one day
        to the next.
        """
        self.world.initialize()
        self.clock.reset()

        self.state = SimulationState(
            current_day=self.clock.current_day,
            current_date=self.clock.current_date,
            temperature_c=0.0,
            weather_condition="normal",
            inventories=self.world.inventories,
        )

        self.completed_days = 0
        self.operation_sequence = 0

        self.cumulative_demand = 0
        self.cumulative_fulfilled_demand = 0
        self.cumulative_unmet_demand = 0
        self.cumulative_stockouts = 0
        self.cumulative_units_received = 0

        self.cumulative_economics = CumulativeEconomicOutcome()
        self.cumulative_action_counts = Counter()
        self.last_action_counts = Counter()
        self.last_scenario = None
        self.last_outcome = None
        self.last_economic_outcome = None
        self.last_decisions = []
        self.last_dataset_path = None

        self.dataset_builder = LeakageSafeDatasetBuilder(
            simulation_id=self.config.simulation_name,
            episode_seed=self.config.random_seed,
        )

        self._validate_engine()

    def run_day(self) -> DailyTransitionOutcome:
        """
        Execute one complete simulation day.

        Chronology:
        1. Receive due operations.
        2. Generate today's observable scenario.
        3. Forecast demand.
        4. Capture leakage-safe feature snapshots.
        5. Freeze one decision for each store-SKU.
        6. Create future supplier orders.
        7. Generate realized demand after decisions are frozen.
        8. Apply transfers and realized demand.
        9. Evaluate economics and attach outcome labels.
        10. Preserve the resulting state for tomorrow.
        """
        state = self._require_state()

        arrival_summary = self.arrival_engine.process(state)

        scenario = self.scenario_generator.generate(
            clock=self.clock,
            world=self.world,
        )

        self._apply_scenario_to_state(
            state=state,
            scenario=scenario,
        )

        (
            transition_actions,
            realized_demands,
            decisions,
        ) = self._prepare_daily_decisions(
            state=state,
            scenario=scenario,
        )

        outcome = self.transition_engine.transition(
            current_state=state,
            actions=transition_actions,
            realized_demands=realized_demands,
        )

        economic_outcome = self.economic_engine.evaluate_day(
            decisions=decisions,
            outcome=outcome,
        )
        self.cumulative_economics.add(economic_outcome)

        decision_rewards = self.reward_engine.evaluate_day(
            day=state.current_day,
            decisions=decisions,
            outcome=outcome,
        )

        validate_reward_total(
            rewards=decision_rewards,
            expected_daily_business_value=(
                economic_outcome.business_value
            ),
        )

        self.dataset_builder.finalize_day(
            decisions=decisions,
            outcome=outcome,
            rewards=decision_rewards,
        )

        self.completed_days += 1
        self.cumulative_units_received += (
            arrival_summary.units_received
        )
        self.cumulative_demand += outcome.total_demand
        self.cumulative_fulfilled_demand += (
            outcome.fulfilled_demand
        )
        self.cumulative_unmet_demand += outcome.unmet_demand
        self.cumulative_stockouts += outcome.stockout_count

        self.last_decisions = decisions
        self.last_action_counts = Counter(
            decision.action.action_type.value
            for decision in decisions
        )
        self.cumulative_action_counts.update(
            self.last_action_counts
        )

        self.last_scenario = scenario
        self.last_outcome = outcome
        self.last_economic_outcome = economic_outcome

        return outcome

    @staticmethod
    def _build_pending_indexes(
        state: SimulationState,
    ) -> tuple[
        dict[tuple[str, str], int],
        dict[
            tuple[
                str,
                str,
                PendingOperationType,
            ],
            int,
        ],
    ]:
        pending_inbound_by_key: dict[
            tuple[str, str],
            int,
        ] = {}

        pending_by_type: dict[
            tuple[
                str,
                str,
                PendingOperationType,
            ],
            int,
        ] = {}

        for operation in state.pending_operations:
            if not operation.is_pending:
                continue

            store_sku_key = (
                operation.destination_store_id,
                operation.sku_id,
            )

            pending_inbound_by_key[store_sku_key] = (
                pending_inbound_by_key.get(
                    store_sku_key,
                    0,
                )
                + operation.quantity
            )

            type_key = (
                operation.destination_store_id,
                operation.sku_id,
                operation.operation_type,
            )

            pending_by_type[type_key] = (
                pending_by_type.get(type_key, 0)
                + operation.quantity
            )

        return (
            pending_inbound_by_key,
            pending_by_type,
        )

    def _prepare_daily_decisions(
        self,
        state: SimulationState,
        scenario: DayScenario,
    ) -> tuple[
        list[InventoryAction],
        list[RealizedDemand],
        list[DecisionResult],
    ]:
        """
        Build and freeze all daily decisions before future demand
        is generated.

        Dataset features are captured before action side effects and
        before realized demand exists.
        """
        products_by_id = {
            product.sku_id: product
            for product in self.world.products
        }

        stores_by_id = {
            store.store_id: store
            for store in self.world.stores
        }

        suppliers_by_id = {
            supplier.supplier_id: supplier
            for supplier in self.world.suppliers
        }

        transition_actions: list[InventoryAction] = []
        realized_demands: list[RealizedDemand] = []
        decisions: list[DecisionResult] = []

        (
            pending_inbound_by_key,
            pending_by_type,
        ) = self._build_pending_indexes(state)

        state._pending_inbound_by_key = (
            pending_inbound_by_key
        )
        state._pending_by_type = pending_by_type

        reserved_transfer_out: dict[tuple[str, str], int] = {}
        forecasts: list[DemandForecast] = []

        for inventory in state.inventories:
            product = products_by_id[inventory.sku_id]
            store = stores_by_id[inventory.store_id]

            forecast = self.demand_engine.create_forecast(
                product=product,
                store=store,
                scenario=scenario,
            )

            forecasts.append(forecast)

        for inventory, forecast in zip(
            state.inventories,
            forecasts,
            strict=True,
        ):
            product = products_by_id[inventory.sku_id]
            store = stores_by_id[inventory.store_id]
            supplier = suppliers_by_id[product.supplier_id]

            forecasts_by_key = {
                (item.store_id, item.sku_id): item
                for item in forecasts
            }

            decision = self.decision_policy.decide(
                state=state,
                inventory=inventory,
                product=product,
                store=store,
                supplier=supplier,
                forecast=forecast,
                forecasts_by_key=forecasts_by_key,
            )

            action = self._validate_transfer_reservation(
                state=state,
                action=decision.action,
                reserved_transfer_out=reserved_transfer_out,
            )

            if action != decision.action:
                decision = DecisionResult(
                    action=action,
                    reason=(
                        "The original transfer quantity was reduced "
                        "because some source inventory had already been "
                        "reserved by another decision today."
                    ),
                    forecast_daily_demand=(
                        decision.forecast_daily_demand
                    ),
                    forecast_next_3d=(
                        decision.forecast_next_3d
                    ),
                    projected_stock_gap=(
                        decision.projected_stock_gap
                    ),
                )

            # This snapshot is taken before the action creates an order
            # or changes any stock, and before realized demand exists.
            self.dataset_builder.capture_before_decision(
                state=state,
                inventory=inventory,
                supplier=supplier,
                forecast=forecast,
                projected_stock_gap=(
                    decision.projected_stock_gap
                ),
            )

            decisions.append(decision)

            if action.action_type in {
                ActionType.ORDER_NORMAL,
                ActionType.ORDER_EXPEDITE,
            }:
                self._create_supplier_order(
                    state=state,
                    action=action,
                    supplier_id=supplier.supplier_id,
                    normal_lead_time_days=(
                        supplier.lead_time_days
                    ),
                )
            else:
                transition_actions.append(action)

        for forecast in forecasts:
            realized_demands.append(
                self.demand_engine.realize_demand(
                    forecast=forecast,
                )
            )

        return (
            transition_actions,
            realized_demands,
            decisions,
        )

    def _validate_transfer_reservation(
        self,
        state: SimulationState,
        action: InventoryAction,
        reserved_transfer_out: dict[tuple[str, str], int],
    ) -> InventoryAction:
        if action.action_type != ActionType.TRANSFER_STOCK:
            return action

        if action.source_store_id is None:
            raise ValueError(
                "Transfer action requires a source store."
            )

        source_key = (
            action.source_store_id,
            action.sku_id,
        )

        source_inventory = state.get_inventory(
            store_id=action.source_store_id,
            sku_id=action.sku_id,
        )

        already_reserved = reserved_transfer_out.get(
            source_key,
            0,
        )

        remaining_available = max(
            0,
            source_inventory.available_stock - already_reserved,
        )

        approved_quantity = min(
            action.quantity,
            remaining_available,
        )

        if approved_quantity <= 0:
            return InventoryAction(
                action_type=ActionType.DO_NOTHING,
                destination_store_id=(
                    action.destination_store_id
                ),
                sku_id=action.sku_id,
                quantity=0,
            )

        reserved_transfer_out[source_key] = (
            already_reserved + approved_quantity
        )

        if approved_quantity == action.quantity:
            return action

        return InventoryAction(
            action_type=ActionType.TRANSFER_STOCK,
            source_store_id=action.source_store_id,
            destination_store_id=(
                action.destination_store_id
            ),
            sku_id=action.sku_id,
            quantity=approved_quantity,
        )

    def _create_supplier_order(
        self,
        state: SimulationState,
        action: InventoryAction,
        supplier_id: str,
        normal_lead_time_days: int,
    ) -> None:
        self.operation_sequence += 1

        if action.action_type == ActionType.ORDER_EXPEDITE:
            operation_type = (
                PendingOperationType.EXPEDITE_ORDER
            )
            arrival_day = state.current_day + 1
        else:
            operation_type = (
                PendingOperationType.NORMAL_ORDER
            )
            arrival_day = (
                state.current_day
                + max(1, normal_lead_time_days)
            )

        operation = PendingOperation(
            operation_id=(
                f"OP_{self.operation_sequence:08d}"
            ),
            operation_type=operation_type,
            sku_id=action.sku_id,
            destination_store_id=(
                action.destination_store_id
            ),
            quantity=action.quantity,
            created_day=state.current_day,
            arrival_day=arrival_day,
            supplier_id=supplier_id,
        )

        state.add_pending_operation(operation)

        # Keep the daily O(1) indexes synchronized so later
        # decisions on the same day observe newly created orders.
        pending_inbound_by_key = getattr(
            state,
            "_pending_inbound_by_key",
            None,
        )

        if pending_inbound_by_key is not None:
            store_sku_key = (
                operation.destination_store_id,
                operation.sku_id,
            )
            pending_inbound_by_key[store_sku_key] = (
                pending_inbound_by_key.get(
                    store_sku_key,
                    0,
                )
                + operation.quantity
            )

        pending_by_type = getattr(
            state,
            "_pending_by_type",
            None,
        )

        if pending_by_type is not None:
            type_key = (
                operation.destination_store_id,
                operation.sku_id,
                operation.operation_type,
            )
            pending_by_type[type_key] = (
                pending_by_type.get(type_key, 0)
                + operation.quantity
            )

    def advance_day(self) -> None:
        state = self._require_state()

        self.clock.advance()

        state.current_day = self.clock.current_day
        state.current_date = self.clock.current_date

        state.active_promotions.clear()
        state.active_events.clear()

    def run(self, verbose: bool = True) -> None:
        if self.state is None:
            self.initialize()

        for day_index in range(self.config.number_of_days):
            outcome = self.run_day()

            should_print = (
                self.completed_days == 1
                or self.completed_days % 30 == 0
                or self.completed_days
                == self.config.number_of_days
            )

            if verbose and should_print:
                print(self._monthly_progress(outcome))

            is_last_day = (
                day_index
                == self.config.number_of_days - 1
            )

            if not is_last_day:
                self.advance_day()

        self.dataset_builder.assert_no_unfinalized_snapshots()

        if self.export_dataset:
            self.last_dataset_path = (
                self.dataset_builder.write_csv(
                    self._dataset_output_path()
                )
            )

    def _dataset_output_path(self) -> Path:
        policy_name = (
            self.decision_policy.__class__.__name__
            .replace("DecisionPolicy", "")
            .replace("Policy", "")
            .strip("_")
            .lower()
        )

        if not policy_name:
            policy_name = "policy"

        filename = (
            f"{self.config.simulation_name}"
            f"_seed_{self.config.random_seed}"
            f"_{policy_name}.csv"
        )

        return self.dataset_output_directory / filename

    def _monthly_progress(
        self,
        outcome: DailyTransitionOutcome,
    ) -> str:
        state = self._require_state()
        scenario = self.last_scenario
        economic_outcome = self.last_economic_outcome

        if scenario is None:
            raise RuntimeError(
                "Daily scenario is unavailable."
            )

        if economic_outcome is None:
            raise RuntimeError(
                "Daily economic outcome is unavailable."
            )

        action_text = ", ".join(
            f"{action}={count}"
            for action, count
            in sorted(self.last_action_counts.items())
        )

        return (
            f"Day {self.completed_days:03d}/"
            f"{self.config.number_of_days} "
            f"| Date: {state.current_date.isoformat()} "
            f"| Weather: {scenario.weather_condition} "
            f"| Temp: {scenario.temperature_c:.1f} C "
            f"| Demand: {outcome.total_demand} "
            f"| Unmet: {outcome.unmet_demand} "
            f"| Stockouts: {outcome.stockout_count} "
            f"| Stock: {state.total_stock} "
            f"| Pending: {state.pending_operation_count} "
            f"| Value: ${economic_outcome.business_value:,.0f} "
            f"| Decisions: {action_text}"
        )

    @staticmethod
    def _apply_scenario_to_state(
        state: SimulationState,
        scenario: DayScenario,
    ) -> None:
        state.temperature_c = scenario.temperature_c
        state.weather_condition = (
            scenario.weather_condition
        )
        state.is_holiday = scenario.is_holiday

        state.active_promotions = {
            (promotion.store_id, promotion.sku_id)
            for promotion in scenario.promotions
        }

        state.active_events = [
            asdict(event)
            for event in scenario.events
        ]

    def _require_state(self) -> SimulationState:
        if self.state is None:
            raise RuntimeError(
                "SimulationEngine must be initialized before use."
            )

        return self.state

    def _validate_engine(self) -> None:
        state = self._require_state()

        expected_inventories = (
            self.config.number_of_products
            * self.config.number_of_stores
        )

        if len(self.world.products) != (
            self.config.number_of_products
        ):
            raise RuntimeError(
                "Product count does not match configuration."
            )

        if len(self.world.stores) != (
            self.config.number_of_stores
        ):
            raise RuntimeError(
                "Store count does not match configuration."
            )

        if len(self.world.suppliers) != (
            self.config.number_of_suppliers
        ):
            raise RuntimeError(
                "Supplier count does not match configuration."
            )

        if len(state.inventories) != expected_inventories:
            raise RuntimeError(
                "Inventory count does not match "
                "store-SKU combinations."
            )

    @property
    def cumulative_service_level(self) -> float:
        if self.cumulative_demand == 0:
            return 1.0

        return (
            self.cumulative_fulfilled_demand
            / self.cumulative_demand
        )

    def _action_summary(self) -> str:
        action_types = (
            ActionType.DO_NOTHING,
            ActionType.ORDER_NORMAL,
            ActionType.ORDER_EXPEDITE,
            ActionType.TRANSFER_STOCK,
        )

        return "\n".join(
            f"{action.value:<20}: "
            f"{self.cumulative_action_counts.get(action.value, 0)}"
            for action in action_types
        )

    def summary(self) -> str:
        state = self._require_state()

        dataset_path = (
            str(self.last_dataset_path)
            if self.last_dataset_path is not None
            else "not exported"
        )

        return (
            "SUPPLY CHAIN SIMULATION ENGINE\n"
            "==============================\n"
            f"Simulation          : "
            f"{self.config.simulation_name}\n"
            f"Days Completed      : {self.completed_days}\n"
            f"Current Date        : "
            f"{state.current_date.isoformat()}\n"
            f"Products            : "
            f"{len(self.world.products)}\n"
            f"Stores              : "
            f"{len(self.world.stores)}\n"
            f"Suppliers           : "
            f"{len(self.world.suppliers)}\n"
            f"Inventories         : "
            f"{len(state.inventories)}\n"
            f"Pending Operations  : "
            f"{state.pending_operation_count}\n"
            f"Ending Total Stock  : "
            f"{state.total_stock}\n"
            f"Total Demand        : "
            f"{self.cumulative_demand}\n"
            f"Fulfilled Demand    : "
            f"{self.cumulative_fulfilled_demand}\n"
            f"Unmet Demand        : "
            f"{self.cumulative_unmet_demand}\n"
            f"Stockout Events     : "
            f"{self.cumulative_stockouts}\n"
            f"Units Received      : "
            f"{self.cumulative_units_received}\n"
            f"Service Level       : "
            f"{self.cumulative_service_level:.2%}\n"
            f"Dataset Rows        : "
            f"{self.dataset_builder.row_count:,}\n"
            f"Dataset Path        : "
            f"{dataset_path}\n"
            "\nCUMULATIVE DECISIONS\n"
            "--------------------\n"
            f"{self._action_summary()}\n"
            "\n"
            f"{self.cumulative_economics.summary()}"
        )


def main() -> None:
    engine = SimulationEngine(
        config=SimulationConfig(),
    )

    engine.initialize()
    engine.run(verbose=True)

    print()
    print(engine.summary())
    print()
    print("Simulation completed successfully.")


if __name__ == "__main__":
    main()
