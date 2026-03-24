class RoundCostAwarenessHook:
    """
    Hook for per-round cost awareness in MassGen.
    Injects cumulative cost metadata with tool results.
    Addresses issue #781.
    """
    def __init__(self, budget=None):
        self.cumulative_cost = 0.0
        self.budget = budget

    def update_cost(self, cost):
        self.cumulative_cost += cost
        if self.budget and self.cumulative_cost > self.budget * 0.75:
            print(f"Warning: Nearing budget limit [${self.cumulative_cost:.2f} / ${self.budget:.2f}]")

    def get_status_string(self):
        if self.budget:
            return f"Cost: ${self.cumulative_cost:.2f} / ${self.budget:.2f} budget"
        return f"Cost: ${self.cumulative_cost:.2f}"
