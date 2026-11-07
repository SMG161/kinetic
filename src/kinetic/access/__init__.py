"""access: the policy decision point. The only place that decides who may see or do what.

Language: Principal, Action, Target, Decision, Policy. It knows the rules, not the data:
facts arrive through ports (TeamFacts, PracticeFacts) that other contexts implement, so
access imports no other context.
"""
