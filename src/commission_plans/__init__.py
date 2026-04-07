from src.commission_plans.sdr import SDRCommissionPlan

PLAN_REGISTRY = {
    "sdr": SDRCommissionPlan,
    # Future roles:
    # "ae": AECommissionPlan,
    # "am": AMCommissionPlan,
    # "cs": CSCommissionPlan,
    # "se": SECommissionPlan,
    # "manager": ManagerCommissionPlan,
}


def get_plan(role: str):
    return PLAN_REGISTRY.get(role)
