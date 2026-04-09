from src.commission_plans.sdr import SDRCommissionPlan
from src.commission_plans.cs import CSACommissionPlan
from src.commission_plans.ae import AECommissionPlan
from src.commission_plans.sdr_lead import SDRLeadCommissionPlan

PLAN_REGISTRY = {
    "sdr":      SDRCommissionPlan,
    "cs":       CSACommissionPlan,
    "ae":       AECommissionPlan,
    "sdr_lead": SDRLeadCommissionPlan,
    # Future roles:
    # "am": AMCommissionPlan,
    # "se": SECommissionPlan,
    # "manager": ManagerCommissionPlan,
}


def get_plan(role: str):
    return PLAN_REGISTRY.get(role)
