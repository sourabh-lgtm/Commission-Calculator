from src.commission_plans.sdr import SDRCommissionPlan
from src.commission_plans.cs import CSACommissionPlan

PLAN_REGISTRY = {
    "sdr": SDRCommissionPlan,
    "cs":  CSACommissionPlan,
    # Future roles:
    # "ae": AECommissionPlan,
    # "am": AMCommissionPlan,
    # "se": SECommissionPlan,
    # "manager": ManagerCommissionPlan,
}


def get_plan(role: str):
    return PLAN_REGISTRY.get(role)
