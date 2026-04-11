from src.commission_plans.sdr import SDRCommissionPlan
from src.commission_plans.cs import CSACommissionPlan
from src.commission_plans.cs_lead import CSLeadCommissionPlan
from src.commission_plans.ae import AECommissionPlan
from src.commission_plans.sdr_lead import SDRLeadCommissionPlan
from src.commission_plans.am import AMCommissionPlan
from src.commission_plans.am_lead import AMLeadCommissionPlan
from src.commission_plans.se import SECommissionPlan

PLAN_REGISTRY = {
    "sdr":         SDRCommissionPlan,
    "cs":          CSACommissionPlan,
    "cs_lead":     CSLeadCommissionPlan,
    "cs_director": CSLeadCommissionPlan,  # Same plan; pipeline aggregates all CSAs
    "ae":          AECommissionPlan,
    "sdr_lead":    SDRLeadCommissionPlan,
    "am":          AMCommissionPlan,
    "am_lead":     AMLeadCommissionPlan,
    "se":          SECommissionPlan,
    # Future roles:
    # "manager": ManagerCommissionPlan,
}


def get_plan(role: str):
    return PLAN_REGISTRY.get(role)
